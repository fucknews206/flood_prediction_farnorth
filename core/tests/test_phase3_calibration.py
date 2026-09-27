"""Replay fixture for the documented Zina → Maga September/October 2019 event."""

import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from flood_prediction.data_sources import calculate_calibrated_basin_risk


class Phase3CalibrationReplayTests(unittest.TestCase):
    def test_zina_rainfall_and_delayed_maga_propagation(self):
        # Open-Meteo replay: Zina received 10.6 mm on 28 Sep and 20.6 mm on
        # 29 Sep.  The 31.2 mm two-day total crosses its stored 30 mm trigger.
        zina = calculate_calibrated_basin_risk(
            rainfall_mm=20.6,
            rainfall_two_day_mm=31.2,
            community_count=0,
            discharge_cms=None,
            discharge_status="unavailable",
            local_daily_threshold_mm=20.0,
            local_two_day_threshold_mm=30.0,
        )
        self.assertEqual(zina.risk_source, "local_rainfall")
        self.assertEqual(zina.risk_level, "Moderate")
        self.assertGreaterEqual(zina.risk_score, 4.0)

        # Five days later (4 Oct), Maga's local rain is deliberately zero.
        # Its risk is elevated only by the stored Zina trigger arriving within
        # the configured Zina→Maga 5–7 day propagation window.
        maga = calculate_calibrated_basin_risk(
            rainfall_mm=0.0,
            rainfall_two_day_mm=0.0,
            community_count=0,
            discharge_cms=None,
            discharge_status="unavailable",
            local_daily_threshold_mm=20.0,
            local_two_day_threshold_mm=30.0,
            upstream_propagation_active=True,
            upstream_sources=["upstream:Zina (Logone/Chari):rainfall_on:2019-09-29"],
        )
        self.assertEqual(maga.risk_source, "upstream_propagation")
        self.assertIn("upstream_propagation", maga.trigger_reasons)
        self.assertEqual(maga.risk_level, "Moderate")
        self.assertGreaterEqual(maga.risk_score, 4.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
