from __future__ import annotations

from dataclasses import dataclass
import pickle
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class ModelTrainResult:
    model_type: str
    rows: int
    features: list[str]
    target: str
    output_path: str
    train_score: float


def _safe_numeric_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in out.columns:
        if out[c].dtype == object:
            out[c] = pd.to_numeric(out[c], errors="ignore")
    return out


def train_model_from_csv(
    input_path: str,
    output_path: str,
    *,
    target_col: str = "edge_bps",
    model_type: str = "random_forest",
) -> ModelTrainResult:
    df = pd.read_csv(input_path)
    df = _safe_numeric_frame(df)
    if target_col not in df.columns:
        raise ValueError(f"missing_target_column:{target_col}")

    y = pd.to_numeric(df[target_col], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    feature_cols = [c for c in df.columns if c != target_col and pd.api.types.is_numeric_dtype(df[c])]
    if not feature_cols:
        raise ValueError("no_numeric_features")

    X = df[feature_cols].to_numpy(dtype=float)
    model: Any
    score = 0.0
    used_model = str(model_type).strip().lower()

    if used_model in {"random_forest", "rf"}:
        try:
            from sklearn.ensemble import RandomForestRegressor  # type: ignore

            model = RandomForestRegressor(n_estimators=128, random_state=42)
            model.fit(X, y)
            score = float(model.score(X, y))
            used_model = "random_forest"
        except Exception:
            # Deterministic fallback when sklearn is not available.
            coef, *_ = np.linalg.lstsq(X, y, rcond=None)
            model = {"type": "linear_lstsq", "coef": coef.tolist()}
            preds = X @ coef
            var = float(np.var(y)) or 1.0
            score = 1.0 - float(np.var(y - preds) / var)
            used_model = "linear_lstsq_fallback"
    else:
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        model = {"type": "linear_lstsq", "coef": coef.tolist()}
        preds = X @ coef
        var = float(np.var(y)) or 1.0
        score = 1.0 - float(np.var(y - preds) / var)
        used_model = "linear_lstsq"

    payload = {
        "model_type": used_model,
        "features": feature_cols,
        "target": target_col,
        "model": model,
        "train_score": float(score),
    }
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("wb") as fh:
        pickle.dump(payload, fh)

    return ModelTrainResult(
        model_type=used_model,
        rows=int(len(df)),
        features=feature_cols,
        target=target_col,
        output_path=str(out),
        train_score=float(score),
    )
