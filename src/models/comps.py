"""Trading Comps (동종업계 비교 분석) 모델"""
import pandas as pd
import numpy as np
from typing import Optional


MULTIPLE_COLS = ["EV/EBITDA", "EV/Revenue", "P/E", "P/B", "EV/EBIT"]


def calculate_multiples(
    market_cap: float,
    net_debt: float,
    revenue: float,
    ebitda: float,
    ebit: float,
    net_income: float,
    book_equity: float,
) -> dict:
    """기업 멀티플 계산 (억원 단위 입력)"""
    ev = market_cap + net_debt

    def safe_div(a, b):
        return round(a / b, 2) if b and b != 0 and not np.isnan(b) else None

    return {
        "시가총액(억)": round(market_cap, 0),
        "EV(억)": round(ev, 0),
        "EV/EBITDA": safe_div(ev, ebitda),
        "EV/EBIT": safe_div(ev, ebit),
        "EV/Revenue": safe_div(ev, revenue),
        "P/E": safe_div(market_cap, net_income),
        "P/B": safe_div(market_cap, book_equity),
    }


def implied_value_from_comps(
    target_metrics: dict,
    peer_multiples_df: pd.DataFrame,
    agg: str = "median",
) -> dict:
    """피어 멀티플 중앙값/평균으로 대상 기업 implied EV 계산"""
    if peer_multiples_df.empty:
        return {}

    func = np.median if agg == "median" else np.mean
    results = {}

    for col in ["EV/EBITDA", "EV/EBIT", "EV/Revenue"]:
        vals = peer_multiples_df[col].dropna()
        if vals.empty:
            continue
        multiple = func(vals)
        metric_key = col.split("/")[1].lower()
        metric_val = target_metrics.get(metric_key)
        if metric_val and metric_val > 0:
            implied_ev = multiple * metric_val
            results[col] = {
                "peer_multiple": round(multiple, 2),
                "implied_ev": round(implied_ev, 0),
                "implied_equity": round(implied_ev - target_metrics.get("net_debt", 0), 0),
            }

    # P/E implied
    pe_vals = peer_multiples_df["P/E"].dropna()
    if not pe_vals.empty and target_metrics.get("net_income", 0) > 0:
        pe = func(pe_vals)
        results["P/E"] = {
            "peer_multiple": round(pe, 2),
            "implied_equity": round(pe * target_metrics["net_income"], 0),
        }

    return results


def build_comps_summary(peer_multiples_df: pd.DataFrame) -> pd.DataFrame:
    """피어 멀티플 요약 통계 (min, 25%, median, 75%, max)"""
    if peer_multiples_df.empty:
        return pd.DataFrame()
    numeric_cols = [c for c in MULTIPLE_COLS if c in peer_multiples_df.columns]
    summary = peer_multiples_df[numeric_cols].describe(percentiles=[0.25, 0.5, 0.75])
    return summary.loc[["min", "25%", "50%", "75%", "max"]].round(2)
