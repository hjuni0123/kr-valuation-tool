"""동종업계 피어 Comps 자동 수집 — DART 산업코드 기반"""
import requests
import pandas as pd
import os
from typing import Optional

DART_BASE = "https://opendart.fss.or.kr/api"


def _key():
    return os.getenv("DART_API_KEY", "")


def get_industry_code(corp_code: str) -> Optional[str]:
    """DART 기업개황에서 산업코드 조회"""
    try:
        resp = requests.get(
            f"{DART_BASE}/company.json",
            params={"crtfc_key": _key(), "corp_code": corp_code},
            timeout=10,
        )
        data = resp.json()
        if data.get("status") == "000":
            return data.get("induty_code", "")
    except Exception:
        pass
    return None


def find_peers_by_industry(
    target_corp_code: str,
    corp_list_df: pd.DataFrame,
    max_peers: int = 8,
) -> pd.DataFrame:
    """같은 산업코드의 상장사 목록 반환 (시총 기준 상위)"""
    industry_code = get_industry_code(target_corp_code)
    if not industry_code:
        return pd.DataFrame()

    # 산업코드 앞 2자리(대분류)로 매칭
    prefix = industry_code[:2] if len(industry_code) >= 2 else industry_code
    peers = corp_list_df[
        corp_list_df["corp_code"].apply(lambda c: _matches_industry(c, prefix))
    ].copy()
    peers = peers[peers["corp_code"] != target_corp_code]
    return peers.head(max_peers).reset_index(drop=True)


def _matches_industry(corp_code: str, prefix: str) -> bool:
    try:
        resp = requests.get(
            f"{DART_BASE}/company.json",
            params={"crtfc_key": _key(), "corp_code": corp_code},
            timeout=5,
        )
        code = resp.json().get("induty_code", "")
        return code[:2] == prefix if code else False
    except Exception:
        return False


def fetch_peer_multiples(
    peer_corp_codes: list,
    year: int = 2023,
    current_prices: dict = None,
) -> pd.DataFrame:
    """
    피어 기업들의 재무 데이터를 가져와 멀티플 계산
    peer_corp_codes: [(corp_code, corp_name, stock_code), ...]
    current_prices:  {stock_code: price}
    """
    from src.data.dart_api import get_multi_year_financials, get_shares_outstanding
    from src.data.market_data import get_current_price, get_market_cap_from_shares

    rows = []
    for corp_code, corp_name, stock_code in peer_corp_codes:
        try:
            fin = get_multi_year_financials(corp_code, [year], "CFS")
            if fin.empty:
                continue
            latest = fin.iloc[-1]

            def sv(v, d=0.0):
                try:
                    f = float(v)
                    return d if f != f else f
                except Exception:
                    return d

            revenue  = sv(latest.get("revenue"))
            op_inc   = sv(latest.get("operating_income"))
            depr     = sv(latest.get("depreciation"), revenue * 0.05)
            ebitda   = op_inc + depr
            net_inc  = sv(latest.get("net_income"))
            equity   = sv(latest.get("total_equity"))
            long_d   = sv(latest.get("long_term_debt"))
            short_d  = sv(latest.get("short_term_debt"))
            cash     = sv(latest.get("cash"))
            net_debt = long_d + short_d - cash

            # 시총
            shares   = get_shares_outstanding(corp_code, year)
            price    = (current_prices or {}).get(stock_code) or get_current_price(stock_code)
            mkt_cap  = (price * shares / 1e8) if (price and shares) else 0

            if mkt_cap <= 0 or revenue <= 0:
                continue

            ev = mkt_cap + net_debt

            def safe_div(a, b):
                return round(a / b, 2) if b and abs(b) > 0.1 else None

            rows.append({
                "기업명":        corp_name,
                "시총(억)":      round(mkt_cap, 0),
                "EV(억)":       round(ev, 0),
                "EV/Revenue":   safe_div(ev, revenue),
                "EV/EBITDA":    safe_div(ev, ebitda),
                "EV/EBIT":      safe_div(ev, op_inc),
                "P/E":          safe_div(mkt_cap, net_inc),
                "P/B":          safe_div(mkt_cap, equity),
                "EBITDA마진":    f"{ebitda/revenue*100:.1f}%" if revenue > 0 else "N/A",
            })
        except Exception:
            continue

    return pd.DataFrame(rows) if rows else pd.DataFrame()


def comps_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Min / 25% / Median / 75% / Max 요약"""
    if df.empty:
        return pd.DataFrame()
    numeric_cols = ["EV/Revenue", "EV/EBITDA", "EV/EBIT", "P/E", "P/B"]
    valid_cols = [c for c in numeric_cols if c in df.columns]
    numeric = df[valid_cols].apply(pd.to_numeric, errors="coerce")
    return numeric.describe(percentiles=[0.25, 0.5, 0.75]).loc[
        ["min", "25%", "50%", "75%", "max"]
    ].round(2)
