"""Minimal FastAPI stub — alert read/acknowledge lands in Phase 1."""

from fastapi import FastAPI

app = FastAPI(
    title="Curie Prediction Pipeline API",
    version="0.1.0",
    description="Prototype only — synthetic data, not for clinical use.",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/alerts")
def list_alerts() -> list[dict]:
    """Placeholder until the alerts topic + store are wired."""
    return []
