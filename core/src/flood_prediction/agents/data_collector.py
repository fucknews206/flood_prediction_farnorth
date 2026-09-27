"""
Enhanced Data Collector Agent for Cameroon.
Collects Open-Meteo weather data and checks GloFAS discharge status.
Operates exclusively in metric units (m³/s for discharge, mm for rainfall).
"""

import asyncio
import aiohttp
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
import json
import logging

from .base_agent import BaseAgent, AgentInsight, AgentAlert
from ..settings import settings

logger = logging.getLogger(__name__)

class DataCollectorAgent(BaseAgent):
    """Agent responsible for collecting real-time weather and flood forecasting data"""
    
    def __init__(self):
        super().__init__(
            name="Data Collector",
            description="Pulls real-time weather forecasts and GloFAS discharge forecasts for Cameroon",
            check_interval=300
        )
        self.last_openmeteo_update = None
        self.last_glofas_update = None
        self.data_quality_score = 0.0
        self.api_retry_attempts = 3
        self.request_timeout = 30
        self.initialized_time = datetime.now(timezone.utc)
        self.has_attempted_collection = False
        self._last_api_status = {}
        
    async def analyze(self, data: Dict[str, Any]) -> List[AgentInsight]:
        """Analyze data collection status and quality"""
        insights = []
        
        # Data freshness insight
        freshness_score = self._calculate_data_freshness()
        insights.append(AgentInsight(
            title="🔄 Data Freshness",
            value=f"{freshness_score:.0f}% current",
            trend='up' if freshness_score > 85 else 'down' if freshness_score < 70 else 'stable',
            urgency='high' if freshness_score < 50 else 'normal'
        ))
        
        # API status insight
        api_status = await self._check_api_status()
        working_apis = sum(1 for status in api_status.values() if status)
        total_apis = len(api_status)
        
        insights.append(AgentInsight(
            title="🌐 API Connectivity",
            value=f"{working_apis}/{total_apis} active",
            trend='up' if working_apis == total_apis else 'down' if working_apis < total_apis/2 else 'stable',
            urgency='high' if working_apis < total_apis/2 else 'normal'
        ))
        
        # Data quality insight
        self.data_quality_score = self._calculate_data_quality()
        insights.append(AgentInsight(
            title="📊 Data Quality",
            value=f"{self.data_quality_score:.1f}/10",
            trend='up' if self.data_quality_score > 8 else 'down' if self.data_quality_score < 6 else 'stable',
            urgency='high' if self.data_quality_score < 5 else 'normal'
        ))
        
        # Update frequency insight
        updates_per_hour = self._calculate_update_frequency()
        insights.append(AgentInsight(
            title="⚡ Update Frequency",
            value=f"{updates_per_hour} updates/hour",
            trend='stable',
            urgency='normal'
        ))
        
        return insights
    
    async def check_alerts(self, data: Dict[str, Any]) -> List[AgentAlert]:
        """Check for data collection issues that require alerts"""
        alerts = []
        
        # Check for stale data
        if self._is_data_stale():
            alerts.append(AgentAlert(
                id=f"data_stale_{datetime.now().strftime('%Y%m%d')}",
                title="⚠️ Stale Data Detected",
                message="Weather or discharge forecast updates have failed for over 2 hours.",
                severity="warning",
                source_agent=self.name,
                recommendations=[
                    "Check Open-Meteo connectivity",
                    "Verify GloFAS configurations"
                ]
            ))
        
        # Check for API failures
        api_status = await self._check_api_status()
        failed_apis = [api for api, status in api_status.items() if not status]
        
        if failed_apis:
            alerts.append(AgentAlert(
                id=f"api_failure_{len(failed_apis)}_{datetime.now().strftime('%Y%m%d%H')}",
                title="🚨 API Connection Failures",
                message=f"Failed to connect to: {', '.join(failed_apis)}",
                severity="critical" if len(failed_apis) > len(api_status)/2 else "warning",
                source_agent=self.name,
                recommendations=[
                    "Check network access",
                    "Verify endpoints"
                ]
            ))
        
        return alerts

    async def _make_request_with_retry(self, url: str, params: dict = None, headers: dict = None) -> Optional[Dict[str, Any]]:
        """Make HTTP request with retry logic and backoff"""
        for attempt in range(self.api_retry_attempts):
            try:
                connector = aiohttp.TCPConnector(limit=10, ttl_dns_cache=300)
                timeout = aiohttp.ClientTimeout(total=self.request_timeout)
                
                async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                    async with session.get(url, params=params, headers=headers) as response:
                        if response.status == 200:
                            content_type = response.headers.get('content-type', '')
                            if 'application/json' in content_type:
                                return await response.json()
                            else:
                                text_data = await response.text()
                                try:
                                    return json.loads(text_data)
                                except json.JSONDecodeError:
                                    logger.warning(f"Non-JSON response from {url}")
                                    return None
                        else:
                            logger.warning(f"HTTP {response.status} from {url}")
                            if attempt == self.api_retry_attempts - 1:
                                return None
                            await asyncio.sleep(2 ** attempt)
            
            except asyncio.TimeoutError:
                logger.warning(f"Timeout accessing {url}")
            except Exception as e:
                logger.error(f"Error accessing {url}: {e}")
            
            if attempt < self.api_retry_attempts - 1:
                await asyncio.sleep(2 ** attempt)
        
        return None
    
    async def collect_openmeteo_rainfall(self, basins: List[Dict[str, Any]]) -> Dict[int, float]:
        """
        Collect real-time rainfall data from Open-Meteo for each basin centroid.
        Returns a dictionary mapping basin_id -> 24h precipitation in mm.
        """
        self.has_attempted_collection = True
        rainfall_map = {}
        
        if not basins:
            return rainfall_map
            
        base_url = "https://api.open-meteo.com/v1/forecast"
        
        # Fetch rainfall for all basins using aiohttp in parallel
        async def fetch_rainfall(basin):
            basin_id = basin['id']
            lat = basin.get('lat')
            lon = basin.get('lon')
            if lat is None or lon is None:
                return basin_id, 0.0
                
            params = {
                'latitude': lat,
                'longitude': lon,
                'daily': 'precipitation_sum',
                'timezone': 'Africa/Lagos',  # West Africa Time
                'forecast_days': 1
            }
            
            try:
                data = await self._make_request_with_retry(base_url, params)
                if data and 'daily' in data:
                    precip_sum = data['daily'].get('precipitation_sum', [0.0])[0]
                    return basin_id, float(precip_sum or 0.0)
            except Exception as e:
                logger.error(f"Failed to fetch rainfall for basin {basin_id}: {e}")
            return basin_id, 0.0

        tasks = [fetch_rainfall(b) for b in basins]
        results = await asyncio.gather(*tasks)
        
        for basin_id, rainfall_val in results:
            rainfall_map[basin_id] = rainfall_val
            
        self.last_openmeteo_update = datetime.now(timezone.utc)
        return rainfall_map

    async def collect_glofas_discharge(self, basins: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
        """Collect real river discharge forecasts for each basin.

        Primary source: Open-Meteo Flood API (GloFAS v4 model, keyless, 0.05° grid).
        Covers the Far North Region (Logone-et-Chari, Mayo-Danay, Diamaré) with daily
        river_discharge in m³/s at 0–14 day lead time.  No API key required.

        If APP_GLOFAS_API_KEY is set (Copernicus EWDS Personal Access Token), a
        background download of the high-resolution ensemble forecast is also scheduled
        via ``download_glofas_ewds_forecast()``; that file is subsequently used by the
        risk engine as a higher-resolution supplement.
        """
        self.has_attempted_collection = True
        results = {}

        async def fetch_one(basin: Dict[str, Any]):
            basin_id = basin['id']
            lat = basin.get('lat')
            lon = basin.get('lon')
            if lat is None or lon is None:
                return basin_id, {"discharge_cms": None, "discharge_status": "unavailable", "discharge_source": "no_coords"}

            url = "https://flood-api.open-meteo.com/v1/flood"
            params = {
                "latitude": lat,
                "longitude": lon,
                "daily": "river_discharge",
                "forecast_days": 7,
                "past_days": 3,
            }
            try:
                timeout = aiohttp.ClientTimeout(total=12)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url, params=params, headers={"User-Agent": "AquaGuard-Cameroon/1.0"}) as resp:
                        if resp.status != 200:
                            logger.warning(f"GloFAS Flood API returned {resp.status} for basin {basin_id}")
                            return basin_id, {"discharge_cms": None, "discharge_status": "unavailable", "discharge_source": "open-meteo-glofas"}
                        raw = await resp.json()
                daily = raw.get("daily", {})
                times = daily.get("time", [])
                vals  = daily.get("river_discharge", [])
                by_date = {t: float(v) for t, v in zip(times, vals) if v is not None}
                today = datetime.now(timezone.utc).date().isoformat()
                latest = by_date.get(today) or (list(by_date.values())[-1] if by_date else None)
                status = "available" if latest is not None else "unavailable"
                return basin_id, {
                    "discharge_cms": latest,
                    "discharge_status": status,
                    "discharge_source": "Open-Meteo GloFAS Flood API (v4, 0.05°)",
                    "discharge_by_date": by_date,
                }
            except Exception as exc:
                logger.warning(f"GloFAS Flood API error for basin {basin_id}: {exc}")
                return basin_id, {"discharge_cms": None, "discharge_status": "unavailable", "discharge_source": "open-meteo-glofas", "error": str(exc)}

        tasks = [fetch_one(b) for b in basins]
        raw_results = await asyncio.gather(*tasks)
        for basin_id, info in raw_results:
            results[basin_id] = info

        self.last_glofas_update = datetime.now(timezone.utc)

        # Trigger EWDS high-resolution download asynchronously if key is set
        glofas_key = getattr(settings, 'glofas_api_key', None)
        if glofas_key:
            asyncio.create_task(self.download_glofas_ewds_forecast(glofas_key))

        return results

    async def download_glofas_ewds_forecast(self, api_key: str) -> None:
        """Background: download the latest GloFAS v4 ensemble forecast via Copernicus EWDS.

        Uses the cdsapi package (``pip install cdsapi>=0.7.7``).
        The downloaded NetCDF is written to
        ``data_quality/farnorth_consolidation/glofas_ewds_latest.nc``
        and converted to parquet for ``farnorth_risk_engine.py``.

        Far North Region bounding box: lat 9.5–13.5°N, lon 13.5–15.5°E.
        """
        try:
            import importlib
            cdsapi = importlib.import_module("cdsapi")
        except ImportError:
            logger.warning("cdsapi not installed — skipping EWDS GloFAS download (pip install cdsapi>=0.7.7)")
            return

        from pathlib import Path
        import tempfile
        import os

        today = datetime.now(timezone.utc).date()
        out_dir = Path(__file__).resolve().parents[4] / "data_quality" / "farnorth_consolidation"
        nc_path  = out_dir / "glofas_ewds_latest.nc"
        parquet_path = out_dir / "glofas_ewds_latest.parquet"

        try:
            logger.info("Downloading GloFAS v4 ensemble forecast from Copernicus EWDS…")
            # Write a temporary .cdsapirc so cdsapi picks up our credentials
            cdsapirc_content = (
                "url: https://ewds.climate.copernicus.eu/api\n"
                f"key: {api_key}\n"
            )
            with tempfile.NamedTemporaryFile(mode='w', suffix='.cdsapirc', delete=False) as f:
                f.write(cdsapirc_content)
                tmp_rc = f.name

            os.environ["CDSAPI_RC"] = tmp_rc
            c = cdsapi.Client(quiet=True)

            request = {
                "system_version": "operational",
                "hydrological_model": "lisflood",
                "product_type": "ensemble_perturbed_forecasts",
                "variable": "river_discharge_in_the_last_24_hours",
                "leadtime_hour": [str(h) for h in range(24, 24*7+1, 24)],
                "area": [13.5, 13.5, 9.5, 15.5],  # N, W, S, E
                "format": "netcdf",
            }

            # Run blocking cdsapi call in executor to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: c.retrieve("cems-glofas-forecast", request, str(nc_path))
            )

            os.unlink(tmp_rc)
            logger.info(f"GloFAS EWDS download complete → {nc_path}")

            # Convert to parquet for use by farnorth_risk_engine
            await loop.run_in_executor(None, lambda: _convert_glofas_nc_to_parquet(nc_path, parquet_path))

        except Exception as exc:
            logger.error(f"GloFAS EWDS download failed: {exc}")
        finally:
            if 'tmp_rc' in dir() and os.path.exists(tmp_rc):
                try:
                    os.unlink(tmp_rc)
                except Exception:
                    pass


    def _calculate_data_freshness(self) -> float:
        """Calculate overall data freshness score (0-100)"""
        now = datetime.now(timezone.utc)
        scores = []
        
        if not self.has_attempted_collection:
            init_age_minutes = (now - self.initialized_time).total_seconds() / 60
            initialization_score = max(0, 100 - (init_age_minutes * 5))
            return initialization_score
        
        if self.last_openmeteo_update:
            age_minutes = (now - self.last_openmeteo_update).total_seconds() / 60
            om_score = max(0, 100 - (age_minutes / 60) * 10)
            scores.append(om_score)
        else:
            scores.append(0)
            
        if self.last_glofas_update:
            age_minutes = (now - self.last_glofas_update).total_seconds() / 60
            glofas_score = max(0, 100 - (age_minutes / 120) * 10)
            scores.append(glofas_score)
        else:
            scores.append(100) # Do not penalize if never run/unavailable by design
            
        return sum(scores) / len(scores) if scores else 0
        
    def _calculate_data_quality(self) -> float:
        """Calculate data quality score (0 to 10)"""
        quality_factors = []
        
        api_status = self._last_api_status
        if api_status:
            working_count = sum(1 for status in api_status.values() if status)
            api_score = (working_count / len(api_status)) * 10
            quality_factors.append(api_score)
            
        freshness = self._calculate_data_freshness()
        quality_factors.append((freshness / 100.0) * 10.0)
        
        # Baselines
        quality_factors.append(8.0)
        
        return sum(quality_factors) / len(quality_factors) if quality_factors else 0.0
        
    async def _check_api_status(self) -> Dict[str, bool]:
        """Check if Open-Meteo weather and GloFAS Flood APIs are responsive."""
        status: Dict[str, bool] = {'OpenMeteo': False, 'GloFAS_FloodAPI': False}

        async def check_openmeteo():
            try:
                params = {'latitude': '4.5', 'longitude': '11.5', 'daily': 'precipitation_sum', 'forecast_days': 1}
                timeout = aiohttp.ClientTimeout(total=10)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get('https://api.open-meteo.com/v1/forecast', params=params) as response:
                        return response.status == 200
            except Exception:
                return False

        async def check_glofas_flood():
            try:
                # Use a stable Far North point (Kousséri) as health check
                params = {'latitude': '12.076', 'longitude': '15.031', 'daily': 'river_discharge', 'forecast_days': 1}
                timeout = aiohttp.ClientTimeout(total=10)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get('https://flood-api.open-meteo.com/v1/flood', params=params,
                                           headers={'User-Agent': 'AquaGuard-Cameroon/1.0'}) as response:
                        return response.status == 200
            except Exception:
                return False

        om_ok, gf_ok = await asyncio.gather(check_openmeteo(), check_glofas_flood())
        status['OpenMeteo'] = om_ok
        status['GloFAS_FloodAPI'] = gf_ok

        glofas_key = getattr(settings, 'glofas_api_key', None)
        if glofas_key:
            status['GloFAS_EWDS_Configured'] = True  # Key present; download may be pending

        self._last_api_status = status
        return status
        
    def _is_data_stale(self) -> bool:
        """Check if any active data source has timed out (>2 hours)"""
        now = datetime.now(timezone.utc)
        stale_threshold = timedelta(hours=2)
        
        if self.last_openmeteo_update and (now - self.last_openmeteo_update) > stale_threshold:
            return True
            
        return False
        
    def _calculate_update_frequency(self) -> int:
        """Calculate updates per hour"""
        if self.check_interval:
            return int(3600 / self.check_interval)
        return 12


def _convert_glofas_nc_to_parquet(nc_path, parquet_path) -> None:
    """Convert the downloaded GloFAS NetCDF to a flat parquet suitable for risk engine lookup."""
    try:
        import netCDF4 as nc
        import numpy as np
        import pandas as pd
        from pathlib import Path

        FAR_NORTH_LOCALITIES = {
            "Kousséri":  (12.076, 15.031),
            "Maroua I":  (10.590, 14.316),
            "Yagoua":    (10.340, 15.237),
            "Maga":      (10.859, 15.004),
            "Pouss":     (11.068, 15.041),
            "Mora":      (11.047, 14.141),
            "Gobo":      (10.134, 14.965),
        }

        ds = nc.Dataset(str(nc_path))
        lats = ds.variables["latitude"][:]
        lons = ds.variables["longitude"][:]
        times = nc.num2date(ds.variables["time"][:], ds.variables["time"].units)
        dis = ds.variables["dis24"][:]  # shape: (time, ensemble, lat, lon) or (time, lat, lon)
        ds.close()

        rows = []
        for name, (locality_lat, locality_lon) in FAR_NORTH_LOCALITIES.items():
            ilat = int(np.argmin(np.abs(lats - locality_lat)))
            ilon = int(np.argmin(np.abs(lons - locality_lon)))
            for t_idx, t in enumerate(times):
                val = dis[t_idx]
                if val.ndim == 2:
                    q = float(np.ma.filled(val[ilat, ilon], np.nan))
                else:
                    # ensemble: take median
                    q = float(np.nanmedian(np.ma.filled(val[:, ilat, ilon], np.nan)))
                rows.append({"name": name, "date": t.strftime("%Y-%m-%d"), "discharge_m3s_ewds": q if not np.isnan(q) else None})

        df = pd.DataFrame(rows)
        df.to_parquet(str(parquet_path), index=False)
        import logging
        logging.getLogger(__name__).info(f"GloFAS EWDS parquet written → {parquet_path} ({len(df)} rows)")
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error(f"GloFAS NC→Parquet conversion failed: {exc}")