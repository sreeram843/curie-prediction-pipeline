"""Semantic version helpers for rule-bundle resolution (CURIE-002)."""

from __future__ import annotations

import re

_CORE_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def parse_semver(version: str) -> tuple[int, int, int]:
    """Parse major.minor.patch; prerelease/build suffixes are ignored for ordering."""
    if not version or not isinstance(version, str):
        raise ValueError(f"Invalid semver: {version!r}")
    core = version.strip().split("+", 1)[0].split("-", 1)[0]
    if not _CORE_RE.match(core):
        raise ValueError(f"Invalid semver: {version!r}")
    major, minor, patch = (int(p) for p in core.split("."))
    return major, minor, patch


def compare_semver(a: str, b: str) -> int:
    """Return -1 if a<b, 0 if equal, 1 if a>b (core major.minor.patch only)."""
    ta, tb = parse_semver(a), parse_semver(b)
    if ta < tb:
        return -1
    if ta > tb:
        return 1
    return 0
