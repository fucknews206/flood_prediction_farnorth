# Centre consolidation: Phases B–G status

Phase B and Phase C were re-run with the repaired ERA5 and GloFAS inputs. Phase G was re-run and now includes the verified Obala historical event in the assistant knowledge base.

The authoritative training decision is **FAIL — DO NOT TRAIN**. See [the readiness gate](centre_readiness_gate.md) and the complete [candidate verification audit](centre_evidence_verification_audit.csv).

Current verified catalogue: one canonical event, `CTR-FLD-2022-001`, at Obala on 2022-05-18. Its locality-day feature row is complete, but one positive episode cannot support a chronological train/test split with positives in both partitions. No labels, negative samples, model, or metrics have been created.

Environmental re-checks: ERA5 is 132/132 readable; GloFAS covers every year 2015–2025; the only current DEM fails a full TIFF read and therefore elevation/slope remain null and explicitly flagged.
