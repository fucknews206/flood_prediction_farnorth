import cdsapi
import os
import time

client = cdsapi.Client()

# Variables
variables = [
    "total_precipitation",
    "runoff",
    "sub_surface_runoff",
    "volumetric_soil_water_layer_1",
    "2m_temperature",
    "2m_dewpoint_temperature",
    "potential_evaporation",
    "10m_u_component_of_wind",
    "10m_v_component_of_wind"
]

# Cameroon regions [North, West, South, East]
regions = {
   "Far_North": [13.0, 9.5, 15.4, 13.2]
}

years = range(2005, 2027)      # 2015 → 2024
months = range(1, 13)

days = [
    "01","02","03","04","05","06","07","08","09","10",
    "11","12","13","14","15","16","17","18","19","20",
    "21","22","23","24","25","26","27","28","29","30","31"
]

times = [
    "00:00",
    "06:00",
    "12:00",
    "18:00"
]

# Save here
BASE_DIR = os.path.expanduser(
    "~/Desktop/projects/end-of -year-defence/ERA5-datasets"
)

os.makedirs(BASE_DIR, exist_ok=True)

for region_name, area in regions.items():

    region_dir = os.path.join(BASE_DIR, region_name)
    os.makedirs(region_dir, exist_ok=True)

    print(f"\n========== {region_name} ==========\n")

    for year in years:

        for month in months:

            outfile = os.path.join(
                region_dir,
                f"ERA5_{region_name}_{year}_{month:02d}.nc"
            )

            if os.path.exists(outfile):
                print(f"✓ Already downloaded: {outfile}")
                continue

            print(f"Downloading {region_name} {year}-{month:02d}")

            request = {
                "variable": variables,
                "year": str(year),
                "month": f"{month:02d}",
                "day": days,
                "time": times,
                "data_format": "netcdf",
                "download_format": "unarchived",
                "area": area
            }

            try:
                client.retrieve(
                    "reanalysis-era5-land",
                    request
                ).download(outfile)

                print(f"✓ Saved: {outfile}")

                time.sleep(2)

            except Exception as e:
                print(f"✗ Failed: {year}-{month:02d}")
                print(e)

                # Wait before continuing
                time.sleep(10)

print("\n====================================")
print("Download complete!")
print("Saved in:")
print(BASE_DIR)
print("====================================")