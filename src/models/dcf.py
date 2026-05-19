"""DCF 모델 — 영업레버리지·CapEx-D&A 커플링·레버드베타 WACC 포함"""
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DCFAssumptions:
    projection_years: int = 5

    # 매출 성장률 (연도별)
    revenue_growth_rates: list = field(default_factory=lambda: [0.10, 0.09, 0.08, 0.07, 0.06])

    # EBITDA 마진 (기준연도)
    ebitda_margin: float = 0.20

    # 영업레버리지: 연간 마진 개선 폭 (예: 0.005 = 매년 50bps 상승)
    margin_expansion_annual: float = 0.0

    # D&A / Revenue (기준연도)
    da_pct_revenue: float = 0.05

    # CapEx / Revenue
    capex_pct_revenue: float = 0.04

    # CapEx-D&A 커플링: 신규 CapEx의 내용연수 (년). 0이면 커플링 없음
    capex_useful_life: int = 5

    # NWC 변동 / 매출증가액
    nwc_change_pct: float = 0.02

    # 세율
    tax_rate: float = 0.22

    # WACC
    wacc: float = 0.10

    # 터미널 성장률
    terminal_growth_rate: float = 0.025

    # Terminal Value 방식: "gordon" or "exit_multiple"
    terminal_method: str = "gordon"

    # Exit EV/EBITDA
    exit_multiple: float = 10.0


# ── WACC / CAPM 유틸 ──────────────────────────────────────────────────────

def unlever_beta(levered_beta: float, tax_rate: float, debt: float, equity: float) -> float:
    """Hamada: β_U = β_L / (1 + (1-t) × D/E)"""
    if equity <= 0:
        return levered_beta
    return levered_beta / (1 + (1 - tax_rate) * debt / equity)


def relever_beta(unlevered_beta: float, tax_rate: float, debt: float, equity: float) -> float:
    """Hamada 역산: β_L = β_U × (1 + (1-t) × D/E)"""
    if equity <= 0:
        return unlevered_beta
    return unlevered_beta * (1 + (1 - tax_rate) * debt / equity)


def estimate_cost_of_equity(
    beta: float,
    rf: float = 0.035,
    erp: float = 0.06,
) -> float:
    """CAPM: Ke = Rf + β × ERP"""
    return rf + beta * erp


def calculate_wacc(
    equity_value: float,
    debt: float,
    cost_of_equity: float,
    cost_of_debt: float,
    tax_rate: float = 0.22,
) -> float:
    """WACC = E/(E+D)×Ke + D/(E+D)×Kd×(1-t)"""
    total = equity_value + debt
    if total <= 0:
        return cost_of_equity
    return (equity_value / total) * cost_of_equity + (debt / total) * cost_of_debt * (1 - tax_rate)


def compute_wacc_from_beta(
    unlevered_beta: float,
    market_cap: float,
    net_debt: float,
    cost_of_debt: float = 0.05,
    tax_rate: float = 0.22,
    rf: float = 0.035,
    erp: float = 0.06,
) -> dict:
    """업종 Unlevered Beta → 레버드 베타 → CAPM → WACC 전체 계산"""
    equity  = max(market_cap, 1)
    debt    = max(net_debt, 0)
    lev_beta = relever_beta(unlevered_beta, tax_rate, debt, equity)
    ke       = estimate_cost_of_equity(lev_beta, rf, erp)
    wacc     = calculate_wacc(equity, debt, ke, cost_of_debt, tax_rate)
    return {
        "levered_beta": round(lev_beta, 3),
        "cost_of_equity": round(ke, 4),
        "wacc": round(wacc, 4),
    }


# ── DCF 핵심 모델 ──────────────────────────────────────────────────────────

def run_dcf(
    base_revenue: float,
    base_ebitda: float,       # 기준연도 EBITDA (초기 EBITDA 마진 계산에 사용)
    net_debt: float,
    assumptions: DCFAssumptions,
    base_da: Optional[float] = None,  # 기준연도 D&A (None이면 da_pct×revenue)
) -> dict:
    years  = assumptions.projection_years
    wacc   = assumptions.wacc
    tgr    = assumptions.terminal_growth_rate
    growth = assumptions.revenue_growth_rates
    if len(growth) < years:
        growth = growth + [growth[-1]] * (years - len(growth))

    base_margin = base_ebitda / base_revenue if base_revenue > 0 else assumptions.ebitda_margin
    base_da_val = base_da if base_da else base_revenue * assumptions.da_pct_revenue

    revenues, ebitdas, das, fcfs, pv_fcfs = [], [], [], [], []
    revenue    = base_revenue
    running_da = base_da_val          # 누적 D&A (CapEx 커플링 반영)
    new_capex_history = []            # 과거 CapEx 기록 (커플링용)

    for i in range(years):
        # 매출
        revenue = revenue * (1 + growth[i])

        # EBITDA 마진: 영업레버리지 반영 (매년 margin_expansion_annual 상승)
        margin  = base_margin + (i + 1) * assumptions.margin_expansion_annual
        margin  = min(margin, 0.80)   # 80% 상한
        ebitda  = revenue * margin

        # D&A: 기본 % + 누적 CapEx 내용연수 상각 (커플링)
        base_da_this = revenue * assumptions.da_pct_revenue
        capex_this   = revenue * assumptions.capex_pct_revenue
        new_capex_history.append(capex_this)

        if assumptions.capex_useful_life > 0:
            # 지난 useful_life 기간 CapEx의 1/useful_life씩 추가 D&A
            look_back = min(i + 1, assumptions.capex_useful_life)
            incremental_da = sum(
                new_capex_history[-(j+1)] / assumptions.capex_useful_life
                for j in range(look_back)
            )
            da = base_da_this + incremental_da * 0.3  # 과도한 누적 방지 dampener
        else:
            da = base_da_this

        ebit   = ebitda - da
        nopat  = ebit * (1 - assumptions.tax_rate)
        delta_nwc = revenue * assumptions.nwc_change_pct * growth[i]
        fcf    = nopat + da - capex_this - delta_nwc

        revenues.append(revenue)
        ebitdas.append(ebitda)
        das.append(da)
        fcfs.append(fcf)
        pv_fcfs.append(fcf / ((1 + wacc) ** (i + 1)))

    pv_sum = sum(pv_fcfs)

    # Terminal Value
    if assumptions.terminal_method == "gordon":
        tv = fcfs[-1] * (1 + tgr) / (wacc - tgr) if (wacc - tgr) > 0 else 0
    else:
        tv = ebitdas[-1] * assumptions.exit_multiple

    pv_tv = tv / ((1 + wacc) ** years)
    ev    = pv_sum + pv_tv
    eq    = ev - net_debt

    proj_df = pd.DataFrame({
        "Year":   [f"Y+{i+1}" for i in range(years)],
        "매출액":  revenues,
        "EBITDA": ebitdas,
        "D&A":    das,
        "FCF":    fcfs,
        "PV(FCF)": pv_fcfs,
    })

    return {
        "enterprise_value":   ev,
        "equity_value":       eq,
        "pv_fcf_sum":         pv_sum,
        "terminal_value":     tv,
        "pv_terminal_value":  pv_tv,
        "tv_pct":             pv_tv / ev * 100 if ev else 0,
        "projection":         proj_df,
        "wacc":               wacc,
        "tgr":                tgr,
        "_base_rev":          base_revenue,
        "_base_ebitda":       base_ebitda,
        "_net_debt":          net_debt,
    }


def sensitivity_analysis(
    base_revenue: float,
    base_ebitda: float,
    net_debt: float,
    assumptions: DCFAssumptions,
) -> pd.DataFrame:
    """WACC × TGR 5×5 민감도"""
    w = assumptions.wacc
    t = assumptions.terminal_growth_rate
    wacc_range = [w-0.02, w-0.01, w, w+0.01, w+0.02]
    tgr_range  = [t-0.01, t, t+0.005, t+0.01, t+0.015]

    rows = {}
    for tgr in tgr_range:
        if tgr <= 0:
            continue
        row = {}
        for wacc in wacc_range:
            if wacc <= tgr:
                row[f"{wacc*100:.1f}%"] = None
                continue
            a = DCFAssumptions(**{**assumptions.__dict__,
                                  "wacc": wacc, "terminal_growth_rate": tgr})
            val = run_dcf(base_revenue, base_ebitda, net_debt, a)["equity_value"]
            row[f"{wacc*100:.1f}%"] = round(val, 0)
        rows[f"{tgr*100:.1f}%"] = row

    df = pd.DataFrame(rows).T
    df.index.name = "TGR \\ WACC"
    return df
