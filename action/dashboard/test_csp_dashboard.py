"""CURIE-031: dashboard stays CSP-safe without CDN Mermaid."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DASH = REPO / "action" / "dashboard"
API_MAIN = REPO / "action" / "api" / "app" / "main.py"


def test_no_cdn_mermaid_dependency() -> None:
    index = (DASH / "index.html").read_text(encoding="utf-8")
    app_js = (DASH / "app.js").read_text(encoding="utf-8")
    assert "cdn.jsdelivr.net" not in index
    assert "mermaid" not in index.lower()
    assert "cdn.jsdelivr.net" not in app_js
    assert "renderC4Static" in app_js
    assert "waitForMermaid" not in app_js


def test_csp_script_src_is_self_only() -> None:
    main = API_MAIN.read_text(encoding="utf-8")
    assert "cdn.jsdelivr.net" not in main
    assert "script-src 'self'" in main
