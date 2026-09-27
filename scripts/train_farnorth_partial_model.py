#!/usr/bin/env python3
"""Train a deployable Far North partial-data model only from compatible data.

This is intentionally a guardrailed training entry point.  The repository's
existing operational table uses CHIRPS precipitation and does not contain
ERA5-Land runoff, while production currently obtains precipitation from
Open-Meteo.  Training a no-discharge model on that table and serving it with
different runtime semantics would produce an unvalidated model.  Therefore the
script refuses to write an artifact unless an explicitly supplied compatible
training table documents the same feature sources and units as production.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, brier_score_loss, confusion_matrix, precision_score, recall_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data_quality" / "farnorth_consolidation"
FEATURES = ["rainfall_3d", "swvl1", "runoff_mm", "elevation_m", "slope_deg", "basin_id", "season"]
REQUIRED_METADATA = {
    "rainfall_3d": {"provider": "Open-Meteo", "unit": "mm"},
    "swvl1": {"provider": "Open-Meteo", "unit": "m³/m³"},
    "runoff_mm": {"provider": "ERA5-Land", "unit": "mm"},
}


def ece(y_true: np.ndarray, probabilities: np.ndarray, bins: int = 10) -> float:
    edges = np.linspace(0, 1, bins + 1)
    return float(sum(
        (mask.sum() / len(y_true)) * abs(y_true[mask].mean() - probabilities[mask].mean())
        for low, high in zip(edges[:-1], edges[1:])
        for mask in [((probabilities >= low) & (probabilities < high if high < 1 else probabilities <= high))]
        if mask.any()
    ))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True, help="CSV with production-compatible features and flood_label")
    parser.add_argument("--metadata", type=Path, required=True, help="JSON declaring provider/unit for each feature")
    parser.add_argument("--output", type=Path, default=OUT / "farnorth_partial_no_discharge_model.joblib")
    args = parser.parse_args()

    metadata = json.loads(args.metadata.read_text(encoding="utf-8"))
    declared = metadata.get("feature_sources", {})
    incompatible = {
        field: expected for field, expected in REQUIRED_METADATA.items()
        if declared.get(field) != expected
    }
    if incompatible:
        raise SystemExit(
            "Refusing partial-model deployment: source/unit metadata is not production compatible: "
            + json.dumps(incompatible, sort_keys=True)
        )

    data = pd.read_csv(args.data)
    required = {"date", "flood_label", *FEATURES}
    missing = sorted(required - set(data.columns))
    if missing:
        raise SystemExit(f"Refusing partial-model deployment: missing columns {missing}")
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data = data.dropna(subset=["date", "flood_label", *FEATURES]).sort_values("date")
    split = pd.Timestamp("2022-01-01")
    train, test = data[data.date < split], data[data.date >= split]
    if train.flood_label.nunique() < 2 or test.flood_label.nunique() < 2:
        raise SystemExit("Refusing partial-model deployment: chronological train/test split lacks both classes")

    pipeline = Pipeline([
        ("scale", StandardScaler()),
        ("classifier", CalibratedClassifierCV(
            estimator=HistGradientBoostingClassifier(max_iter=100, max_depth=4, class_weight="balanced", random_state=42),
            method="sigmoid", cv=3,
        )),
    ])
    pipeline.fit(train[FEATURES], train.flood_label.astype(int))
    probability = pipeline.predict_proba(test[FEATURES])[:, 1]
    threshold = 0.5
    predicted = probability >= threshold
    metrics = {
        "chronological_holdout": {"train_end": "2021-12-31", "test_start": "2022-01-01"},
        "train_rows": len(train), "test_rows": len(test),
        "train_positives": int(train.flood_label.sum()), "test_positives": int(test.flood_label.sum()),
        "pr_auc": float(average_precision_score(test.flood_label, probability)),
        "precision": float(precision_score(test.flood_label, predicted, zero_division=0)),
        "recall": float(recall_score(test.flood_label, predicted, zero_division=0)),
        "brier_score": float(brier_score_loss(test.flood_label, probability)),
        "ece": ece(test.flood_label.to_numpy(), probability),
        "confusion_matrix": confusion_matrix(test.flood_label, predicted).tolist(),
    }
    baseline = float(test.flood_label.mean())
    # Deployment floor: demonstrate signal beyond the prevalence baseline and
    # basic probability calibration.  A human must still review the artifact.
    if metrics["pr_auc"] <= baseline or metrics["brier_score"] > 0.20 or metrics["ece"] > 0.10:
        raise SystemExit("Partial-model validation did not meet deployment thresholds: " + json.dumps(metrics, sort_keys=True))
    artifact = {
        "pipeline": pipeline, "features": FEATURES, "threshold": threshold,
        "metrics": metrics, "model_profile": "PARTIAL_NO_DISCHARGE_V1",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "feature_sources": declared,
        "runtime_contract": "Open-Meteo rainfall/soil + ERA5-Land historical runoff + terrain/season",
    }
    joblib.dump(artifact, args.output)
    args.output.with_suffix(".evaluation.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(f"Wrote validated partial model: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
