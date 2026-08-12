package com.curie.sofa;

import com.curie.sofa.model.AlertEvent;
import com.curie.sofa.model.CanonicalEvent;
import com.curie.sofa.model.DlqEvent;
import com.curie.sofa.model.RuleBundle;
import com.curie.sofa.operators.SofaAlertFunction;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Properties;
import org.apache.flink.api.common.eventtime.WatermarkStrategy;
import org.apache.flink.api.common.serialization.DeserializationSchema;
import org.apache.flink.api.common.serialization.SerializationSchema;
import org.apache.flink.api.common.typeinfo.TypeInformation;
import org.apache.flink.connector.base.DeliveryGuarantee;
import org.apache.flink.connector.kafka.sink.KafkaRecordSerializationSchema;
import org.apache.flink.connector.kafka.sink.KafkaSink;
import org.apache.flink.connector.kafka.source.KafkaSource;
import org.apache.flink.connector.kafka.source.enumerator.initializer.OffsetsInitializer;
import org.apache.flink.streaming.api.datastream.BroadcastStream;
import org.apache.flink.streaming.api.datastream.DataStream;
import org.apache.flink.streaming.api.datastream.SingleOutputStreamOperator;
import org.apache.flink.streaming.api.environment.StreamExecutionEnvironment;

/**
 * Flink job: clinical envelopes + rule broadcasts → naive SOFA alerts.
 *
 * <p>Args (optional):
 *
 * <ul>
 *   <li>--bootstrap localhost:9092 (host) or kafka:29092 (in-compose)
 *   <li>--rules-file path to JSON rule bundle (seeded once at startup into rules topic expected
 *       separately; also used as fallback defaults file)
 * </ul>
 */
public final class SofaJob {

  private static final ObjectMapper MAPPER = new ObjectMapper();

  private SofaJob() {}

  public static void main(String[] args) throws Exception {
    String bootstrap = arg(args, "--bootstrap", "kafka:29092");
    String groupId = arg(args, "--group", "curie-sofa-v1");

    StreamExecutionEnvironment env = StreamExecutionEnvironment.getExecutionEnvironment();
    env.enableCheckpointing(10_000);

    KafkaSource<CanonicalEvent> clinicalSource =
        KafkaSource.<CanonicalEvent>builder()
            .setBootstrapServers(bootstrap)
            .setTopics("observations", "conditions", "medications")
            .setGroupId(groupId)
            .setStartingOffsets(OffsetsInitializer.earliest())
            .setValueOnlyDeserializer(jsonDeserializer(CanonicalEvent.class))
            .build();

    KafkaSource<RuleBundle> rulesSource =
        KafkaSource.<RuleBundle>builder()
            .setBootstrapServers(bootstrap)
            .setTopics("rules")
            .setGroupId(groupId + "-rules")
            .setStartingOffsets(OffsetsInitializer.earliest())
            .setValueOnlyDeserializer(jsonDeserializer(RuleBundle.class))
            .build();

    // Flink watermarks alone do not reorder; SofaAlertFunction applies EventTimeBuffer
    // (5m lateness) before feature mutation / scoring.
    DataStream<CanonicalEvent> clinical =
        env.fromSource(
                clinicalSource,
                WatermarkStrategy.<CanonicalEvent>forBoundedOutOfOrderness(Duration.ofMinutes(5))
                    .withTimestampAssigner(
                        (e, ts) -> {
                          Long ms =
                              SofaAlertFunction.tryParseTimeMs(e != null ? e.event_time : null);
                          return ms != null ? ms : 0L;
                        }),
                "clinical-events")
            .filter(e -> e != null && e.patient_id != null);

    BroadcastStream<RuleBundle> rulesBroadcast =
        env.fromSource(
                rulesSource,
                WatermarkStrategy.noWatermarks(),
                "rule-bundles")
            .filter(r -> r != null && r.bundle_id != null)
            .broadcast(SofaAlertFunction.RULE_STATE_DESC);

    SingleOutputStreamOperator<AlertEvent> naiveAlerts =
        clinical
            .keyBy(e -> e.patient_id)
            .connect(rulesBroadcast)
            .process(new SofaAlertFunction())
            .name("sofa-score-alert");

    DataStream<DlqEvent> dlq = naiveAlerts.getSideOutput(SofaAlertFunction.DLQ_TAG);

    DataStream<AlertEvent> alerts =
        naiveAlerts
            .keyBy(a -> a.patient_id)
            .connect(rulesBroadcast)
            .process(new com.curie.sofa.operators.GovernanceFilterFunction())
            .name("alert-governance");

    Properties sinkProps = new Properties();
    sinkProps.setProperty("transaction.timeout.ms", "600000");

    KafkaSink<AlertEvent> alertSink =
        KafkaSink.<AlertEvent>builder()
            .setBootstrapServers(bootstrap)
            .setRecordSerializer(
                KafkaRecordSerializationSchema.builder()
                    .setTopic("alerts")
                    .setKeySerializationSchema(
                        (SerializationSchema<AlertEvent>)
                            (AlertEvent a) ->
                                a.patient_id == null
                                    ? null
                                    : a.patient_id.getBytes(StandardCharsets.UTF_8))
                    .setValueSerializationSchema(jsonSerializer(AlertEvent.class))
                    .build())
            .setDeliveryGuarantee(DeliveryGuarantee.AT_LEAST_ONCE)
            .setKafkaProducerConfig(sinkProps)
            .build();

    KafkaSink<DlqEvent> dlqSink =
        KafkaSink.<DlqEvent>builder()
            .setBootstrapServers(bootstrap)
            .setRecordSerializer(
                KafkaRecordSerializationSchema.builder()
                    .setTopic("dlq")
                    .setKeySerializationSchema(
                        (SerializationSchema<DlqEvent>)
                            (DlqEvent d) ->
                                d.patient_id == null
                                    ? null
                                    : d.patient_id.getBytes(StandardCharsets.UTF_8))
                    .setValueSerializationSchema(jsonSerializer(DlqEvent.class))
                    .build())
            .setDeliveryGuarantee(DeliveryGuarantee.AT_LEAST_ONCE)
            .setKafkaProducerConfig(sinkProps)
            .build();

    alerts.sinkTo(alertSink).name("alerts-sink");
    dlq.sinkTo(dlqSink).name("dlq-sink");
    env.execute("curie-sofa-alert-job");
  }

  private static String arg(String[] args, String key, String defaultValue) {
    for (int i = 0; i < args.length - 1; i++) {
      if (key.equals(args[i])) {
        return args[i + 1];
      }
    }
    return defaultValue;
  }

  /** Optional helper for tooling: load a rule bundle JSON from disk. */
  public static RuleBundle loadRulesFile(Path path) throws Exception {
    return MAPPER.readValue(Files.readString(path), RuleBundle.class);
  }

  private static <T> DeserializationSchema<T> jsonDeserializer(Class<T> type) {
    return new DeserializationSchema<>() {
      @Override
      public T deserialize(byte[] message) {
        if (message == null) {
          return null;
        }
        try {
          return MAPPER.readValue(message, type);
        } catch (Exception e) {
          if (type == CanonicalEvent.class) {
            CanonicalEvent bad = new CanonicalEvent();
            bad.patient_id = "__malformed__";
            bad.resource_type = "ParseError";
            bad.parse_error = e.getClass().getSimpleName() + ": " + e.getMessage();
            bad.idempotency_key =
                "parse-" + java.util.UUID.nameUUIDFromBytes(message).toString();
            @SuppressWarnings("unchecked")
            T cast = (T) bad;
            return cast;
          }
          return null;
        }
      }

      @Override
      public boolean isEndOfStream(T nextElement) {
        return false;
      }

      @Override
      public TypeInformation<T> getProducedType() {
        return TypeInformation.of(type);
      }
    };
  }

  private static <T> SerializationSchema<T> jsonSerializer(Class<T> type) {
    return (SerializationSchema<T>)
        (T value) -> {
          try {
            return MAPPER.writeValueAsBytes(value);
          } catch (Exception e) {
            throw new RuntimeException(e);
          }
        };
  }
}
