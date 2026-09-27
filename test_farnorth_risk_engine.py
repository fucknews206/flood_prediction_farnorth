#!/usr/bin/env python3
import argparse, json
from farnorth_risk_engine import get_locality_risk
ap=argparse.ArgumentParser(description='Far North interim rules-based risk engine (not trained ML)')
ap.add_argument('locality',nargs='?',default='Kousseri'); a=ap.parse_args()
print(json.dumps(get_locality_risk(a.locality),indent=2,default=str))
