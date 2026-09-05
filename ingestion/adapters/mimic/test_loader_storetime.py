"""Infrastructure tests: MIMIC storetime must survive to demo-schema events.

Phase C requirement: ``storetime`` (availability time) is carried through the
loader and demo-schema conversion instead of being replaced by ``charttime``.
"""

from __future__ import annotations

import csv
import gzip
from pathlib import Path

from ingestion.adapters.mimic.loader import (
    index_chartevents,
    index_inputevents_pressors,
    index_labevents,
    index_outputevents_urine,
)
from ingestion.adapters.mimic.to_demo_schema import convert_mimic_demo


def _write_gz(path: Path, header: list[str], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)


def _make_root(tmp: Path) -> Path:
    root = tmp / "mimic"
    _write_gz(
        root / "icu" / "icustays.csv.gz",
        ["subject_id", "hadm_id", "stay_id", "intime", "outtime"],
        [["1", "10", "100", "2150-01-01 00:00:00", "2150-01-02 00:00:00"]],
    )
    _write_gz(
        root / "hosp" / "labevents.csv.gz",
        ["subject_id", "hadm_id", "itemid", "charttime", "storetime", "valuenum"],
        [["1", "10", "50912", "2150-01-01 01:00:00", "2150-01-01 02:00:00", "1.2"]],
    )
    _write_gz(
        root / "icu" / "chartevents.csv.gz",
        ["stay_id", "charttime", "storetime", "itemid", "valuenum"],
        [["100", "2150-01-01 01:00:00", "2150-01-01 01:30:00", "220052", "75"]],
    )
    _write_gz(
        root / "icu" / "inputevents.csv.gz",
        [
            "stay_id", "starttime", "endtime", "storetime", "itemid", "rate",
            "rateuom", "ordercategoryname", "statusdescription",
        ],
        [
            [
                "100", "2150-01-01 03:00:00", "2150-01-01 04:00:00",
                "2150-01-01 03:10:00", "221906", "0.1", "mcg/kg/min", "", "",
            ]
        ],
    )
    _write_gz(
        root / "icu" / "outputevents.csv.gz",
        ["stay_id", "charttime", "storetime", "itemid", "value"],
        [["100", "2150-01-01 10:00:00", "2150-01-01 10:05:00", "226559", "300"]],
    )
    return root


def test_loader_carries_storetime(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    charts = index_chartevents(root, stay_ids={"100"}, itemids={220052})
    assert charts["100"][0]["storetime"] == "2150-01-01 01:30:00"
    labs = index_labevents(root, subject_ids={"1"}, itemids={50912})
    assert labs["1"][0]["storetime"] == "2150-01-01 02:00:00"
    pressors = index_inputevents_pressors(root, stay_ids={"100"}, itemids={221906})
    assert pressors["100"][0]["storetime"] == "2150-01-01 03:10:00"
    urine = index_outputevents_urine(root, stay_ids={"100"}, itemids={226559})
    assert urine["100"][0]["storetime"] == "2150-01-01 10:05:00"


def test_demo_schema_preserves_storetime(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    stays = [
        {
            "stay_id": "100",
            "subject_id": "1",
            "hadm_id": "10",
            "intime": "2150-01-01 00:00:00",
            "outtime": "2150-01-02 00:00:00",
        }
    ]
    converted = convert_mimic_demo(root, stays=stays)
    stay = converted["stays"][0]
    labs = {str(e["itemid"]): e for e in stay["labs"]}
    charts = {str(e["itemid"]): e for e in stay["charts"]}
    assert labs["50912"]["storetime"] == "2150-01-01 02:00:00"
    assert charts["220052"]["storetime"] == "2150-01-01 01:30:00"
    assert charts["226559"]["storetime"] == "2150-01-01 10:05:00"
    assert charts["221906"]["storetime"] == "2150-01-01 03:10:00"


def test_demo_schema_falls_back_to_charttime_when_storetime_missing(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    (root / "icu" / "chartevents.csv.gz").unlink()
    _write_gz(
        root / "icu" / "chartevents.csv.gz",
        ["stay_id", "charttime", "itemid", "valuenum"],
        [["100", "2150-01-01 01:00:00", "220052", "75"]],
    )
    stays = [
        {
            "stay_id": "100",
            "subject_id": "1",
            "hadm_id": "10",
            "intime": "2150-01-01 00:00:00",
            "outtime": "2150-01-02 00:00:00",
        }
    ]
    converted = convert_mimic_demo(root, stays=stays)
    charts = {str(e["itemid"]): e for e in converted["stays"][0]["charts"]}
    map_event = charts["220052"]
    assert map_event["storetime"] == map_event["charttime"] == "2150-01-01 01:00:00"
