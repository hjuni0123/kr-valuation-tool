"""주가 데이터 — pykrx (로컬) / yfinance (Streamlit Cloud 배포 폴백)"""
from datetime import datetime, timedelta
from typing import Optional

# pykrx: setuptools 의존성 문제로 배포 환경에서 실패할 수 있음
try:
    from pykrx import stock as krx
    _PYKRX = True
except Exception:
    _PYKRX = False

# yfinance: 배포 환경 대체
try:
    import yfinance as yf
    _YFINANCE = True
except Exception:
    _YFINANCE = False


def _date_range(days_back: int = 10) -> tuple:
    end   = datetime.today().strftime("%Y%m%d")
    start = (datetime.today() - timedelta(days=days_back)).strftime("%Y%m%d")
    return start, end


def get_current_price(ticker: str) -> Optional[float]:
    """현재 주가 조회 — pykrx 우선, yfinance 폴백"""
    # pykrx (로컬)
    if _PYKRX:
        try:
            start, end = _date_range(10)
            df = krx.get_market_ohlcv_by_date(start, end, ticker)
            if not df.empty:
                return float(df["종가"].iloc[-1])
        except Exception:
            pass

    # yfinance (배포 환경)
    if _YFINANCE:
        for suffix in [".KS", ".KQ"]:
            try:
                hist = yf.Ticker(ticker + suffix).history(period="5d")
                if not hist.empty:
                    return float(hist["Close"].iloc[-1])
            except Exception:
                continue

    return None


def get_market_cap_from_shares(ticker: str, shares: float) -> Optional[float]:
    """주가 × 발행주식수 → 시가총액 (억원)"""
    price = get_current_price(ticker)
    if price and shares > 0:
        return round(price * shares / 1e8, 1)
    return None
