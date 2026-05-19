"""주가 데이터 (pykrx OHLCV — 시총은 DART 주식수 × 주가로 계산)"""
import pandas as pd
from pykrx import stock as krx
from datetime import datetime, timedelta
from typing import Optional


def _date_range(days_back: int = 10) -> tuple:
    end   = datetime.today().strftime("%Y%m%d")
    start = (datetime.today() - timedelta(days=days_back)).strftime("%Y%m%d")
    return start, end


def get_current_price(ticker: str) -> Optional[float]:
    try:
        start, end = _date_range(10)
        df = krx.get_market_ohlcv_by_date(start, end, ticker)
        if df.empty:
            return None
        return float(df["종가"].iloc[-1])
    except Exception:
        return None


def get_market_cap_from_shares(ticker: str, shares: float) -> Optional[float]:
    """주가 × 발행주식수 → 시가총액 (억원)"""
    price = get_current_price(ticker)
    if price and shares > 0:
        return round(price * shares / 1e8, 1)
    return None
