#!/usr/bin/env bash
# Submit SofaJob (+ AkiJob) to the compose Flink cluster. Idempotent: skips if already running.
set -euo pipefail

JM="${FLINK_JOBMANAGER:-jobmanager:8081}"
JAR="${JAR_PATH:-/jars/curie-sofa.jar}"
BOOT="${KAFKA_BOOTSTRAP:-kafka:29092}"
REST="http://${JM}"

wait_for_jm() {
  local i=0
  until curl -sf "${REST}/overview" >/dev/null 2>&1; do
    i=$((i + 1))
    if [[ $i -gt 60 ]]; then
      echo "Flink JobManager not ready at ${REST}" >&2
      exit 1
    fi
    sleep 2
  done
}

has_running_job() {
  local needle="$1"
  /opt/flink/bin/flink list -r -m "${JM}" 2>/dev/null | grep -F "${needle}" >/dev/null
}

submit() {
  local main="$1"
  local name="$2"
  if has_running_job "$name"; then
    echo "Already RUNNING: ${name} — skip"
    return 0
  fi
  if [[ ! -f "$JAR" ]]; then
    echo "Missing jar: $JAR" >&2
    exit 1
  fi
  echo "Submitting ${name} (${main}) bootstrap=${BOOT}"
  /opt/flink/bin/flink run -d -m "${JM}" -c "${main}" "${JAR}" \
    --bootstrap "${BOOT}"
}

wait_for_jm
echo "JobManager ready."

if [[ ! -f "$JAR" ]]; then
  echo "Missing jar: $JAR (did flink-package finish?)" >&2
  exit 1
fi

submit "com.curie.sofa.SofaJob" "curie-sofa-alert-job"
submit "com.curie.sofa.aki.AkiJob" "curie-aki-alert-job"

echo "Submit complete. Running jobs:"
/opt/flink/bin/flink list -r -m "${JM}" || true
