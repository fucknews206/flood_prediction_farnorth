import cdsapi
import os
import time

client = cdsapi.Client()

# Save here
BASE_DIR = os.path.expanduser(
    "~/Desktop/projects/end-of -year-defence/data/GPM"
)

os.makedirs(BASE_DIR, exist_ok=True)

# Cameroon regions [North, West, South, East]
regions = {
    'Far_North': [13.0, 13.0, 10.0, 16.0],
    'North': [10.5, 12.5, 8.0, 15.5],
    "Centre": [5.0, 10.5, 3.5, 12.5],
    "Littoral": [4.5, 9.0, 3.5, 10.5],
    "South_West": [5.5, 8.5, 4.0, 10.0],
}

years = range(2015, 2025)      # 2015 → 2024
months = range(1, 13)

days = [
    "01","02","03","04","05","06","07","08","09","10",
    "11","12","13","14","15","16","17","18","19","20",
    "21","22","23","24","25","26","27","28","29","30","31"
]

# GPM is 30min data. We use 00:00 to 23:30
times = [f"{h:02d}:{m:02d}" for h in range(24) for m in [0, 30]]

for region_name, area in regions.items():

    region_dir = os.path.join(BASE_DIR, region_name)
    os.makedirs(region_dir, exist_ok=True)

    print(f"\n========== {region_name} ==========\n")

    for year in years:

        for month in months:

            outfile = os.path.join(
                region_dir,
                f"GPM_{region_name}_{year}_{month:02d}.nc"
            )

            if os.path.exists(outfile):
                print(f"✓ Already downloaded: {outfile}")
                continue

            print(f"Downloading {region_name} {year}-{month:02d}")

            request = {
                "product_type": "gpm_imerg_early_run",
                "variable": "precipitation_amount",
                "year": str(year),
                "month": f"{month:02d}",
                "day": days,
                "time": times,
                "area": area,  # [N, W, S, E]
                "format": "netcdf"
            }

            try:
                client.retrieve(
                    "satellite-precipitation-gpm", # <-- GPM dataset
                    request
                ).download(outfile)

                print(f"✓ Saved: {outfile}")
                time.sleep(2)

            except Exception as e:
                print(f"✗ Failed: {year}-{month:02d}")
                print(e)
                time.sleep(10)

print("\n====================================")
print("GPM Download complete!")
print("Saved in:")
print(BASE_DIR)
print("====================================")


