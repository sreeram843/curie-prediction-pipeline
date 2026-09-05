"""Tests for per-value observation freshness + expiry in the reference scorer state.

Mirrors the Java ``PatientSofaStateTest`` / ``CheckpointStyleStateTest``
scenarios: partial updates must not refresh unrelated old fields, out-of-order
events are rejected per clinical value (not per component), and stale values
expire per value class.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from eval.sofa.scoring import SofaComponentInput, SofaComponentName
from eval.sofa.stream_scorer import VALUE_TTL, PatientState


def _t(hours: float) -> datetime:
    return datetime(2024, 1, 1, 0, 0, tzinfo=UTC) + timedelta(hours=hours)


class TestPartialUpdatesDoNotRefreshUnrelatedFields:
    def test_new_platelets_do_not_refresh_old_bilirubin(self) -> None:
        state = PatientState()
        state.apply(
            SofaComponentInput(
                name=SofaComponentName.COAGULATION, platelets_10e9_l=150.0
            ),
            _t(0),
        )
        state.apply(
            SofaComponentInput(name=SofaComponentName.LIVER, bilirubin_mg_dl=2.0),
            _t(0),
        )
        # 30 hours later only platelets update: bilirubin is stale (>24h TTL).
        state.apply(
            SofaComponentInput(
                name=SofaComponentName.COAGULATION, platelets_10e9_l=100.0
            ),
            _t(30),
        )
        inputs = {i.name: i for i in state.inputs(_t(30))}
        assert inputs[SofaComponentName.COAGULATION].platelets_10e9_l == 100.0
        assert inputs[SofaComponentName.LIVER].bilirubin_mg_dl is None

    def test_fresh_value_within_ttl_survives(self) -> None:
        state = PatientState()
        state.apply(
            SofaComponentInput(name=SofaComponentName.LIVER, bilirubin_mg_dl=2.0),
            _t(0),
        )
        state.apply(
            SofaComponentInput(
                name=SofaComponentName.COAGULATION, platelets_10e9_l=150.0
            ),
            _t(23),
        )
        inputs = {i.name: i for i in state.inputs(_t(23))}
        assert inputs[SofaComponentName.LIVER].bilirubin_mg_dl == 2.0

    def test_expired_value_removed_at_boundary(self) -> None:
        state = PatientState()
        state.apply(
            SofaComponentInput(name=SofaComponentName.LIVER, bilirubin_mg_dl=2.0),
            _t(0),
        )
        ttl = VALUE_TTL["bilirubin_mg_dl"]
        assert ttl == timedelta(hours=24)
        kept = {i.name: i for i in state.inputs(_t(24))}  # inclusive boundary
        dropped = {i.name: i for i in state.inputs(_t(24) + timedelta(seconds=1))}
        assert kept[SofaComponentName.LIVER].bilirubin_mg_dl == 2.0
        assert dropped[SofaComponentName.LIVER].bilirubin_mg_dl is None


class TestPerValueEventOrdering:
    def test_older_value_for_one_field_does_not_block_newer_for_another(self) -> None:
        state = PatientState()
        state.apply(
            SofaComponentInput(name=SofaComponentName.RESPIRATION, spo2_percent=96.0),
            _t(2),
        )
        # Out-of-order FiO2 event (t=1) is older than the SpO2 event but is the
        # newest value for the FiO2 field itself → applies per field.
        applied = state.apply(
            SofaComponentInput(name=SofaComponentName.RESPIRATION, fio2_fraction=0.4),
            _t(1),
        )
        assert applied
        inputs = {i.name: i for i in state.inputs(_t(2))}
        resp = inputs[SofaComponentName.RESPIRATION]
        assert resp.spo2_percent == 96.0
        assert resp.fio2_fraction == 0.4

    def test_older_value_for_same_field_is_rejected(self) -> None:
        state = PatientState()
        assert state.apply(
            SofaComponentInput(
                name=SofaComponentName.COAGULATION, platelets_10e9_l=150.0
            ),
            _t(2),
        )
        assert not state.apply(
            SofaComponentInput(
                name=SofaComponentName.COAGULATION, platelets_10e9_l=40.0
            ),
            _t(1),
        )
        inputs = {i.name: i for i in state.inputs(_t(2))}
        assert inputs[SofaComponentName.COAGULATION].platelets_10e9_l == 150.0

    def test_equal_timestamp_later_value_wins(self) -> None:
        state = PatientState()
        state.apply(
            SofaComponentInput(name=SofaComponentName.CNS, gcs=15),
            _t(1),
        )
        state.apply(SofaComponentInput(name=SofaComponentName.CNS, gcs=8), _t(1))
        inputs = {i.name: i for i in state.inputs(_t(1))}
        assert inputs[SofaComponentName.CNS].gcs == 8


class TestExpiryByValueClass:
    def test_map_expires_faster_than_labs(self) -> None:
        state = PatientState()
        state.apply(
            SofaComponentInput(name=SofaComponentName.CARDIOVASCULAR, map_mmhg=65.0),
            _t(0),
        )
        state.apply(
            SofaComponentInput(name=SofaComponentName.RENAL, creatinine_mg_dl=3.0),
            _t(0),
        )
        assert VALUE_TTL["map_mmhg"] == timedelta(hours=1)
        assert VALUE_TTL["creatinine_mg_dl"] == timedelta(hours=24)
        at_2h = {i.name: i for i in state.inputs(_t(2))}
        assert at_2h[SofaComponentName.CARDIOVASCULAR].map_mmhg is None
        assert at_2h[SofaComponentName.RENAL].creatinine_mg_dl == 3.0

    def test_evidence_tracks_the_winning_value_per_field(self) -> None:
        state = PatientState()
        state.apply(
            SofaComponentInput(
                name=SofaComponentName.RENAL,
                creatinine_mg_dl=3.0,
                evidence_ids=["Observation/cr-old"],
            ),
            _t(0),
        )
        state.apply(
            SofaComponentInput(
                name=SofaComponentName.RENAL,
                creatinine_mg_dl=5.0,
                evidence_ids=["Observation/cr-new"],
            ),
            _t(1),
        )
        inputs = {i.name: i for i in state.inputs(_t(1))}
        assert inputs[SofaComponentName.RENAL].evidence_ids == ["Observation/cr-new"]

    def test_expired_value_drops_its_evidence(self) -> None:
        state = PatientState()
        state.apply(
            SofaComponentInput(
                name=SofaComponentName.CARDIOVASCULAR,
                map_mmhg=65.0,
                evidence_ids=["Observation/map"],
            ),
            _t(0),
        )
        inputs = {i.name: i for i in state.inputs(_t(5))}
        assert inputs[SofaComponentName.CARDIOVASCULAR].map_mmhg is None
        assert inputs[SofaComponentName.CARDIOVASCULAR].evidence_ids == []


class TestEncounterReset:
    def test_encounter_change_clears_values(self) -> None:
        state = PatientState()
        state.set_encounter("Encounter/1")
        state.apply(
            SofaComponentInput(name=SofaComponentName.RENAL, creatinine_mg_dl=3.0),
            _t(0),
        )
        state.set_encounter("Encounter/2")
        inputs = {i.name: i for i in state.inputs(_t(1))}
        assert inputs[SofaComponentName.RENAL].creatinine_mg_dl is None
