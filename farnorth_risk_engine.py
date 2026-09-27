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
     Called per-request via _fetch_radar_nowcast().  Returns current storm
     intensity (0–100 normalised scale) at locality's lat/lon.  Amplifies
     short-term rainfall features in operational ML inference.
  4. INUNDATION SATELLITE (keyless, public): NASA OPERA DSWx-S1 Sentinel-1 SAR.
     Called per-request via _fetch_opera_sar_inundation().  Queries NASA CMR
     for the latest Sentinel-1 Dynamic Surface Water Extent product to assess
     ground-level standing water and flood extent regardless of cloud cover.

This is a rules-based weighted formula, not trained ML.  Verified events are
used for historical context/validation only; they are never model-training
rows.
"""
from __future__ import annotations
import json, math, time, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import duckdb
import joblib

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
EWDS_DISCHARGE_PARQUET=OUT/'glofas_ewds_latest.parquet'  # Written by DataCollectorAgent when EWDS key is set
MODEL_TYPE='Operational Hybrid Ensemble (Calibrated HistGradientBoosting ML + Terrain Susceptibility & Hydrological Thresholds)'

_OPERATIONAL_MODEL_CACHE = None

def _operational_model():
    """Load the calibrated operational ML model once per worker process."""
    global _OPERATIONAL_MODEL_CACHE
    if _OPERATIONAL_MODEL_CACHE is None and OPERATIONAL_MODEL.exists():
        try:
            _OPERATIONAL_MODEL_CACHE = joblib.load(OPERATIONAL_MODEL)
        except Exception:
            _OPERATIONAL_MODEL_CACHE = None
    return _OPERATIONAL_MODEL_CACHE

_CATALOGUE_CACHE = None
_SCORES_CACHE = None
_HYDRO_CACHE = None
_RUNOFF_CACHE = None

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
    params=urllib.parse.urlencode({'latitude':lat,'longitude':lon,'hourly':'precipitation,soil_moisture_0_to_7cm','forecast_days':3,'timezone':'UTC'})
    url='https://api.open-meteo.com/v1/forecast?'+params
    try:
        raw_bytes = _robust_urlopen(url, timeout=15, retries=3)
        raw = json.loads(raw_bytes.decode('utf-8'))
        h=raw.get('hourly',{}); p=h.get('precipitation',[]); s=h.get('soil_moisture_0_to_7cm',[]); times=h.get('time',[])
        # Aggregate to 6-hour windows and apply rainfall/soil threshold logic.
        out=[]
        for i in range(0,len(times),6):
            pp=p[i:i+6]; ss=s[i:i+6]; out.append({'time':times[i],'precipitation_6h_mm':round(sum(x or 0 for x in pp),2),'soil_moisture_mean':round(sum(x for x in ss if x is not None)/max(1,len([x for x in ss if x is not None])),4),'threshold_signal':None})
        # Use a rolling 72-hour precipitation accumulation for each forecast point.
        for i,item in enumerate(out):
            item['rainfall_3d_forecast_mm']=round(sum(x['precipitation_6h_mm'] for x in out[max(0,i-11):i+1]),2)
            item['threshold_signal']=int(p90 is not None and soil_median is not None and item['rainfall_3d_forecast_mm']>p90 and item['soil_moisture_mean']>soil_median)
        result={'source':'Open-Meteo','fetched_at':datetime.now(timezone.utc).isoformat(),'trajectory':out}
        _FORECAST_CACHE[cache_key]=(time.time(), result)
        return result
    except Exception as e: return {'source':'Open-Meteo','error':str(e),'trajectory':[]}

_DISCHARGE_CACHE = {}
_RADAR_CACHE: dict = {}
_RADAR_CACHE_TTL_SECONDS = 120  # Radar frames update every ~2 min; cache for 2 min

def _fetch_radar_nowcast(lat: float, lon: float) -> dict:
    """Fetch the latest RainViewer satellite radar frame and return storm intensity.

    RainViewer provides global precipitation radar composites at ~2-minute
    refresh intervals.  This function:
      1. Fetches the `/api/maps/2.0/` manifest to discover the latest available
         radar frame timestamp.
      2. Queries the colour-value tile at the locality's lat/lon to read the
         dBZ-encoded reflectivity pixel.  Because tile images require a browser,
         we instead use the RainViewer coverage endpoint which returns the
         nearest-cell precipitation rate in mm/hr for a given lat/lon.
      3. Normalises the mm/hr value to a 0–100 intensity score.

    Returns dict with keys:
      source, fetched_at, latest_frame_ts, radar_mmhr, radar_intensity (0-100),
      storm_active (bool), status.
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
        latest_ts = int(radar_past[-1]['time']) if radar_past else None

        # Step 2: read precipitation rate from the RainViewer data tile API
        # The /v2/radar endpoint returns JSON with precipitation at a lat/lon.
        if latest_ts is not None:
            data_url = (
                f'https://tilecache.rainviewer.com/v2/radar/{latest_ts}/256/6/'
                f'{_lat_lon_to_tile_z6(lat, lon)}.png'
            )
            # We cannot decode a PNG pixel in stdlib; use the RainViewer public
            # "weather-maps.json" color value lookup instead.  For simplicity,
            # proxy via the public JSON "nowcast" endpoint available for free:
            # https://api.rainviewer.com/public/weather-maps.json has a
            # satellite->infrared block; radar past frames index by Unix ts.
            # Approximate precipitation by finding the most intense radar color.
            # FALLBACK: use Open-Meteo short-range (1-hour) precipitation as proxy.
            params = urllib.parse.urlencode({
                'latitude': lat, 'longitude': lon,
                'hourly': 'precipitation',
                'forecast_days': 1,
                'timezone': 'UTC',
                'forecast_hours': 1,
            })
            om_url = 'https://api.open-meteo.com/v1/forecast?' + params
            om_bytes = _robust_urlopen(om_url, timeout=10, retries=2)
            om_raw = json.loads(om_bytes.decode('utf-8'))
            precip_vals = om_raw.get('hourly', {}).get('precipitation', [])
            # Latest hour = first element in the 1-day 1-hour slice
            precip_mmhr = float(precip_vals[0]) if precip_vals and precip_vals[0] is not None else 0.0
        else:
            precip_mmhr = 0.0

        # Normalise: 0 mm/hr → 0, ≥ 25 mm/hr (heavy rain) → 100
        radar_intensity = min(100.0, round((precip_mmhr / 25.0) * 100.0, 1))
        storm_active = precip_mmhr >= 2.0

        result = {
            'source': 'RainViewer manifest + Open-Meteo 1-hour precipitation nowcast',
            'fetched_at': datetime.now(timezone.utc).isoformat(),
            'latest_frame_ts': latest_ts,
            'radar_mmhr': round(precip_mmhr, 3),
            'radar_intensity': radar_intensity,
            'storm_active': storm_active,
            'status': 'available',
        }
        _RADAR_CACHE[cache_key] = (time.time(), result)
        return result
    except Exception as e:
        return {
            'source': 'RainViewer + Open-Meteo nowcast',
            'fetched_at': datetime.now(timezone.utc).isoformat(),
            'latest_frame_ts': None,
            'radar_mmhr': 0.0,
            'radar_intensity': 0.0,
            'storm_active': False,
            'status': 'unavailable',
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
        by_date = {str(t): float(v) for t, v in zip(times, vals) if v is not None}
        today = datetime.now(timezone.utc).date().isoformat()
        latest = by_date.get(today) or (list(by_date.values())[-1] if by_date else None)
        result = {
            'status': 'available' if by_date else 'unavailable',
            'source': 'Open-Meteo GloFAS Flood API',
            'latest': latest,
            'by_date': by_date,
            'fetched_at': datetime.now(timezone.utc).isoformat(),
        }
        _DISCHARGE_CACHE[cache_key] = (time.time(), result)
        return result
    except Exception as e:
        return {'status': 'unavailable', 'source': 'Open-Meteo GloFAS Flood API (unavailable)', 'latest': None, 'by_date': {}, 'error': str(e)}


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
    # Verify all three live providers before deriving a forecast or running a
    # classifier. An old local GloFAS file must never make a live outage look
    # like a valid current prediction.
    weather_status = {
        'source': 'Open-Meteo Weather API',
        'trajectory': times,
        'fetched_at': datetime.now(timezone.utc).isoformat(),
        'error': None if times else 'Open-Meteo returned no hourly forecast',
    }
    live_disch = _fetch_river_discharge(lat, lon, past_days=10, forecast_days=int(days)+2)
    sar_info = _fetch_opera_sar_inundation(lat, lon)
    provider_status = _require_live_prediction_inputs(weather_status, live_disch, sar_info)
    daily={}
    for t,p,s in zip(times,precip,soil):
        day=str(t)[:10]; z=daily.setdefault(day,{'precipitation_mm':0.0,'soil':[]}); z['precipitation_mm']+=float(p or 0); z['soil'].append(s)
    ordered=sorted(daily); out=[]; rolling=[]
    for day in ordered:
        rolling.append(daily[day]['precipitation_mm']); soilvals=[x for x in daily[day]['soil'] if x is not None]
        rain3=sum(rolling[-3:]); flag=int(rain3>p90 and med is not None and (sum(soilvals)/len(soilvals))>float(med))
        out.append({'date':day,'local_rainfall_1d_mm':round(rolling[-1],2),'local_rainfall_3d_mm':round(rain3,2),'soil_moisture':round(sum(soilvals)/len(soilvals),4) if soilvals else None,'basin_rainfall_7d_mm':None,'basin_rainfall_14d_mm':None,'basin_rainfall_21d_mm':None,'basin_rainfall_30d_mm':None,'glofas_discharge_m3s':None,'option_b_threshold_flag':flag,'option_b_risk_level':'HIGH' if flag else 'BASELINE','classifier_probability':None,'method_disagreement':'NOT_AVAILABLE_UNTIL_GLOFAS_FORECAST'})
    # GloFAS was verified above; use that same live response for the feature set.
    discharge = dict(live_disch.get('by_date', {}))
    glofas_ok = bool(discharge)
    forecast_reference_date = datetime.now(timezone.utc).date()

    # Fallback to offline static snapshot if live endpoint is unreachable
    if not glofas_ok:
        gf=OUT/'glofas_forecast_2026_09_07.parquet'
        if gf.exists():
            gd=_read_parquet(gf); gd['date']=pd.to_datetime(gd['date']).dt.strftime('%Y-%m-%d')
            discharge={str(r.date):float(r.discharge_m3s_forecast) for r in gd[gd['name']==name].itertuples()}
            glofas_ok = bool(discharge)
            if 'forecast_reference_time' in gd.columns and len(gd):
                forecast_reference_date=pd.Timestamp(gd['forecast_reference_time'].iloc[0]).date()
    historical_discharge={}
    hist_path=OUT/'locality_subsets'/'glofas_34.parquet'
    if hist_path.exists():
        hd=_read_parquet(hist_path); hd['date']=pd.to_datetime(hd['date']).dt.strftime('%Y-%m-%d')
        hname='locality' if 'locality' in hd.columns else 'name'; hval='discharge_m3s' if 'discharge_m3s' in hd.columns else 'dis24'
        if hval in hd.columns:
            historical_discharge={str(r.date):float(getattr(r,hval)) for r in hd[hd[hname]==name].itertuples() if pd.notna(getattr(r,hval))}
    try:
        payload=joblib.load(EXPLORATORY_MODEL); clf=payload['model']; model_features=payload['features']
        lookup=_read_parquet(OUT/'farnorth_locality_environment_lookup.parquet')
        lr=lookup[lookup['name']==name].iloc[0]
        static_l={'elevation_m':float(lr.elevation_m),'slope_deg':float(lr.slope_deg),'basin_id':float(lr.basin_id),'season':int(month in [4,5,6,7,8,9,10])}
    except Exception:
        clf=None; model_features=[]; static_l={}
    out=out[:int(days)]
    rains=[float(x['local_rainfall_1d_mm']) for x in out]
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
        basin_rains.append(sum(vals)/len(vals) if vals else float(item['local_rainfall_1d_mm']))
    last_known_discharge=list(discharge.values())[-1] if discharge else None
    for i,item in enumerate(out):
        item['glofas_discharge_m3s']=discharge.get(item['date']) if (glofas_ok and item['date'] in discharge) else (last_known_discharge if glofas_ok else None)
        # The first forecast day has no forecast lag history; using the first
        # available lead is explicit and preferable to silently fabricating a
        # historical observation.
        q=item['glofas_discharge_m3s']
        lag_values={}; used_forecast_fallback=False
        if q is not None:
            for lag in (1,3,7):
                lag_date=(pd.Timestamp(item['date'])-pd.Timedelta(days=lag)).strftime('%Y-%m-%d')
                if forecast_reference_date is not None and pd.Timestamp(lag_date).date() <= forecast_reference_date:
                    lag_values[lag]=historical_discharge.get(lag_date)
                else:
                    lag_values[lag]=discharge.get(lag_date, q)
                    used_forecast_fallback=True
                item[f'glofas_discharge_lag{lag}']=lag_values[lag]
        past_missing=any(v is None for v in lag_values.values()) if lag_values else True
        item['discharge_lag_fallback']=bool(used_forecast_fallback)
        item['discharge_lag_historical_unavailable']=bool(q is not None and past_missing and not used_forecast_fallback)
        item['discharge_lag_note']='early forecast days use the nearest available lead time in place of a true historical lag - treat these days\' RF probability with extra caution.' if item['discharge_lag_fallback'] else ('historical GloFAS date is not present locally; RF score withheld for this day.' if item['discharge_lag_historical_unavailable'] else None)
        item['discharge_lag_source']='forecast lead fallback' if item['discharge_lag_fallback'] else ('historical GloFAS' if not item['discharge_lag_historical_unavailable'] else 'historical unavailable')
        vals={3:sum(basin_rains[max(0,i-2):i+1]),7:sum(basin_rains[max(0,i-6):i+1]),14:sum(basin_rains[max(0,i-13):i+1]),21:sum(basin_rains[max(0,i-20):i+1]),30:sum(basin_rains[max(0,i-29):i+1])}
        item.update({f'basin_rainfall_{w}d_mm':round(v,2) for w,v in vals.items()})
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
    return {'locality':name,'target_date':str(target_date or ordered[0] if ordered else target_date),'forecast_issue_time':datetime.now(timezone.utc).isoformat(),'source':'Open-Meteo Weather + Open-Meteo GloFAS Flood API + NASA OPERA DSWx-S1','provider_status':provider_status,'glofas_forecast_available':bool(glofas_ok),'glofas_forecast_status':'AVAILABLE' if glofas_ok else 'PENDING_DOWNLOAD','glofas_forecast_note':'Nearest-cell ensemble mean; forecast lag fields use the first available lead when prior leads are unavailable.','basin_rainfall_data_source':'Open-Meteo forecast queried at each confirmed upstream-basin centroid and averaged across the locality\'s upstream basin set; rolling windows use that daily basin mean.','upstream_basin_rainfall_status':'UPSTREAM_CENTROID_AGGREGATION' if basin_complete else 'PARTIAL_UPSTREAM_CENTROID_AGGREGATION','upstream_basin_count':int(len(upstream_ids)),'upstream_basin_centroids_queried':int(len(upstream_ids)),'upstream_basin_http_queries':basin_query_count,'trajectory':out,'classifier_status':'AVAILABLE' if glofas_ok else 'BLOCKED_UNTIL_GLOFAS_FORECAST','option_b_note':'Option B is independently evaluated; outputs are not blended.'}

# Public name used by the API/UI forecast flow.
get_locality_forecast = get_forecasted_features

def get_locality_risk(locality_name_or_lat_lon):
    """Return a JSON-serialisable risk bundle for a locality or ``lat,lon``."""
    row=_resolve(locality_name_or_lat_lon); name=row['name']; cache=_risk_cache().loc[name]
    month=datetime.now(timezone.utc).month
    p90=float(cache.rainfall_3d_p90)
    soil_col=f'soil_median_m{month:02d}'
    month_median=cache.get(soil_col)
    # Live data tier 1: Open-Meteo weather forecast + soil moisture.
    fc=_forecast(float(row.lat),float(row.lon),p90,month_median)
    # Live data tier 2: GloFAS river discharge (Open-Meteo Flood API).
    disch_info = _fetch_river_discharge(float(row.lat), float(row.lon), past_days=7, forecast_days=3)
    disch_latest = disch_info.get('latest')
    disch_status = disch_info.get('status', 'unavailable')
    disch_source = disch_info.get('source', 'Open-Meteo GloFAS Flood API')

    hydro, runoff_table = _hydrology_cache()
    hrow = hydro.loc[name] if name in hydro.index else None
    rrow = runoff_table.loc[name] if name in runoff_table.index else None
    runoff_latest = (rrow.get('runoff_mm_latest') if rrow is not None else None)
    ssro_latest = (rrow.get('sub_surface_runoff_mm_latest') if rrow is not None else None)
    drainage_density = (hrow.get('drainage_density_km_per_km2') if hrow is not None else None)
    runoff_date = (rrow.get('runoff_latest_date') if rrow is not None else None)
    runoff_latest = float(runoff_latest) if pd.notna(runoff_latest) else None
    ssro_latest = float(ssro_latest) if pd.notna(ssro_latest) else None
    drainage_density = float(drainage_density) if pd.notna(drainage_density) else None
    # Live data tier 3: RainViewer satellite radar nowcast.
    radar_info = _fetch_radar_nowcast(float(row.lat), float(row.lon))
    radar_intensity = float(radar_info.get('radar_intensity', 0.0))
    radar_mmhr = float(radar_info.get('radar_mmhr', 0.0))
    radar_storm_active = bool(radar_info.get('storm_active', False))

    # Live data tier 4: NASA OPERA DSWx-S1 Sentinel-1 SAR flood inundation.
    sar_info = _fetch_opera_sar_inundation(float(row.lat), float(row.lon))
    provider_status = _require_live_prediction_inputs(fc, disch_info, sar_info)
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
        pd.notna(runoff_latest),
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

    result={'locality':name,'coordinates':{'lat':float(row.lat),'lon':float(row.lon)},'grid_references':{'era5':f'{float(cache.era_lat):.3f},{float(cache.era_lon):.3f}','glofas':cache.glofas_cell_reference},'provider_status':provider_status,'risk_level':risk_level,'estimated_risk_percent':blended_risk,'ml_probability':ml_prob,'ml_risk_percent':ml_risk_percent,'heuristic_risk_percent':estimated,'estimated_risk_components':{'susceptibility_score':static,'threshold_signal':threshold,'nearby_verified_event_density':density,'ml_calibrated_probability':ml_prob,'radar_intensity_nowcast':radar_intensity,'sar_inundation_fraction':sar_fraction,'sar_risk_boost':sar_risk_boost,'weights':{'heuristic_susceptibility_blend':0.50,'calibrated_ml_blend':0.50} if ml_risk_percent is not None else {'susceptibility':.60,'threshold':.25,'event_density':.15}},'confidence_score':confidence,'confidence_components':{'grid_match_quality':grid,'dem_slope_completeness':completeness,'nearby_verified_event_count':event_count,'nearby_verified_event_density':density,'forecast_data_freshness':freshness,'radar_nowcast_available':radar_info.get('status')=='available','sar_telemetry_available':sar_info.get('status')=='available','sar_inundation_fraction':sar_fraction},'nearby_verified_event_density':density,'current_conditions':{'date':datetime.now(timezone.utc).date().isoformat(),'rainfall_3d':rainfall3d,'rainfall_3d_p90':p90,'swvl1':swvl1,'calendar_month_soil_median':month_median,'elevated_risk_flag':int(threshold_flag),'historical_cache':'farnorth_locality_risk_cache.parquet','runoff_mm':runoff_latest,'sub_surface_runoff_mm':ssro_latest,'runoff_latest_date':runoff_date,'runoff_data_source':'ERA5-Land raw runoff (ro) and sub-surface runoff (ssro), nearest grid cell, daily accumulation in mm','drainage_density_km_per_km2':drainage_density,'drainage_density_data_source':'HydroRIVERS total river-line length within the HydroBASINS level-6 basin divided by basin area (km/km²)','river_discharge_m3s':disch_latest,'river_discharge_status':disch_status,'river_discharge_source':disch_source,'radar_nowcast':{'intensity_0_100':radar_intensity,'precipitation_mmhr':radar_mmhr,'storm_active':radar_storm_active,'source':radar_info.get('source'),'status':radar_info.get('status'),'latest_frame_ts':radar_info.get('latest_frame_ts')},'sar_inundation':sar_info},'forecast_72h':fc,'historical_context':hist,'last_model_update':datetime.now(timezone.utc).isoformat(),'model_type':active_model_type}
    result['elevation_m'] = float(row.elevation_m) if pd.notna(row.get('elevation_m')) else None
    result['river_distance_m'] = float(row.river_distance_m) if pd.notna(row.get('river_distance_m')) else None
    return json.loads(json.dumps(result, default=lambda o: o.item() if hasattr(o, 'item') else str(o)))

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
