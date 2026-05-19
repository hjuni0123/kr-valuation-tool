"""DART(금융감독원 전자공시) API 연동 모듈"""
import requests, io, zipfile, os, time, pickle
import xml.etree.ElementTree as ET
import pandas as pd
import numpy as np
from typing import Optional

_CORP_CACHE_PATH = os.path.join(os.path.dirname(__file__), "../../.dart_corp_cache.pkl")
_CORP_CACHE_TTL  = 86400  # 24시간

DART_BASE = "https://opendart.fss.or.kr/api"
_CORP_LIST_CACHE: Optional[pd.DataFrame] = None


def _get_api_key() -> str:
    key = os.getenv("DART_API_KEY", "")
    if not key:
        raise ValueError("DART_API_KEY가 설정되지 않았습니다.")
    return key


# ── 계정 매핑 ──────────────────────────────────────────────────────────────
# account_id (XBRL) 기준
ACCOUNT_ID_MAP = {
    "revenue":           ["ifrs-full_Revenue", "dart_Revenue",
                          "ifrs-full_InterestRevenueExpense",   # 은행 순이자손익
                          "ifrs-full_InterestIncome"],          # 은행 이자수익
    "operating_income":  ["dart_OperatingIncomeLoss",
                          "ifrs-full_ProfitLossFromOperatingActivities"],
    "net_income":        ["ifrs-full_ProfitLoss", "dart_ProfitLoss",
                          "ifrs-full_ProfitLossAttributableToOwnersOfParent"],
    "total_assets":      ["ifrs-full_Assets"],
    "total_liabilities": ["ifrs-full_Liabilities"],
    "total_equity":      ["ifrs-full_Equity",
                          "ifrs-full_EquityAttributableToOwnersOfParent"],
    "cash":              ["ifrs-full_CashAndCashEquivalents",
                          "dart_CashAndDuefromBanks"],
    "short_term_debt":   ["ifrs-full_ShorttermBorrowings",
                          "dart_ShorttermBorrowings", "dart_CurrentBorrowings"],
    "long_term_debt":    ["dart_LongTermBorrowings",
                          "ifrs-full_NoncurrentPortionOfLongtermBorrowings"],
    "interest_expense":  ["ifrs-full_FinanceCosts", "dart_FinanceCosts",
                          "ifrs-full_InterestExpense"],
    "depreciation":      ["ifrs-full_DepreciationAndAmortisationExpense",
                          "dart_DepreciationAndAmortisation"],
    "capex":             ["dart_AcquisitionOfPropertyPlantAndEquipment",
                          "ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"],
    "cfo":               ["ifrs-full_CashFlowsFromUsedInOperatingActivities",
                          "dart_CashFlowsFromUsedInOperatingActivities"],
}

# account_nm (한국어 계정명) fallback — 산업별 다양한 표현 포함
ACCOUNT_NM_MAP = {
    "revenue": [
        "매출액", "수익(매출액)", "영업수익", "매출",
        # 은행/금융
        "총영업이익", "순영업이익", "이자및수수료수익", "이자수익",
        "영업이익및이자수익", "순이자손익",
        # 보험
        "보험료수익", "순보험료수익",
    ],
    "operating_income": [
        "영업이익", "영업이익(손실)", "영업손익",
        # 은행/금융
        "순영업이익", "영업이익(은행)",
    ],
    "net_income": [
        "당기순이익", "당기순이익(손실)", "분기순이익",
        "당기순손익", "연결당기순이익",
        # 은행
        "대손준비금 반영 후 조정이익",
    ],
    "total_assets":      ["자산총계"],
    "total_liabilities": ["부채총계"],
    "total_equity":      ["자본총계", "지배기업 소유주지분"],
    "cash":              ["현금및현금성자산", "현금및예치금"],
    "short_term_debt":   ["단기차입금", "유동성장기부채", "단기사채"],
    "long_term_debt":    ["장기차입금", "사채", "장기미지급금", "장기부채"],
    "interest_expense":  ["이자비용", "금융비용"],
    "depreciation":      ["감가상각비", "감가상각비및상각비", "유형자산감가상각비"],
    "capex":             ["유형자산의 취득", "유형자산 취득",
                          "유형자산의취득", "설비투자"],
    "cfo":               ["영업활동 현금흐름", "영업활동으로 인한 현금흐름",
                          "영업활동현금흐름"],
}


# ── 기업 목록 ──────────────────────────────────────────────────────────────
def _load_corp_list() -> pd.DataFrame:
    """기업목록 로드: 메모리 → 디스크 캐시 → DART API 순으로 시도"""
    global _CORP_LIST_CACHE

    # L1: 메모리 캐시
    if _CORP_LIST_CACHE is not None:
        return _CORP_LIST_CACHE

    # L2: 디스크 캐시 (24h TTL)
    cache_path = os.path.abspath(_CORP_CACHE_PATH)
    try:
        if os.path.exists(cache_path):
            age = time.time() - os.path.getmtime(cache_path)
            if age < _CORP_CACHE_TTL:
                with open(cache_path, "rb") as f:
                    _CORP_LIST_CACHE = pickle.load(f)
                return _CORP_LIST_CACHE
    except Exception:
        pass

    # L3: DART API 다운로드
    resp = requests.get(
        f"{DART_BASE}/corpCode.xml",
        params={"crtfc_key": _get_api_key()}, timeout=30,
    )
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        xml_content = z.read([n for n in z.namelist() if n.endswith(".xml")][0])
    root = ET.fromstring(xml_content)
    df = pd.DataFrame([
        {"corp_code": item.findtext("corp_code",""),
         "corp_name": item.findtext("corp_name",""),
         "stock_code": item.findtext("stock_code",""),
         "modify_date": item.findtext("modify_date","")}
        for item in root.findall("list")
    ])
    df = df[df["stock_code"].str.strip() != ""].reset_index(drop=True)
    _CORP_LIST_CACHE = df

    # 디스크에 저장 (실패해도 무시)
    try:
        with open(cache_path, "wb") as f:
            pickle.dump(df, f)
    except Exception:
        pass

    return df


def search_company(name: str) -> pd.DataFrame:
    df = _load_corp_list()
    return df[df["corp_name"].str.contains(name, na=False)].reset_index(drop=True)


# ── 주식수 조회 ────────────────────────────────────────────────────────────
def get_shares_outstanding(corp_code: str, year: int = 2024) -> Optional[float]:
    """DART 주식총수현황 API — 보통주(의결권있는주식) 발행주식수"""
    for y in [year, year - 1, year - 2]:
        for reprt in ["11011", "11013", "11012"]:  # 사업/3분기/반기
            try:
                resp = requests.get(
                    f"{DART_BASE}/stockTotqySttus.json",
                    params={"crtfc_key": _get_api_key(), "corp_code": corp_code,
                            "bsns_year": str(y), "reprt_code": reprt},
                    timeout=10,
                )
                data = resp.json()
                if data.get("status") != "000":
                    continue
                for item in data.get("list", []):
                    se = item.get("se", "")
                    if se not in ("보통주", "의결권 있는 주식"):
                        continue
                    # isu_stock_totqy가 '-'인 경우 여러 대체 필드 시도
                    for field in ["isu_stock_totqy", "istc_totqy",
                                  "now_to_isu_stock_totqy", "distb_stock_co"]:
                        raw = (item.get(field) or "").replace(",", "").strip()
                        if raw and raw not in ("-", "0", ""):
                            try:
                                val = float(raw)
                                if val > 1000:   # 최소 1000주 이상이어야 유효
                                    return val
                            except ValueError:
                                pass
            except Exception:
                continue
    return None


# ── 재무제표 조회 ──────────────────────────────────────────────────────────
def get_financial_statements(corp_code: str, year: int, fs_div: str = "CFS") -> pd.DataFrame:
    resp = requests.get(
        f"{DART_BASE}/fnlttSinglAcntAll.json",
        params={"crtfc_key": _get_api_key(), "corp_code": corp_code,
                "bsns_year": str(year), "reprt_code": "11011", "fs_div": fs_div},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") != "000":
        return pd.DataFrame()
    return pd.DataFrame(data.get("list", []))


def _parse_amount(val) -> Optional[float]:
    if val is None or str(val).strip() in ("", "-"):
        return None
    try:
        return float(str(val).replace(",", "").strip())
    except ValueError:
        return None


def _extract_value(df: pd.DataFrame, key: str) -> Optional[float]:
    """account_id 1차 → account_nm 한국어 2차"""
    # 1차: XBRL account_id
    for aid in ACCOUNT_ID_MAP.get(key, []):
        rows = df[df["account_id"] == aid]
        if not rows.empty:
            val = _parse_amount(rows.iloc[0].get("thstrm_amount"))
            if val is not None:
                return val
    # 2차: 한국어 account_nm (strip 후 완전 일치)
    for nm in ACCOUNT_NM_MAP.get(key, []):
        rows = df[df["account_nm"].str.strip() == nm]
        if not rows.empty:
            val = _parse_amount(rows.iloc[0].get("thstrm_amount"))
            if val is not None:
                return val
    return None


def parse_financials(df: pd.DataFrame) -> dict:
    return {key: _extract_value(df, key) for key in ACCOUNT_ID_MAP}


def get_multi_year_financials(corp_code: str, years: list, fs_div: str = "CFS") -> pd.DataFrame:
    records = []
    for year in sorted(years, reverse=True):
        raw = get_financial_statements(corp_code, year, fs_div)
        if raw.empty:
            continue
        parsed = parse_financials(raw)
        parsed["year"] = year
        records.append(parsed)
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame(records).set_index("year").sort_index()
    for col in df.columns:
        df[col] = df[col].apply(
            lambda x: x / 1e8 if (x is not None and not np.isnan(float(x))) else None
        )
    return df
