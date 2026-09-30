"""JAMIA Open submission-format checks for the LaTeX package."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "paper" / "main.tex"
SUPPLEMENT = ROOT / "paper" / "jamiaopen" / "supplement.tex"
ALT_TEXT = ROOT / "paper" / "jamiaopen" / "figure-alt-text.md"


def _block(text: str, environment: str) -> str:
    match = re.search(
        rf"\\begin\{{{environment}\}}(.*?)\\end\{{{environment}\}}",
        text,
        flags=re.DOTALL,
    )
    assert match is not None
    return match.group(1)


def _plain_word_count(latex: str) -> int:
    text = re.sub(r"%.*", "", latex)
    text = re.sub(r"\\(?:noindent|textbf|texttt|emph|mathrm)\b", "", text)
    text = re.sub(r"\\[a-zA-Z]+(?:\[[^]]*\])?", " ", text)
    text = re.sub(r"[{}$~]", " ", text)
    return len(re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*", text))


def test_main_manuscript_meets_jamia_open_limits_and_structure() -> None:
    text = MAIN.read_text(encoding="utf-8")
    assert _plain_word_count(_block(text, "abstract")) <= 250
    abstract = _block(text, "abstract")
    for heading in ("Objectives", "Materials and Methods", "Results", "Discussion", "Conclusion"):
        assert rf"\textbf{{{heading}:}}" in abstract
    assert r"\textbf{Background and Significance:}" not in abstract
    lay = re.search(r"\\section\*\{Lay summary\}(.*?)\\section", text, re.DOTALL)
    assert lay is not None and _plain_word_count(lay.group(1)) <= 200
    assert text.count(r"\begin{table}") <= 4
    assert text.count(r"\begin{figure}") <= 3
    assert r"\doublespacing" in text
    assert r"\section{Background and Significance}" in text
    assert r"\textbf{Keywords:}" in text
    assert r"\textbf{Word count:}" in text
    assert "https://github.com/sreeram843/curie-prediction-pipeline" in text
    assert "10.13026/v64v-d857" in text
    assert r"\section*{Author contributions}" in text
    assert r"\section*{Data availability}" in text
    assert "AUTHOR:" not in text
    assert "All emits interruptive" not in text


def test_supplement_and_alt_text_cover_submission_assets() -> None:
    supplement = SUPPLEMENT.read_text(encoding="utf-8")
    alt_text = ALT_TEXT.read_text(encoding="utf-8")
    assert "23-candidate" in supplement
    assert "legacy grace-6" in supplement
    assert "87.6" in supplement and "88.4" in supplement
    for figure in ("Figure 1", "Figure 2", "Figure 3"):
        assert figure in alt_text
