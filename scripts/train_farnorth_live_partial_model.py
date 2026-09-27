#!/usr/bin/env python3
"""Train the validated no-upstream-window Far North partial risk model.

This profile deliberately excludes only the five upstream-basin accumulation
columns that cannot yet be built from the live request path. It retains local
rainfall windows, soil water, current/lagged GloFAS discharge, terrain and
season. Radar and SAR were never model features and are not considered here.

The split is chronological: training before 2022-01-01 and holdout from that
date forward. The resulting output is a calibrated *risk score* profile; its
provider provenance is retained in the artifact and API response.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    average_precision_score, brier_score_loss, confusion_matrix,
    f1_score, precision_score, recall_score, roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data_quality" / "farnorth_consolidation"
DATA = OUT / "farnorth_training_table_basin.csv"
ARTIFACT = OUT / "farnorth_partial_live_model.joblib"
EVALUATION = OUT / "farnorth_partial_live_model_evaluation.json"
FEATURES = [
    "rainfall_1d", "rainfall_3d", "rainfall_7d", "rainfall_14d", "rainfall_anomaly",
    "swvl1", "discharge_m3s", "discharge_lag1", "discharge_lag3", "discharge_lag7",
    "elevation_m", "slope_deg", "basin_id", "season",
]


def expected_calibration_error(y: np.ndarray, probability: np.ndarray, bins: int = 10) -> float:
    edges = np.linspace(0.0, 1.0, bins + 1)
    total = 0.0
    for start, end in zip(edges[:-1], edges[1:]):
        mask = (probability >= start) & (probability < end if end < 1 else probability <= end)
        if mask.any():
            total += (mask.sum() / len(y)) * abs(float(y[mask].mean()) - float(probability[mask].mean()))
    return float(total)


def main() -> int:
    data = pd.read_csv(DATA)
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data = data.dropna(subset=["date", "flood_label", *FEATURES]).sort_values("date")
    split = pd.Timestamp("2022-01-01")
    train, test = data[data.date < split], data[data.date >= split]
    if train.flood_label.nunique() != 2 or test.flood_label.nunique() != 2:
        raise SystemExit("Chronological split must contain positive and negative samples")

    pipeline = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
        ("classifier", CalibratedClassifierCV(
            estimator=HistGradientBoostingClassifier(max_iter=100, max_depth=4, class_weight="balanced", random_state=42),
            method="sigmoid", cv=3,
        )),
    ])
    pipeline.fit(train[FEATURES], train.flood_label.astype(int))
    train_probability = pipeline.predict_proba(train[FEATURES])[:, 1]
    threshold = max(np.linspace(0.01, 0.95, 95), key=lambda value: f1_score(train.flood_label, train_probability >= value, zero_division=0))
    probability = pipeline.predict_proba(test[FEATURES])[:, 1]
    predicted = probability >= threshold
    metrics = {
        "model_name": "Calibrated_HistGradientBoosting_PartialLive",
        "chronological_holdout": {"training_end": "2021-12-31", "test_start": "2022-01-01"},
        "train_rows": len(train), "test_rows": len(test),
        "train_positives": int(train.flood_label.sum()), "test_positives": int(test.flood_label.sum()),
        "decision_threshold_train_optimal": round(float(threshold), 4),
        "test_pr_auc": round(float(average_precision_score(test.flood_label, probability)), 4),
        "test_roc_auc": round(float(roc_auc_score(test.flood_label, probability)), 4),
        "test_brier_score": round(float(brier_score_loss(test.flood_label, probability)), 4),
        "test_ece": round(expected_calibration_error(test.flood_label.to_numpy(), probability), 4),
        "test_precision": round(float(precision_score(test.flood_label, predicted, zero_division=0)), 4),
        "test_recall": round(float(recall_score(test.flood_label, predicted, zero_division=0)), 4),
        "test_f1": round(float(f1_score(test.flood_label, predicted, zero_division=0)), 4),
        "confusion_matrix": confusion_matrix(test.flood_label, predicted).tolist(),
        "always_no_flood_baseline_pr_auc": round(float(test.flood_label.mean()), 4),
    }
    if not (metrics["test_pr_auc"] > metrics["always_no_flood_baseline_pr_auc"] and metrics["test_brier_score"] <= 0.10 and metrics["test_ece"] <= 0.10):
        raise SystemExit("Partial profile failed deployment criteria: " + json.dumps(metrics, sort_keys=True))
    artifact = {
        "pipeline": pipeline,
        "features": FEATURES,
        "threshold": float(threshold),
        "metrics": metrics,
        "candidate_name": metrics["model_name"],
        "model_profile": "PARTIAL_LIVE_NO_UPSTREAM_V1",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "feature_definitions": {
            "rainfall": "daily local precipitation accumulations in mm (1/3/7/14 days)",
            "swvl1": "top-layer volumetric soil water (m³/m³)",
            "discharge": "daily GloFAS discharge and exact 1/3/7 day lags (m³/s)",
            "terrain": "locality elevation, slope, HydroBASINS basin id, seasonal indicator",
        },
        "not_model_features": ["rainviewer_radar", "sar_inundation", "surface_runoff", "upstream_basin_rainfall"],
        "source_provenance": {
            "training": "CHIRPS precipitation, ERA5 soil water, GloFAS historical discharge, DEM/HydroBASINS",
            "runtime": "Open-Meteo precipitation/soil, Open-Meteo GloFAS Flood API, DEM/HydroBASINS",
            "disclosure": "Provider change is recorded in every result; this profile is a calibrated risk score, not an unconditional flood probability.",
        },
    }
    joblib.dump(artifact, ARTIFACT)
    EVALUATION.write_text(json.dumps({"features": FEATURES, "metrics": metrics, "trained_at": artifact["trained_at"]}, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))
    print(f"Wrote {ARTIFACT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
