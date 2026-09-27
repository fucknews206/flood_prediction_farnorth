"""Offline safety tests for the Far North environmental-data contract.

These tests intentionally use provider doubles: a production safety check must
be able to prove failure semantics without requiring an internet connection.
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import numpy as np
import pandas as pd

import farnorth_environment as environment_module
import farnorth_risk_engine as risk_engine

from farnorth_environment import (
    EnvironmentalObservation,
    EnvironmentalOrchestrator,
    NO_DATA,
    PROVIDER_ERROR,
    REAL_CURRENT,
    REAL_HISTORICAL,
    REAL_RECENT_BUT_NOT_CURRENT,
    STALE_DATA,
    INVALID_RESPONSE,
    INVALID_VALUE,
    OUTSIDE_COVERAGE,
    RATE_LIMITED,
    TIMEOUT,
    OpenMeteoGloFASProvider,
    OpenMeteoWeatherProvider,
    RainViewerVisualProvider,
    assess_model_eligibility,
)


def observation(variable: str, value, *, status: str = REAL_CURRENT, quality: str = "VALID"):
    return EnvironmentalObservation(
        variable=variable, value=value, unit="unit", provider="test",
        provider_product="test-product", source_type="test", observation_type="test",
        requested_latitude=12.0, requested_longitude=15.0, status=status, quality=quality,
    )


class FailingWeather:
    def get(self, lat, lon):
        return {
            key: observation(key, None, status=PROVIDER_ERROR, quality="UNAVAILABLE")
            for key in ("precipitation_3d", "soil_moisture_0_to_7cm", "runoff")
        }


class GoodWeather:
    def get(self, lat, lon):
        return {
            "precipitation_3d": observation("precipitation_3d", 0.0),
            "soil_moisture_0_to_7cm": observation("soil_moisture_0_to_7cm", 0.32),
            "runoff": observation("runoff", 0.0),
        }


class ZeroDischarge:
    def get(self, lat, lon, **kwargs):
        return observation("river_discharge", 0.0), {"2026-09-27": 0.0}


class BrokenDischarge:
    def get(self, lat, lon, **kwargs):
        return observation("river_discharge", None, status=PROVIDER_ERROR, quality="UNAVAILABLE"), {}


class VisualRadar:
    def get(self, lat, lon):
        return observation("radar_visual_layer", None, status=REAL_RECENT_BUT_NOT_CURRENT, quality="VISUAL_ONLY")


class NoSurfaceWater:
    def get(self, lat, lon):
        return observation("surface_water", None, status=NO_DATA, quality="UNAVAILABLE")


class EnvironmentalContractTests(unittest.TestCase):
    def test_weather_variables_remain_independent_when_runoff_is_missing(self):
        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        times = [(now - timedelta(hours=72 - index)).isoformat() for index in range(73)]
        payload = {
            "latitude": 12.775, "longitude": 14.625, "timezone": "UTC",
            "hourly": {
                "time": times,
                "precipitation": [0.1] * 73,
                "soil_moisture_0_to_7cm": [0.3] * 73,
                "runoff": [None] * 73,
            },
        }
        with patch.object(environment_module, "_urlopen_json", return_value=payload):
            weather = OpenMeteoWeatherProvider().get(12.7744, 14.6036)
        self.assertTrue(weather["precipitation_3d"].is_valid)
        self.assertTrue(weather["soil_moisture_0_to_7cm"].is_valid)
        self.assertIsNone(weather["runoff"].value)
        self.assertEqual(weather["runoff"].status, NO_DATA)

    def _glofas_payload(self, value, *, latitude=12.775, longitude=14.625, day=None):
        day = day or datetime.now(timezone.utc).date().isoformat()
        return {"latitude": latitude, "longitude": longitude, "daily": {"time": [day], "river_discharge": [value]}}

    def test_glofas_positive_value_has_validated_reference_cell(self):
        with patch.object(environment_module, "_urlopen_json", return_value=self._glofas_payload(145.7)):
            result, _ = OpenMeteoGloFASProvider().get(12.7744, 14.6036, hydrological_context={"glofas_cell_reference": "12.775,14.625", "basin_id": 1060695700})
        self.assertEqual(result.value, 145.7)
        self.assertEqual(result.status, REAL_CURRENT)
        self.assertEqual(result.quality, "VALID")
        self.assertEqual(result.provenance["hydrobasins_basin_id"], 1060695700)

    def test_glofas_genuine_zero_is_not_missing(self):
        with patch.object(environment_module, "_urlopen_json", return_value=self._glofas_payload(0.0)):
            result, _ = OpenMeteoGloFASProvider().get(12.7744, 14.6036, hydrological_context={"glofas_cell_reference": "12.775,14.625"})
        self.assertEqual(result.value, 0.0)
        self.assertEqual(result.status, REAL_CURRENT)
        self.assertTrue(result.is_valid)

    def test_glofas_malformed_or_invalid_values_are_not_zero(self):
        malformed = {"latitude": 12.775, "longitude": 14.625, "daily": {"time": ["2026-01-01"], "river_discharge": ["bad"]}}
        with patch.object(environment_module, "_urlopen_json", return_value=malformed):
            result, _ = OpenMeteoGloFASProvider().get(12.7744, 14.6036)
        self.assertIsNone(result.value)
        self.assertEqual(result.status, INVALID_VALUE)

    def test_glofas_missing_schema_is_explicit_invalid_response(self):
        with patch.object(environment_module, "_urlopen_json", return_value={"latitude": 12.775, "longitude": 14.625}):
            result, _ = OpenMeteoGloFASProvider().get(12.7744, 14.6036)
        self.assertIsNone(result.value)
        self.assertEqual(result.status, INVALID_RESPONSE)

    def test_glofas_rejects_unrepresentative_reference_cell(self):
        payload = self._glofas_payload(50.0, latitude=10.0, longitude=10.0)
        with patch.object(environment_module, "_urlopen_json", return_value=payload):
            result, _ = OpenMeteoGloFASProvider().get(12.7744, 14.6036, hydrological_context={"glofas_cell_reference": "12.775,14.625"})
        self.assertIsNone(result.value)
        self.assertEqual(result.status, OUTSIDE_COVERAGE)

    def test_glofas_timeout_and_rate_limit_never_become_zero(self):
        with patch.object(environment_module, "_urlopen_json", side_effect=TimeoutError("request timed out")):
            timed_out, _ = OpenMeteoGloFASProvider().get(12.7744, 14.6036)
        with patch.object(environment_module, "_urlopen_json", side_effect=RuntimeError("HTTP 429")):
            limited, _ = OpenMeteoGloFASProvider().get(12.7744, 14.6036)
        self.assertIsNone(timed_out.value)
        self.assertEqual(timed_out.status, TIMEOUT)
        self.assertIsNone(limited.value)
        self.assertEqual(limited.status, RATE_LIMITED)

    def test_rainviewer_is_visual_only_even_when_a_frame_exists(self):
        manifest = {"host": "https://tilecache.rainviewer.com", "radar": {"past": [{"time": 1_700_000_000, "path": "/v2/radar/1"}]}}
        with patch.object(environment_module, "_urlopen_json", return_value=manifest):
            radar = RainViewerVisualProvider().get(12.0, 15.0)
        self.assertIsNone(radar.value)
        self.assertEqual(radar.quality, "VISUAL_ONLY")
        self.assertFalse(radar.is_valid)

    def test_rainviewer_timeout_does_not_fail_other_valid_variables(self):
        class BrokenRadar:
            def get(self, lat, lon):
                return observation("radar_visual_layer", None, status=TIMEOUT, quality="UNAVAILABLE")

        result = EnvironmentalOrchestrator(
            weather=GoodWeather(), discharge=ZeroDischarge(), radar=BrokenRadar(), surface_water=NoSurfaceWater(),
        ).collect(12.0, 15.0)
        self.assertEqual(result["objects"]["radar_visual_layer"].status, TIMEOUT)
        self.assertTrue(result["objects"]["precipitation_3d"].is_valid)
        self.assertTrue(result["objects"]["river_discharge"].is_valid)

    def test_real_zero_is_preserved(self):
        data = EnvironmentalOrchestrator(
            weather=GoodWeather(), discharge=ZeroDischarge(), radar=VisualRadar(), surface_water=NoSurfaceWater(),
        ).collect(12.0, 15.0)
        self.assertEqual(data["objects"]["precipitation_3d"].value, 0.0)
        self.assertEqual(data["objects"]["runoff"].value, 0.0)
        self.assertEqual(data["objects"]["river_discharge"].value, 0.0)
        self.assertTrue(data["objects"]["river_discharge"].is_valid)

    def test_provider_failure_is_never_coerced_to_zero(self):
        data = EnvironmentalOrchestrator(
            weather=FailingWeather(), discharge=ZeroDischarge(), radar=VisualRadar(), surface_water=NoSurfaceWater(),
        ).collect(12.0, 15.0)
        for variable in ("precipitation_3d", "soil_moisture_0_to_7cm", "runoff"):
            item = data["objects"][variable]
            self.assertIsNone(item.value)
            self.assertEqual(item.status, PROVIDER_ERROR)
            self.assertFalse(item.is_valid)

    def test_radar_visual_layer_never_becomes_a_numeric_feature(self):
        data = EnvironmentalOrchestrator(
            weather=GoodWeather(), discharge=ZeroDischarge(), radar=VisualRadar(), surface_water=NoSurfaceWater(),
        ).collect(12.0, 15.0)
        radar = data["objects"]["radar_visual_layer"]
        self.assertIsNone(radar.value)
        self.assertEqual(radar.quality, "VISUAL_ONLY")
        self.assertFalse(radar.is_valid)

    def test_stale_archive_is_context_not_live_runoff_fallback(self):
        data = EnvironmentalOrchestrator(
            weather=FailingWeather(), discharge=ZeroDischarge(), radar=VisualRadar(), surface_water=NoSurfaceWater(),
        ).collect(12.0, 15.0, archived_runoff={"value": 0.0, "date": "2020-01-01"})
        runoff = data["objects"]["runoff"]
        self.assertEqual(runoff.value, 0.0)
        self.assertEqual(runoff.status, REAL_HISTORICAL)
        self.assertEqual(runoff.quality, "HISTORICAL_CONTEXT")
        self.assertFalse(runoff.is_valid)

    def test_discharge_failure_does_not_hide_valid_weather(self):
        data = EnvironmentalOrchestrator(
            weather=GoodWeather(), discharge=BrokenDischarge(), radar=VisualRadar(), surface_water=NoSurfaceWater(),
        ).collect(12.0, 15.0)
        self.assertTrue(data["objects"]["precipitation_3d"].is_valid)
        self.assertIsNone(data["objects"]["river_discharge"].value)
        self.assertEqual(data["objects"]["river_discharge"].status, PROVIDER_ERROR)

    def test_incomplete_full_model_inputs_return_insufficient_data(self):
        observations = EnvironmentalOrchestrator(
            weather=GoodWeather(), discharge=ZeroDischarge(), radar=VisualRadar(), surface_water=NoSurfaceWater(),
        ).collect(12.0, 15.0)["objects"]
        decision = assess_model_eligibility(
            observations, terrain_ready=True, upstream_rainfall_ready=False, discharge_lags_ready=False,
        )
        self.assertEqual(decision["prediction_status"], "INSUFFICIENT_DATA")
        self.assertIn("upstream_rainfall", decision["features_missing"])
        self.assertIn("discharge_lags", decision["features_missing"])

    def test_only_complete_validated_features_can_unlock_full_profile(self):
        observations = EnvironmentalOrchestrator(
            weather=GoodWeather(), discharge=ZeroDischarge(), radar=VisualRadar(), surface_water=NoSurfaceWater(),
        ).collect(12.0, 15.0)["objects"]
        decision = assess_model_eligibility(
            observations, terrain_ready=True, upstream_rainfall_ready=True, discharge_lags_ready=True,
        )
        self.assertEqual(decision["prediction_status"], "FULL_PREDICTION")

    def test_partial_profile_uses_core_inputs_without_radar_or_sar(self):
        """Radar/SAR availability must never gate the valid partial profile."""
        class FixedPipeline:
            def predict_proba(self, frame):
                self.columns = list(frame.columns)
                return np.array([[0.82, 0.18]])

        today = datetime.now(timezone.utc).date()
        observations = {
            "precipitation_1d": observation("precipitation_1d", 2.0),
            "precipitation_3d": observation("precipitation_3d", 8.0),
            "precipitation_7d": observation("precipitation_7d", 20.0),
            "precipitation_14d": observation("precipitation_14d", 36.0),
            "soil_moisture_0_to_7cm": observation("soil_moisture_0_to_7cm", 0.31),
            "river_discharge": EnvironmentalObservation(
                variable="river_discharge", value=24.0, unit="m³/s", provider="test",
                provider_product="test-glofas", source_type="test", observation_type="test",
                requested_latitude=12.0, requested_longitude=15.0,
                status=REAL_CURRENT, quality="VALID", valid_time=today.isoformat(),
            ),
            # These intentionally unavailable supporting products are absent
            # from the partial feature schema.
            "radar_visual_layer": observation("radar_visual_layer", None, status=NO_DATA, quality="UNAVAILABLE"),
            "surface_water": observation("surface_water", None, status=NO_DATA, quality="UNAVAILABLE"),
        }
        features = [
            "rainfall_1d", "rainfall_3d", "rainfall_7d", "rainfall_14d", "rainfall_anomaly",
            "swvl1", "discharge_m3s", "discharge_lag1", "discharge_lag3", "discharge_lag7",
            "elevation_m", "slope_deg", "basin_id", "season",
        ]
        payload = {
            "pipeline": FixedPipeline(), "features": features, "threshold": 0.18,
            "metrics": {}, "candidate_name": "test-partial", "model_profile": "PARTIAL_TEST",
            "source_provenance": {},
        }
        series = {
            (today - timedelta(days=1)).isoformat(): 22.0,
            (today - timedelta(days=3)).isoformat(): 20.0,
            (today - timedelta(days=7)).isoformat(): 18.0,
        }
        row = pd.Series({"elevation_m": 285.0, "slope_deg": 1.5})
        hydrology = pd.Series({"basin_id": 1060695700})
        with patch.object(risk_engine, "_partial_live_model", return_value=payload):
            result, missing = risk_engine._partial_live_prediction(
                observations=observations, discharge_series=series, row=row,
                hrow=hydrology, rainfall_p90=12.0,
            )
        self.assertEqual(missing, [])
        self.assertEqual(result["risk_score_percent"], 18.0)
        self.assertEqual(result["risk_level"], "LOW")
        self.assertNotIn("radar_visual_layer", result["features_used"])
        self.assertNotIn("surface_water", result["features_used"])

    def test_partial_profile_withholds_score_when_discharge_lag_is_missing(self):
        today = datetime.now(timezone.utc).date()
        observations = {
            "precipitation_1d": observation("precipitation_1d", 2.0),
            "precipitation_3d": observation("precipitation_3d", 8.0),
            "precipitation_7d": observation("precipitation_7d", 20.0),
            "precipitation_14d": observation("precipitation_14d", 36.0),
            "soil_moisture_0_to_7cm": observation("soil_moisture_0_to_7cm", 0.31),
            "river_discharge": EnvironmentalObservation(
                variable="river_discharge", value=24.0, unit="m³/s", provider="test",
                provider_product="test-glofas", source_type="test", observation_type="test",
                requested_latitude=12.0, requested_longitude=15.0,
                status=REAL_CURRENT, quality="VALID", valid_time=today.isoformat(),
            ),
        }
        payload = {"pipeline": object(), "features": [], "threshold": 0.18, "metrics": {}, "candidate_name": "test", "model_profile": "PARTIAL_TEST"}
        with patch.object(risk_engine, "_partial_live_model", return_value=payload):
            result, missing = risk_engine._partial_live_prediction(
                observations=observations,
                discharge_series={(today - timedelta(days=1)).isoformat(): 22.0},
                row=pd.Series({"elevation_m": 285.0, "slope_deg": 1.5}),
                hrow=pd.Series({"basin_id": 1060695700}), rainfall_p90=12.0,
            )
        self.assertIsNone(result)
        self.assertIn("discharge_lag3", missing)
        self.assertIn("discharge_lag7", missing)


if __name__ == "__main__":
    unittest.main()
