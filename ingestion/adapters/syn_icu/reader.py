"""Read SYN-ICU `.xlsx` tables.

Uses `openpyxl` lazily so the rest of the adapter (and the test suite) works
without the optional `[syn-icu]` extra installed.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any


def _load_openpyxl():
    try:
        import openpyxl  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise ImportError(
            "openpyxl is required to read SYN-ICU xlsx. Install with "
            "`pip install -e '.[syn-icu]'`."
        ) from exc
    return openpyxl


def table_path(root: Path, table: str) -> Path:
    for name in (f"{table}.xlsx", f"{table}.XLSX"):
        candidate = root / name
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"SYN-ICU table not found: {root / (table + '.xlsx')}")


def iter_table(root: Path, table: str) -> Iterator[dict[str, Any]]:
    """Yield each row of a SYN-ICU table as a dict keyed by column name."""
    openpyxl = _load_openpyxl()
    path = table_path(root, table)
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    header: list[str] = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            header = [str(c).strip() if c is not None else "" for c in row]
            continue
        if not any(v is not None and str(v).strip() != "" for v in row):
            continue
        yield {header[j]: row[j] for j in range(len(header))}
    wb.close()


def read_table(root: Path, table: str) -> list[dict[str, Any]]:
    return list(iter_table(root, table))
