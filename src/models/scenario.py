"""Bull / Base / Bear 3-Scenario DCF Engine"""
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Optional
from src.models.dcf import DCFAssumptions, run_dcf


@dataclass
class ScenarioSet:
    """3개 시나리오 가정 묶음"""
    # 각 시나리오 이름
    names: list = field(default_factory=lambda: ["Bear", "Base", "Bull"])

    # 확률 가중치
    weights: list = field(default_factory=lambda: [0.25, 0.50, 0.25])

    # 매출 성장률 배율 (Base = 1.0, Bull = 1.3, Bear = 0.6 등)
    growth_multipliers: list = field(default_factory=lambda: [0.5, 1.0, 1.5])

    # EBITDA 마진 조정 (절대값, 예: -0.03 = -3%p)
    margin_deltas: list = field(default_factory=lambda: [-0.03, 0.0, 0.04])

    # WACC 조정 (절대값)
    wacc_deltas: list = field(default_factory=lambda: [0.01, 0.0, -0.01])

    # Terminal Growth Rate 조정
    tgr_deltas: list = field(default_factory=lambda: [-0.005, 0.0, 0.005])


def run_scenarios(
    base_revenue: float,
    base_ebitda: float,
    net_debt: float,
    base_assumptions: DCFAssumptions,
    scenario_set: ScenarioSet,
    base_da: Optional[float] = None,
) -> dict:
    """3개 시나리오 DCF 실행 → 결과 dict"""
    results = {}
    for i, name in enumerate(scenario_set.names):
        growth = [
            g * scenario_set.growth_multipliers[i]
            for g in base_assumptions.revenue_growth_rates
        ]
        a = DCFAssumptions(
            projection_years      = base_assumptions.projection_years,
            revenue_growth_rates  = growth,
            ebitda_margin         = base_assumptions.ebitda_margin + scenario_set.margin_deltas[i],
            margin_expansion_annual = base_assumptions.margin_expansion_annual,
            da_pct_revenue        = base_assumptions.da_pct_revenue,
            capex_pct_revenue     = base_assumptions.capex_pct_revenue,
            capex_useful_life     = base_assumptions.capex_useful_life,
            nwc_change_pct        = base_assumptions.nwc_change_pct,
            tax_rate              = base_assumptions.tax_rate,
            wacc                  = base_assumptions.wacc + scenario_set.wacc_deltas[i],
            terminal_growth_rate  = base_assumptions.terminal_growth_rate + scenario_set.tgr_deltas[i],
            terminal_method       = base_assumptions.terminal_method,
            exit_multiple         = base_assumptions.exit_multiple,
        )
        res = run_dcf(base_revenue, base_ebitda, net_debt, a, base_da=base_da)
        res["scenario_name"]   = name
        res["growth_mult"]     = scenario_set.growth_multipliers[i]
        res["margin_delta"]    = scenario_set.margin_deltas[i]
        res["wacc_used"]       = a.wacc
        res["weight"]          = scenario_set.weights[i]
        results[name] = res

    # 확률가중 Equity Value
    pw_equity = sum(
        results[n]["equity_value"] * w
        for n, w in zip(scenario_set.names, scenario_set.weights)
    )
    pw_ev = sum(
        results[n]["enterprise_value"] * w
        for n, w in zip(scenario_set.names, scenario_set.weights)
    )
    return {
        "scenarios":          results,
        "probability_weighted_equity": pw_equity,
        "probability_weighted_ev":     pw_ev,
        "names":   scenario_set.names,
        "weights": scenario_set.weights,
    }


def scenario_summary_df(scenario_results: dict) -> pd.DataFrame:
    rows = []
    for name, res in scenario_results["scenarios"].items():
        rows.append({
            "시나리오":         name,
            "확률 가중치":       f"{res['weight']*100:.0f}%",
            "WACC":             f"{res['wacc_used']*100:.1f}%",
            "EV (억원)":        round(res["enterprise_value"], 0),
            "Equity Value (억)": round(res["equity_value"], 0),
            "TV 비중":          f"{res['tv_pct']:.1f}%",
        })
    rows.append({
        "시나리오":         "▶ 확률가중 평균",
        "확률 가중치":       "100%",
        "WACC":             "-",
        "EV (억원)":        round(scenario_results["probability_weighted_ev"], 0),
        "Equity Value (억)": round(scenario_results["probability_weighted_equity"], 0),
        "TV 비중":          "-",
    })
    return pd.DataFrame(rows)
