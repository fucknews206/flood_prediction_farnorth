#!/usr/bin/env python3
"""Chronological, locality-restricted baseline model for the Centre catalogue."""
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, f1_score, precision_score, recall_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path('/home/ongou/Desktop/projects/end-of -year-defence')
OUT = ROOT / 'h2oai-flood-intelligence-agent-main' / 'data_quality' / 'centre_consolidation'
FEATURES = [
    'rainfall_1d_m', 'rainfall_3d_m', 'rainfall_7d_m', 'rainfall_14d_m', 'rainfall_anomaly_m',
    'soil_saturation', 'discharge_m3s', 'discharge_lag1_m3s', 'discharge_lag3_m3s', 'discharge_lag7_m3s',
    'month', 'elevation_m', 'slope_deg', 'basin_id',
]


def negatives_for_event(frame: pd.DataFrame, event_date: pd.Timestamp, n: int = 20) -> pd.DataFrame:
    eligible = frame[(frame.data_completeness_flag == 'COMPLETE') & ((frame.date - event_date).abs().dt.days > 14)].copy()
    # Half hard near-misses (the heaviest seven-day rainfall), half broad
    # non-event days. This remains within the event's own locality.
    hard = eligible.nlargest(n // 2, 'rainfall_7d_m')
    remaining = eligible.drop(index=hard.index)
    broad = remaining.sample(n=n - len(hard), random_state=20260901)
    result = pd.concat([hard.assign(sampling_reason='HEAVY_RAIN_NEAR_MISS'), broad.assign(sampling_reason='SAME_LOCALITY_NON_EVENT')])
    return result


def main() -> None:
    all_features = pd.read_parquet(OUT / 'centre_ml_feature_table_unlabelled.parquet')
    all_features['date'] = pd.to_datetime(all_features['date'])
    events = pd.read_csv(OUT / 'canonical_flood_events.csv')
    events = events[events.event_status.eq('VERIFIED_FLOOD_EVENT')].copy()
    events['event_start_date'] = pd.to_datetime(events.event_start_date)
    parts = []
    for event in events.itertuples(index=False):
        local = all_features[all_features.locality_name.eq(event.locality_name)].copy()
        positive = local[local.date.eq(event.event_start_date)].copy()
        if len(positive) != 1 or positive.data_completeness_flag.iloc[0] != 'COMPLETE':
            raise ValueError(f'No complete unique feature row for {event.canonical_event_id}')
        positive['flood_label'] = 1; positive['sampling_reason'] = 'VERIFIED_EVENT'; positive['canonical_event_id'] = event.canonical_event_id
        negative = negatives_for_event(local, event.event_start_date)
        negative['flood_label'] = 0; negative['canonical_event_id'] = event.canonical_event_id
        parts.extend([positive, negative])
    dataset = pd.concat(parts, ignore_index=True).sort_values('date')
    dataset.to_parquet(OUT / 'centre_ml_training_dataset.parquet', index=False)
    dataset.to_csv(OUT / 'centre_ml_training_dataset.csv', index=False)
    # Strict chronological split: last event year (2022) held out.
    split = pd.Timestamp('2022-01-01')
    train, test = dataset[dataset.date < split].copy(), dataset[dataset.date >= split].copy()
    if train.flood_label.sum() < 1 or test.flood_label.sum() < 1:
        raise ValueError('Chronological split does not place a positive in each partition.')
    model = Pipeline([('impute', SimpleImputer(strategy='median')), ('scale', StandardScaler()), ('model', LogisticRegression(class_weight='balanced', max_iter=500, random_state=20260901))])
    model.fit(train[FEATURES], train.flood_label)
    train_prob = model.predict_proba(train[FEATURES])[:, 1]
    # Select a decision threshold from training only.
    thresholds = np.linspace(.05, .95, 91)
    threshold = max(thresholds, key=lambda value: f1_score(train.flood_label, train_prob >= value, zero_division=0))
    test_prob = model.predict_proba(test[FEATURES])[:, 1]
    test_pred = test_prob >= threshold
    metrics = {
        'split': 'train < 2022-01-01; test >= 2022-01-01', 'train_rows': len(train), 'test_rows': len(test),
        'train_positives': int(train.flood_label.sum()), 'test_positives': int(test.flood_label.sum()),
        'decision_threshold_selected_on_train': float(threshold),
        'precision': float(precision_score(test.flood_label, test_pred, zero_division=0)),
        'recall': float(recall_score(test.flood_label, test_pred, zero_division=0)),
        'f1': float(f1_score(test.flood_label, test_pred, zero_division=0)),
        'pr_auc': float(average_precision_score(test.flood_label, test_prob)),
        'always_no_flood_pr_auc': float(average_precision_score(test.flood_label, np.zeros(len(test)))),
        'brier_score': float(brier_score_loss(test.flood_label, test_prob)),
        'warning': (f'Only {len(events)} independent positive episodes exist. Metrics are demonstrative, not deployment-valid; '
                    'collect substantially more verified events before operational use.'),
    }
    pd.DataFrame([metrics]).to_csv(OUT / 'centre_model_evaluation.csv', index=False)
    predictions = test[['locality_id', 'locality_name', 'date', 'flood_label', 'sampling_reason', 'canonical_event_id']].copy()
    predictions['predicted_probability'] = test_prob; predictions['predicted_label'] = test_pred.astype(int)
    predictions.to_csv(OUT / 'centre_model_test_predictions.csv', index=False)
    joblib.dump({'pipeline': model, 'features': FEATURES, 'threshold': threshold, 'metrics': metrics}, OUT / 'centre_logistic_regression_baseline.joblib')
    (OUT / 'centre_model_evaluation.md').write_text(
        '# Centre flood baseline evaluation\n\n'
        f"Chronological split: train before 2022; test from 2022. Rows: {len(train)} train / {len(test)} test; positives: {int(train.flood_label.sum())} / {int(test.flood_label.sum())}.\n\n"
        f"Precision {metrics['precision']:.3f}; Recall {metrics['recall']:.3f}; F1 {metrics['f1']:.3f}; PR-AUC {metrics['pr_auc']:.3f}; always-no-flood PR-AUC {metrics['always_no_flood_pr_auc']:.3f}; Brier score {metrics['brier_score']:.3f}.\n\n"
        f"**Warning:** {metrics['warning']}\n", encoding='utf-8')
    print(metrics)


if __name__ == '__main__':
    main()
