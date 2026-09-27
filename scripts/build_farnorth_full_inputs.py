from pathlib import Path
import re,unicodedata
import numpy as np,pandas as pd,xarray as xr,geopandas as gpd
ROOT=Path(__file__).resolve().parents[1]; EXT=ROOT.parent
OUT=ROOT/'data_quality/farnorth_consolidation'; GLO=EXT/'GLOFAS-datasets'/'far-north'
CAT=pd.read_csv(OUT/'canonical_flood_events_farnorth.csv'); CAT=CAT[CAT.event_start_date.str[:4].astype(int).between(2005,2025)]
gaz=pd.read_csv(EXT/'boundaries-data/gazetteer_farnorth.csv')
def norm(x): return re.sub(r'[^a-z0-9]','',unicodedata.normalize('NFKD',str(x)).encode('ascii','ignore').decode().lower())
gaz['_n']=gaz.name.map(norm)
over={'FNR-FLD-2013-002':'Dougui','FNR-FLD-2021-001':'Mora','FNR-FLD-2021-002':'Yagoua','FNR-FLD-2025-005':'Hilé - Alifa'}
names=[]
for _,e in CAT.iterrows():
 q=over.get(e.canonical_event_id,str(e.locality_name).split(';')[0]); h=gaz[gaz._n.eq(norm(q))]
 if not h.empty: names.append(h.iloc[0].name)
sel=gaz.loc[sorted(set(names))].copy(); rows=[]
for f in sorted(GLO.glob('data_*.nc')):
 y=int(f.stem.split('_')[1])
 if y<2005 or y>2025: continue
 with xr.open_dataset(f) as ds:
  t=pd.to_datetime(ds.valid_time.values).normalize()-pd.Timedelta(days=1); a=ds.avg_dis.values
  for _,g in sel.iterrows():
   iy=int(np.argmin(abs(ds.latitude.values-float(g.lat)))); ix=int(np.argmin(abs(ds.longitude.values-float(g.lon))))
   rows.extend(zip(t,[g['name']]*len(t),a[:,iy,ix],[ds.latitude.values[iy]]*len(t),[ds.longitude.values[ix]]*len(t)))
d=pd.DataFrame(rows,columns=['date','locality','discharge_m3s','glofas_grid_lat','glofas_grid_lon']).sort_values(['locality','date'])
d['discharge_lag1']=d.groupby('locality').discharge_m3s.shift(1); d['discharge_lag3']=d.groupby('locality').discharge_m3s.shift(3); d['discharge_lag7']=d.groupby('locality').discharge_m3s.shift(7)
d.to_parquet(OUT/'farnorth_full_discharge_timeseries.parquet',index=False)
# Historical CHIRPS exports omitted from the interim DuckDB are appended here.
import duckdb
hist=['CHIRPS_FarNorth_2005_2007.csv','CHIRPS_FarNorth_2011_only.csv','CHIRPS_FarNorth_2012_2013.csv']
con=duckdb.connect(); vals=','.join("'"+str(x).replace("'","''")+"'" for x in sel['name'].tolist())
for fn in hist:
 p=EXT/'CHIRPS-datasets/far-north'/fn
 if p.exists():
  con.execute(f"COPY (select date,name,lat,lon,first as rainfall_mm from read_csv_auto('{p}',sample_size=10000) where name in ({vals})) TO '{OUT/'locality_subsets'/('hist_'+fn.replace('.csv','.parquet'))}' (FORMAT PARQUET)")
con.close()
parts=[pd.read_parquet(OUT/'locality_subsets/chirps_16.parquet')]+[pd.read_parquet(p) for p in (OUT/'locality_subsets').glob('hist_*.parquet')]
pd.concat(parts,ignore_index=True).drop_duplicates(['date','name']).to_parquet(OUT/'locality_subsets/chirps_16.parquet',index=False)
# Append historical ERA5 daily soil observations from the monthly NetCDF files.
eroot=EXT/'ERA5-datasets/Far_North'; erows=[]
for f in sorted(eroot.glob('ERA5_Far_North_*.nc')):
 y=int(f.name.split('_')[-2]);
 if y<2005 or y>2014: continue
 try:
  with xr.open_dataset(f) as ds:
   var=next((v for v in ds.data_vars if 'soil' in v or 'volumetric' in v or v=='swvl1'),None)
   if var is None: continue
   for _,g in sel.iterrows():
    iy=int(np.argmin(abs(ds.latitude.values-float(g.lat)))); ix=int(np.argmin(abs(ds.longitude.values-float(g.lon))))
    t=pd.to_datetime(ds.valid_time.values).normalize(); erows.extend(zip([g['name']]*len(t),[g.lat]*len(t),[g.lon]*len(t),t,ds[var].values[:,iy,ix]))
 except Exception: continue
if erows:
 old=pd.read_parquet(OUT/'locality_subsets/era5_16.parquet')
 histera=pd.DataFrame(erows,columns=['name','lat','lon','date','swvl1'])
 histera['era_lat']=histera['lat']; histera['era_lon']=histera['lon']
 cols=['name','lat','lon','era_lat','era_lon','date','swvl1']
 pd.concat([old[cols],histera[cols]],ignore_index=True).drop_duplicates(['name','date']).to_parquet(OUT/'locality_subsets/era5_16.parquet',index=False)
shp=next((EXT/'HydroBasins-datasets').rglob('*lev06*.shp')); bas=gpd.read_file(shp)[['HYBAS_ID','geometry']]
pts=gpd.GeoDataFrame(sel,geometry=gpd.points_from_xy(sel.lon,sel.lat),crs=4326); j=gpd.sjoin(pts,bas,predicate='within',how='left')
lookup=pd.read_parquet(OUT/'farnorth_locality_environment_lookup.parquet'); lookup=lookup.merge(j[['name','HYBAS_ID']].rename(columns={'HYBAS_ID':'basin_id'}),on='name',how='left'); lookup.to_parquet(OUT/'farnorth_locality_environment_lookup.parquet',index=False)
print('localities',len(sel),'discharge_rows',len(d),'null_discharge',int(d.discharge_m3s.isna().sum()),'basin_null',int(lookup.basin_id.isna().sum()))
