# Far North Operational Flood Prediction Model Evaluation

- **Model Type**: Calibrated_HistGradientBoosting
- **Artifact Path**: `data_quality/farnorth_consolidation/farnorth_operational_model.joblib`
- **Training Window**: 2005-01-01 to 2021-12-31 (368 rows, 23 verified flood episodes)
- **Holdout Test Window**: 2022-01-01 to 2025-12-31 (256 rows, 16 verified flood episodes)
- **Decision Threshold (Train-Optimized)**: 0.16

## Performance Metrics (Chronological Test Set)
| Metric | Value | Baseline / Interpretation |
|---|---|---|
| **PR-AUC** | **0.1751** | Baseline (no-flood rate): 0.0625 |
| **ROC-AUC** | **0.6784** | 0.50 = random guessing |
| **Brier Score** | **0.0562** | Lower is better (0.0 = perfect calibration) |
| **ECE (Calibration Error)** | **0.011** | Lower is better |
| **F1 Score** | **0.1765** | Precision: 0.1667, Recall: 0.1875 |

## Features Used (19)
`rainfall_1d, rainfall_3d, rainfall_7d, rainfall_14d, rainfall_anomaly, swvl1, discharge_m3s, discharge_lag1, discharge_lag3, discharge_lag7, elevation_m, slope_deg, basin_id, season, basin_rainfall_3d, basin_rainfall_7d, basin_rainfall_14d, basin_rainfall_21d, basin_rainfall_30d`
