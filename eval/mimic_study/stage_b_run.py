"""Memory-safe full-cohort Stage B (CURIE-041) runner.

Streams protocol stays from the Parquet index, attaches a materialized label
artifact, and runs selection / locked test / ablations without materializing an
8GB canonical-rows JSON. Stay events are loaded one-at-a-time (or per worker);
only compact ablation result rows are retained.

Parallelism uses a fork pool on macOS/Linux so workers inherit the parent’s
read-only stay/label tables (spawn would copy ~GBs per worker and OOM).
"""

from __future__ import annotations

import json
import multiprocessing as mp
import os
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eval.mimic_harness.replay import stable_report_hash
from eval.mimic_study.ablations import ABLATION_KNOBS, SELECTION_CANDIDATES
from eval.mimic_study.bootstrap import bootstrap_percentile_ci
from eval.mimic_study.index_replay import (
    _load_mimic_patients_rows,
    mimic_stay_from_index,
    select_stay_ids,
)
from eval.mimic_study.indexing import load_index_meta, load_stays
from eval.mimic_study.metrics import stay_detection, summarize_cohort
from eval.mimic_study.protocol import (
    assert_command_allowed_on_split,
    assert_split_allowed_for_tuning,
    load_protocol,
    split_for_anchor_year_group,
)
from eval.mimic_study.study import (
    FROZEN_DIR,
    STUDY_VERSION,
    build_manifest,
)
from eval.mimic_study.study_replay import replay_stay_ablation

# Process-pool worker state. With fork, children inherit this from the parent.
_WORKER: dict[str, Any] = {}


def _init_worker(index_dir: str, labels_path: str, protocol_version: str) -> None:
    from eval.mimic_study.labels.materialize import load_label_artifact

    index = Path(index_dir)
    protocol = load_protocol(version=protocol_version)
    artifact = load_label_artifact(Path(labels_path))
    if artifact["protocol_id"] != protocol["protocol_id"]:
        raise RuntimeError(
            f"label protocol {artifact['protocol_id']!r} != {protocol['protocol_id']!r}"
        )
    # Slim stay rows: keep fields needed for replay/split, drop bulky unused keys.
    stay_meta: dict[str, dict[str, Any]] = {}
    for row in load_stays(index):
        sid = str(row["stay_id"])
        stay_meta[sid] = {
            "stay_id": row.get("stay_id"),
            "subject_id": row.get("subject_id"),
            "hadm_id": row.get("hadm_id"),
            "intime": row.get("intime"),
            "outtime": row.get("outtime"),
            "dischtime": row.get("dischtime"),
            "extra_json": row.get("extra_json") if isinstance(row.get("extra_json"), dict) else {},
        }
    patients = {
        str(row["subject_id"]): {
            "subject_id": row.get("subject_id"),
            "anchor_age": row.get("anchor_age"),
            "anchor_year_group": row.get("anchor_year_group"),
        }
        for row in _load_mimic_patients_rows(index)
    }
    _WORKER.clear()
    _WORKER.update(
        {
            "index_dir": index,
            "protocol": protocol,
            "labels": {str(row["stay_id"]): row for row in artifact["stays"]},
            "label_hash": artifact["content_hash"],
            "stay_meta": stay_meta,
            "patients": patients,
        }
    )


def _process_context() -> mp.context.BaseContext:
    """Prefer fork so workers inherit read-only tables instead of reloading them."""
    if hasattr(mp, "get_context"):
        try:
            return mp.get_context("fork")
        except ValueError:
            return mp.get_context()
    return mp


def _build_stay(stay_id: str) -> dict[str, Any]:
    meta = dict(_WORKER["stay_meta"][stay_id])
    patient = _WORKER["patients"].get(str(meta.get("subject_id"))) or {}
    proto = _WORKER["protocol"]
    if (proto.get("splits") or {}).get("scheme") == "anchor_year_group":
        meta["split_id"] = split_for_anchor_year_group(
            patient.get("anchor_year_group") or "", proto
        )
    stay = mimic_stay_from_index(_WORKER["index_dir"], meta)
    stay["split_id"] = meta.get("split_id")
    stay["labels"] = _WORKER["labels"].get(
        stay_id,
        {
            "sepsis3_onset": None,
            "aki_kdigo_stage_ge_1": None,
            "sepsis3_label_observed": False,
        },
    )
    return stay


def _eval_one(payload: tuple[str, dict[str, Any] | None]) -> dict[str, Any]:
    stay_id, knobs = payload
    stay = _build_stay(stay_id)
    return replay_stay_ablation(stay, knobs=knobs)


def split_stay_ids(
    index_dir: Path,
    *,
    protocol: dict[str, Any],
    labels_path: Path,
) -> dict[str, list[str]]:
    """Protocol-cohort stay ids grouped by v2 split (outside_protocol dropped)."""
    from eval.mimic_study.labels.materialize import load_label_artifact

    artifact = load_label_artifact(labels_path)
    if artifact["protocol_id"] != protocol["protocol_id"]:
        raise ValueError(
            f"label protocol {artifact['protocol_id']!r} != {protocol['protocol_id']!r}"
        )
    selected = select_stay_ids(
        index_dir,
        apply_protocol_cohort=True,
        limit=None,
        protocol=protocol,
    )
    stay_meta = {str(row["stay_id"]): row for row in load_stays(index_dir)}
    patients = {
        str(row["subject_id"]): row for row in _load_mimic_patients_rows(index_dir)
    }
    by_split: dict[str, list[str]] = defaultdict(list)
    for sid in selected:
        row = stay_meta[sid]
        patient = patients.get(str(row.get("subject_id"))) or {}
        split = split_for_anchor_year_group(
            patient.get("anchor_year_group") or "", protocol
        )
        if split in {"development", "calibration", "test"}:
            by_split[split].append(sid)
    return {k: sorted(v) for k, v in by_split.items()}


def evaluate_stay_ids(
    *,
    index_dir: Path,
    labels_path: Path,
    protocol_version: str,
    stay_ids: list[str],
    knobs: dict[str, Any] | None,
    workers: int,
    progress_path: Path | None = None,
    phase: str = "",
) -> list[dict[str, Any]]:
    """Replay ``stay_ids`` under ``knobs``; return compact ablation rows."""
    if not stay_ids:
        return []
    n_workers = max(1, workers)
    payloads = [(sid, knobs) for sid in stay_ids]
    rows: list[dict[str, Any]] = []
    started = time.perf_counter()
    done = 0

    # Load tables once in the parent; fork workers inherit them (COW).
    _init_worker(str(index_dir), str(labels_path), protocol_version)

    if n_workers == 1:
        for payload in payloads:
            rows.append(_eval_one(payload))
            done += 1
            if progress_path and (done % 50 == 0 or done == len(payloads)):
                _write_progress(
                    progress_path,
                    phase=phase,
                    done=done,
                    total=len(payloads),
                    started=started,
                )
        return rows

    ctx = _process_context()
    with ProcessPoolExecutor(max_workers=n_workers, mp_context=ctx) as pool:
        # No per-worker initializer: fork children already have _WORKER.
        for row in pool.map(_eval_one, payloads, chunksize=16):
            rows.append(row)
            done += 1
            if progress_path and (done % 50 == 0 or done == len(payloads)):
                _write_progress(
                    progress_path,
                    phase=phase,
                    done=done,
                    total=len(payloads),
                    started=started,
                )
    rows.sort(key=lambda r: str(r.get("stay_id") or ""))
    return rows


def _write_progress(
    path: Path, *, phase: str, done: int, total: int, started: float
) -> None:
    elapsed = time.perf_counter() - started
    rate = done / elapsed if elapsed > 0 else 0.0
    remaining = (total - done) / rate if rate > 0 else None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "phase": phase,
                "done": done,
                "total": total,
                "elapsed_s": round(elapsed, 1),
                "stays_per_s": round(rate, 3),
                "eta_s": None if remaining is None else round(remaining, 1),
                "updated_at": datetime.now(UTC).isoformat(),
            },
            indent=2,
        )
        + "\n"
    )


def _select_operating_point_from_summaries(
    scored: list[dict[str, Any]],
    *,
    protocol: dict[str, Any],
) -> dict[str, Any]:
    eligible = [c for c in scored if c["meets_pe1"]]
    pool = eligible or scored

    def _sort_key(c: dict[str, Any]) -> tuple:
        red = c["interruptive_reduction_ratio"]
        red_key = red if red is not None else 1.0
        nna = c["interruptive_nna"]
        nna_key = nna if nna is not None else 1e9
        sens = c["governed_sensitivity"]
        sens_key = -(sens if sens is not None else -1.0)
        return (red_key, nna_key, sens_key, c["candidate_id"])

    pool.sort(key=_sort_key)
    winner = pool[0]
    return {
        "name": "mimic_stage_b_operating_point",
        "schema_version": "1.0.0",
        "study_version": "0.2.0",
        "protocol_id": protocol["protocol_id"],
        "candidate_id": winner["candidate_id"],
        "selected_at": datetime.now(UTC).isoformat(),
        "source_splits": ["development", "calibration"],
        "forbidden_selection_split": "test",
        "goals": {
            "primary": protocol["primary_endpoint"]["success_rule"],
            "coprimary": protocol["coprimary_endpoint"]["success_rule"],
        },
        "calibration": winner["calibration"],
        "knobs": winner["knobs"],
        "candidates_scored": [
            {
                "candidate_id": c["candidate_id"],
                "meets_pe1": c["meets_pe1"],
                "interruptive_reduction_ratio": c["interruptive_reduction_ratio"],
                "governed_sensitivity": c["governed_sensitivity"],
            }
            for c in scored
        ],
    }


def _parse_alert_times(raw_times: list[Any]) -> list[datetime]:
    out: list[datetime] = []
    for t in raw_times:
        if isinstance(t, datetime):
            out.append(t.replace(tzinfo=None) if t.tzinfo else t)
            continue
        parsed = datetime.fromisoformat(str(t).replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.replace(tzinfo=None)
        out.append(parsed)
    return out


def miss_analysis(
    stay_rows: list[dict[str, Any]],
    *,
    protocol: dict[str, Any],
) -> dict[str, Any]:
    """Stay-level false-negative attribution for the locked detection window."""
    timing = protocol.get("detection_timing") or {}
    before = float(timing.get("before_hours", 12))
    after = float(timing.get("after_hours", 6))
    misses: list[dict[str, Any]] = []
    labeled = 0
    detected = 0
    for row in stay_rows:
        labels = row.get("labels") or {}
        gov = stay_detection(
            labels=labels,
            alert_times=_parse_alert_times(list(row.get("governed_alert_times") or [])),
            before_hours=before,
            after_hours=after,
        )
        naive = stay_detection(
            labels=labels,
            alert_times=_parse_alert_times(list(row.get("naive_alert_times") or [])),
            before_hours=before,
            after_hours=after,
        )
        if not gov["labeled_positive"]:
            continue
        labeled += 1
        if gov["detected"]:
            detected += 1
            continue
        misses.append(
            {
                "stay_id": row.get("stay_id"),
                "onset": labels.get("sepsis3_onset"),
                "naive_detected": bool(naive["detected"]),
                "governed_detected": False,
                "naive_alert_count": row.get("naive_alert_count"),
                "governed_alert_count": row.get("governed_alert_count"),
                "completeness_partial": row.get("completeness_partial"),
            }
        )
    return {
        "labeled_positive": labeled,
        "detected_governed": detected,
        "miss_count": len(misses),
        "miss_rate": (len(misses) / labeled) if labeled else None,
        "misses": misses,
    }


def bootstrap_primary_metrics(
    stay_rows: list[dict[str, Any]],
    *,
    protocol: dict[str, Any],
) -> dict[str, Any]:
    def _sens(rows: list[dict[str, Any]]) -> float:
        summary = summarize_cohort(rows, protocol=protocol)
        value = summary.get("governed_sensitivity")
        if value is None:
            raise ZeroDivisionError("no sensitivity")
        return float(value)

    def _reduction(rows: list[dict[str, Any]]) -> float:
        summary = summarize_cohort(rows, protocol=protocol)
        value = summary.get("interruptive_reduction_ratio")
        if value is None:
            raise ZeroDivisionError("no reduction")
        return float(value)

    def _nna(rows: list[dict[str, Any]]) -> float:
        summary = summarize_cohort(rows, protocol=protocol)
        value = summary.get("interruptive_nna")
        if value is None:
            raise ZeroDivisionError("no nna")
        return float(value)

    return {
        "governed_sensitivity": bootstrap_percentile_ci(_sens, stay_rows),
        "interruptive_reduction_ratio": bootstrap_percentile_ci(_reduction, stay_rows),
        "interruptive_nna": bootstrap_percentile_ci(_nna, stay_rows),
        "unit": "icu_stay",
        "n_replicates": 1000,
        "seed": 42,
    }


def run_full_cohort_stage_b(
    *,
    index_dir: Path,
    labels_path: Path,
    protocol_version: str = "v2",
    workers: int | None = None,
    progress_path: Path | None = None,
    report_out: Path | None = None,
    miss_out: Path | None = None,
    frozen_dir: Path | None = None,
    write_frozen: bool = True,
    limit_per_split: int | None = None,
) -> dict[str, Any]:
    """Execute CURIE-041 selection + locked test over the indexed protocol cohort."""
    protocol = load_protocol(version=protocol_version)
    assert_split_allowed_for_tuning("development", command="sweep", protocol=protocol)
    assert_split_allowed_for_tuning(
        "calibration", command="operating_point_selection", protocol=protocol
    )
    assert_command_allowed_on_split("test", "locked_primary_eval", protocol=protocol)

    meta = load_index_meta(index_dir)
    by_split = split_stay_ids(index_dir, protocol=protocol, labels_path=labels_path)
    if limit_per_split and limit_per_split > 0:
        by_split = {k: v[:limit_per_split] for k, v in by_split.items()}

    n_workers = workers if workers is not None else max(1, (os.cpu_count() or 2) - 2)
    progress = progress_path or (Path("data/stage_b") / "curie041_progress.json")

    # Selection uses calibration only (same winner rule as study.select_operating_point).
    # Development is allowed for sweeps but does not change the selected candidate; skip
    # replaying it here to keep full-cohort wall time tractable.
    scored: list[dict[str, Any]] = []
    for cid, knobs in SELECTION_CANDIDATES.items():
        cal_rows = evaluate_stay_ids(
            index_dir=index_dir,
            labels_path=labels_path,
            protocol_version=protocol_version,
            stay_ids=by_split.get("calibration", []),
            knobs=knobs,
            workers=n_workers,
            progress_path=progress,
            phase=f"select:{cid}:calibration",
        )
        cal = summarize_cohort(cal_rows, protocol=protocol)
        scored.append(
            {
                "candidate_id": cid,
                "knobs": knobs,
                "calibration": cal,
                "meets_pe1": bool(cal.get("meets_pe1")),
                "interruptive_reduction_ratio": cal.get("interruptive_reduction_ratio"),
                "governed_sensitivity": cal.get("governed_sensitivity"),
                "interruptive_nna": cal.get("interruptive_nna"),
            }
        )

    operating_point = _select_operating_point_from_summaries(scored, protocol=protocol)
    knobs = operating_point["knobs"]

    primary_rows = evaluate_stay_ids(
        index_dir=index_dir,
        labels_path=labels_path,
        protocol_version=protocol_version,
        stay_ids=by_split.get("test", []),
        knobs=knobs,
        workers=n_workers,
        progress_path=progress,
        phase="primary:test",
    )
    primary_summary = summarize_cohort(primary_rows, protocol=protocol)
    primary_summary["split_id"] = "test"

    ablations: dict[str, Any] = {}
    for ablation_id, abl_knobs in ABLATION_KNOBS.items():
        use = knobs if ablation_id == "full_governance" else abl_knobs
        rows = evaluate_stay_ids(
            index_dir=index_dir,
            labels_path=labels_path,
            protocol_version=protocol_version,
            stay_ids=by_split.get("test", []),
            knobs=use,
            workers=n_workers,
            progress_path=progress,
            phase=f"ablation:{ablation_id}",
        )
        summary = summarize_cohort(rows, protocol=protocol)
        summary["split_id"] = "test"
        ablations[ablation_id] = summary

    naive_rows = evaluate_stay_ids(
        index_dir=index_dir,
        labels_path=labels_path,
        protocol_version=protocol_version,
        stay_ids=by_split.get("test", []),
        knobs=None,
        workers=n_workers,
        progress_path=progress,
        phase="naive:test",
    )
    naive_summary = summarize_cohort(naive_rows, protocol=protocol)
    naive_summary["split_id"] = "test"

    misses = miss_analysis(primary_rows, protocol=protocol)
    boot = bootstrap_primary_metrics(primary_rows, protocol=protocol)

    from eval.mimic_study.labels.materialize import load_label_artifact

    labels_artifact = load_label_artifact(labels_path)
    fixture_meta = {
        "schema_version": "1.0.0",
        "source": "indexed_stream",
        "dataset": meta.get("dataset"),
        "index_hash": meta.get("index_hash"),
        "labels_content_hash": labels_artifact["content_hash"],
        "split_counts": {k: len(v) for k, v in by_split.items()},
        "workers": n_workers,
    }

    report = {
        "study_version": "0.2.0" if protocol["protocol_id"].endswith(".v2") else STUDY_VERSION,
        "protocol_id": protocol["protocol_id"],
        "operating_point": {
            "candidate_id": operating_point["candidate_id"],
            "knobs": knobs,
            "calibration": operating_point["calibration"],
        },
        "selection_guard": {
            "tuned_on": ["development", "calibration"],
            "test_used_for_selection": False,
        },
        "primary_test": primary_summary,
        "naive_test": naive_summary,
        "ablations_test": ablations,
        "bootstrap_ci": boot,
        "miss_analysis": {
            "labeled_positive": misses["labeled_positive"],
            "detected_governed": misses["detected_governed"],
            "miss_count": misses["miss_count"],
            "miss_rate": misses["miss_rate"],
        },
        "fixture_schema_version": fixture_meta["schema_version"],
        "cohort": fixture_meta["split_counts"],
        "index_hash": meta.get("index_hash"),
        "labels_content_hash": labels_artifact["content_hash"],
    }
    report["content_hash"] = stable_report_hash(
        {k: v for k, v in report.items() if k != "content_hash"}
    )

    manifest = build_manifest(
        operating_point=operating_point,
        primary_test={"summary": primary_summary},
        ablations=ablations,
        fixture_meta=fixture_meta,
        protocol=protocol,
    )
    manifest["bootstrap_ci"] = boot
    manifest["miss_analysis_summary"] = report["miss_analysis"]
    manifest["labels_content_hash"] = labels_artifact["content_hash"]
    manifest["index_hash"] = meta.get("index_hash")
    manifest["content_hash"] = stable_report_hash(
        {k: v for k, v in manifest.items() if k != "content_hash"}
    )

    out_dir = frozen_dir or FROZEN_DIR
    if write_frozen:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "operating_point.v2.json").write_text(
            json.dumps(operating_point, indent=2) + "\n"
        )
        (out_dir / "study_manifest.v2.json").write_text(
            json.dumps(manifest, indent=2) + "\n"
        )

    if report_out is not None:
        report_out.parent.mkdir(parents=True, exist_ok=True)
        report_out.write_text(
            json.dumps(
                {"report": report, "manifest": manifest, "operating_point": operating_point},
                indent=2,
            )
            + "\n"
        )
    if miss_out is not None:
        miss_out.parent.mkdir(parents=True, exist_ok=True)
        miss_out.write_text(json.dumps(misses, indent=2) + "\n")

    return {
        "report": report,
        "manifest": manifest,
        "operating_point": operating_point,
        "miss_analysis": misses,
    }
