"""Build an inspectable Far North GloFAS event feature table.

GloFAS exports use a hydrological-year coordinate (02 Jan ... 01 Jan).
The loader shifts valid_time back one day before any event-date lookup.
"""
from pathlib import Path
import re, unicodedata
import numpy as np
import pandas as pd
import xarray as xr

ROOT=Path(__file__).resolve().parents[1]
EXT=ROOT.parent
GLO=EXT/'GLOFAS-datasets'/'far-north'
CAT=ROOT/'data_quality'/'farnorth_consolidation'/'canonical_flood_events_farnorth.csv'
GAZ=EXT/'boundaries-data'/'gazetteer_farnorth.csv'
OUT=ROOT/'data_quality'/'farnorth_consolidation'/'farnorth_event_discharge_features.csv'

def norm(x):
    return re.sub(r'[^a-z0-9]+','',unicodedata.normalize('NFKD',str(x)).encode('ascii','ignore').decode().lower())

def main():
    gaz=pd.read_csv(GAZ)
    ncol=next(c for c in gaz.columns if c.lower() in ('name','locality','locality_name'))
    latcol=next(c for c in gaz.columns if c.lower() in ('lat','latitude'))
    loncol=next(c for c in gaz.columns if c.lower() in ('lon','longitude','lng'))
    gaz['_n']=gaz[ncol].map(norm)
    # Keep only the requested event dates/lags in memory; the full multi-year
    # raster is deliberately never materialized as a pandas table.
    opened={}
    def value(day, lat, lon):
        if pd.isna(day) or not np.isfinite(lat): return np.nan, np.nan, np.nan
        raw=pd.Timestamp(day)+pd.Timedelta(days=1) # inverse of normalization
        f=GLO/f'data_{raw.year}.nc'
        try:
            if f not in opened: opened[f]=xr.open_dataset(f)
            ds=opened[f]
            target=pd.Timestamp(raw).to_datetime64()
            ix=int(np.argmin(np.abs(ds.valid_time.values-target)))
            iy=int(np.argmin(np.abs(ds.latitude.values-lat))); jx=int(np.argmin(np.abs(ds.longitude.values-lon)))
            v=float(ds.avg_dis.values[ix,iy,jx]); return v,float(ds.latitude.values[iy]),float(ds.longitude.values[jx])
        except Exception: return np.nan,np.nan,np.nan
    cat=pd.read_csv(CAT)
    cat=cat[cat.event_start_date.str[:4].astype(int).between(2005,2025)].copy()
    # Audited footprint overrides for composite/truncated catalogue fields.
    # These are explicit proxies, never silent substitutions.
    overrides={
        'FNR-FLD-2013-002':'Dougui',
        'FNR-FLD-2021-001':'Mora', # Seradoumda absent; Mora is named road context proxy
        'FNR-FLD-2021-002':'Yagoua', # Mayo-Danay division centroid proxy
        'FNR-FLD-2025-005':'Hilé - Alifa',
    }
    out=[]
    for _,e in cat.iterrows():
        raw=str(e.locality_name); candidates=[]
        if e.canonical_event_id in overrides:
            raw=overrides[e.canonical_event_id]
        for g in raw.split(';'):
            q=norm(g)
            h=gaz[gaz['_n'].eq(q)]
            if h.empty: h=gaz[gaz['_n'].str.contains(q,regex=False)] if q else h
            if not h.empty: candidates.append(h.iloc[0])
        if candidates:
            g=candidates[0]; lat=float(g[latcol]); lon=float(g[loncol]); locality=str(g[ncol]); reason=''
            if e.canonical_event_id=='FNR-FLD-2021-002': reason='division-level approximation (Mayo-Danay anchored at Yagoua)'
        else:
            lat=lon=np.nan; locality=raw; reason='No exact locality match in Far North gazetteer'
        if np.isfinite(lat):
            day=pd.to_datetime(str(e.event_start_date),errors='coerce')
            vals=[]
            glat=glon=np.nan
            for lag in (0,1,3,7):
                v,glat,glon=value(day-pd.Timedelta(days=lag),lat,lon); vals.append(v)
            dist=float(np.sqrt((glat-lat)**2+(glon-lon)**2)) if np.isfinite(glat) else np.nan
            reason='' if all(pd.notna(vals)) else 'Date absent or discharge value null after normalized lookup'
            precision=('division-level approximation' if e.canonical_event_id=='FNR-FLD-2021-002' else ('locality proxy (Seradoumda absent; Mora context)' if e.canonical_event_id=='FNR-FLD-2021-001' else 'gazetteer locality'))
            out.append([e.canonical_event_id,locality,str(e.event_start_date),*vals,glat,glon,dist,precision,reason])
        else: out.append([e.canonical_event_id,locality,str(e.event_start_date),np.nan,np.nan,np.nan,np.nan,np.nan,np.nan,np.nan,'unresolved',reason])
    cols=['event_id','locality','event_date','discharge_m3s','discharge_lag1','discharge_lag3','discharge_lag7','glofas_grid_lat','glofas_grid_lon','match_distance_deg','location_precision','join_note']
    for ds in opened.values(): ds.close()
    pd.DataFrame(out,columns=cols).to_csv(OUT,index=False)
    print(OUT, len(out), 'complete', int(pd.DataFrame(out,columns=cols)[['discharge_m3s','discharge_lag1','discharge_lag3','discharge_lag7']].notna().all(axis=1).sum()))

if __name__=='__main__': main()
