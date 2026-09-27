# Centre region consolidation — Phase 0 discovery report

Discovery run: 2026-08-30  
Project source root: `/home/ongou/Desktop/projects/end-of -year-defence/`

## Inventory reconciliation

| Expected source | Discovery result | Decision |
|---|---|---|
| ERA5 Centre monthly NetCDF (2015–2025) | 132 files, one for every expected month | Present, but nine files fail to open; see limitations. |
| CHIRPS history | Three CSV chunks, 718,443 rows total, 2010-01-01 to 2025-12-30 | Present as chunks. `CHIRPS_full_history.csv` does not yet exist and will be generated without dropping distinct observations. |
| Centre DEM | Two 7,200 × 5,400 WGS84 GeoTIFFs with the same bounds (10.5–12.5 E, 3.5–5.0 N) but different SHA-256 checksums | Present but both fail a full raster read with TIFF tile truncation errors, so neither can be used for elevation or slope. |
| Boundaries and gazetteers | Admin GDB/SHP, populated places GPKG, 123-row merged gazetteer, 106-row verified gazetteer, geocoder script | Present. |
| GloFAS | Eight `data_N.nc` files, all confirmed as `avg_dis` on a 30 × 40 0.05° grid | Present, with confirmed annual identities and 2015–2017 coverage gap. |
| HydroBASINS/HydroRIVERS | Level 01–12 basin data, HydroRIVERS, both technical PDFs | Present. |
| Centre canonical flood catalogue | Not present | Blocking for labels/training; no Centre event will be inferred from generic Cameroon/Far North records. |

## Confirmed coverage and schemas

- ERA5 successful files: `valid_time`, `latitude`, `longitude`; 16 × 21 cells, 3.5–5.0 N and 10.5–12.5 E. Variables are `tp`, `ro`, `ssro`, `swvl1`, `t2m`, `d2m`, `pev`, `u10`, and `v10` (the abbreviated equivalents of the documented variables). `swvl2` is absent and will remain excluded.
- GloFAS successful files: `valid_time`, `latitude`, `longitude`; 30 × 40 cells, 3.525–4.975 N and 10.525–12.475 E; `avg_dis`.
- Confirmed GloFAS identities: `data_6` = 2018, `data_2` = 2019, `data_1` = 2020, `data_5` = 2021, `data_3` = 2022, `data_8` = 2023, `data_4` = 2024, `data_7` = 2025. Gaps versus 2015–2025: 2015, 2016, 2017.
- The 718,443 CHIRPS rows are unique by source index and by `(name, coordinate, date)`. The only repeated name/date is **Ayéné**, which represents a neighbourhood and a village at different locations; it must not be deduplicated by name alone.

## Data-quality limitations found before implementation

1. The following ERA5 files cannot be opened with NetCDF4 and will be recorded as missing coverage: `2016_02`, `2016_08`, `2017_02`, `2023_04`, `2023_05`, `2023_08`, `2023_10`, `2023_12`, and `2024_07`.
2. GloFAS contains no 2015–2017 data. Missing discharge must be explicitly flagged, never replaced with zero or interpolated.
3. The previous national `master_events.csv` is not a Centre catalogue. Its four `region=Centre` rows contain no dates or coordinates and are false region matches from text such as “health centre” and “Makary centre” in Far North reports. They are not valid Centre positive labels.
4. Both DEMs fail full reads: the declared COP30 file fails near row 2048 and the second GeoTIFF fails near row 6656. Elevation/slope must remain unknown until a complete DEM is supplied.
5. Consequently, Phase E/F cannot ethically create labels, negative samples, or a trained classifier until a source-verified Centre canonical flood-event catalogue exists.

## Discovery conclusion

The environmental and locality layers can be standardised and published with coverage/confidence flags. A numeric **labelled** ML training table and trained flood classifier are deliberately blocked, rather than fabricated, because there are zero verified Centre-region flood events in the available canonical catalogue.
