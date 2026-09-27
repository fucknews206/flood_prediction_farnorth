"""Validated, variable-centric environmental acquisition for Far North risk.

This module deliberately keeps provider payloads out of the prediction layer.
An environmental number is useful only together with its data state, time,
location and provenance.  In particular, a failed provider is never expressed
as a physical zero.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import json
import math
import time
import urllib.parse
import urllib.request
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Optional


# These values are part of the API contract.  Keep them as strings so both the
# Python API and TypeScript UI can consume them without enum serialisation.
REAL_CURRENT = "REAL_CURRENT"
REAL_FORECAST = "REAL_FORECAST"
REAL_HISTORICAL = "REAL_HISTORICAL"
REAL_RECENT_BUT_NOT_CURRENT = "REAL_RECENT_BUT_NOT_CURRENT"
STALE_DATA = "STALE_DATA"
NO_DATA = "NO_DATA"
PROVIDER_ERROR = "PROVIDER_ERROR"
OUTSIDE_COVERAGE = "OUTSIDE_COVERAGE"
INVALID_RESPONSE = "INVALID_RESPONSE"
INVALID_VALUE = "INVALID_VALUE"
TIMEOUT = "TIMEOUT"
AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
RATE_LIMITED = "RATE_LIMITED"

VALID_DATA_STATES = {
    REAL_CURRENT, REAL_FORECAST, REAL_HISTORICAL, REAL_RECENT_BUT_NOT_CURRENT,
}


class ProviderDataError(ValueError):
    """A reachable provider response that failed an explicit validation rule."""
    def __init__(self, state: str, message: str) -> None:
        super().__init__(message)
        self.state = state


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def parse_time(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def failure_state(exc: Exception) -> str:
    if isinstance(exc, ProviderDataError):
        return exc.state
    text = str(exc).lower()
    if "timed out" in text or "timeout" in text:
        return TIMEOUT
    if "429" in text:
        return RATE_LIMITED
    if "401" in text or "403" in text:
        return AUTHENTICATION_ERROR
    return PROVIDER_ERROR


def valid_lat_lon(lat: Any, lon: Any) -> bool:
    return (
        isinstance(lat, (int, float)) and isinstance(lon, (int, float))
        and math.isfinite(float(lat)) and math.isfinite(float(lon))
        and -90 <= float(lat) <= 90 and -180 <= float(lon) <= 180
    )


def parse_grid_reference(value: Any) -> Optional[tuple[float, float]]:
    """Parse the project's precomputed locality-to-GloFAS reference cell."""
    try:
        lat_text, lon_text = str(value).split(",", 1)
        lat, lon = float(lat_text), float(lon_text)
        return (lat, lon) if valid_lat_lon(lat, lon) else None
    except (TypeError, ValueError):
        return None


def grid_distance_degrees(first: tuple[float, float], second: tuple[float, float]) -> float:
    return math.hypot(first[0] - second[0], first[1] - second[1])


@dataclass
class EnvironmentalObservation:
    variable: str
    value: Optional[float]
    unit: str
    provider: str
    provider_product: str
    source_type: str
    observation_type: str
    requested_latitude: float
    requested_longitude: float
    status: str
    actual_latitude: Optional[float] = None
    actual_longitude: Optional[float] = None
    requested_time: Optional[str] = None
    valid_time: Optional[str] = None
    retrieved_at: Optional[str] = None
    source_update_time: Optional[str] = None
    freshness_seconds: Optional[float] = None
    spatial_resolution: Optional[str] = None
    temporal_resolution: Optional[str] = None
    quality: str = "UNAVAILABLE"
    confidence: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    provenance: dict[str, Any] = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        return self.status in VALID_DATA_STATES and self.value is not None and self.quality in {"VALID", "CACHED_WITHIN_TOLERANCE"}

    def as_dict(self) -> dict[str, Any]:
        return {
            "variable": self.variable,
            "value": self.value,
            "unit": self.unit,
            "provider": self.provider,
            "provider_product": self.provider_product,
            "source_type": self.source_type,
            "observation_type": self.observation_type,
            "requested_latitude": self.requested_latitude,
            "requested_longitude": self.requested_longitude,
            "actual_latitude": self.actual_latitude,
            "actual_longitude": self.actual_longitude,
            "requested_time": self.requested_time,
            "valid_time": self.valid_time,
            "retrieved_at": self.retrieved_at,
            "source_update_time": self.source_update_time,
            "freshness_seconds": self.freshness_seconds,
            "spatial_resolution": self.spatial_resolution,
            "temporal_resolution": self.temporal_resolution,
            "status": self.status,
            "quality": self.quality,
            "confidence": self.confidence,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "provenance": self.provenance,
        }


class ProviderHealth:
    """Small in-process health record; it never synthesises observations."""
    def __init__(self) -> None:
        self._items: dict[str, dict[str, Any]] = {}

    def record(self, provider: str, observations: list[EnvironmentalObservation], latency_ms: int) -> None:
        successful = any(o.is_valid for o in observations)
        item = self._items.setdefault(provider, {"failure_count": 0, "timeout_count": 0})
        item.update({
            "availability": "HEALTHY" if successful else "DEGRADED",
            "latency_ms": latency_ms,
            "last_checked_at": iso(utcnow()),
            "last_success_at": iso(utcnow()) if successful else item.get("last_success_at"),
            "last_failure_at": None if successful else iso(utcnow()),
            "failure_count": 0 if successful else int(item["failure_count"]) + 1,
            "timeout_count": int(item["timeout_count"]) + int(any(o.status == TIMEOUT for o in observations)),
        })

    def snapshot(self) -> dict[str, dict[str, Any]]:
        return {name: dict(value) for name, value in self._items.items()}


HEALTH = ProviderHealth()
AUDIT_LOG = Path(__file__).resolve().parent / "data_quality" / "farnorth_consolidation" / "environmental_observation_audit.jsonl"
_PROVIDER_CACHE: dict[str, tuple[datetime, Any]] = {}
_PROVIDER_CACHE_LOCK = Lock()


def _urlopen_json(url: str, timeout: int, retries: int = 2) -> dict[str, Any]:
    last_error: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "AquaGuard-Cameroon/1.0"})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                if response.status != 200:
                    raise RuntimeError(f"HTTP {response.status}")
                payload = json.loads(response.read().decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("Provider returned a non-object JSON payload")
                return payload
        except Exception as exc:  # bounded retries; the caller retains the error state
            last_error = exc
            if attempt < retries:
                time.sleep(0.25 * (2 ** attempt))
    assert last_error is not None
    raise last_error


def _failure(variable: str, unit: str, provider: str, product: str, lat: float, lon: float,
             exc: Exception, source_type: str = "external_api") -> EnvironmentalObservation:
    return EnvironmentalObservation(
        variable=variable, value=None, unit=unit, provider=provider,
        provider_product=product, source_type=source_type, observation_type="unknown",
        requested_latitude=lat, requested_longitude=lon, status=failure_state(exc),
        retrieved_at=iso(utcnow()), quality="UNAVAILABLE", error_code=failure_state(exc),
        error_message=str(exc),
    )


def _cacheable(payload: Any) -> bool:
    """Only cache actual provider responses; error and no-data states retry live."""
    if isinstance(payload, EnvironmentalObservation):
        return payload.status in VALID_DATA_STATES and payload.quality != "UNAVAILABLE"
    if isinstance(payload, dict):
        return bool(payload) and all(_cacheable(value) for value in payload.values())
    if isinstance(payload, tuple):
        return bool(payload) and _cacheable(payload[0])
    return False


def _mark_cached(payload: Any, retrieved_at: datetime) -> Any:
    """Return a copy whose state makes cache reuse visible to all consumers."""
    if isinstance(payload, EnvironmentalObservation):
        quality = "CACHED_WITHIN_TOLERANCE" if payload.quality == "VALID" else payload.quality
        provenance = dict(payload.provenance)
        provenance["cache"] = {"served_from_cache": True, "cached_retrieved_at": payload.retrieved_at}
        return replace(
            payload, status=REAL_RECENT_BUT_NOT_CURRENT, quality=quality,
            freshness_seconds=max(0.0, (retrieved_at - parse_time(payload.retrieved_at)).total_seconds()) if parse_time(payload.retrieved_at) else None,
            provenance=provenance,
        )
    if isinstance(payload, dict):
        return {key: _mark_cached(value, retrieved_at) for key, value in payload.items()}
    if isinstance(payload, tuple):
        return (_mark_cached(payload[0], retrieved_at), dict(payload[1]))
    return payload


def cached_provider_response(key: str, max_age_seconds: int, fetch: Callable[[], Any]) -> Any:
    """Use a variable-specific bounded cache without re-labelling it current."""
    now = utcnow()
    with _PROVIDER_CACHE_LOCK:
        cached = _PROVIDER_CACHE.get(key)
        if cached and (now - cached[0]).total_seconds() <= max_age_seconds:
            return _mark_cached(cached[1], now)
    payload = fetch()
    if _cacheable(payload):
        with _PROVIDER_CACHE_LOCK:
            _PROVIDER_CACHE[key] = (now, payload)
    return payload


class OpenMeteoWeatherProvider:
    """Forecast-model precipitation, top-soil moisture and total runoff."""
    provider = "Open-Meteo"
    product = "Forecast API"
    supports = {"precipitation_1d", "precipitation_3d", "precipitation_7d", "precipitation_14d", "soil_moisture_0_to_7cm", "runoff"}

    def get(self, lat: float, lon: float) -> dict[str, EnvironmentalObservation]:
        started = time.monotonic()
        now = utcnow()
        params = urllib.parse.urlencode({
            "latitude": lat, "longitude": lon,
            "hourly": "precipitation,soil_moisture_0_to_7cm,runoff",
            # The validated partial profile uses 1/3/7/14-day local rain
            # windows. Request exactly the history necessary to build those
            # real windows; missing hours remain missing, never zero-filled.
            "past_days": 14, "forecast_days": 1, "timezone": "UTC",
        })
        try:
            raw = _urlopen_json(f"https://api.open-meteo.com/v1/forecast?{params}", timeout=12)
            hourly = raw.get("hourly")
            if not isinstance(hourly, dict):
                raise ValueError("Missing hourly object")
            times = [parse_time(item) for item in hourly.get("time", [])]
            precipitation = hourly.get("precipitation", [])
            soil = hourly.get("soil_moisture_0_to_7cm", [])
            runoff = hourly.get("runoff", [])
            if not times or not (len(times) == len(precipitation) == len(soil) == len(runoff)):
                raise ValueError("Hourly arrays are missing or have incompatible lengths")
            actual_lat = raw.get("latitude")
            actual_lon = raw.get("longitude")
            if not isinstance(actual_lat, (float, int)) or not isinstance(actual_lon, (float, int)):
                raise ValueError("Provider response has no valid grid coordinates")
            indexed = [(t, precipitation[i], soil[i], runoff[i]) for i, t in enumerate(times) if t is not None]
            past = [item for item in indexed if item[0] <= now]
            if not past:
                raise ValueError("No current or historical weather timestamp returned")
            latest = past[-1]
            last_72 = [item for item in past if (now - item[0]).total_seconds() <= 72 * 3600]
            common = dict(
                provider=self.provider, provider_product=self.product, source_type="numerical_weather_model",
                observation_type="forecast_model", requested_latitude=lat, requested_longitude=lon,
                actual_latitude=float(actual_lat), actual_longitude=float(actual_lon), retrieved_at=iso(now),
                source_update_time=iso(now), spatial_resolution="provider-selected weather grid",
                temporal_resolution="hourly",
                provenance={"endpoint": "https://api.open-meteo.com/v1/forecast", "model": raw.get("model"), "timezone": raw.get("timezone")},
            )
            result: dict[str, EnvironmentalObservation] = {}
            for days in (1, 3, 7, 14):
                hours = days * 24
                window = [item for item in past if (now - item[0]).total_seconds() <= hours * 3600]
                values = [item[1] for item in window]
                variable = f"precipitation_{days}d"
                if len(window) < hours or any(not isinstance(value, (int, float)) or not math.isfinite(float(value)) or value < 0 for value in values):
                    result[variable] = EnvironmentalObservation(variable=variable, value=None, unit="mm", status=INVALID_VALUE, valid_time=iso(latest[0]), quality="UNAVAILABLE", error_code=INVALID_VALUE, error_message=f"A complete valid {hours}-hour precipitation window is required", **common)
                else:
                    result[variable] = EnvironmentalObservation(variable=variable, value=round(float(sum(values)), 3), unit="mm", status=REAL_CURRENT, valid_time=iso(latest[0]), freshness_seconds=max(0.0, (now-latest[0]).total_seconds()), quality="VALID", **common)
            soil_value = latest[2]
            if not isinstance(soil_value, (int, float)) or not 0 <= float(soil_value) <= 1:
                result["soil_moisture_0_to_7cm"] = EnvironmentalObservation(variable="soil_moisture_0_to_7cm", value=None, unit="m³/m³", status=INVALID_VALUE, valid_time=iso(latest[0]), quality="UNAVAILABLE", error_code=INVALID_VALUE, error_message="Missing or physically invalid top-soil moisture", **common)
            else:
                result["soil_moisture_0_to_7cm"] = EnvironmentalObservation(variable="soil_moisture_0_to_7cm", value=float(soil_value), unit="m³/m³", status=REAL_CURRENT, valid_time=iso(latest[0]), freshness_seconds=max(0.0, (now-latest[0]).total_seconds()), quality="VALID", **common)
            runoff_value = latest[3]
            if not isinstance(runoff_value, (int, float)) or float(runoff_value) < 0:
                result["runoff"] = EnvironmentalObservation(variable="runoff", value=None, unit="mm", status=NO_DATA, valid_time=iso(latest[0]), quality="UNAVAILABLE", error_code=NO_DATA, error_message="Open-Meteo did not return a valid runoff value for this grid cell", **common)
            else:
                result["runoff"] = EnvironmentalObservation(variable="runoff", value=float(runoff_value), unit="mm", status=REAL_CURRENT, valid_time=iso(latest[0]), freshness_seconds=max(0.0, (now-latest[0]).total_seconds()), quality="VALID", **common)
        except Exception as exc:
            result = {
                "precipitation_1d": _failure("precipitation_1d", "mm", self.provider, self.product, lat, lon, exc),
                "precipitation_3d": _failure("precipitation_3d", "mm", self.provider, self.product, lat, lon, exc),
                "precipitation_7d": _failure("precipitation_7d", "mm", self.provider, self.product, lat, lon, exc),
                "precipitation_14d": _failure("precipitation_14d", "mm", self.provider, self.product, lat, lon, exc),
                "soil_moisture_0_to_7cm": _failure("soil_moisture_0_to_7cm", "m³/m³", self.provider, self.product, lat, lon, exc),
                "runoff": _failure("runoff", "mm", self.provider, self.product, lat, lon, exc),
            }
        HEALTH.record(self.provider, list(result.values()), int((time.monotonic() - started) * 1000))
        return result


class OpenMeteoGloFASProvider:
    provider = "Open-Meteo"
    product = "Flood API / GloFAS v4"
    supports = {"river_discharge"}

    def get(self, lat: float, lon: float, forecast_days: int = 7,
            hydrological_context: Optional[dict[str, Any]] = None) -> tuple[EnvironmentalObservation, dict[str, float]]:
        started = time.monotonic()
        now = utcnow()
        if not valid_lat_lon(lat, lon):
            error = ValueError("Latitude/longitude are outside valid geographic bounds")
            observation = _failure("river_discharge", "m³/s", self.provider, self.product, float(lat or 0), float(lon or 0), error, "hydrological_simulation")
            observation.status = INVALID_VALUE
            observation.error_code = INVALID_VALUE
            return observation, {}
        params = urllib.parse.urlencode({"latitude": lat, "longitude": lon, "daily": "river_discharge", "past_days": 7, "forecast_days": min(14, max(1, forecast_days))})
        series: dict[str, float] = {}
        try:
            raw = _urlopen_json(f"https://flood-api.open-meteo.com/v1/flood?{params}", timeout=12)
            daily = raw.get("daily")
            if not isinstance(daily, dict):
                raise ProviderDataError(INVALID_RESPONSE, "Missing daily object")
            raw_values = list(daily.get("river_discharge", []))
            for day, value in zip(daily.get("time", []), daily.get("river_discharge", [])):
                if isinstance(value, (int, float)) and math.isfinite(float(value)) and 0 <= float(value) <= 10_000_000:
                    series[str(day)] = float(value)  # zero remains a genuine zero
            actual_lat, actual_lon = raw.get("latitude"), raw.get("longitude")
            if not valid_lat_lon(actual_lat, actual_lon):
                raise ProviderDataError(INVALID_RESPONSE, "Provider response has no usable grid coordinate")
            if not series:
                raise ProviderDataError(INVALID_VALUE if raw_values else NO_DATA, "No finite non-negative discharge values in the provider response")
            expected_cell = parse_grid_reference((hydrological_context or {}).get("glofas_cell_reference"))
            candidates = [{"request": {"latitude": lat, "longitude": lon}, "actual": {"latitude": float(actual_lat), "longitude": float(actual_lon)}}]
            # The historical locality-to-cell mapping is our hydrological
            # context. If the provider snaps the locality to another cell, try
            # that documented reference cell once; never scan surrounding cells
            # looking for a non-zero discharge value.
            if expected_cell and grid_distance_degrees((float(actual_lat), float(actual_lon)), expected_cell) > 0.051:
                reference_params = urllib.parse.urlencode({"latitude": expected_cell[0], "longitude": expected_cell[1], "daily": "river_discharge", "past_days": 7, "forecast_days": min(14, max(1, forecast_days))})
                reference_raw = _urlopen_json(f"https://flood-api.open-meteo.com/v1/flood?{reference_params}", timeout=12)
                reference_daily = reference_raw.get("daily")
                reference_lat, reference_lon = reference_raw.get("latitude"), reference_raw.get("longitude")
                if not isinstance(reference_daily, dict) or not valid_lat_lon(reference_lat, reference_lon):
                    raise ProviderDataError(INVALID_RESPONSE, "Reference GloFAS cell could not be validated")
                reference_series = {
                    str(day): float(value) for day, value in zip(reference_daily.get("time", []), reference_daily.get("river_discharge", []))
                    if isinstance(value, (int, float)) and math.isfinite(float(value)) and 0 <= float(value) <= 10_000_000
                }
                candidates.append({"request": {"latitude": expected_cell[0], "longitude": expected_cell[1]}, "actual": {"latitude": float(reference_lat), "longitude": float(reference_lon)}})
                if not reference_series or grid_distance_degrees((float(reference_lat), float(reference_lon)), expected_cell) > 0.051:
                    raise ProviderDataError(OUTSIDE_COVERAGE, "No spatially representative GloFAS grid cell for the locality hydrological context")
                raw, series, actual_lat, actual_lon = reference_raw, reference_series, reference_lat, reference_lon
            today = now.date().isoformat()
            eligible = [(day, value) for day, value in series.items() if day <= today]
            if not eligible:
                raise ProviderDataError(NO_DATA, "No current discharge date returned")
            valid_day, value = max(eligible, key=lambda pair: pair[0])
            valid_time = parse_time(valid_day + "T00:00:00+00:00")
            freshness = max(0.0, (now-valid_time).total_seconds()) if valid_time else None
            if freshness is None or freshness > 3 * 24 * 60 * 60:
                raise ProviderDataError(STALE_DATA, "GloFAS discharge timestamp exceeds the current-data freshness policy")
            spatially_validated = bool(expected_cell and grid_distance_degrees((float(actual_lat), float(actual_lon)), expected_cell) <= 0.051)
            observation = EnvironmentalObservation(
                variable="river_discharge", value=value, unit="m³/s", provider=self.provider,
                provider_product=self.product, source_type="hydrological_simulation", observation_type="modelled_discharge",
                requested_latitude=lat, requested_longitude=lon, actual_latitude=float(actual_lat), actual_longitude=float(actual_lon),
                valid_time=iso(valid_time), retrieved_at=iso(now), source_update_time=iso(now),
                freshness_seconds=freshness,
                spatial_resolution="0.05° (~5 km)", temporal_resolution="daily", status=REAL_CURRENT,
                quality="VALID" if spatially_validated else "SPATIAL_VALIDATION_PENDING",
                error_code=None if spatially_validated else "GLOFAS_CELL_NOT_BASIN_VALIDATED",
                error_message=None if spatially_validated else "No locality-to-GloFAS reference cell is available; discharge remains evidence only.",
                provenance={"endpoint": "https://flood-api.open-meteo.com/v1/flood", "cell_selection": "validated locality reference cell" if spatially_validated else "provider cell; locality reference unavailable", "expected_glofas_cell": expected_cell, "candidate_cells": candidates, "hydrobasins_basin_id": (hydrological_context or {}).get("basin_id"), "series": series},
            )
        except Exception as exc:
            observation = _failure("river_discharge", "m³/s", self.provider, self.product, lat, lon, exc, "hydrological_simulation")
        HEALTH.record(self.product, [observation], int((time.monotonic() - started) * 1000))
        return observation, series


class RainViewerVisualProvider:
    """Records map availability only. Raster alpha is never an observation."""
    provider = "RainViewer"
    product = "Weather Maps API"
    supports: set[str] = set()

    def get(self, lat: float, lon: float) -> EnvironmentalObservation:
        started = time.monotonic()
        try:
            raw = _urlopen_json("https://api.rainviewer.com/public/weather-maps.json", timeout=8, retries=1)
            frames = raw.get("radar", {}).get("past", [])
            latest = frames[-1] if isinstance(frames, list) and frames else None
            if not isinstance(latest, dict):
                raise ValueError("No current radar frame")
            timestamp = datetime.fromtimestamp(int(latest["time"]), tz=timezone.utc)
            obs = EnvironmentalObservation(
                variable="radar_visual_layer", value=None, unit="", provider=self.provider, provider_product=self.product,
                source_type="radar_map_image", observation_type="visualisation_only", requested_latitude=lat, requested_longitude=lon,
                valid_time=iso(timestamp), retrieved_at=iso(utcnow()), spatial_resolution="map tile (not a physical point measurement)",
                temporal_resolution="provider frame", status=REAL_RECENT_BUT_NOT_CURRENT, quality="VISUAL_ONLY",
                provenance={"host": raw.get("host"), "path": latest.get("path"), "coverage_not_validated": True},
            )
        except Exception as exc:
            obs = _failure("radar_visual_layer", "", self.provider, self.product, lat, lon, exc, "radar_map_image")
        HEALTH.record(self.provider, [obs], int((time.monotonic() - started) * 1000))
        return obs


class OperaSurfaceWaterProvider:
    """CMR discovery is retained, but never turns a browse PNG into a value."""
    provider = "NASA"
    product = "OPERA DSWx-S1"
    supports = {"surface_water"}

    def get(self, lat: float, lon: float) -> EnvironmentalObservation:
        # A proper value requires downloading a georeferenced DSWx COG, applying
        # the product mask/classes and clipping it to the locality/basin.  This
        # deployment does not yet have that validated processing chain.
        return EnvironmentalObservation(
            variable="surface_water", value=None, unit="fraction", provider=self.provider, provider_product=self.product,
            source_type="satellite_derived_observation", observation_type="geospatial_raster_required",
            requested_latitude=lat, requested_longitude=lon, retrieved_at=iso(utcnow()), status=NO_DATA,
            quality="UNAVAILABLE", error_code="GEOSPATIAL_PROCESSING_NOT_CONFIGURED",
            error_message="OPERA browse imagery is not a valid locality metric; no numerical value is emitted until COG clipping and classification validation are configured.",
            spatial_resolution="30 m native product", temporal_resolution="6–12 day revisit", provenance={"discovery_endpoint": "https://cmr.earthdata.nasa.gov/search/granules.json"},
        )


class EnvironmentalOrchestrator:
    """Queries independent variable providers concurrently and exposes provenance."""
    def __init__(self, weather: Optional[Any] = None, discharge: Optional[Any] = None,
                 radar: Optional[Any] = None, surface_water: Optional[Any] = None) -> None:
        self.weather = weather or OpenMeteoWeatherProvider()
        self.discharge = discharge or OpenMeteoGloFASProvider()
        self.radar = radar or RainViewerVisualProvider()
        self.surface_water = surface_water or OperaSurfaceWaterProvider()

    def collect(self, lat: float, lon: float, archived_runoff: Optional[dict[str, Any]] = None,
                hydrological_context: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        coordinate_key = f"{lat:.4f},{lon:.4f}"
        hydrology_key = str((hydrological_context or {}).get("glofas_cell_reference") or "unvalidated")
        with ThreadPoolExecutor(max_workers=4) as pool:
            weather_task = pool.submit(cached_provider_response, f"weather:{self.weather.__class__.__name__}:{coordinate_key}", 15 * 60, lambda: self.weather.get(lat, lon))
            discharge_task = pool.submit(cached_provider_response, f"glofas:{self.discharge.__class__.__name__}:{coordinate_key}:{hydrology_key}", 6 * 60 * 60, lambda: self.discharge.get(lat, lon, hydrological_context=hydrological_context))
            radar_task = pool.submit(cached_provider_response, f"rainviewer:{self.radar.__class__.__name__}:{coordinate_key}", 10 * 60, lambda: self.radar.get(lat, lon))
            surface_task = pool.submit(cached_provider_response, f"opera:{self.surface_water.__class__.__name__}:{coordinate_key}", 6 * 60 * 60, lambda: self.surface_water.get(lat, lon))
            weather = weather_task.result()
            discharge, discharge_series = discharge_task.result()
            radar = radar_task.result()
            surface_water = surface_task.result()
        observations: dict[str, EnvironmentalObservation] = {**weather, "river_discharge": discharge, "radar_visual_layer": radar, "surface_water": surface_water}
        # ERA5-Land is retained as explicitly historical context only, never an
        # operational replacement for a missing current runoff observation.
        if not observations["runoff"].is_valid and archived_runoff:
            date = parse_time(str(archived_runoff.get("date")) + "T00:00:00+00:00")
            value = archived_runoff.get("value")
            age = (utcnow() - date).total_seconds() if date else None
            observations["runoff"] = EnvironmentalObservation(
                variable="runoff", value=float(value) if isinstance(value, (int, float)) else None, unit="mm",
                provider="Copernicus", provider_product="ERA5-Land archive", source_type="land_reanalysis",
                observation_type="historical_reanalysis", requested_latitude=lat, requested_longitude=lon,
                valid_time=iso(date), retrieved_at=iso(utcnow()), freshness_seconds=age, status=REAL_HISTORICAL,
                quality="HISTORICAL_CONTEXT", spatial_resolution="~9 km", temporal_resolution="daily",
                error_code="HISTORICAL_REFERENCE_ONLY", error_message="ERA5-Land archive is a valid historical/reference observation and is not used as a current runoff substitute.",
                provenance={"dataset": "farnorth_locality_runoff_daily.parquet", "selection": "same locality; latest observation on or before requested reference date", "unit_definition": "daily ERA5-Land surface runoff stored by the project in mm"},
            )
        return {
            "observations": {name: observation.as_dict() for name, observation in observations.items()},
            "objects": observations,
            "discharge_series": discharge_series,
            "provider_health": HEALTH.snapshot(),
        }


def persist_observation_audit(*, locality: str, latitude: float, longitude: float,
                              observations: dict[str, dict[str, Any]], eligibility: dict[str, Any]) -> bool:
    """Append a compact machine-readable assessment record without affecting risk logic.

    Audit persistence is deliberately best-effort: a filesystem problem must
    not turn environmental evidence into a fabricated result or hide provider
    failure states from the caller.
    """
    record = {
        "assessment_timestamp": iso(utcnow()),
        "locality": locality,
        "requested_latitude": latitude,
        "requested_longitude": longitude,
        "prediction_status": eligibility.get("prediction_status"),
        "model_profile": eligibility.get("model_profile"),
        "features_used": eligibility.get("features_used", []),
        "features_missing": eligibility.get("features_missing", []),
        "observations": observations,
    }
    try:
        AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        with AUDIT_LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")
        return True
    except OSError:
        return False


def assess_model_eligibility(observations: dict[str, EnvironmentalObservation], *, terrain_ready: bool,
                             upstream_rainfall_ready: bool, discharge_lags_ready: bool) -> dict[str, Any]:
    """Choose only independently validated model profiles.

    No reduced production model is present in this repository, so absent full
    features must lead to transparent insufficient-data status rather than
    imputation or column deletion at runtime.
    """
    required = {
        "precipitation_3d": observations["precipitation_3d"].is_valid,
        "soil_moisture_0_to_7cm": observations["soil_moisture_0_to_7cm"].is_valid,
        "river_discharge": observations["river_discharge"].is_valid,
        "terrain": terrain_ready,
        "upstream_rainfall": upstream_rainfall_ready,
        "discharge_lags": discharge_lags_ready,
    }
    missing = [name for name, ready in required.items() if not ready]
    if not missing:
        return {"prediction_status": "FULL_PREDICTION", "model_profile": "MODEL_FULL_V1", "features_missing": [], "features_used": list(required)}
    return {
        "prediction_status": "INSUFFICIENT_DATA",
        "model_profile": None,
        "features_used": [name for name, ready in required.items() if ready],
        "features_missing": missing,
        "reason": "No separately trained and validated reduced model profile is available for this feature set.",
    }
