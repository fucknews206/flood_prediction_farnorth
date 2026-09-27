# Far North region only — 2004–2014 environmental extension verification

Verification was performed by opening the NetCDF files with xarray and inspecting their time coordinate; filenames were not trusted.

## ERA5-Land

The monthly files are present for 2005–2007 and 2010–2013, but the extension is **not usable as a continuous layer**. Files with HDF/NetCDF errors include 2005-11, 2006-05 through 2006-09, 2007-06, 2010-01 and 2010-05 through 2010-12, 2011-01, 2011-03, 2011-05 and 2011-10 through 2011-12, 2012-05 through 2012-09 and 2012-11 through 2012-12, and 2013-02 through 2013-04. Consequently the required years 2010–2012 have major gaps; 2005–2007 and 2013 also have missing months.

## GloFAS

`data_2004.nc`–`data_2014.nc` open successfully and provide annual coverage, but the coordinate convention runs approximately 2 January through the following 1 January (and 2025 has one fewer timestep). This is documented as a boundary/convention issue and must be normalized before matching exact event dates.

## CHIRPS

* `CHIRPS_FarNorth_2005_2007.csv`: 4,226,700 data rows = 3,860 × 1,095 days; 3,860 localities; 2005-01-01–2007-12-31. No duplicate date/name keys were found in the vectorized check.
* `CHIRPS_FarNorth_2010_2011.csv`: 1,408,900 data rows = 3,860 × 365; 3,860 localities; **only 2010-01-01–2010-12-31**. Despite its filename it contains no 2011 dates, so the 2011 chunk is missing.
* `CHIRPS_FarNorth_2012_2013.csv`: 2,821,660 rows (the expected 3,860 × 731 for 2012–2013); the file is complete by row count. A full duplicate scan could not be completed within the memory limit, so this chunk is not marked fully cleared until that check is rerun on a machine with sufficient memory.

## SAHA thesis (FNR-FLD-2005-003)

The cited Scribd URL is an HTML landing page and the actual thesis PDF is not present in the project folders; therefore its claimed 2005 event cannot be independently verified. The directly retrieved Arabi paper contains 2011 and 2015 entries, but **no 2005 entry**. FNR-FLD-2005-003 remains unverified and is excluded from the trainable catalogue.

## Environmental matching consequence

The extension cannot yet support a complete 2004–2014 feature match. Events in 2010–2012 cannot be matched reliably because of missing/corrupt ERA5 months and the absent 2011 CHIRPS data. Do not train on these rows or impute the missing weather data. The existing 2015–2025 layer remains the only consistently usable training window until the corrupt ERA5 files and missing CHIRPS 2011 data are replaced.

