"""VC Unit Economics — LTV/CAC, Cohort, Rule of 40, SaaS Metrics"""
import pandas as pd
import numpy as np
from dataclasses import dataclass


@dataclass
class UnitEconomicsInputs:
    # 고객 획득
    cac: float = 50000.0          # 고객 획득 비용 (원)
    monthly_churn: float = 0.03   # 월간 이탈률
    arpu_monthly: float = 30000.0 # 월 평균 매출 (원/고객)
    gross_margin: float = 0.70    # 매출총이익률

    # 성장
    monthly_new_customers: float = 1000.0
    monthly_growth_rate: float = 0.05

    # SaaS/플랫폼
    arr: float = 0.0              # Annual Recurring Revenue (억원), 0이면 자동 계산
    revenue_growth_yoy: float = 0.40
    ebitda_margin: float = -0.10  # 성장 초기엔 마이너스


def compute_unit_economics(inp: UnitEconomicsInputs) -> dict:
    # ── LTV 계산 ──────────────────────────────────────────────────────────
    avg_lifetime_months = 1 / inp.monthly_churn if inp.monthly_churn > 0 else 999
    ltv_revenue = inp.arpu_monthly * avg_lifetime_months
    ltv = ltv_revenue * inp.gross_margin          # Gross-profit LTV

    # ── 핵심 비율 ──────────────────────────────────────────────────────────
    ltv_cac_ratio  = ltv / inp.cac if inp.cac > 0 else 0
    payback_months = inp.cac / (inp.arpu_monthly * inp.gross_margin) if (inp.arpu_monthly * inp.gross_margin) > 0 else 999
    magic_number   = (inp.revenue_growth_yoy * inp.arr * 1e8) / (inp.arr * 1e8 * 0.5) if inp.arr > 0 else None

    # ── Rule of 40 ────────────────────────────────────────────────────────
    rule_of_40 = inp.revenue_growth_yoy * 100 + inp.ebitda_margin * 100

    # ── Cohort 분석 (12개월) ──────────────────────────────────────────────
    cohort_rows = []
    for m in range(1, 25):
        retention = (1 - inp.monthly_churn) ** m
        cum_rev   = inp.arpu_monthly * sum(
            (1 - inp.monthly_churn) ** k for k in range(m)
        )
        cum_gp    = cum_rev * inp.gross_margin
        payback_reached = cum_gp >= inp.cac
        cohort_rows.append({
            "Month": m,
            "잔존율": f"{retention*100:.1f}%",
            "누적 Gross Profit (원)": round(cum_gp, 0),
            "CAC 회수 여부": "✅ 회수" if payback_reached else "❌ 미회수",
        })
    cohort_df = pd.DataFrame(cohort_rows)

    # ── ARR Bridge ────────────────────────────────────────────────────────
    arr_val = inp.arr if inp.arr > 0 else (inp.arpu_monthly * 12 * inp.monthly_new_customers / 1e8)

    return {
        "ltv":             round(ltv, 0),
        "cac":             inp.cac,
        "ltv_cac":         round(ltv_cac_ratio, 2),
        "payback_months":  round(payback_months, 1),
        "avg_lifetime_mo": round(avg_lifetime_months, 1),
        "rule_of_40":      round(rule_of_40, 1),
        "gross_margin":    inp.gross_margin,
        "monthly_churn":   inp.monthly_churn,
        "arr_억":          round(arr_val, 1),
        "cohort_df":       cohort_df,
        "magic_number":    round(magic_number, 2) if magic_number else None,
        # 등급 판정
        "ltv_cac_grade":   "우수 (>3x)" if ltv_cac_ratio > 3 else ("양호 (1~3x)" if ltv_cac_ratio >= 1 else "위험 (<1x)"),
        "payback_grade":   "우수 (<12M)" if payback_months < 12 else ("양호 (12~18M)" if payback_months < 18 else "주의 (>18M)"),
        "r40_grade":       "Best-in-class (>40)" if rule_of_40 > 40 else ("Good (20~40)" if rule_of_40 > 20 else "Below avg (<20)"),
    }
