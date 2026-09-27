#!/usr/bin/env python3
"""Re-run changed Centre phases C–G from existing validated source Parquet."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from build_centre_consolidation import (  # noqa: E402
    OUT, build_event_audit, build_feature_table, build_knowledge_base,
    build_spatial_lookup, write_final_report,
)


def main() -> None:
    era5_daily = pd.read_parquet(OUT / 'era5_centre_daily.parquet')
    era5_flat = pd.read_parquet(OUT / 'era5_centre_flat.parquet')
    glofas = pd.read_parquet(OUT / 'glofas_centre_flat.parquet')
    lookup = build_spatial_lookup(era5_daily, glofas)
    features = build_feature_table(lookup, era5_daily, glofas)
    canonical = build_event_audit()
    knowledge = build_knowledge_base(lookup, features, canonical)
    write_final_report(era5_flat, era5_daily, glofas, lookup, features, canonical, knowledge)
    print('Completed Centre phases C–G downstream re-run.')


if __name__ == '__main__':
    main()
