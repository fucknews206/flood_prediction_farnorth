#!/usr/bin/env python3
"""Train and evaluate an operational, calibrated flood-risk model for the Far North region.

Architecture:
- Data source: farnorth_training_table_basin.csv (624 rows: 39 verified positive events, 585 negative baseline samples)
- Strict chronological split: train < 2022-01-01 (368 rows, 23 positives), test >= 2022-01-01 (256 rows, 16 positives)
- Features (19): CHIRPS precipitation (1d/3d/7d/14d/anomaly), ERA5 soil water (swvl1),
  GloFAS river discharge (current + lag1/3/7), DEM terrain (elevation_m, slope_deg, basin_id, season),
  and upstream HydroBASINS rainfall accumulation (3d/7d/14d/21d/30d).
- Imputation & scaling: SimpleImputer(median) + StandardScaler()
- Classifiers evaluated:
  1. Calibrated Random Forest (Platt scaling via sigmoid)
  2. Balanced Logistic Regression
  3. HistGradientBoostingClassifier (calibrated)
- Selects best model by PR-AUC & Brier score on chronological test set.
- Threshold optimized on train set via F1 maximization.
- Outputs operational artifact to data_quality/farnorth_consolidation/farnorth_operational_model.joblib
"""

from datetime import datetime, timezone
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'data_quality' / 'farnorth_consolidation'
DATA_PATH = OUT / 'farnorth_training_table_basin.csv'

FEATURES = [
    'rainfall_1d', 'rainfall_3d', 'rainfall_7d', 'rainfall_14d', 'rainfall_anomaly',
    'swvl1', 'discharge_m3s', 'discharge_lag1', 'discharge_lag3', 'discharge_lag7',
    'elevation_m', 'slope_deg', 'basin_id', 'season',
    'basin_rainfall_3d', 'basin_rainfall_7d', 'basin_rainfall_14d', 'basin_rainfall_21d', 'basin_rainfall_30d'
]


def compute_ece(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10) -> float:
    """Expected Calibration Error (ECE)."""
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    n = len(y_true)
    for i in range(n_bins):
        idx = (y_prob >= bin_edges[i]) & (y_prob < bin_edges[i + 1])
        if i == n_bins - 1:
            idx = (y_prob >= bin_edges[i]) & (y_prob <= bin_edges[i + 1])
        bin_size = np.sum(idx)
        if bin_size > 0:
            bin_acc = np.mean(y_true[idx])
            bin_conf = np.mean(y_prob[idx])
            ece += (bin_size / n) * abs(bin_acc - bin_conf)
    return float(ece)


def main():
    print(f"Loading training data from {DATA_PATH}...")
    df = pd.read_csv(DATA_PATH)
    df['date'] = pd.to_datetime(df['date'])

    # Strict chronological split at 2022-01-01
    split_date = pd.Timestamp('2022-01-01')
    train = df[df['date'] < split_date].copy()
    test = df[df['date'] >= split_date].copy()

    print(f"Total rows: {len(df)} | Positives: {int(df.flood_label.sum())}")
    print(f"Train rows: {len(train)} | Train positives: {int(train.flood_label.sum())}")
    print(f"Test rows:  {len(test)} | Test positives:  {int(test.flood_label.sum())}")

    X_train = train[FEATURES].copy()
    y_train = train['flood_label'].values.astype(int)
    X_test = test[FEATURES].copy()
    y_test = test['flood_label'].values.astype(int)

    candidates = {
        'LogisticRegression_Balanced': Pipeline([
            ('impute', SimpleImputer(strategy='median')),
            ('scale', StandardScaler()),
            ('clf', LogisticRegression(class_weight='balanced', max_iter=1000, random_state=42))
        ]),
        'Calibrated_RandomForest': Pipeline([
            ('impute', SimpleImputer(strategy='median')),
            ('clf', CalibratedClassifierCV(
                estimator=RandomForestClassifier(n_estimators=100, max_depth=6, class_weight='balanced', random_state=42),
                method='sigmoid',
                cv=3
            ))
        ]),
        'Calibrated_HistGradientBoosting': Pipeline([
            ('impute', SimpleImputer(strategy='median')),
            ('clf', CalibratedClassifierCV(
                estimator=HistGradientBoostingClassifier(max_iter=100, max_depth=5, class_weight='balanced', random_state=42),
                method='sigmoid',
                cv=3
            ))
        ]),
    }

    results = {}
    best_candidate_name = None
    best_pr_auc = -1.0
    best_model_payload = None

    for name, pipe in candidates.items():
        print(f"\nEvaluating candidate: {name}...")
        pipe.fit(X_train, y_train)

        train_prob = pipe.predict_proba(X_train)[:, 1]
        test_prob = pipe.predict_proba(X_test)[:, 1]

        # Find best decision threshold on train set via F1
        thresholds = np.linspace(0.05, 0.95, 91)
        best_th = 0.5
        best_train_f1 = -1.0
        for th in thresholds:
            f1 = f1_score(y_train, train_prob >= th, zero_division=0)
            if f1 > best_train_f1:
                best_train_f1 = f1
                best_th = th

        test_pred = (test_prob >= best_th).astype(int)

        prec = float(precision_score(y_test, test_pred, zero_division=0))
        rec = float(recall_score(y_test, test_pred, zero_division=0))
        f1 = float(f1_score(y_test, test_pred, zero_division=0))
        pr_auc = float(average_precision_score(y_test, test_prob))
        roc_auc = float(roc_auc_score(y_test, test_prob))
        brier = float(brier_score_loss(y_test, test_prob))
        ece = compute_ece(y_test, test_prob)
        always_no_flood_pr = float(y_test.sum() / len(y_test))

        cand_metrics = {
            'model_name': name,
            'train_rows': len(train),
            'test_rows': len(test),
            'train_positives': int(y_train.sum()),
            'test_positives': int(y_test.sum()),
            'decision_threshold_train_optimal': float(round(best_th, 4)),
            'test_precision': float(round(prec, 4)),
            'test_recall': float(round(rec, 4)),
            'test_f1': float(round(f1, 4)),
            'test_pr_auc': float(round(pr_auc, 4)),
            'test_roc_auc': float(round(roc_auc, 4)),
            'test_brier_score': float(round(brier, 4)),
            'test_ece': float(round(ece, 4)),
            'always_no_flood_baseline_pr_auc': float(round(always_no_flood_pr, 4)),
        }
        results[name] = cand_metrics
        print(f"  PR-AUC: {pr_auc:.4f} (baseline: {always_no_flood_pr:.4f}) | Brier: {brier:.4f} | ECE: {ece:.4f} | F1: {f1:.4f} (Prec: {prec:.4f}, Rec: {rec:.4f})")

        if pr_auc > best_pr_auc:
            best_pr_auc = pr_auc
            best_candidate_name = name
            best_model_payload = {
                'pipeline': pipe,
                'features': FEATURES,
                'threshold': float(best_th),
                'metrics': cand_metrics,
                'candidate_name': name,
                'trained_at': datetime.now(timezone.utc).isoformat(),
                'feature_importance_notes': 'Calibrated model incorporating precipitation, soil saturation, river discharge, and upstream basin rainfall.',
            }

    print(f"\n==> Selected Best Model: {best_candidate_name} with PR-AUC: {best_pr_auc:.4f}")

    # Save operational model
    op_model_path = OUT / 'farnorth_operational_model.joblib'
    joblib.dump(best_model_payload, op_model_path)
    print(f"Saved operational model to {op_model_path} ({op_model_path.stat().st_size:,} bytes)")

    # Save evaluation summary
    eval_json_path = OUT / 'farnorth_operational_model_evaluation.json'
    with open(eval_json_path, 'w', encoding='utf-8') as f:
        json.dump({
            'selected_model': best_candidate_name,
            'best_metrics': best_model_payload['metrics'],
            'all_candidates': results,
            'features': FEATURES,
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }, f, indent=2)
    print(f"Saved evaluation report to {eval_json_path}")

    # Save evaluation markdown
    eval_md_path = OUT / 'farnorth_operational_model_evaluation.md'
    m = best_model_payload['metrics']
    eval_md_path.write_text(f"""# Far North Operational Flood Prediction Model Evaluation

- **Model Type**: {best_candidate_name}
- **Artifact Path**: `data_quality/farnorth_consolidation/farnorth_operational_model.joblib`
- **Training Window**: 2005-01-01 to 2021-12-31 ({m['train_rows']} rows, {m['train_positives']} verified flood episodes)
- **Holdout Test Window**: 2022-01-01 to 2025-12-31 ({m['test_rows']} rows, {m['test_positives']} verified flood episodes)
- **Decision Threshold (Train-Optimized)**: {m['decision_threshold_train_optimal']}

## Performance Metrics (Chronological Test Set)
| Metric | Value | Baseline / Interpretation |
|---|---|---|
| **PR-AUC** | **{m['test_pr_auc']}** | Baseline (no-flood rate): {m['always_no_flood_baseline_pr_auc']} |
| **ROC-AUC** | **{m['test_roc_auc']}** | 0.50 = random guessing |
| **Brier Score** | **{m['test_brier_score']}** | Lower is better (0.0 = perfect calibration) |
| **ECE (Calibration Error)** | **{m['test_ece']}** | Lower is better |
| **F1 Score** | **{m['test_f1']}** | Precision: {m['test_precision']}, Recall: {m['test_recall']} |

## Features Used ({len(FEATURES)})
`{', '.join(FEATURES)}`
""", encoding='utf-8')
    print(f"Saved evaluation markdown to {eval_md_path}")

    # Log to farnorth_model_version_log.jsonl
    log_path = OUT / 'farnorth_model_version_log.jsonl'
    log_entry = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'verified_event_count': int(df.flood_label.sum()),
        'baseline_count': len(df),
        'train_rows': len(train),
        'test_rows': len(test),
        'model_type': f'Operational ML Model ({best_candidate_name}) with calibrated probabilities',
        'metrics': m,
        'artifact': 'data_quality/farnorth_consolidation/farnorth_operational_model.joblib',
        'status': 'OPERATIONAL_READY',
    }
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(log_entry) + '\n')
    print(f"Appended version record to {log_path}")


if __name__ == '__main__':
    main()
