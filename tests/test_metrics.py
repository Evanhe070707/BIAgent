"""
Minimal pytest suite for BIAgent metrics.

Generates a synthetic 3600-row (1-hour) CSV with known constant signals
and validates a selection of metrics against hand-calculated expected values.
"""

from __future__ import annotations

import csv
import math
import os
import tempfile
from pathlib import Path

import pytest

from biagent.cli import load_metrics, run_metrics

# ---------------------------------------------------------------------------
# Synthetic CSV generation
# ---------------------------------------------------------------------------

METRICS_YAML = str(Path(__file__).parent.parent / "config" / "metrics.yaml")

# Constant signal values used across all 3600 rows
SIGNALS = {
    "VehSpd": 36.0,          # km/h  → dist = 36/3600 km/s → 36 km total
    "BattCurr": 10.0,         # A
    "BattVolt": 400.0,        # V
    "MotCurr": 20.0,          # A
    "MotVolt": 300.0,         # V
    "StkCurr": 50.0,          # A
    "StkVolt": 200.0,         # V
    "DcfCurrOut": 60.0,       # A
    "DcfVoltOut": 250.0,      # V
    "WcpCurr": 5.0,
    "WcpVolt": 100.0,
    "HrbCurr": 3.0,
    "HrbVolt": 100.0,
    "AcpCurr": 2.0,
    "AcpVolt": 100.0,
}

N_ROWS = 3600  # 1 hour at 1 s sampling


@pytest.fixture(scope="module")
def synthetic_csv(tmp_path_factory) -> str:
    tmp = tmp_path_factory.mktemp("data")
    csv_path = str(tmp / "test_data.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(SIGNALS.keys()))
        writer.writeheader()
        for _ in range(N_ROWS):
            writer.writerow(SIGNALS)
    return csv_path


@pytest.fixture(scope="module")
def metrics():
    return load_metrics(METRICS_YAML)


@pytest.fixture(scope="module")
def results(synthetic_csv, metrics):
    params = {"stk_cell_count": 400, "stk_h2_corr": 0.985}
    rows = run_metrics(synthetic_csv, metrics, params)
    return {r["metric_id"]: r for r in rows}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def approx(expected, rel=1e-4):
    return pytest.approx(expected, rel=rel)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTimeDist:
    def test_time_ready(self, results):
        assert float(results["TimeReady"]["metric_value"]) == approx(N_ROWS)

    def test_time_drv(self, results):
        # All rows have VehSpd > 0
        assert float(results["TimeDrv"]["metric_value"]) == approx(N_ROWS)

    def test_time_stop(self, results):
        # No rows with VehSpd == 0
        assert float(results["TimeStop"]["metric_value"]) == approx(0.0)

    def test_time_fc(self, results):
        # All rows have StkCurr > 0
        assert float(results["TimeFC"]["metric_value"]) == approx(N_ROWS)

    def test_total_dist(self, results):
        expected = N_ROWS * SIGNALS["VehSpd"] / 3600.0
        assert float(results["TotalDist"]["metric_value"]) == approx(expected)


class TestEnergy:
    def _kwh(self, curr_key, volt_key) -> float:
        return N_ROWS * SIGNALS[curr_key] * SIGNALS[volt_key] / 1000.0 / 3600.0

    def test_stk_eng(self, results):
        assert float(results["StkEng_all"]["metric_value"]) == approx(self._kwh("StkCurr", "StkVolt"))

    def test_batt_eng(self, results):
        assert float(results["BattEng_all"]["metric_value"]) == approx(self._kwh("BattCurr", "BattVolt"))

    def test_dcf_out_eng(self, results):
        assert float(results["DcfOutEng_all"]["metric_value"]) == approx(self._kwh("DcfCurrOut", "DcfVoltOut"))

    def test_wcp_eng(self, results):
        assert float(results["WcpEng_all"]["metric_value"]) == approx(self._kwh("WcpCurr", "WcpVolt"))

    def test_hrb_eng(self, results):
        assert float(results["HrbEng_all"]["metric_value"]) == approx(self._kwh("HrbCurr", "HrbVolt"))

    def test_acp_eng(self, results):
        assert float(results["AcpEng_all"]["metric_value"]) == approx(self._kwh("AcpCurr", "AcpVolt"))

    def test_fc_eng(self, results):
        expected = (
            self._kwh("DcfCurrOut", "DcfVoltOut")
            - self._kwh("WcpCurr", "WcpVolt")
            - self._kwh("HrbCurr", "HrbVolt")
            - self._kwh("AcpCurr", "AcpVolt")
        )
        assert float(results["FCEng_all"]["metric_value"]) == approx(expected)

    def test_drv_eng(self, results):
        assert float(results["DrvEng_all"]["metric_value"]) == approx(self._kwh("MotCurr", "MotVolt"))

    def test_drv_eng_pos(self, results):
        # MotCurr*MotVolt = 20*300 > 0 always → all positive
        assert float(results["DrvEng_Pos_all"]["metric_value"]) == approx(self._kwh("MotCurr", "MotVolt"))

    def test_drv_eng_neg(self, results):
        # No negative power
        assert float(results["DrvEng_Neg_all"]["metric_value"]) == approx(0.0)

    def test_veh_eng(self, results):
        expected = (
            self._kwh("DcfCurrOut", "DcfVoltOut")
            - self._kwh("WcpCurr", "WcpVolt")
            - self._kwh("HrbCurr", "HrbVolt")
            - self._kwh("AcpCurr", "AcpVolt")
            + self._kwh("BattCurr", "BattVolt")
        )
        assert float(results["VehEng_all"]["metric_value"]) == approx(expected)

    def test_aux_eng(self, results):
        fc = (
            self._kwh("DcfCurrOut", "DcfVoltOut")
            - self._kwh("WcpCurr", "WcpVolt")
            - self._kwh("HrbCurr", "HrbVolt")
            - self._kwh("AcpCurr", "AcpVolt")
        )
        veh = fc + self._kwh("BattCurr", "BattVolt")
        drv = self._kwh("MotCurr", "MotVolt")
        assert float(results["AuxEng_all"]["metric_value"]) == approx(veh - drv)


class TestHydrogen:
    def _h2_kg(self, stk_cell_count=400, h2_corr=0.985) -> float:
        return N_ROWS * SIGNALS["StkCurr"] / 2.016 / 96485 * 2 / 3600 * stk_cell_count / h2_corr

    def test_h2_all_long(self, results):
        assert float(results["H2_all_long"]["metric_value"]) == approx(self._h2_kg())

    def test_h2_ele_ratio(self, results):
        fc = (
            N_ROWS * SIGNALS["DcfCurrOut"] * SIGNALS["DcfVoltOut"] / 1000.0 / 3600.0
            - N_ROWS * SIGNALS["WcpCurr"] * SIGNALS["WcpVolt"] / 1000.0 / 3600.0
            - N_ROWS * SIGNALS["HrbCurr"] * SIGNALS["HrbVolt"] / 1000.0 / 3600.0
            - N_ROWS * SIGNALS["AcpCurr"] * SIGNALS["AcpVolt"] / 1000.0 / 3600.0
        )
        h2 = self._h2_kg()
        expected_ratio = fc / h2
        assert float(results["H2EleRatio"]["metric_value"]) == approx(expected_ratio)


class TestEfficiency:
    def _h2_kg(self, stk_cell_count=400, h2_corr=0.985) -> float:
        return N_ROWS * SIGNALS["StkCurr"] / 2.016 / 96485 * 2 / 3600 * stk_cell_count / h2_corr

    def test_stk_eff(self, results):
        stk_kwh = N_ROWS * SIGNALS["StkCurr"] * SIGNALS["StkVolt"] / 1000.0 / 3600.0
        h2 = self._h2_kg()
        expected = stk_kwh / (h2 * 33.5) * 100
        assert float(results["StkEff"]["metric_value"]) == approx(expected)

    def test_fc_sys_eff(self, results):
        fc_kwh = (
            N_ROWS * SIGNALS["DcfCurrOut"] * SIGNALS["DcfVoltOut"] / 1000.0 / 3600.0
            - N_ROWS * SIGNALS["WcpCurr"] * SIGNALS["WcpVolt"] / 1000.0 / 3600.0
            - N_ROWS * SIGNALS["HrbCurr"] * SIGNALS["HrbVolt"] / 1000.0 / 3600.0
            - N_ROWS * SIGNALS["AcpCurr"] * SIGNALS["AcpVolt"] / 1000.0 / 3600.0
        )
        h2 = self._h2_kg()
        expected = fc_kwh / (h2 * 33.5) * 100
        assert float(results["FcSysEff"]["metric_value"]) == approx(expected)


class TestDistMetrics:
    def _kwh(self, curr_key, volt_key) -> float:
        return N_ROWS * SIGNALS[curr_key] * SIGNALS[volt_key] / 1000.0 / 3600.0

    def test_drv_eng_dist(self, results):
        dist = N_ROWS * SIGNALS["VehSpd"] / 3600.0
        drv = self._kwh("MotCurr", "MotVolt")
        assert float(results["DrvEng_Dist"]["metric_value"]) == approx(drv / dist * 100)

    def test_total_dist_value(self, results):
        expected = N_ROWS * SIGNALS["VehSpd"] / 3600.0
        assert float(results["TotalDist"]["metric_value"]) == approx(expected)

    def test_sys_opr_dist(self, results):
        # All rows have StkCurr > 0 → SysOpr_Dist == TotalDist
        expected = N_ROWS * SIGNALS["VehSpd"] / 3600.0
        assert float(results["SysOpr_Dist"]["metric_value"]) == approx(expected)


class TestAveragePower:
    def test_drv_eng_t(self, results):
        drv_kwh = N_ROWS * SIGNALS["MotCurr"] * SIGNALS["MotVolt"] / 1000.0 / 3600.0
        hours = N_ROWS / 3600.0
        assert float(results["DrvEng_T"]["metric_value"]) == approx(drv_kwh / hours)

    def test_drv_eng_drvt(self, results):
        # Same as DrvEng_T since all rows have VehSpd > 0
        assert float(results["DrvEng_DrvT"]["metric_value"]) == approx(
            float(results["DrvEng_T"]["metric_value"])
        )
