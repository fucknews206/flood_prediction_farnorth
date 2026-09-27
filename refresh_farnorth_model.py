"""Refresh Far North rules-based engine metadata; never trains ML."""
from pathlib import Path
from datetime import datetime, timezone
import json, pandas as pd
from farnorth_risk_engine import _catalogue, _scores, MODEL_TYPE, OUT

def refresh():
    c=_catalogue(); s=_scores(); n=len(c); baseline=n
    entry={'timestamp':datetime.now(timezone.utc).isoformat(),'verified_event_count':n,'baseline_count':baseline,'validation_pass_rate':'not recomputed automatically; validation-only catalogue','weights_changed':False,'model_type':MODEL_TYPE,'classifier_threshold_reached':n>=30,'recommendation':'Begin classifier feasibility work only at >=30 verified independent episodes.' if n>=30 else 'Continue interim rules-based operation; collect independent event evidence before ML training.'}
    log=OUT/'farnorth_model_version_log.jsonl'; log.open('a',encoding='utf-8').write(json.dumps(entry)+'\n')
    print(json.dumps({'localities':len(s),'verified_events':n,'baseline':baseline,'classifier_threshold_reached':n>=30,'model_type':MODEL_TYPE},indent=2)); return entry
if __name__=='__main__': refresh()
