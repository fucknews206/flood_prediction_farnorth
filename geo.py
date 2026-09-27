import cdsapi

client = cdsapi.Client()  # make sure .cdsapirc points to ewds.climate.copernicus.eu

dataset = "cems-glofas-forecast"
request = {
    "system_version": "operational",
    "hydrological_model": "lisflood",
    "product_type": "ensemble_perturbed_forecasts",
    "variable": "river_discharge_in_the_last_24_hours",
    "year": "2026",
    "month": "09",
    "day": "07",
    "leadtime_hour": ["24", "48", "72", "96", "120"],
    "area": [13.2, 13.0, 9.5, 15.4],
    "data_format": "netcdf",
    "download_format": "unarchived",
}


ALTER USER postgres WITH PASSWORD '1234';
\q

client.retrieve(dataset, request).download("GLOFAS_forecast_2026_09_07.nc")
# api_key = 67b20b58067b398e2e10ce3dd0e269df

# https://portal.opentopography.org/API/globaldem?demtype=COP30&south=3.5&north=5.0&west=10.5&east=12.5&outputFormat=GTiff&API_Key=67b20b58067b398e2e10ce3dd0e269df
# https://portal.opentopography.org/API/globaldem?demtype=SRTMGL1&south=3.5&north=5.0&west=10.5&east=12.5&outputFormat=GTiff&API_Key=67b20b58067b398e2e10ce3dd0e269df

# https://portal.opentopography.org/API/globaldem?demtype=SRTMGL1&south=3.5&north=5.0&west=10.5&east=12.5&outputFormat=GTiff&API_Key=abc123yourrealkeyhere
# important question:how many rows in the training table have flood_label = 1, and across how many distinct localities and years