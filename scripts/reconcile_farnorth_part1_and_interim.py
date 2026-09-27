#!/usr/bin/env python3
"""Far North only: correct the canonical event logic and build interim warning outputs.

This is a physically-derived warning system, not a supervised classifier.
"""
from pathlib import Path
import re
import unicodedata
import numpy as np
import pandas as pd
import geopandas as gpd
import xarray as xr
import duckdb

ROOT=Path(__file__).resolve().parents[1]
BASE=Path('/home/ongou/Desktop/projects/end-of -year-defence')
OUT=ROOT/'data_quality'/'farnorth_consolidation'
CANON=OUT/'canonical_flood_events_farnorth.csv'
GAZ=BASE/'boundaries-data/gazetteer_farnorth.csv'
DEM=BASE/'DEM (elevation)-datasets/DEM_slope_localities_FarNorth_fixed.csv'
ERA=BASE/'ERA5-datasets/Far_North'
RIVERS=BASE/'HydroBasins-datasets/HydroRIVERS_v10_af_shp/HydroRIVERS_v10_af.shp'
CHIRPS=[BASE/'CHIRPS-datasets/far-north/CHIRPS_FarNorth_fixed_2015_2019.csv',BASE/'CHIRPS-datasets/far-north/CHIRPS_FarNorth_fixed_2020_2025.csv']

def norm(v):
    v=unicodedata.normalize('NFKD',str(v)).encode('ascii','ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+','',v)

def reconcile_catalogue():
    d=pd.read_csv(CANON)
    # The late October Makary/Blangoua reporting is part of the prolonged 2020
    # August–November flood season. It is retained as supporting evidence only.
    d=d[d.canonical_event_id.ne('FNR-FLD-2020-004')].copy()
    e=d.loc[d.canonical_event_id.eq('FLD-CMR-2020-001')].index
    d.loc[e,'event_end_date']='2020-11'
    d.loc[e,'division']='Logone-et-Chari; Mayo-Danay; Mayo-Kani; Mayo-Sava; Diamaré'
    d.loc[e,'locality_name']='Blangoua; Kousseri; Makary; Logone-Birni'
    d.loc[e,'evidence_summary']=d.loc[e,'evidence_summary'].fillna('')+' Refined: late-October/November impacts in Makary and Blangoua are continuation of the 2020 season, not a new label.'
    # The 2019 evidence establishes two temporally separated river overflows
    # with distinct administrative footprints. Split the pre-existing broad
    # September-November episode into the documented 1 Oct and 14 Oct pulses.
    d=d[d.canonical_event_id.ne('FLD-CMR-2019-001')].copy()
    rows=pd.DataFrame([
      {'canonical_event_id':'FNR-FLD-2019-001','event_status':'VERIFIED_FLOOD_EVENT','event_start_date':'2019-10-01','event_end_date':'2019-10-01','date_precision':'DAY','locality_name':'Zina commune','division':'Logone-et-Chari','region':'Far North','latitude':None,'longitude':None,'location_precision':'ADMINISTRATIVE_FOOTPRINT','source_document_title':'International Charter for Space and Major Disasters, Activation 627; ACAPS','source_document_url':'https://disasterscharter.org/activations/flood-flash-in-cameroon-activation-627-','source_event_id':'split-from-FLD-CMR-2019-001','duplicate_of':None,'evidence_summary':'Logone River burst its banks on 1 October 2019, flooding the Zina valley, Logone-et-Chari.','supporting_evidence':'ACAPS and IFRC MDRCM028 corroborate the Zina/Maga impacts.','evidence_quality':'HIGH'},
      {'canonical_event_id':'FNR-FLD-2019-002','event_status':'VERIFIED_FLOOD_EVENT','event_start_date':'2019-10-14','event_end_date':'2019-10-14','date_precision':'DAY','locality_name':'Mayo-Danay administrative footprint','division':'Mayo-Danay','region':'Far North','latitude':None,'longitude':None,'location_precision':'ADMINISTRATIVE_FOOTPRINT','source_document_title':'International Charter for Space and Major Disasters, Activation 627; IFRC MDRCM028','source_document_url':'https://disasterscharter.org/activations/flood-flash-in-cameroon-activation-627-','source_event_id':'split-from-FLD-CMR-2019-001','duplicate_of':None,'evidence_summary':'A second Logone overflow on 14 October 2019 affected Mayo-Danay; Charter reports the continuing crisis separately from the 1 October Zina pulse.','supporting_evidence':'IFRC MDRCM028 provides named Maga, Kai-Kai and Yagoua impact evidence.','evidence_quality':'HIGH'},
    ])
    d=pd.concat([d,rows],ignore_index=True,sort=False)
    # Strengthen, but do not duplicate, the 2024 episode.
    e=d.loc[d.canonical_event_id.eq('FLD-CMR-2024-001')].index
    citations=('Evidence quality HIGH: International independent corroboration — CERF Rapid Response allocation (~US$4m; 450,000+ affected); '
               'Action contre la Faim reports 198,000 affected in Mayo-Danay and 156,000 in Logone-et-Chari, identifying Blangoua and Kousseri as hardest hit; '
               'WFP reports 400,000+ affected and 56,000+ homes destroyed.')
    d.loc[e,'evidence_summary']=d.loc[e,'evidence_summary'].fillna('')+' '+citations
    d.loc[e,'supporting_evidence']='CERF; Action contre la Faim (23 Oct 2024); WFP (12 Nov 2024); IFRC; UNFPA; UNICEF'
    d.loc[e,'evidence_quality']='VERY_HIGH'
    d['evidence_quality']=d.get('evidence_quality','HIGH').fillna('HIGH')
    d=d.drop_duplicates('canonical_event_id',keep='last').sort_values(['event_start_date','canonical_event_id'])
    d.to_csv(CANON,index=False)
    return d

def make_static(gaz):
    dem=pd.read_csv(DEM)[['name','lat','lon','elevation_m','slope_deg']]
    # DEM source is keyed to the same location coordinates; retain each unique
    # locality point rather than unreliable loose name-only matching.
    g=gaz[['name','lat','lon','division']].copy()
    # The two GEE exports preserve names but round coordinates differently;
    # names are unique in both 3,860-row files and are the stable key.
    g=g.merge(dem[['name','elevation_m','slope_deg']],on='name',how='left',validate='one_to_one')
    if g.elevation_m.isna().any() or g.slope_deg.isna().any():
        raise ValueError('DEM join left null locality values')
    pts=gpd.GeoDataFrame(g,geometry=gpd.points_from_xy(g.lon,g.lat),crs='EPSG:4326').to_crs('EPSG:32633')
    rv=gpd.read_file(RIVERS,bbox=(12.5,9.5,16.5,13.5)).to_crs('EPSG:32633')
    nearest=gpd.sjoin_nearest(pts,rv[['geometry']],how='left',distance_col='river_distance_m')
    return pd.DataFrame(nearest.drop(columns='geometry'))

def era_cell_daily(localities):
    # Map each locality to its nearest ERA5-Land cell, then create one daily
    # soil table per unique cell, avoiding a 3,860 x 4-hour intermediate table.
    first=xr.open_dataset(sorted(ERA.glob('*.nc'))[0])
    lats=first.latitude.values; lons=first.longitude.values
    localities=localities.copy()
    localities['era_lat']=localities.lat.map(lambda x: float(lats[np.abs(lats-x).argmin()]))
    localities['era_lon']=localities.lon.map(lambda x: float(lons[np.abs(lons-x).argmin()]))
    cells=localities[['era_lat','era_lon']].drop_duplicates().reset_index(drop=True)
    frames=[]
    for p in sorted(ERA.glob('*.nc')):
        ds=xr.open_dataset(p)
        ds_lats=ds.latitude.values; ds_lons=ds.longitude.values
        dates=pd.to_datetime(ds.valid_time.values).normalize()
        # 4 hourly values -> one daily mean, selected only at required cells.
        arr=ds['swvl1'].values
        for day in np.unique(dates):
            mean=arr[dates==day].mean(axis=0)
            ilat=np.abs(ds_lats[:,None]-cells.era_lat.to_numpy()).argmin(axis=0)
            ilon=np.abs(ds_lons[:,None]-cells.era_lon.to_numpy()).argmin(axis=0)
            # Store actual grid coordinates from each file: a few monthly
            # files have a clipped edge grid and must not inherit indices from
            # January 2015.
            frames.append(pd.DataFrame({'date':day,'era_lat':ds_lats[ilat],'era_lon':ds_lons[ilon],'swvl1':mean[ilat,ilon]}))
        ds.close()
    soil=pd.concat(frames,ignore_index=True)
    soil.to_parquet(OUT/'farnorth_era5_soil_daily_cells.parquet',index=False)
    return localities,soil

def build_interim(canonical):
    gaz=pd.read_csv(GAZ)
    loc=make_static(gaz)
    loc,soil=era_cell_daily(loc)
    loc.to_parquet(OUT/'farnorth_locality_environment_lookup.parquet',index=False)
    con=duckdb.connect(str(OUT/'farnorth_interim.duckdb'))
    con.execute('PRAGMA threads=4')
    con.execute('PRAGMA memory_limit=\'5GB\'')
    chirps_sql='['+','.join("'"+str(x).replace("'","''")+"'" for x in CHIRPS)+']'
    con.execute(f"CREATE OR REPLACE VIEW rain AS SELECT CAST(date AS DATE) date, name, lat, lon, CAST(first AS DOUBLE) rainfall_mm FROM read_csv_auto({chirps_sql}, union_by_name=true)")
    # Determine the wet season from actual local CHIRPS monthly means.
    monthly=con.execute('SELECT month(date) AS month_num, avg(rainfall_mm) AS avg_rainfall_mm FROM rain GROUP BY 1 ORDER BY 1').df()
    threshold=.75*monthly.avg_rainfall_mm.max()
    wet=monthly.loc[monthly.avg_rainfall_mm>=threshold,'month_num'].astype(int).tolist()
    monthly.to_csv(OUT/'farnorth_chirps_monthly_climatology.csv',index=False)
    con.register('loc',loc)
    con.register('soil',soil)
    con.execute('CREATE OR REPLACE TABLE locality_soil AS SELECT l.name,l.lat,l.lon,l.era_lat,l.era_lon,s.date,s.swvl1 FROM loc l JOIN soil s USING(era_lat,era_lon)')
    wet_sql=','.join(map(str,wet))
    static=con.execute(f'''WITH rain7 AS (
      SELECT name, date, sum(rainfall_mm) OVER (PARTITION BY name ORDER BY date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS rainfall_7d FROM rain),
      r AS (SELECT name, quantile_cont(rainfall_7d,0.9) rainfall_7d_p90 FROM rain7 GROUP BY name),
      s AS (SELECT name, avg(swvl1) soil_wet_season_swvl1 FROM locality_soil WHERE month(date) IN ({wet_sql}) GROUP BY name)
      SELECT l.*, r.rainfall_7d_p90, s.soil_wet_season_swvl1 FROM loc l LEFT JOIN r USING(name) LEFT JOIN s USING(name)''').df()
    if static[['rainfall_7d_p90','soil_wet_season_swvl1']].isna().any().any(): raise ValueError('missing static climate values')
    for raw,fac,invert in [('elevation_m','elevation_factor',True),('slope_deg','slope_factor',True),('river_distance_m','drainage_proximity_factor',True),('soil_wet_season_swvl1','soil_saturation_factor',False),('rainfall_7d_p90','rainfall_intensity_factor',False)]:
      a=static[raw]; z=(a-a.min())/(a.max()-a.min()) if a.max()>a.min() else a*0
      static[fac]=1-z if invert else z
    fs=['elevation_factor','slope_factor','drainage_proximity_factor','soil_saturation_factor','rainfall_intensity_factor']
    static['susceptibility_score']=100*static[fs].mean(axis=1)
    static['susceptibility_percentile']=static.susceptibility_score.rank(pct=True)*100
    static['scope_label']='Far North region only, 2015-2025 — interim rules-based system, not a trained classifier'
    static.to_csv(OUT/'farnorth_susceptibility_scores.csv',index=False)
    # Full daily rule: local rainfall 3-day p90 AND local calendar-month median soil saturation.
    con.register('static',static[['name','lat','lon','era_lat','era_lon']])
    con.execute('''CREATE OR REPLACE TABLE daily_flags AS WITH r AS (
      SELECT date,name,lat,lon,rainfall_mm, sum(rainfall_mm) OVER (PARTITION BY name ORDER BY date ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) rainfall_3d FROM rain),
      t AS (SELECT name, quantile_cont(rainfall_3d,0.9) rainfall_3d_p90 FROM r GROUP BY name),
      x AS (SELECT r.*,s.swvl1, median(s.swvl1) OVER (PARTITION BY r.name,month(r.date)) monthly_swvl1_median FROM r JOIN locality_soil s USING(name,date))
      SELECT x.name,x.lat,x.lon,x.date,x.rainfall_3d,x.swvl1,t.rainfall_3d_p90,x.monthly_swvl1_median,
      CASE WHEN x.rainfall_3d>t.rainfall_3d_p90 AND x.swvl1>x.monthly_swvl1_median THEN 1 ELSE 0 END elevated_risk_flag
      FROM x JOIN t USING(name)''')
    con.execute(f"COPY daily_flags TO '{OUT/'farnorth_daily_risk_flags.parquet'}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    # Validation is a descriptive nearest-locality/date check; broad-window
    # records remain transparent rather than being falsely precise.
    events=[]
    for _,e in canonical.iterrows():
      start=str(e.event_start_date)
      exact=len(start)>=10
      names=[x.strip() for x in str(e.locality_name).split(';') if x.strip() and x.strip()!='UNKNOWN']
      match=next((n for n in names if norm(n) in set(loc.name.map(norm))),None)
      events.append({'canonical_event_id':e.canonical_event_id,'event_start_date':start,'date_precision':e.date_precision,'event_locality':'; '.join(names),'matched_locality':match or 'NO_EXACT_LOCALITY_MATCH','validation_status':'CHECK_DAILY_FLAG' if exact and match else 'WINDOW_OR_FOOTPRINT_ONLY'})
    val=pd.DataFrame(events)
    con.register('val',val[val.validation_status.eq('CHECK_DAILY_FLAG')])
    v=con.execute('SELECT v.*,d.rainfall_3d,d.swvl1,d.elevated_risk_flag FROM val v LEFT JOIN daily_flags d ON v.matched_locality=d.name AND CAST(v.event_start_date AS DATE)=d.date').df()
    val=val.merge(v[['canonical_event_id','rainfall_3d','swvl1','elevated_risk_flag']],on='canonical_event_id',how='left')
    val.to_csv(OUT/'farnorth_interim_event_validation.csv',index=False)
    # A reproducible high-information sample: most recent elevated Kousseri day;
    # fall back to Kousseri maximum 3-day-rain day if no flag exists.
    sample=con.execute("SELECT * FROM daily_flags WHERE lower(name)='kousseri' ORDER BY elevated_risk_flag DESC,date DESC LIMIT 1").df()
    if sample.empty: sample=con.execute("SELECT * FROM daily_flags ORDER BY elevated_risk_flag DESC,rainfall_3d DESC LIMIT 1").df()
    sample=sample.merge(static[['name','susceptibility_score','susceptibility_percentile']],on='name',how='left')
    sample.to_csv(OUT/'farnorth_interim_warning_sample.csv',index=False)
    con.close()
    return wet,sample,static

def main():
    canonical=reconcile_catalogue()
    wet,sample,static=build_interim(canonical)
    summary=f'''# Far North region only, 2015-2025 — interim susceptibility and threshold warning system

This is a physically-derived **interim rules-based system, not a trained classifier**. Supervised training remains blocked because the reconciled catalogue has {len(canonical)} independent verified episodes, below the 30-event minimum.

## Method
- Static score: equal weights for elevation, slope, nearest-river proximity, wet-season ERA5-Land soil saturation and CHIRPS 7-day rainfall intensity climatology.
- Wet months derived from observed CHIRPS locality averages using >=75% of the maximum monthly mean: {wet}.
- Daily flag: rainfall_3d exceeds each locality's historic 90th percentile **and** swvl1 exceeds that locality's calendar-month median.

## Sample
{sample.to_markdown(index=False)}
'''
    (OUT/'farnorth_interim_susceptibility_validation.md').write_text(summary,encoding='utf-8')

if __name__=='__main__': main()
