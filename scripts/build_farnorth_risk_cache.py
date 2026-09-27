#!/usr/bin/env python3
"""Build the compact historical cache used by the Far North risk engine."""
from pathlib import Path
import duckdb
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'data_quality'/'farnorth_consolidation'; DB=OUT/'farnorth_interim.duckdb'
def main():
 c=duckdb.connect(str(DB)); c.execute("PRAGMA threads=4"); c.execute("PRAGMA memory_limit='6GB'")
 c.execute('''CREATE OR REPLACE TABLE locality_risk_cache AS
 WITH r AS (
   SELECT name, date, sum(rainfall_mm) OVER(PARTITION BY name ORDER BY date ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) rainfall_3d
   FROM rain
 ), rp AS (SELECT name, quantile_cont(rainfall_3d,0.9) rainfall_3d_p90 FROM r GROUP BY name),
 sm AS (SELECT name, month(date) month_num, median(swvl1) soil_monthly_median FROM locality_soil GROUP BY name, month(date)),
 sp AS (SELECT name,
   max(CASE WHEN month_num=1 THEN soil_monthly_median END) soil_median_m01,
   max(CASE WHEN month_num=2 THEN soil_monthly_median END) soil_median_m02,
   max(CASE WHEN month_num=3 THEN soil_monthly_median END) soil_median_m03,
   max(CASE WHEN month_num=4 THEN soil_monthly_median END) soil_median_m04,
   max(CASE WHEN month_num=5 THEN soil_monthly_median END) soil_median_m05,
   max(CASE WHEN month_num=6 THEN soil_monthly_median END) soil_median_m06,
   max(CASE WHEN month_num=7 THEN soil_monthly_median END) soil_median_m07,
   max(CASE WHEN month_num=8 THEN soil_monthly_median END) soil_median_m08,
   max(CASE WHEN month_num=9 THEN soil_monthly_median END) soil_median_m09,
   max(CASE WHEN month_num=10 THEN soil_monthly_median END) soil_median_m10,
   max(CASE WHEN month_num=11 THEN soil_monthly_median END) soil_median_m11,
   max(CASE WHEN month_num=12 THEN soil_monthly_median END) soil_median_m12
 FROM sm GROUP BY name)
 SELECT s.*,rp.rainfall_3d_p90,l.era_lat,l.era_lon,l.lat,l.lon,l.division,l.elevation_m,l.slope_deg,l.river_distance_m,sc.susceptibility_score,sc.susceptibility_percentile,
        CAST(NULL AS VARCHAR) AS glofas_cell_reference
 FROM sp s JOIN rp USING(name) JOIN (SELECT * FROM read_parquet('''+repr(str(OUT/'farnorth_locality_environment_lookup.parquet'))+''') QUALIFY row_number() OVER (PARTITION BY name ORDER BY name)=1) l USING(name)
 JOIN (SELECT name, susceptibility_score, susceptibility_percentile FROM read_csv_auto('''+repr(str(OUT/'farnorth_susceptibility_scores.csv'))+''') QUALIFY row_number() OVER (PARTITION BY name ORDER BY name)=1) sc USING(name)''')
 d=c.execute('SELECT * FROM locality_risk_cache').df(); d.to_parquet(OUT/'farnorth_locality_risk_cache.parquet',index=False); d.to_csv(OUT/'farnorth_locality_risk_cache.csv',index=False); print('cache_rows',len(d),'cache_columns',len(d.columns)); c.close()
if __name__=='__main__': main()
