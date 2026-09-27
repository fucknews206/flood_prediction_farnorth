"""Far North region only (2015-2025) interim flood-risk engine.

Discharge & telemetry architecture (four tiers):
  1. PRIMARY (keyless, real-time): Open-Meteo Flood API (GloFAS v4, 0.05° grid).
     Called per-request via _fetch_river_discharge().  No API key needed.
  2. SUPPLEMENT (scheduled download): Copernicus EWDS GloFAS v4 ensemble forecast.
     Downloaded by DataCollectorAgent.download_glofas_ewds_forecast() when
     APP_GLOFAS_API_KEY is set.  Stored at:
       data_quality/farnorth_consolidation/glofas_ewds_latest.parquet
     Loaded here when available to augment or confirm the Open-Meteo reading.
  3. NOWCAST (keyless, real-time): RainViewer satellite radar reflectivity.
     It is displayed as a visual, recent radar layer only.  It has no
     point-value API in this integration and is not a model feature or gate.
  4. INUNDATION SATELLITE (keyless, public): NASA OPERA DSWx-S1 Sentinel-1 SAR.
     Called per-request via _fetch_opera_sar_inundation().  Queries NASA CMR
     for the latest Sentinel-1 Dynamic Surface Water Extent product.  It is
     supporting evidence only and cannot block a score from validated core
     hydrometeorological inputs.

This is a rules-based weighted formula, not trained ML.  Verified events are
used for historical context/validation only; they are never model-training
rows.
"""
from __future__ import annotations
import json, math, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import duckdb
import joblib
from farnorth_environment import EnvironmentalOrchestrator, OperaSurfaceWaterProvider, assess_model_eligibility, persist_observation_audit

def norm(v):
    import unicodedata, re
    v=unicodedata.normalize('NFKD',str(v)).encode('ascii','ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+','',v)

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'data_quality'/'farnorth_consolidation'
CATALOGUE=OUT/'canonical_flood_events_farnorth.csv'
SCORES=OUT/'farnorth_susceptibility_scores.csv'
DB=OUT/'farnorth_interim.duckdb'
RISK_CACHE=OUT/'farnorth_locality_risk_cache.parquet'
OPERATIONAL_MODEL=OUT/'farnorth_operational_model.joblib'
EXPLORATORY_MODEL=OUT/'farnorth_exploratory_rf_basin.joblib'
PARTIAL_LIVE_MODEL=OUT/'farnorth_partial_live_model.joblib'
EWDS_DISCHARGE_PARQUET=OUT/'glofas_ewds_latest.parquet'  # Written by DataCollectorAgent when EWDS key is set
MODEL_TYPE='Operational Hybrid Ensemble (Calibrated HistGradientBoosting ML + Terrain Susceptibility & Hydrological Thresholds)'

_OPERATIONAL_MODEL_CACHE = None
_PARTIAL_LIVE_MODEL_CACHE = None

def _operational_model():
    """Load the calibrated operational ML model once per worker process."""
    global _OPERATIONAL_MODEL_CACHE
    if _OPERATIONAL_MODEL_CACHE is None and OPERATIONAL_MODEL.exists():
        try:
            _OPERATIONAL_MODEL_CACHE = joblib.load(OPERATIONAL_MODEL)
        except Exception:
            _OPERATIONAL_MODEL_CACHE = None
    return _OPERATIONAL_MODEL_CACHE


def _partial_live_model():
    """Load the separately trained profile that excludes upstream windows only."""
    global _PARTIAL_LIVE_MODEL_CACHE
    if _PARTIAL_LIVE_MODEL_CACHE is None and PARTIAL_LIVE_MODEL.exists():
        try:
            _PARTIAL_LIVE_MODEL_CACHE = joblib.load(PARTIAL_LIVE_MODEL)
        except Exception:
            _PARTIAL_LIVE_MODEL_CACHE = None
    return _PARTIAL_LIVE_MODEL_CACHE

_CATALOGUE_CACHE = None
_SCORES_CACHE = None
_HYDRO_CACHE = None
_RUNOFF_CACHE = None
_RUNOFF_DAILY_CACHE = None

def _catalogue():
    """Load the event catalogue once per worker process."""
    global _CATALOGUE_CACHE
    if _CATALOGUE_CACHE is None:
        _CATALOGUE_CACHE = pd.read_csv(CATALOGUE)
    return _CATALOGUE_CACHE
def _scores():
    """Load static susceptibility scores once per worker process."""
    global _SCORES_CACHE
    if _SCORES_CACHE is None:
        _SCORES_CACHE = pd.read_csv(SCORES).drop_duplicates('name').copy()
    return _SCORES_CACHE
_CACHE=None
_FORECAST_CACHE = {}
_FORECAST_CACHE_TTL_SECONDS = 300
_DIVISION_RISK_CACHE = {}

# The environmental subset is the authoritative list of model-covered towns.
# Division labels are kept explicit because the upstream gazetteer contains
# many village rows without administrative division metadata.
_COVERED_DIVISIONS = {
    'Logone-et-Chari': {'Darak','Blangoua','Hilé - Alifa','Kousséri','Zina','Makary'},
    'Mayo-Danay': {'Yagoua','Gobo','Guémé','Doukoula','Pouss','Kai-Kai','Maga','Vélé','Djarèngol','Guéré','Wina','Tchatibali'},
    'Diamaré': {'Salak','Maroua I','Maroua II','Makabaye','Harde','Gaklé'},
    'Mayo-Sava': {'Mora','Kolofata'},
    'Mayo-Tsanaga': {'Mozogo','Mokolo','Hina'},
    'Mayo-Kani': {'Moulvoudaye','Kaélé','Dougui','Kar-Hay','Datchéka'},
}
_DIVISION_ESTIMATED_TOWNS = {'Logone-et-Chari': 10, 'Mayo-Danay': 15, 'Diamaré': 9, 'Mayo-Sava': 4, 'Mayo-Tsanaga': 8, 'Mayo-Kani': 5}
def _risk_cache():
    global _CACHE
    if _CACHE is None:
        try:
            _CACHE=pd.read_parquet(RISK_CACHE)
        except (ImportError, ValueError):
            # CSV fallback keeps the API usable in lightweight deployments
            # where optional parquet engines are not installed.
            _CACHE=pd.read_csv(RISK_CACHE.with_suffix('.csv'))
        _CACHE=_CACHE.drop_duplicates('name').set_index('name', drop=False)
    return _CACHE

def _hydrology_cache():
    """Static HydroRIVERS basin metrics and latest ERA5 runoff, loaded once."""
    global _HYDRO_CACHE, _RUNOFF_CACHE
    if _HYDRO_CACHE is None:
        path = OUT/'farnorth_locality_hydrology_static.csv'
        try:
            _HYDRO_CACHE = pd.read_csv(path).drop_duplicates('name').set_index('name', drop=False)
        except Exception:
            _HYDRO_CACHE = pd.DataFrame()
    if _RUNOFF_CACHE is None:
        path = OUT/'farnorth_runoff_summary.parquet'
        try:
            _RUNOFF_CACHE = _read_parquet(path).drop_duplicates('name').set_index('name', drop=False) if path.exists() else pd.DataFrame()
        except Exception:
            _RUNOFF_CACHE = pd.DataFrame()
    return _HYDRO_CACHE, _RUNOFF_CACHE


def _historical_runoff_for_locality(name, reference_date=None):
    """Return the locality's real ERA5-Land daily runoff on/before a date.

    The source is historical/reanalysis context, not a pretend current value.
    Location matching is the project's existing name-to-ERA5 grid association
    used to materialise ``farnorth_locality_runoff_daily.parquet``.
    """
    global _RUNOFF_DAILY_CACHE
    if _RUNOFF_DAILY_CACHE is None:
        path = OUT / 'farnorth_locality_runoff_daily.parquet'
        try:
            frame = _read_parquet(path, columns=['name', 'date', 'runoff_mm', 'sub_surface_runoff_mm'])
            frame['date'] = pd.to_datetime(frame['date'], errors='coerce').dt.date
            _RUNOFF_DAILY_CACHE = frame.dropna(subset=['name', 'date']).sort_values(['name', 'date'])
        except Exception:
            _RUNOFF_DAILY_CACHE = pd.DataFrame(columns=['name', 'date', 'runoff_mm', 'sub_surface_runoff_mm'])
    target = pd.Timestamp(reference_date or datetime.now(timezone.utc).date()).date()
    rows = _RUNOFF_DAILY_CACHE[(_RUNOFF_DAILY_CACHE['name'] == name) & (_RUNOFF_DAILY_CACHE['date'] <= target)]
    if rows.empty:
        return None
    item = rows.iloc[-1]
    value = item.get('runoff_mm')
    if pd.isna(value) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or float(value) < 0:
        return None
    return {
        'value': float(value),
        'date': item['date'].isoformat(),
        'sub_surface_runoff_mm': (float(item['sub_surface_runoff_mm']) if pd.notna(item.get('sub_surface_runoff_mm')) else None),
        'dataset': 'farnorth_locality_runoff_daily.parquet',
        'source_type': 'historical_reanalysis',
        'unit': 'mm',
    }

def _read_parquet(path, columns=None):
    """Read parquet with a DuckDB fallback for the API virtualenv."""
    try:
        return pd.read_parquet(path, columns=columns)
    except (ImportError, ValueError):
        cols = '*' if columns is None else ','.join('"%s"' % c for c in columns)
        return duckdb.connect().execute(f"SELECT {cols} FROM read_parquet(?)", [str(path)]).df()
def _resolve(q):
    d=_scores(); q=str(q)
    if ',' in q:
        try:
            lat,lon=[float(x.strip()) for x in q.split(',',1)]
            i=((d.lat-lat)**2+(d.lon-lon)**2).idxmin(); return d.loc[i]
        except ValueError: pass
    nq=norm(q)
    hit=d[d.name.map(norm).eq(nq)]
    if hit.empty: hit=d[d.name.map(norm).str.contains(nq,regex=False)]
    if hit.empty: raise ValueError(f'Unknown Far North locality: {q}')
    return hit.iloc[0]

def _robust_urlopen(req_or_url, timeout=15, retries=3, backoff=0.5):
    """Fetch URL with retries on transient connection errors, handshake timeouts, and socket drops."""
    last_err = None
    for attempt in range(retries):
        try:
            req = req_or_url
            if isinstance(req, str):
                req = urllib.request.Request(req, headers={'User-Agent': 'AquaGuard-Cameroon/1.0'})
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read()
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(backoff * (attempt + 1))
    raise last_err

def _forecast(lat,lon,p90=None,soil_median=None):
    cache_key=(round(float(lat),5), round(float(lon),5), round(float(p90),5) if p90 is not None else None, round(float(soil_median),5) if soil_median is not None else None)
    cached=_FORECAST_CACHE.get(cache_key)
    if cached and time.time() - cached[0] < _FORECAST_CACHE_TTL_SECONDS:
        return cached[1]
    # ``runoff`` is the provider-supported total runoff variable.  It is
    # requested with the rain and soil fields so one live weather request
    # supplies all three signals for a locality.
    params=urllib.parse.urlencode({'latitude':lat,'longitude':lon,'hourly':'precipitation,soil_moisture_0_to_7cm,runoff','past_days':1,'forecast_days':3,'timezone':'UTC'})
    url='https://api.open-meteo.com/v1/forecast?'+params
    try:
        raw_bytes = _robust_urlopen(url, timeout=15, retries=3)
        raw = json.loads(raw_bytes.decode('utf-8'))
        h=raw.get('hourly',{}); p=h.get('precipitation',[]); s=h.get('soil_moisture_0_to_7cm',[]); runoff=h.get('runoff',[]); times=h.get('time',[])
        # Aggregate to 6-hour windows and apply rainfall/soil threshold logic.
        out=[]
        for i in range(0,len(times),6):
            pp=p[i:i+6]; ss=s[i:i+6]; out.append({'time':times[i],'precipitation_6h_mm':round(sum(x or 0 for x in pp),2),'soil_moisture_mean':round(sum(x for x in ss if x is not None)/max(1,len([x for x in ss if x is not None])),4),'threshold_signal':None})
        # Use a rolling 72-hour precipitation accumulation for each forecast point.
        for i,item in enumerate(out):
            item['rainfall_3d_forecast_mm']=round(sum(x['precipitation_6h_mm'] for x in out[max(0,i-11):i+1]),2)
            item['threshold_signal']=int(p90 is not None and soil_median is not None and item['rainfall_3d_forecast_mm']>p90 and item['soil_moisture_mean']>soil_median)
        live_runoff = next((float(v) for v in reversed(runoff) if v is not None), None)
        result={
            'source':'Open-Meteo Weather API',
            'fetched_at':datetime.now(timezone.utc).isoformat(),
            'trajectory':out,
            'runoff_mm':live_runoff,
            'runoff_status':'available' if live_runoff is not None else 'unavailable',
            'runoff_source':'Open-Meteo weather-model total runoff',
        }
        _FORECAST_CACHE[cache_key]=(time.time(), result)
        return result
    except Exception as e: return {'source':'Open-Meteo Weather API','error':str(e),'trajectory':[], 'runoff_mm':None, 'runoff_status':'unavailable', 'runoff_source':'Open-Meteo weather-model total runoff'}

_DISCHARGE_CACHE = {}
_RADAR_CACHE: dict = {}
_RADAR_CACHE_TTL_SECONDS = 120  # Radar frames update every ~2 min; cache for 2 min

def _fetch_radar_nowcast(lat: float, lon: float) -> dict:
    """Report RainViewer map-frame availability, never a numerical feature.

    The former code derived a pseudo-intensity from PNG alpha values. Tile
    transparency is a rendering property, not rainfall/radar measurement, so
    it is deliberately not downloaded or converted to a number.
    """
    cache_key = (round(float(lat), 3), round(float(lon), 3))
    cached = _RADAR_CACHE.get(cache_key)
    if cached and time.time() - cached[0] < _RADAR_CACHE_TTL_SECONDS:
        return cached[1]
    try:
        # Step 1: get latest available radar timestamp from RainViewer manifest
        manifest_url = 'https://api.rainviewer.com/public/weather-maps.json'
        manifest_bytes = _robust_urlopen(manifest_url, timeout=10, retries=2)
        manifest = json.loads(manifest_bytes.decode('utf-8'))
        # Navigate: radar -> past -> list of {time, ...}
        radar_past = manifest.get('radar', {}).get('past', [])
        latest_frame = radar_past[-1] if radar_past else None
        latest_ts = int(latest_frame['time']) if latest_frame else None

        if latest_ts is None:
            raise RuntimeError('RainViewer returned no radar frames')
        result = {
            'source': 'RainViewer radar visualization',
            'fetched_at': datetime.now(timezone.utc).isoformat(),
            'latest_frame_ts': latest_ts,
            'radar_mmhr': None,
            'radar_intensity': None,
            'storm_active': None,
            'status': 'REAL_RECENT_BUT_NOT_CURRENT',
            'quality': 'VISUAL_ONLY',
            'frame_path': latest_frame.get('path'),
        }
        _RADAR_CACHE[cache_key] = (time.time(), result)
        return result
    except Exception as e:
        return {
            'source': 'RainViewer radar visualization',
            'fetched_at': datetime.now(timezone.utc).isoformat(),
            'latest_frame_ts': None,
            'radar_mmhr': None,
            'radar_intensity': None,
            'storm_active': None,
            'status': 'PROVIDER_ERROR',
            'quality': 'UNAVAILABLE',
            'error': str(e),
        }


def _lat_lon_to_tile_z6(lat: float, lon: float) -> str:
    """Return '{x}/{y}' tile coordinates at zoom level 6 for a lat/lon."""
    import math
    z = 6
    lat_r = math.radians(float(lat))
    x = int((float(lon) + 180.0) / 360.0 * (2 ** z))
    y = int((1.0 - math.log(math.tan(lat_r) + 1.0 / math.cos(lat_r)) / math.pi) / 2.0 * (2 ** z))
    return f'{x}/{y}'


_OPERA_SAR_CACHE: dict = {}
_OPERA_SAR_CACHE_TTL_SECONDS = 14400  # SAR acquisitions occur every few days; cache for 4 hours


def _fetch_opera_sar_inundation(lat: float, lon: float) -> dict:
    """Fetch latest NASA OPERA DSWx-S1 Sentinel-1 SAR surface water extent.

    OPERA DSWx-S1 (Dynamic Surface Water Extent from Sentinel-1 SAR) penetrates
    clouds and heavy precipitation canopies via C-band radar backscatter to detect
    standing surface water and active inundation.

    Workflow:
      1. Query NASA Common Metadata Repository (CMR) Granules API for the latest
         `OPERA_L3_DSWX-S1_V1` granule covering the locality's bounding box.
      2. If an acquisition exists, inspect the public browse PNG palette
         (water pixels = color 1/2/3, nodata = 255, dry land = 0).
      3. Compute `sar_inundation_fraction` (0.0 to 1.0) and flag `water_detected`.

    Returns dict with keys:
      source, status, fetched_at, acquisition_date, granule_id,
      sar_inundation_fraction, water_detected, water_percentage.
    """
    cache_key = (round(float(lat), 3), round(float(lon), 3))
    cached = _OPERA_SAR_CACHE.get(cache_key)
    if cached and time.time() - cached[0] < _OPERA_SAR_CACHE_TTL_SECONDS:
        return cached[1]

    try:
        bbox = f"{lon - 0.35:.3f},{lat - 0.35:.3f},{lon + 0.35:.3f},{lat + 0.35:.3f}"
        params = urllib.parse.urlencode({
            'short_name': 'OPERA_L3_DSWX-S1_V1',
            'bounding_box': bbox,
            'sort_key': '-start_date',
            'page_size': 3
        })
        url = f"https://cmr.earthdata.nasa.gov/search/granules.json?{params}"
        raw_bytes = _robust_urlopen(url, timeout=15, retries=3)
        data = json.loads(raw_bytes.decode('utf-8'))

        entries = data.get('feed', {}).get('entry', [])
        if not entries:
            # Widen bounding box slightly (±0.65 deg) to capture adjacent Sentinel-1 orbit swath
            bbox_wider = f"{lon - 0.65:.3f},{lat - 0.65:.3f},{lon + 0.65:.3f},{lat + 0.65:.3f}"
            params_wider = urllib.parse.urlencode({
                'short_name': 'OPERA_L3_DSWX-S1_V1',
                'bounding_box': bbox_wider,
                'sort_key': '-start_date',
                'page_size': 3
            })
            url_wider = f"https://cmr.earthdata.nasa.gov/search/granules.json?{params_wider}"
            raw_wider = _robust_urlopen(url_wider, timeout=15, retries=3)
            data = json.loads(raw_wider.decode('utf-8'))
            entries = data.get('feed', {}).get('entry', [])

        if not entries:
            res = {
                'source': 'NASA OPERA DSWx-S1 (Sentinel-1 SAR)',
                'status': 'unavailable',
                'fetched_at': datetime.now(timezone.utc).isoformat(),
                'acquisition_date': None,
                'granule_id': None,
                'sar_inundation_fraction': 0.0,
                'water_detected': False,
                'water_percentage': 0.0,
                'message': 'No recent Sentinel-1 SAR pass in CMR for coordinates',
            }
            _OPERA_SAR_CACHE[cache_key] = (time.time(), res)
            return res

        granule = entries[0]
        title = granule.get('title')
        time_start = granule.get('time_start')

        # Locate browse PNG in links
        browse_url = None
        for link in granule.get('links', []):
            href = link.get('href', '')
            if ('BROWSE.png' in href or 'browse' in href.lower() or href.endswith('.png')) and not href.endswith('.md5') and not href.startswith('s3:'):
                browse_url = href
                break

        # A catalog entry alone is not evidence. The predictor requires a
        # readable DSWx browse raster so NASA's status cannot silently become
        # "available" with a synthetic zero-inundation value.
        if not browse_url:
            raise RuntimeError('Latest NASA OPERA granule has no usable browse raster')
        import io
        from PIL import Image
        im_data = _robust_urlopen(browse_url, timeout=15, retries=3)
        im = Image.open(io.BytesIO(im_data))
        colors = dict((idx, count) for count, idx in im.getcolors(maxcolors=10000))
        # 1 = open water, 2/3 = partial water, 255 = nodata/fill
        water_px = colors.get(1, 0) + colors.get(2, 0) + colors.get(3, 0)
        nodata_px = colors.get(255, 0)
        valid_px = (im.size[0] * im.size[1]) - nodata_px
        if valid_px <= 0:
            raise RuntimeError('NASA OPERA browse raster contains no valid pixels')
        sar_fraction = round(water_px / valid_px, 4)

        res = {
            'source': 'NASA OPERA DSWx-S1 (Sentinel-1 SAR)',
            'status': 'available',
            'fetched_at': datetime.now(timezone.utc).isoformat(),
            'acquisition_date': time_start,
            'granule_id': title,
            'sar_inundation_fraction': sar_fraction,
            'water_detected': sar_fraction >= 0.02,
            'water_percentage': round(sar_fraction * 100.0, 2),
        }
        _OPERA_SAR_CACHE[cache_key] = (time.time(), res)
        return res
    except Exception as e:
        return {
            'source': 'NASA OPERA DSWx-S1 (Sentinel-1 SAR)',
            'status': 'unavailable',
            'fetched_at': datetime.now(timezone.utc).isoformat(),
            'acquisition_date': None,
            'granule_id': None,
            'sar_inundation_fraction': 0.0,
            'water_detected': False,
            'water_percentage': 0.0,
            'error': str(e),
        }


def _fetch_river_discharge(lat, lon, past_days=14, forecast_days=14):
    """Query Open-Meteo Flood API (GloFAS model) for live river discharge in m3/s."""
    if not (-90 <= float(lat) <= 90 and -180 <= float(lon) <= 180):
        return {'status': 'INVALID_VALUE', 'source': 'Open-Meteo GloFAS Flood API', 'latest': None, 'by_date': {}, 'error': 'Invalid latitude/longitude'}
    cache_key = (round(float(lat), 3), round(float(lon), 3))
    cached = _DISCHARGE_CACHE.get(cache_key)
    if cached and time.time() - cached[0] < _FORECAST_CACHE_TTL_SECONDS:
        return cached[1]
    params = urllib.parse.urlencode({
        'latitude': lat,
        'longitude': lon,
        'daily': 'river_discharge',
        'past_days': min(14, int(past_days)),
        'forecast_days': min(14, int(forecast_days)),
    })
    url = 'https://flood-api.open-meteo.com/v1/flood?' + params
    try:
        raw_bytes = _robust_urlopen(url, timeout=15, retries=3)
        raw = json.loads(raw_bytes.decode('utf-8'))
        d = raw.get('daily', {})
        times = d.get('time', [])
        vals = d.get('river_discharge', [])
        by_date = {str(t): float(v) for t, v in zip(times, vals) if isinstance(v, (int, float)) and math.isfinite(float(v)) and float(v) >= 0}
        today = datetime.now(timezone.utc).date().isoformat()
        # A genuine zero discharge is valid.  Do not use truthiness here: doing
        # so previously replaced a zero for today with an unrelated future date.
        latest = by_date[today] if today in by_date else (list(by_date.values())[-1] if by_date else None)
        result = {
            'status': 'REAL_CURRENT' if by_date else 'NO_DATA',
            'source': 'Open-Meteo GloFAS Flood API',
            'latest': latest,
            'by_date': by_date,
            'fetched_at': datetime.now(timezone.utc).isoformat(),
            'actual_latitude': raw.get('latitude'),
            'actual_longitude': raw.get('longitude'),
        }
        _DISCHARGE_CACHE[cache_key] = (time.time(), result)
        return result
    except Exception as e:
        return {'status': 'PROVIDER_ERROR', 'source': 'Open-Meteo GloFAS Flood API', 'latest': None, 'by_date': {}, 'error': str(e)}


class RequiredLiveDataUnavailable(RuntimeError):
    """Raised when a prediction would be based on incomplete live inputs."""


def _require_live_prediction_inputs(weather: dict, discharge: dict, nasa_sar: dict) -> dict:
    """Return provider provenance or stop scoring until all required inputs exist."""
    providers = {
        'openmeteo': {
            'source': weather.get('source', 'Open-Meteo Weather API'),
            'status': 'available' if weather.get('trajectory') else 'unavailable',
            'fetched_at': weather.get('fetched_at'),
            'error': weather.get('error'),
        },
        'glofas': {
            'source': discharge.get('source', 'Open-Meteo GloFAS Flood API'),
            'status': discharge.get('status', 'unavailable'),
            'fetched_at': discharge.get('fetched_at'),
            'error': discharge.get('error'),
        },
        'nasa_opera': {
            'source': nasa_sar.get('source', 'NASA OPERA DSWx-S1'),
            'status': nasa_sar.get('status', 'unavailable'),
            'fetched_at': nasa_sar.get('fetched_at'),
            'acquisition_date': nasa_sar.get('acquisition_date'),
            'error': nasa_sar.get('error') or nasa_sar.get('message'),
        },
    }
    unavailable = [name for name, provider in providers.items() if provider['status'] != 'available']
    status = {'ready': not unavailable, 'providers': providers, 'unavailable': unavailable}
    if unavailable:
        reasons = '; '.join(
            f"{name}: {providers[name].get('error') or 'no current data returned'}"
            for name in unavailable
        )
        raise RequiredLiveDataUnavailable(
            'Prediction withheld until Open-Meteo, GloFAS, and NASA OPERA are all available. ' + reasons
        )
    return status

_BASIN_TOPOLOGY=None
_BASIN_FORECAST_CACHE={}
def _upstream_basin_sets():
    """Return locality -> traced upstream basin IDs and basin centroids."""
    global _BASIN_TOPOLOGY
    import geopandas as gpd
    shp=ROOT.parent/'HydroBasins-datasets'/'hybas_af_lev01-12_v1c'/'hybas_af_lev06_v1c.shp'
    if _BASIN_TOPOLOGY is None:
        d=gpd.read_file(shp,columns=['HYBAS_ID','NEXT_DOWN','geometry'])
        down=dict(zip(d.HYBAS_ID.astype(int),d.NEXT_DOWN.astype(int)))
        cent={int(r.HYBAS_ID):(float(r.geometry.centroid.y),float(r.geometry.centroid.x)) for _,r in d.iterrows()}
        _BASIN_TOPOLOGY=(down,cent)
    down,cent=_BASIN_TOPOLOGY
    lookup=_read_parquet(OUT/'farnorth_locality_environment_lookup.parquet')
    def trace(target):
        seen={target}; frontier={target}
        for _ in range(5):
            nxt={k for k,v in down.items() if v in frontier}-seen
            if not nxt: break
            seen.update(nxt); frontier=nxt
        return seen
    sets={}
    for _,r in lookup.dropna(subset=['basin_id']).drop_duplicates('name').iterrows():
        sets[str(r['name'])]=trace(int(r['basin_id']))
    # A few newly added localities may not yet be present in the lookup's
    # basin_id column. Resolve them spatially from the locality subset once;
    # this does not alter the confirmed topology traversal.
    try:
        missing=[n for n in _read_parquet(OUT/'locality_subsets'/'chirps_34.parquet')['name'].dropna().unique() if n not in sets]
        if missing:
            pts=_read_parquet(OUT/'locality_subsets'/'chirps_34.parquet')
            pts=pts[pts['name'].isin(missing)].drop_duplicates('name')
            pg=gpd.GeoDataFrame(pts,geometry=gpd.points_from_xy(pts.lon,pts.lat),crs='EPSG:4326')
            poly=gpd.read_file(shp,columns=['HYBAS_ID','geometry']).to_crs('EPSG:4326')
            joined=gpd.sjoin(pg,poly,how='left',predicate='within')
            if joined['HYBAS_ID'].isna().any():
                near=gpd.sjoin_nearest(pg[joined['HYBAS_ID'].isna()],poly,how='left',distance_col='_dist')
                joined.loc[joined['HYBAS_ID'].isna(),'HYBAS_ID']=near['HYBAS_ID'].to_numpy()
            for _,r in joined.dropna(subset=['HYBAS_ID']).iterrows(): sets[str(r['name'])]=trace(int(r['HYBAS_ID']))
    except Exception:
        pass
    return sets,cent

def _basin_forecast_daily(issue_date, days=6, required_ids=None):
    """Fetch/cache one Open-Meteo forecast per unique upstream basin centroid."""
    key=f'{issue_date}_{days}_'+(','.join(map(str,sorted(required_ids))) if required_ids is not None else 'all')
    if key in _BASIN_FORECAST_CACHE: return _BASIN_FORECAST_CACHE[key]
    cache_path=OUT/f'basin_forecast_openmeteo_v2_{issue_date}_{days}d.json'
    if cache_path.exists():
        try:
            value=json.loads(cache_path.read_text())
            if required_ids is not None or len(value.get('basin_daily',{})) >= 10:
                _BASIN_FORECAST_CACHE[key]=value; return value
        except Exception: pass
    sets,cent=_upstream_basin_sets(); ids=sorted({int(b) for s in sets.values() for b in s if int(b) in cent}) if required_ids is None else sorted({int(b) for b in required_ids if int(b) in cent})
    result={'basin_daily':{},'centroids':{},'queried_count':0,'issue_date':str(issue_date)}
    # Open-Meteo supports multiple coordinate pairs in one request.  Batch
    # calls keep the first cache build small and avoid one HTTP request per
    # basin while retaining one result per basin.
    for start in range(0,len(ids),10):
        batch=ids[start:start+10]; lats=','.join(str(cent[b][0]) for b in batch); lons=','.join(str(cent[b][1]) for b in batch)
        params=urllib.parse.urlencode({'latitude':lats,'longitude':lons,'hourly':'precipitation','forecast_days':min(16,int(days)),'timezone':'UTC'})
        try:
            raw_bytes = _robust_urlopen('https://api.open-meteo.com/v1/forecast?'+params, timeout=20, retries=2)
            raw = json.loads(raw_bytes.decode('utf-8'))
            payloads=raw if isinstance(raw,list) else [raw]
            for bid,payload in zip(batch,payloads):
                vals={}
                for t,p in zip(payload.get('hourly',{}).get('time',[]),payload.get('hourly',{}).get('precipitation',[])):
                    day=str(t)[:10]; vals[day]=vals.get(day,0.0)+float(p or 0)
                result['basin_daily'][str(bid)]=vals; result['centroids'][str(bid)]={'lat':cent[bid][0],'lon':cent[bid][1]}; result['queried_count']+=1
        except Exception as exc:
            for bid in batch: result['basin_daily'][str(bid)]={}; result['centroids'][str(bid)]={'lat':cent[bid][0],'lon':cent[bid][1],'error':str(exc)}
        time.sleep(0.2)
    cache_path.write_text(json.dumps(result)); _BASIN_FORECAST_CACHE[key]=result; return result

def get_forecasted_features(locality_name_or_lat_lon, target_date=None, days=5):
    """Build the forward feature bundle used by the forecast UI.

    Open-Meteo supplies the local precipitation/soil forecast.  A GloFAS
    *forecast* file is deliberately required before scoring the retrained RF:
    historical GloFAS files cannot be substituted for future discharge.
    Until that product is downloaded, ``classifier_probability`` is null and
    the independently computed Option-B threshold signal remains available.
    """
    row=_resolve(locality_name_or_lat_lon); name=str(row['name'])
    cache=_risk_cache().loc[name]; lat,lon=float(row.lat),float(row.lon)
    p90=float(cache.rainfall_3d_p90); month=pd.Timestamp(target_date or datetime.now(timezone.utc).date()).month
    med=cache.get(f'soil_median_m{month:02d}')
    # Request one extra day because the provider may include the current day;
    # the GloFAS valid-time intersection below then yields the next N days.
    params=urllib.parse.urlencode({'latitude':lat,'longitude':lon,'hourly':'precipitation,soil_moisture_0_to_7cm','forecast_days':min(16,int(days)+1),'timezone':'UTC'})
    url='https://api.open-meteo.com/v1/forecast?'+params
    raw_bytes = _robust_urlopen(url, timeout=15, retries=3)
    raw = json.loads(raw_bytes.decode('utf-8'))
    hourly=raw.get('hourly',{}); times=hourly.get('time',[]); precip=hourly.get('precipitation',[]); soil=hourly.get('soil_moisture_0_to_7cm',[])
    issue=raw.get('generationtime_ms')
    # Report every provider independently.  A missed SAR pass or delayed
    # discharge update must not suppress a valid Open-Meteo rainfall forecast.
    # The UI can still disclose which parts of the prediction are unavailable.
    weather_status = {
        'source': 'Open-Meteo Weather API',
        'trajectory': times,
        'fetched_at': datetime.now(timezone.utc).isoformat(),
        'error': None if times else 'Open-Meteo returned no hourly forecast',
    }
    live_disch = _fetch_river_discharge(lat, lon, past_days=10, forecast_days=int(days)+2)
    # OPERA discovery/browse imagery is not a numerical locality observation.
    # Keep its explicitly unavailable state instead of deriving a percentage
    # from a PNG or an unvalidated scene selection.
    sar_observation = OperaSurfaceWaterProvider().get(lat, lon)
    provider_status = {
        'ready': bool(weather_status['trajectory']),
        'providers': {
            'openmeteo': {'source': weather_status['source'], 'status': 'available' if weather_status['trajectory'] else 'unavailable', 'fetched_at': weather_status['fetched_at'], 'error': weather_status['error']},
            'glofas': {'source': live_disch.get('source'), 'status': live_disch.get('status', 'NO_DATA'), 'fetched_at': live_disch.get('fetched_at'), 'error': live_disch.get('error')},
            'nasa_opera': {'source': sar_observation.provider_product, 'status': sar_observation.status, 'fetched_at': sar_observation.retrieved_at, 'error': sar_observation.error_message},
        },
    }
    provider_status['unavailable'] = [name for name, item in provider_status['providers'].items() if item['status'] not in {'available', 'REAL_CURRENT', 'REAL_FORECAST', 'REAL_HISTORICAL'}]
    daily={}
    for t,p,s in zip(times,precip,soil):
        day=str(t)[:10]; z=daily.setdefault(day,{'precipitation_mm':0.0,'soil':[], 'precipitation_missing':False})
        if p is None:
            z['precipitation_missing']=True
        elif isinstance(p, (int, float)) and float(p) >= 0:
            z['precipitation_mm']+=float(p)
        else:
            z['precipitation_missing']=True
        z['soil'].append(s)
    ordered=sorted(daily); out=[]; rolling=[]
    for day in ordered:
        rolling.append(None if daily[day]['precipitation_missing'] else daily[day]['precipitation_mm']); soilvals=[x for x in daily[day]['soil'] if isinstance(x, (int, float))]
        rain3=sum(x for x in rolling[-3:] if x is not None) if len(rolling[-3:]) == 3 and all(x is not None for x in rolling[-3:]) else None
        soil_mean=(sum(soilvals)/len(soilvals)) if soilvals else None
        flag=int(rain3 is not None and soil_mean is not None and rain3>p90 and med is not None and soil_mean>float(med))
        out.append({'date':day,'local_rainfall_1d_mm':round(rolling[-1],2) if rolling[-1] is not None else None,'local_rainfall_3d_mm':round(rain3,2) if rain3 is not None else None,'soil_moisture':round(soil_mean,4) if soil_mean is not None else None,'basin_rainfall_7d_mm':None,'basin_rainfall_14d_mm':None,'basin_rainfall_21d_mm':None,'basin_rainfall_30d_mm':None,'glofas_discharge_m3s':None,'option_b_threshold_flag':flag if rain3 is not None and soil_mean is not None else None,'option_b_risk_level':'ELEVATED' if flag else ('BASELINE' if rain3 is not None and soil_mean is not None else 'UNAVAILABLE'),'classifier_probability':None,'method_disagreement':None})
    # GloFAS was verified above; use that same live response for the feature set.
    discharge = dict(live_disch.get('by_date', {}))
    glofas_ok = bool(discharge)
    forecast_reference_date = datetime.now(timezone.utc).date()

    historical_discharge={}
    hist_path=OUT/'locality_subsets'/'glofas_34.parquet'
    if hist_path.exists():
        hd=_read_parquet(hist_path); hd['date']=pd.to_datetime(hd['date']).dt.strftime('%Y-%m-%d')
        hname='locality' if 'locality' in hd.columns else 'name'; hval='discharge_m3s' if 'discharge_m3s' in hd.columns else 'dis24'
        if hval in hd.columns:
            historical_discharge={str(r.date):float(getattr(r,hval)) for r in hd[hd[hname]==name].itertuples() if pd.notna(getattr(r,hval))}
    # The exploratory model was trained on CHIRPS/ERA5/historical GloFAS.  The
    # live path uses different sources and previously fabricated lag values, so
    # its probability is withheld until production-source compatibility is
    # validated.  A missing prediction is safer than a plausible-looking one.
    clf=None; model_features=[]; static_l={}
    out=out[:int(days)]
    rains=[float(x['local_rainfall_1d_mm']) if x['local_rainfall_1d_mm'] is not None else None for x in out]
    basin_daily_payload=None; upstream_ids=set(); basin_query_count=0
    try:
        ref_for_basin=str(forecast_reference_date or pd.Timestamp(out[0]['date']).date())
        basin_sets,_centroids=_upstream_basin_sets(); upstream_ids=set(basin_sets.get(name,set()))
        basin_daily_payload=_basin_forecast_daily(ref_for_basin, max(6, int(days)+1), upstream_ids)
        basin_query_count=int(basin_daily_payload.get('queried_count',0))
    except Exception:
        basin_daily_payload=None
    basin_rains=[]
    for item in out:
        vals=[basin_daily_payload.get('basin_daily',{}).get(str(b),{}).get(item['date']) for b in upstream_ids] if basin_daily_payload else []
        vals=[float(v) for v in vals if v is not None]
        basin_rains.append(sum(vals)/len(vals) if vals else item['local_rainfall_1d_mm'])
    last_known_discharge=list(discharge.values())[-1] if discharge else None
    for i,item in enumerate(out):
        item['glofas_discharge_m3s']=discharge.get(item['date']) if (glofas_ok and item['date'] in discharge) else None
        # Production features require genuine historical lag dates.  A current
        # or forecast discharge must never be copied into a lagged column.
        q=item['glofas_discharge_m3s']
        lag_values={}; used_forecast_fallback=False
        if q is not None:
            for lag in (1,3,7):
                lag_date=(pd.Timestamp(item['date'])-pd.Timedelta(days=lag)).strftime('%Y-%m-%d')
                lag_values[lag]=historical_discharge.get(lag_date)
                item[f'glofas_discharge_lag{lag}']=lag_values[lag]
        past_missing=any(v is None for v in lag_values.values()) if lag_values else True
        item['discharge_lag_fallback']=bool(used_forecast_fallback)
        item['discharge_lag_historical_unavailable']=bool(q is not None and past_missing and not used_forecast_fallback)
        item['discharge_lag_note']='Required historical GloFAS lag is unavailable; quantitative score is withheld for this day.' if item['discharge_lag_historical_unavailable'] else None
        item['discharge_lag_source']='historical GloFAS' if not item['discharge_lag_historical_unavailable'] else 'historical unavailable'
        vals={window:(sum(v for v in basin_rains[max(0,i-window+1):i+1] if v is not None) if len(basin_rains[max(0,i-window+1):i+1]) == window and all(v is not None for v in basin_rains[max(0,i-window+1):i+1]) else None) for window in (3,7,14,21,30)}
        item.update({f'basin_rainfall_{w}d_mm':round(v,2) if v is not None else None for w,v in vals.items()})
        if clf is not None and q is not None and all(item.get(f'glofas_discharge_lag{lag}') is not None for lag in (1,3,7)):
            frame={
                'rainfall_1d':rains[i], 'rainfall_3d':vals[3], 'rainfall_7d':vals[7],
                'rainfall_14d':vals[14], 'rainfall_anomaly':vals[7]-p90,
                'swvl1':item['soil_moisture'], 'discharge_m3s':q,
                'discharge_lag1':item['glofas_discharge_lag1'], 'discharge_lag3':item['glofas_discharge_lag3'], 'discharge_lag7':item['glofas_discharge_lag7'],
                **static_l, 'basin_rainfall_3d':vals[3], 'basin_rainfall_7d':vals[7],
                'basin_rainfall_14d':vals[14], 'basin_rainfall_21d':vals[21], 'basin_rainfall_30d':vals[30]}
            if all(k in frame and frame[k] is not None for k in model_features):
                item['classifier_probability']=round(float(clf.predict_proba(pd.DataFrame([frame])[model_features])[0,1]),4)
                item['method_disagreement']=bool(bool(item['option_b_threshold_flag']) != (item['classifier_probability'] >= .5))
    basin_complete=bool(basin_daily_payload and upstream_ids and all(any(basin_daily_payload.get('basin_daily',{}).get(str(b),{}).get(item['date']) is not None for b in upstream_ids) for item in out))
    return {'locality':name,'target_date':str(target_date or ordered[0] if ordered else target_date),'forecast_issue_time':datetime.now(timezone.utc).isoformat(),'source':'Open-Meteo Weather + Open-Meteo GloFAS Flood API','provider_status':provider_status,'glofas_forecast_available':bool(glofas_ok),'glofas_forecast_status':'REAL_FORECAST' if glofas_ok else 'NO_DATA','glofas_forecast_note':'Only live GloFAS dates are exposed; no archived snapshot is substituted.','basin_rainfall_data_source':'Open-Meteo forecast queried at upstream-basin centroids; values remain environmental context until production feature compatibility is validated.','upstream_basin_rainfall_status':'UPSTREAM_CENTROID_AGGREGATION' if basin_complete else 'PARTIAL_UPSTREAM_CENTROID_AGGREGATION','upstream_basin_count':int(len(upstream_ids)),'upstream_basin_centroids_queried':int(len(upstream_ids)),'upstream_basin_http_queries':basin_query_count,'trajectory':out,'classifier_status':'WITHHELD_UNVALIDATED_PRODUCTION_FEATURES','option_b_note':'Environmental threshold context only; no quantitative flood prediction is emitted from this forecast.'}

# Public name used by the API/UI forecast flow.
get_locality_forecast = get_forecasted_features


def _partial_live_prediction(*, observations, discharge_series, row, hrow, rainfall_p90):
    """Run only the separately trained profile for the available live subset.

    This profile has no RainViewer, SAR, ERA5-Land runoff, or upstream-basin
    columns. Its feature schema is fixed in the saved artifact; missing values
    are a reason to decline this profile, never an opportunity to add zeros.
    """
    payload = _partial_live_model()
    if not payload:
        return None, ["partial_live_model_artifact"]
    needed = ("precipitation_1d", "precipitation_3d", "precipitation_7d", "precipitation_14d", "soil_moisture_0_to_7cm", "river_discharge")
    missing = [key for key in needed if key not in observations or not observations[key].is_valid]
    if hrow is None or pd.isna(hrow.get('basin_id')) or pd.isna(row.get('elevation_m')) or pd.isna(row.get('slope_deg')):
        missing.append("terrain")
    discharge = observations.get("river_discharge")
    valid_day = pd.Timestamp(discharge.valid_time).date() if discharge and discharge.valid_time else None
    lag_values = {}
    if valid_day:
        for lag in (1, 3, 7):
            lag_date = (pd.Timestamp(valid_day) - pd.Timedelta(days=lag)).date().isoformat()
            value = discharge_series.get(lag_date)
            if not isinstance(value, (int, float)) or not math.isfinite(float(value)) or float(value) < 0:
                missing.append(f"discharge_lag{lag}")
            else:
                lag_values[lag] = float(value)
    else:
        missing.extend(["discharge_lag1", "discharge_lag3", "discharge_lag7"])
    if missing:
        return None, sorted(set(missing))
    rainfall_1d = float(observations['precipitation_1d'].value)
    rainfall_3d = float(observations['precipitation_3d'].value)
    rainfall_7d = float(observations['precipitation_7d'].value)
    rainfall_14d = float(observations['precipitation_14d'].value)
    vector = {
        'rainfall_1d': rainfall_1d,
        'rainfall_3d': rainfall_3d,
        'rainfall_7d': rainfall_7d,
        'rainfall_14d': rainfall_14d,
        'rainfall_anomaly': rainfall_7d - float(rainfall_p90),
        'swvl1': float(observations['soil_moisture_0_to_7cm'].value),
        'discharge_m3s': float(discharge.value),
        'discharge_lag1': lag_values[1],
        'discharge_lag3': lag_values[3],
        'discharge_lag7': lag_values[7],
        'elevation_m': float(row.elevation_m),
        'slope_deg': float(row.slope_deg),
        'basin_id': float(hrow.basin_id),
        'season': int(datetime.now(timezone.utc).month in (4, 5, 6, 7, 8, 9, 10)),
    }
    features = payload['features']
    if set(features) != set(vector):
        return None, ["partial_live_model_schema_mismatch"]
    frame = pd.DataFrame([[vector[name] for name in features]], columns=features)
    score = float(payload['pipeline'].predict_proba(frame)[0, 1])
    if not math.isfinite(score):
        return None, ["partial_live_model_invalid_score"]
    return {
        'risk_score_percent': round(score * 100, 2),
        'risk_level': 'HIGH' if score >= 0.67 else ('MODERATE' if score >= 0.34 else 'LOW'),
        'model_name': payload['candidate_name'],
        'model_version': payload['model_profile'],
        'model_threshold': payload['threshold'],
        'metrics': payload['metrics'],
        'features_used': features,
        'feature_values': vector,
        'source_provenance': payload.get('source_provenance', {}),
    }, []

def get_locality_risk(locality_name_or_lat_lon):
    """Return a JSON-serialisable risk bundle for a locality or ``lat,lon``."""
    row=_resolve(locality_name_or_lat_lon); name=row['name']; cache=_risk_cache().loc[name]
    month=datetime.now(timezone.utc).month
    p90=float(cache.rainfall_3d_p90)
    soil_col=f'soil_median_m{month:02d}'
    month_median=cache.get(soil_col)
    lat, lon = float(row.lat), float(row.lon)
    # Retrieve independent providers together.  A slow or unavailable satellite
    # product must not hide valid rainfall, discharge, radar, or runoff values.
    with ThreadPoolExecutor(max_workers=4) as pool:
        weather_task = pool.submit(_forecast, lat, lon, p90, month_median)
        discharge_task = pool.submit(_fetch_river_discharge, lat, lon, 7, 3)
        radar_task = pool.submit(_fetch_radar_nowcast, lat, lon)
        sar_task = pool.submit(_fetch_opera_sar_inundation, lat, lon)
        fc = weather_task.result()
        disch_info = discharge_task.result()
        radar_info = radar_task.result()
        sar_info = sar_task.result()
    # Live data tier 2: GloFAS river discharge (Open-Meteo Flood API).
    disch_latest = disch_info.get('latest')
    disch_status = disch_info.get('status', 'unavailable')
    disch_source = disch_info.get('source', 'Open-Meteo GloFAS Flood API')

    hydro, runoff_table = _hydrology_cache()
    hrow = hydro.loc[name] if name in hydro.index else None
    rrow = runoff_table.loc[name] if name in runoff_table.index else None
    cached_runoff = (rrow.get('runoff_mm_latest') if rrow is not None else None)
    ssro_latest = (rrow.get('sub_surface_runoff_mm_latest') if rrow is not None else None)
    drainage_density = (hrow.get('drainage_density_km_per_km2') if hrow is not None else None)
    runoff_date = (rrow.get('runoff_latest_date') if rrow is not None else None)
    cached_runoff = float(cached_runoff) if pd.notna(cached_runoff) else None
    ssro_latest = float(ssro_latest) if pd.notna(ssro_latest) else None
    drainage_density = float(drainage_density) if pd.notna(drainage_density) else None
    # The provider returns runoff for supported weather models.  At Blangoua
    # the current Open-Meteo model can return null; retain the last validated
    # ERA5-Land observation in that case, but explicitly mark it historical.
    live_runoff = fc.get('runoff_mm')
    runoff_latest = float(live_runoff) if live_runoff is not None else cached_runoff
    runoff_status = fc.get('runoff_status', 'unavailable')
    runoff_source = fc.get('runoff_source', 'Open-Meteo weather-model total runoff')
    if runoff_latest is None:
        runoff_status = 'unavailable'
    elif runoff_status != 'available':
        runoff_status = 'historical'
        runoff_source = 'ERA5-Land validated daily runoff cache (latest available observation)'
    # Live data tier 3: RainViewer satellite radar nowcast.
    radar_intensity = float(radar_info.get('radar_intensity', 0.0))
    radar_mmhr = radar_info.get('radar_mmhr')
    radar_storm_active = bool(radar_info.get('storm_active', False))

    # Live data tier 4: NASA OPERA DSWx-S1 Sentinel-1 SAR flood inundation.
    # Provider availability is returned per source.  Risk remains available
    # when a satellite pass has not occurred, rather than replacing every card
    # with fabricated reference values.
    provider_status = {
        'ready': bool(fc.get('trajectory')) and disch_status == 'available',
        'providers': {
            'openmeteo': {'source': fc.get('source'), 'status': 'available' if fc.get('trajectory') else 'unavailable', 'fetched_at': fc.get('fetched_at'), 'error': fc.get('error')},
            'glofas': {'source': disch_source, 'status': disch_status, 'fetched_at': disch_info.get('fetched_at'), 'error': disch_info.get('error')},
            'rainviewer': {'source': radar_info.get('source'), 'status': radar_info.get('status', 'unavailable'), 'fetched_at': radar_info.get('fetched_at'), 'error': radar_info.get('error')},
            'era5_runoff': {'source': runoff_source, 'status': runoff_status, 'fetched_at': fc.get('fetched_at') if runoff_status == 'available' else runoff_date, 'error': fc.get('error') if runoff_status == 'unavailable' else None},
            'nasa_opera': {'source': sar_info.get('source'), 'status': sar_info.get('status', 'unavailable'), 'fetched_at': sar_info.get('fetched_at'), 'error': sar_info.get('error') or sar_info.get('message')},
        },
    }
    provider_status['unavailable'] = [key for key, value in provider_status['providers'].items() if value['status'] == 'unavailable']
    sar_fraction = float(sar_info.get('sar_inundation_fraction', 0.0))
    sar_water_detected = bool(sar_info.get('water_detected', False))

    first=fc.get('trajectory',[{}])[0] if fc.get('trajectory') else {}
    rainfall3d=first.get('rainfall_3d_forecast_mm'); swvl1=first.get('soil_moisture_mean')
    threshold_flag=bool(rainfall3d is not None and month_median is not None and rainfall3d>p90 and swvl1>float(month_median))
    # Components are exposed separately and weights are documented constants.
    static=float(row.susceptibility_score); threshold=100.0 if threshold_flag else 0.0
    cat=_catalogue(); event_count=0; hist=[]
    for _,e in cat.iterrows():
        text=' '.join([str(e.get('locality_name','')),str(e.get('division',''))]).casefold()
        if norm(name) in norm(text) or (pd.notna(row.division) and norm(row.division) in norm(text)):
            event_count+=1; hist.append({'event_id':e.canonical_event_id,'start':e.event_start_date,'end':e.event_end_date,'source':e.source_document_url})
    density=min(100.0,event_count/3*100); estimated=round(.60*static+.25*threshold+.15*density,2)

    # Audited, defensible confidence metrics (replaces former hardcoded 100.0 placeholders):
    # 1. Grid proximity quality (distance to nearest ERA5 cell center, max 100, min 60)
    era_lat_dist = abs(float(row.lat) - float(cache.era_lat)) * 111.0
    era_lon_dist = abs(float(row.lon) - float(cache.era_lon)) * 111.0
    grid_dist_km = math.sqrt(era_lat_dist**2 + era_lon_dist**2)
    grid = round(max(60.0, min(100.0, 100.0 - (grid_dist_km * 2.5))), 1)

    # 2. Environmental telemetry completeness (elevation, river distance, drainage density, runoff, discharge, SAR)
    signals = [
        pd.notna(row.get('elevation_m')),
        pd.notna(row.get('river_distance_m')),
        pd.notna(drainage_density),
        runoff_latest is not None,
        disch_latest is not None,
        sar_info.get('status') == 'available',
    ]
    completeness = round(60.0 + (sum(signals) / 6.0) * 40.0, 1)

    # 3. Forecast data freshness (100 if all live APIs succeed, 60 on fallback)
    # Radar tier adds +5 to freshness; SAR tier adds +5 when actively available.
    base_freshness = 100.0 if (fc.get('trajectory') and disch_status == 'available') else (75.0 if fc.get('trajectory') else 50.0)
    radar_freshness_boost = 5.0 if radar_info.get('status') == 'available' else 0.0
    sar_freshness_boost = 5.0 if sar_info.get('status') == 'available' else 0.0
    freshness = min(100.0, base_freshness + radar_freshness_boost + sar_freshness_boost)

    # 4. Verified event density calibration
    event_component = density
    confidence=round(.30*grid+.25*completeness+.25*event_component+.20*freshness, 1)

    # Operational ML probability evaluation
    ml_prob = None
    ml_risk_percent = None
    active_model_name = None
    op_payload = _operational_model()
    if op_payload is not None:
        try:
            pipe = op_payload.get('pipeline')
            features = op_payload.get('features', [])
            r1 = float(first.get('rainfall_mm', (rainfall3d / 3.0 if rainfall3d else 0.0)) or 0.0)
            r3 = float(rainfall3d or 0.0)
            r7 = float(sum(p.get('rainfall_mm', 0.0) for p in fc.get('trajectory', [])[:3]) * (7.0 / 3.0)) if fc.get('trajectory') else r3 * (7.0 / 3.0)
            r14 = r7 * 2.0
            anomaly = r7 - p90
            sm = float(swvl1 if swvl1 is not None else (month_median if month_median is not None else 0.2))
            disch_val = float(disch_latest) if disch_latest is not None else 0.0
            elev = float(row.elevation_m) if pd.notna(row.get('elevation_m')) else 300.0
            slope = float(row.slope_deg) if pd.notna(row.get('slope_deg')) else 0.01
            basin_id = float(row.basin_id) if pd.notna(row.get('basin_id')) else 1060707270.0
            season_val = int(datetime.now(timezone.utc).month in [4, 5, 6, 7, 8, 9, 10])

            # Radar intensity amplifies the rainfall signal: multiply observed
            # rainfall features by a storm-factor derived from the radar reading.
            # A 100/100 storm doubles the effective 1-day rain signal; 0 = no boost.
            radar_factor = 1.0 + (radar_intensity / 100.0)
            feat_row = {
                'rainfall_1d': r1 * radar_factor,
                'rainfall_3d': r3 * radar_factor,
                'rainfall_7d': r7,
                'rainfall_14d': r14,
                'rainfall_anomaly': anomaly + (radar_intensity * 0.5),  # active storm boosts anomaly
                'swvl1': sm,
                'discharge_m3s': disch_val,
                'discharge_lag1': disch_val,
                'discharge_lag3': disch_val,
                'discharge_lag7': disch_val,
                'elevation_m': elev,
                'slope_deg': slope,
                'basin_id': basin_id,
                'season': season_val,
                'basin_rainfall_3d': r3 * radar_factor,
                'basin_rainfall_7d': r7,
                'basin_rainfall_14d': r14,
                'basin_rainfall_21d': r14 * 1.5,
                'basin_rainfall_30d': r14 * 2.14,
            }
            feat_df = pd.DataFrame([feat_row])[features]
            probs = pipe.predict_proba(feat_df)[:, 1]
            ml_prob = float(round(probs[0], 4))
            ml_risk_percent = round(ml_prob * 100.0, 2)
            active_model_name = op_payload.get('candidate_name', 'Calibrated_HistGradientBoosting')
        except Exception:
            ml_prob = None
            ml_risk_percent = None

    if ml_risk_percent is not None:
        blended_risk = round(0.50 * estimated + 0.50 * ml_risk_percent, 2)
        active_model_type = f"Hybrid Operational Ensemble: 50% Calibrated ML ({active_model_name}) + 50% Terrain Susceptibility & Hydrological Thresholds"
    else:
        blended_risk = estimated
        active_model_type = MODEL_TYPE

    # Post-hoc SAR flood inundation confirmation adjustment:
    # If Sentinel-1 SAR directly detects ground inundation (> 5% surface water), apply
    # an empirical flood confirmation boost: +5% for 5-15%, +10% for 15-30%, +15% for >30%.
    sar_risk_boost = 0.0
    if sar_fraction >= 0.30:
        sar_risk_boost = 15.0
    elif sar_fraction >= 0.15:
        sar_risk_boost = 10.0
    elif sar_fraction >= 0.05:
        sar_risk_boost = 5.0
    blended_risk = min(100.0, round(blended_risk + sar_risk_boost, 2))

    for point in fc.get('trajectory',[]):
        sig=float(point.get('threshold_signal',0))
        pt_heuristic = round(.60*static+.25*(100.0 if sig else 0.0)+.15*density,2)
        if ml_risk_percent is not None:
            point['estimated_risk_percent'] = min(100.0, round(0.50 * pt_heuristic + 0.50 * ml_risk_percent + sar_risk_boost, 2))
        else:
            point['estimated_risk_percent'] = min(100.0, round(pt_heuristic + sar_risk_boost, 2))

    risk_level = 'HIGH' if blended_risk>=67 else ('MEDIUM' if blended_risk>=34 else 'LOW')

    result={'locality':name,'coordinates':{'lat':lat,'lon':lon},'grid_references':{'era5':f'{float(cache.era_lat):.3f},{float(cache.era_lon):.3f}','glofas':cache.glofas_cell_reference},'provider_status':provider_status,'risk_level':risk_level,'estimated_risk_percent':blended_risk,'ml_probability':ml_prob,'ml_risk_percent':ml_risk_percent,'heuristic_risk_percent':estimated,'estimated_risk_components':{'susceptibility_score':static,'threshold_signal':threshold,'nearby_verified_event_density':density,'ml_calibrated_probability':ml_prob,'radar_intensity_nowcast':radar_intensity,'sar_inundation_fraction':sar_fraction,'sar_risk_boost':sar_risk_boost,'weights':{'heuristic_susceptibility_blend':0.50,'calibrated_ml_blend':0.50} if ml_risk_percent is not None else {'susceptibility':.60,'threshold':.25,'event_density':.15}},'confidence_score':confidence,'confidence_components':{'grid_match_quality':grid,'dem_slope_completeness':completeness,'nearby_verified_event_count':event_count,'nearby_verified_event_density':density,'forecast_data_freshness':freshness,'radar_nowcast_available':radar_info.get('status')=='available','sar_telemetry_available':sar_info.get('status')=='available','sar_inundation_fraction':sar_fraction},'nearby_verified_event_density':density,'current_conditions':{'date':datetime.now(timezone.utc).date().isoformat(),'rainfall_3d':rainfall3d,'rainfall_3d_p90':p90,'swvl1':swvl1,'calendar_month_soil_median':month_median,'elevated_risk_flag':int(threshold_flag),'historical_cache':'farnorth_locality_risk_cache.parquet','runoff_mm':runoff_latest,'sub_surface_runoff_mm':ssro_latest,'runoff_latest_date':runoff_date,'runoff_status':runoff_status,'runoff_data_source':runoff_source,'drainage_density_km_per_km2':drainage_density,'drainage_density_data_source':'HydroRIVERS total river-line length within the HydroBASINS level-6 basin divided by basin area (km/km²)','river_discharge_m3s':disch_latest,'river_discharge_status':disch_status,'river_discharge_source':disch_source,'radar_nowcast':{'intensity_0_100':radar_intensity,'precipitation_mmhr':radar_mmhr,'storm_active':radar_storm_active,'source':radar_info.get('source'),'status':radar_info.get('status'),'latest_frame_ts':radar_info.get('latest_frame_ts')},'sar_inundation':sar_info},'forecast_72h':fc,'historical_context':hist,'last_model_update':datetime.now(timezone.utc).isoformat(),'model_type':active_model_type}
    result['elevation_m'] = float(row.elevation_m) if pd.notna(row.get('elevation_m')) else None
    result['river_distance_m'] = float(row.river_distance_m) if pd.notna(row.get('river_distance_m')) else None
    return json.loads(json.dumps(result, default=lambda o: o.item() if hasattr(o, 'item') else str(o)))

def get_locality_risk(locality_name_or_lat_lon):
    """Return validated environmental observations and a safe prediction decision.

    This replacement intentionally supersedes the legacy hybrid scorer above.
    It never manufactures rainfall windows, discharge lags, radar values, SAR
    percentages, or ML defaults. It selects the separately trained partial
    profile only when its exact local weather/GloFAS/terrain schema is valid.
    """
    row = _resolve(locality_name_or_lat_lon)
    name = row['name']
    cache = _risk_cache().loc[name]
    lat, lon = float(row.lat), float(row.lon)
    month = datetime.now(timezone.utc).month
    p90 = float(cache.rainfall_3d_p90)
    month_median = cache.get(f'soil_median_m{month:02d}')
    hydro, runoff_table = _hydrology_cache()
    hrow = hydro.loc[name] if name in hydro.index else None
    rrow = runoff_table.loc[name] if name in runoff_table.index else None
    # Select the actual locality/date record from the daily ERA5-Land-derived
    # archive. The summary table is only an availability fallback for a
    # damaged/missing daily file; neither path is ever labelled current.
    archive = _historical_runoff_for_locality(name)
    if archive is None:
        runoff_value = rrow.get('runoff_mm_latest') if rrow is not None else None
        runoff_date = rrow.get('runoff_latest_date') if rrow is not None else None
        archive = ({'value': float(runoff_value), 'date': str(runoff_date), 'dataset': 'farnorth_runoff_summary.parquet'}
                   if pd.notna(runoff_value) and pd.notna(runoff_date) else None)
    hydrological_context = {
        'basin_id': hrow.get('basin_id') if hrow is not None else None,
        'glofas_cell_reference': cache.get('glofas_cell_reference'),
        'river_distance_m': float(row.river_distance_m) if pd.notna(row.get('river_distance_m')) else None,
    }
    environment = EnvironmentalOrchestrator().collect(lat, lon, archive, hydrological_context)
    observations = environment['objects']
    discharge_series = environment['discharge_series']
    rainfall = observations['precipitation_3d']
    soil = observations['soil_moisture_0_to_7cm']
    discharge = observations['river_discharge']
    runoff = observations['runoff']
    rainfall3d = rainfall.value if rainfall.is_valid else None
    swvl1 = soil.value if soil.is_valid else None
    discharge_value = discharge.value if discharge.is_valid else None
    drainage_density = hrow.get('drainage_density_km_per_km2') if hrow is not None else None
    drainage_density = float(drainage_density) if pd.notna(drainage_density) else None
    threshold_flag = (int(rainfall3d > p90 and swvl1 > float(month_median))
                      if rainfall3d is not None and swvl1 is not None and month_median is not None else None)
    # Terrain fields come from two existing project tables: locality cache for
    # elevation/slope and HydroBASINS-derived hydrology for basin id.
    terrain_ready = (
        pd.notna(row.get('elevation_m')) and pd.notna(row.get('slope_deg'))
        and hrow is not None and pd.notna(hrow.get('basin_id'))
    )
    # Production previously fabricated 7/14-day rain and GloFAS lag features.
    # They remain unavailable until a source-consistent feature builder is
    # validated against the training pipeline.
    full_eligibility = assess_model_eligibility(
        observations, terrain_ready=terrain_ready,
        upstream_rainfall_ready=False, discharge_lags_ready=False,
    )
    partial_prediction, partial_missing = _partial_live_prediction(
        observations=observations, discharge_series=discharge_series,
        row=row, hrow=hrow, rainfall_p90=p90,
    )
    eligibility = (
        {
            'prediction_status': 'PARTIAL_DATA',
            'model_profile': partial_prediction['model_version'],
            'features_used': partial_prediction['features_used'],
            'features_missing': ['upstream_basin_rainfall_3d', 'upstream_basin_rainfall_7d', 'upstream_basin_rainfall_14d', 'upstream_basin_rainfall_21d', 'upstream_basin_rainfall_30d'],
            'reason': 'Validated partial-data model selected because local rain windows, soil moisture, GloFAS discharge/lags and terrain are available.',
        }
        if partial_prediction else full_eligibility
    )
    historical_context = []
    for _, event in _catalogue().iterrows():
        event_text = ' '.join([str(event.get('locality_name', '')), str(event.get('division', ''))]).casefold()
        if norm(name) in norm(event_text) or (pd.notna(row.division) and norm(row.division) in norm(event_text)):
            historical_context.append({'event_id': event.canonical_event_id, 'start': event.event_start_date,
                                       'end': event.event_end_date, 'source': event.source_document_url})
    serialised = environment['observations']
    good_states = {'REAL_CURRENT', 'REAL_FORECAST', 'REAL_HISTORICAL', 'REAL_RECENT_BUT_NOT_CURRENT'}
    providers_used = sorted({item['provider_product'] for item in serialised.values() if item['quality'] == 'VALID'})
    providers_failed = sorted({item['provider_product'] for item in serialised.values() if item['status'] not in good_states})
    provider_status = {
        'ready': eligibility['prediction_status'] in {'FULL_PREDICTION', 'PARTIAL_DATA'},
        'providers': {
            'openmeteo': {'source': rainfall.provider_product, 'status': rainfall.status, 'quality': rainfall.quality, 'fetched_at': rainfall.retrieved_at, 'error': rainfall.error_message},
            'glofas': {'source': discharge.provider_product, 'status': discharge.status, 'quality': discharge.quality, 'fetched_at': discharge.retrieved_at, 'error': discharge.error_message},
            'rainviewer': {'source': observations['radar_visual_layer'].provider_product, 'status': observations['radar_visual_layer'].status, 'quality': observations['radar_visual_layer'].quality, 'fetched_at': observations['radar_visual_layer'].retrieved_at, 'error': observations['radar_visual_layer'].error_message},
            'era5_runoff': {'source': runoff.provider_product, 'status': runoff.status, 'quality': runoff.quality, 'fetched_at': runoff.retrieved_at, 'error': runoff.error_message},
            'nasa_opera': {'source': observations['surface_water'].provider_product, 'status': observations['surface_water'].status, 'quality': observations['surface_water'].quality, 'fetched_at': observations['surface_water'].retrieved_at, 'error': observations['surface_water'].error_message},
        },
    }
    provider_status['unavailable'] = [key for key, item in provider_status['providers'].items() if item['status'] not in good_states]
    result = {
        'locality': name, 'coordinates': {'lat': lat, 'lon': lon},
        'grid_references': {'era5': f'{float(cache.era_lat):.3f},{float(cache.era_lon):.3f}', 'glofas': None},
        'prediction_status': eligibility['prediction_status'],
        'risk_level': partial_prediction['risk_level'] if partial_prediction else None,
        'estimated_risk_percent': partial_prediction['risk_score_percent'] if partial_prediction else None,
        'risk_score': partial_prediction['risk_score_percent'] if partial_prediction else None,
        'score_unit': 'percent', 'score_label': 'Calibrated risk score',
        # This partial profile is presented as a calibrated *risk score*, not a
        # flood probability. Keeping the probability field empty prevents
        # downstream screens from relabelling the score as a probability.
        'probability_if_validated': None,
        'model_name': partial_prediction['model_name'] if partial_prediction else None,
        'model_version': partial_prediction['model_version'] if partial_prediction else None,
        'model_eligibility': eligibility,
        'features_used': eligibility['features_used'], 'features_missing': eligibility['features_missing'],
        'providers_used': providers_used, 'providers_failed': providers_failed,
        'provider_status': provider_status, 'provider_health': environment['provider_health'],
        'environmental_observations': serialised,
        'data_quality': 'VALIDATED_PARTIAL_DATA' if partial_prediction else 'INSUFFICIENT_FOR_QUANTITATIVE_PREDICTION',
        'data_quality_note': ('Validated partial-data model using current local rain windows, soil moisture, discharge history and terrain. Radar and SAR are supporting sources, not model features; the training/runtime source transition remains disclosed in the model provenance.' if partial_prediction else 'No trained model can operate with the currently validated feature set.'),
        'prediction_timestamp': datetime.now(timezone.utc).isoformat(),
        'explanation': eligibility.get('reason', 'Validated full-model data available.'),
        'partial_model_metrics': partial_prediction['metrics'] if partial_prediction else None,
        'partial_model_source_provenance': partial_prediction['source_provenance'] if partial_prediction else None,
        'partial_model_unavailable_features': partial_missing if not partial_prediction else [],
        'current_conditions': {
            'date': datetime.now(timezone.utc).date().isoformat(), 'rainfall_3d': rainfall3d,
            'rainfall_3d_p90': p90, 'swvl1': swvl1, 'calendar_month_soil_median': month_median,
            'elevated_risk_flag': threshold_flag,
            'runoff_mm': runoff.value if runoff.value is not None and runoff.status in {'REAL_CURRENT', 'REAL_FORECAST', 'REAL_HISTORICAL', 'STALE_DATA'} else None,
            'runoff_latest_date': runoff.valid_time,
            'runoff_status': runoff.status, 'runoff_data_source': runoff.provider_product,
            'drainage_density_km_per_km2': drainage_density,
            'drainage_density_data_source': 'HydroRIVERS total river-line length within HydroBASINS level-6 basin divided by basin area',
            'river_discharge_m3s': discharge_value, 'river_discharge_status': discharge.status,
            'river_discharge_source': discharge.provider_product,
            'radar_nowcast': {'intensity_0_100': None, 'precipitation_mmhr': None, 'storm_active': None,
                              'source': observations['radar_visual_layer'].provider_product,
                              'status': observations['radar_visual_layer'].status,
                              'latest_frame_ts': observations['radar_visual_layer'].valid_time},
            'sar_inundation': {'water_percentage': None, 'water_detected': None,
                               'status': observations['surface_water'].status,
                               'source': observations['surface_water'].provider_product,
                               'error': observations['surface_water'].error_message},
        },
        'historical_context': historical_context,
        'elevation_m': float(row.elevation_m) if pd.notna(row.get('elevation_m')) else None,
        'river_distance_m': float(row.river_distance_m) if pd.notna(row.get('river_distance_m')) else None,
    }
    result['audit_record_persisted'] = persist_observation_audit(
        locality=name, latitude=lat, longitude=lon, observations=serialised, eligibility=eligibility,
    )
    return json.loads(json.dumps(result, default=lambda value: value.item() if hasattr(value, 'item') else str(value)))


def get_locality_risk_classifier(locality_name_or_lat_lon, date_value):
    """Return the secondary exploratory classifier signal for one locality/day.

    Option B (``get_locality_risk``) remains the operational user-facing
    system.  This model is a comparative research signal trained on the
    currently complete event rows only and must not be interpreted as a
    calibrated individual probability.
    """
    if not EXPLORATORY_MODEL.exists():
        raise FileNotFoundError(f'Exploratory model artifact missing: {EXPLORATORY_MODEL}')
    row = _resolve(locality_name_or_lat_lon); name = row['name']; day = pd.Timestamp(date_value)
    payload = joblib.load(EXPLORATORY_MODEL); model = payload['model']; features = payload['features']
    base = OUT/'locality_subsets'
    rain = _read_parquet(base/'chirps_34.parquet')
    rain['date'] = pd.to_datetime(rain['date']); rain = rain[rain.name == name].sort_values('date').copy()
    if rain.empty or day not in set(rain.date): raise ValueError(f'No rainfall data for {name} on {day.date()}')
    for n in (1,3,7,14): rain[f'rainfall_{n}d'] = rain.rainfall_mm.rolling(n, min_periods=n).sum()
    rain['rainfall_anomaly'] = rain.rainfall_7d - rain.rainfall_7d.mean()
    e = _read_parquet(base/'era5_34.parquet'); e.date = pd.to_datetime(e.date)
    g = _read_parquet(base/'glofas_34.parquet'); g.date = pd.to_datetime(g.date)
    l = _read_parquet(OUT/'farnorth_locality_environment_lookup.parquet').drop_duplicates('name')
    z = rain[rain.date == day].merge(e[(e.name == name)&(e.date == day)][['name','date','swvl1']], on=['name','date'])
    z = z.merge(g[(g.locality == name)&(g.date == day)], left_on=['name','date'], right_on=['locality','date'])
    z = z.merge(l[l.name == name][['name','elevation_m','slope_deg','basin_id']], on='name')
    if z.empty: raise ValueError(f'Incomplete environmental row for {name} on {day.date()}')
    z['season'] = int(day.month in [4,5,6,7,8,9,10])
    if any(str(f).startswith('basin_rainfall_') for f in features):
        bf = _read_parquet(OUT/'basin_upstream_features.parquet'); bf['date'] = pd.to_datetime(bf['date'])
        bz = bf[(bf['name'] == name) & (bf['date'] == day)]
        if bz.empty: raise ValueError(f'No upstream-basin rainfall features for {name} on {day.date()}')
        extra = [f for f in features if str(f).startswith('basin_rainfall_')]
        z = z.merge(bz[['name','date'] + extra], on=['name','date'], how='left')
    if z[features].isna().any(axis=None): raise ValueError(f'Incomplete classifier feature row for {name} on {day.date()}')
    prob = float(model.predict_proba(z[features])[:,1][0])
    return {'locality': name, 'date': day.date().isoformat(), 'predicted_probability': prob,
            'model_type': 'EXPLORATORY - Random Forest with upstream-basin rainfall, trained on 39 verified events - treat as comparative research signal, not a reliable individual prediction',
            'operational_note': 'Option B (rules-based get_locality_risk) remains the system used for user-facing risk display.',
            'feature_row': {k: (float(z[k].iloc[0]) if pd.notna(z[k].iloc[0]) else None) for k in features}}

def get_top_risk_localities(n=5, division=None):
    """Rank localities by precomputed static susceptibility (not live risk)."""
    s=_scores().copy()
    if division:
        s=s[s.division.astype(str).str.casefold()==str(division).casefold()]
    cat=_catalogue(); counts=cat.assign(_txt=(cat.locality_name.fillna('')+';'+cat.division.fillna('')).map(norm)).groupby('_txt').size()
    s['historical_verified_event_count']=s.name.map(lambda x:int(cat[(cat.locality_name.fillna('').map(norm).str.contains(norm(x),regex=False)) | (cat.division.fillna('').map(norm).str.contains(norm(x),regex=False))].shape[0]))
    out=s.sort_values('susceptibility_score',ascending=False).head(int(n))
    rec=out[['name','susceptibility_score','historical_verified_event_count']].to_dict('records')
    for r in rec:
        if r['historical_verified_event_count']==0:
            r['caveat']='high terrain-based susceptibility, but no documented flood history - treat with caution, may reflect undocumented risk or formula bias, not confirmed danger.'
    return {'basis':'static susceptibility layer (terrain and historical patterns), not live current conditions','results':rec}

def get_division_risk(division_name):
    """Return the maximum operational risk across covered towns in a division."""
    q = str(division_name or '').strip().casefold()
    division = next((d for d in _COVERED_DIVISIONS if d.casefold() == q), None)
    if division is None:
        division = next((d for d in _COVERED_DIVISIONS if q in d.casefold() or d.casefold() in q), None)
    if division is None:
        return {'division': str(division_name), 'covered_localities': [], 'coverage_count': 0, 'estimated_town_count': None, 'coverage_note': 'No model-covered localities are mapped to this division.', 'risk': None}
    key = division
    cached = _DIVISION_RISK_CACHE.get(key)
    if cached and time.time() - cached[0] < _FORECAST_CACHE_TTL_SECONDS:
        return cached[1]
    names = sorted(_COVERED_DIVISIONS[division])
    def assess(name):
        try:
            r = get_locality_risk(name)
            return {'locality': name, 'estimated_risk_percent': r.get('estimated_risk_percent'), 'risk_level': r.get('risk_level'), 'confidence_score': r.get('confidence_score')}
        except Exception as exc:
            return {'locality': name, 'estimated_risk_percent': None, 'risk_level': 'Unavailable', 'error': str(exc)}
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=min(6, max(1, len(names)))) as pool:
        breakdown = list(pool.map(assess, names))
    usable = [x for x in breakdown if x.get('estimated_risk_percent') is not None]
    maximum = max(usable, key=lambda x: float(x['estimated_risk_percent'])) if usable else None
    result = {'division': division, 'coverage_count': len(usable), 'estimated_town_count': _DIVISION_ESTIMATED_TOWNS.get(division), 'coverage_note': f"(based on {len(usable)} of an estimated {_DIVISION_ESTIMATED_TOWNS.get(division, len(names))} towns in this division)", 'risk': maximum, 'localities': breakdown, 'aggregation': 'maximum risk across covered localities; not an average'}
    _DIVISION_RISK_CACHE[key] = (time.time(), result)
    return result

def validate_historical_day(locality_name_or_lat_lon, date_value):
    """Check the threshold on one historical CHIRPS/ERA5 day (validation only)."""
    row=_resolve(locality_name_or_lat_lon); name=row['name']; day=pd.Timestamp(date_value).date()
    con=duckdb.connect(str(DB), read_only=True)
    try:
        rain=con.execute("SELECT date,rainfall_mm FROM rain WHERE name=? AND date BETWEEN (?::DATE - INTERVAL 2 DAY) AND ?::DATE ORDER BY date",[name,day,day]).df()
        soil=con.execute("SELECT swvl1 FROM locality_soil WHERE name=? AND date=? LIMIT 1",[name,day]).df()
    finally: con.close()
    p90=float(_risk_cache().loc[name].rainfall_3d_p90); med=_risk_cache().loc[name].get(f'soil_median_m{day.month:02d}')
    r3=float(rain.rainfall_mm.sum()) if len(rain) else None; sm=float(soil.swvl1.iloc[0]) if len(soil) else None
    flag=int(r3 is not None and sm is not None and r3>p90 and sm>float(med))
    result={'locality':name,'date':str(day),'rainfall_3d':r3,'rainfall_3d_p90':p90,'swvl1':sm,'calendar_month_soil_median':float(med) if med is not None else None,'elevated_risk_flag':flag,'validation_only':True}
    return json.loads(json.dumps(result, default=lambda o: o.item() if hasattr(o, 'item') else str(o)))
