"""LBO (Leveraged Buyout) 모델 — Entry→Exit IRR/MOIC"""
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LBOAssumptions:
    # ── Entry ──────────────────────────────────────────────────────────────
    entry_ev: float = 0.0            # 인수 EV (억원), 0이면 DCF EV 사용
    entry_ev_ebitda: float = 10.0    # 인수 EV/EBITDA 배수 (entry_ev==0일 때 사용)
    equity_pct: float = 0.40         # 자기자본 비율 (40% = 60% 레버리지)

    # ── 부채 구조 ──────────────────────────────────────────────────────────
    senior_pct: float = 0.50         # Senior Debt 비율 (EV 대비)
    senior_rate: float = 0.055       # Senior 금리
    mezz_pct: float = 0.10           # Mezzanine 비율
    mezz_rate: float = 0.10          # Mezzanine 금리
    debt_amort_years: int = 7        # 부채 상환 기간

    # ── Exit ───────────────────────────────────────────────────────────────
    exit_year: int = 5               # 보유 기간
    exit_ev_ebitda: float = 10.0     # 엑싯 EV/EBITDA

    # ── 운영 ───────────────────────────────────────────────────────────────
    revenue_growth_rates: list = field(default_factory=lambda: [0.08]*5)
    ebitda_margin: float = 0.20
    tax_rate: float = 0.22
    capex_pct_revenue: float = 0.04
    da_pct_revenue: float = 0.05


def run_lbo(
    base_revenue: float,
    base_ebitda: float,
    assumptions: LBOAssumptions,
) -> dict:
    """LBO 모델 실행 → IRR / MOIC / Cash Flow 반환"""
    a = assumptions

    # ── Entry ──────────────────────────────────────────────────────────────
    entry_ev = a.entry_ev if a.entry_ev > 0 else base_ebitda * a.entry_ev_ebitda
    equity_in  = entry_ev * a.equity_pct
    senior     = entry_ev * a.senior_pct
    mezz       = entry_ev * a.mezz_pct
    total_debt = senior + mezz

    if equity_in <= 0:
        return {"error": "Entry EV 또는 EBITDA를 입력해주세요."}

    # ── 운영 모델 (연도별) ─────────────────────────────────────────────────
    years = max(a.exit_year, len(a.revenue_growth_rates))
    growth = a.revenue_growth_rates
    if len(growth) < years:
        growth = growth + [growth[-1]] * (years - len(growth))

    rows = []
    revenue = base_revenue
    senior_bal = senior
    mezz_bal   = mezz

    for yr in range(1, years + 1):
        revenue    = revenue * (1 + growth[yr-1])
        ebitda     = revenue * a.ebitda_margin
        da         = revenue * a.da_pct_revenue
        ebit       = ebitda - da
        int_senior = senior_bal * a.senior_rate
        int_mezz   = mezz_bal   * a.mezz_rate
        ebt        = ebit - int_senior - int_mezz
        tax        = max(ebt * a.tax_rate, 0)
        net_inc    = ebt - tax
        capex      = revenue * a.capex_pct_revenue
        # FCF to Equity (단순화: NWC 무시)
        fcfe       = net_inc + da - capex

        # 부채 상환 (straight-line)
        amort_sr = senior / a.debt_amort_years if yr <= a.debt_amort_years else 0
        amort_mz = mezz   / a.debt_amort_years if yr <= a.debt_amort_years else 0
        debt_repay = min(amort_sr + amort_mz, max(fcfe, 0))
        senior_bal = max(senior_bal - amort_sr, 0)
        mezz_bal   = max(mezz_bal   - amort_mz, 0)

        rows.append({
            "연도": f"Y{yr}",
            "매출": revenue, "EBITDA": ebitda,
            "이자비용": int_senior + int_mezz,
            "순이익": net_inc,
            "FCFE": fcfe,
            "Senior잔액": senior_bal,
            "Mezz잔액": mezz_bal,
        })

    df = pd.DataFrame(rows)
    exit_yr_data = df.iloc[a.exit_year - 1]
    exit_ebitda  = exit_yr_data["EBITDA"]
    exit_ev      = exit_ebitda * a.exit_ev_ebitda
    exit_debt    = exit_yr_data["Senior잔액"] + exit_yr_data["Mezz잔액"]
    exit_equity  = exit_ev - exit_debt

    # ── 수익률 계산 ────────────────────────────────────────────────────────
    moic = exit_equity / equity_in if equity_in > 0 else 0
    irr_cashflows = [-equity_in] + [0] * (a.exit_year - 1) + [exit_equity]
    try:
        irr = np.irr(irr_cashflows) if hasattr(np, 'irr') else _irr(irr_cashflows)
    except Exception:
        irr = _irr(irr_cashflows)

    # ── 최대 인수 가능 배수 (Target IRR 기준) ─────────────────────────────
    target_irrs = [0.20, 0.25, 0.30]
    max_entry_mults = {}
    for tgt in target_irrs:
        # binary search: 어떤 entry multiple이면 이 IRR이 나오는가
        lo, hi = 1.0, 30.0
        for _ in range(50):
            mid = (lo + hi) / 2
            test_ev     = base_ebitda * mid
            test_eq_in  = test_ev * a.equity_pct
            test_exit   = exit_equity  # exit은 고정
            test_cf     = [-test_eq_in] + [0] * (a.exit_year - 1) + [test_exit]
            test_irr    = _irr(test_cf)
            if test_irr > tgt:
                hi = mid
            else:
                lo = mid
        max_entry_mults[f"{tgt*100:.0f}% IRR"] = round((lo + hi) / 2, 1)

    return {
        "entry_ev":        entry_ev,
        "equity_in":       equity_in,
        "total_debt":      total_debt,
        "senior":          senior,
        "mezz":            mezz,
        "exit_ev":         exit_ev,
        "exit_equity":     exit_equity,
        "exit_debt":       exit_debt,
        "moic":            round(moic, 2),
        "irr":             round(irr, 4) if irr else None,
        "max_entry_mults": max_entry_mults,
        "operating_df":    df,
        "entry_ev_ebitda": entry_ev / base_ebitda if base_ebitda > 0 else 0,
        "exit_ev_ebitda":  a.exit_ev_ebitda,
    }


def _irr(cashflows: list, guess: float = 0.1) -> float:
    """Newton-Raphson IRR 계산"""
    cf = np.array(cashflows, dtype=float)
    r = guess
    for _ in range(1000):
        t   = np.arange(len(cf))
        npv = np.sum(cf / (1 + r) ** t)
        dnpv = np.sum(-t * cf / (1 + r) ** (t + 1))
        if abs(dnpv) < 1e-12:
            break
        r_new = r - npv / dnpv
        if abs(r_new - r) < 1e-8:
            return r_new
        r = r_new
    return r


def lbo_sensitivity(
    base_revenue: float,
    base_ebitda: float,
    a: LBOAssumptions,
    entry_range: list = None,
    exit_range: list = None,
) -> pd.DataFrame:
    """Entry Multiple × Exit Multiple → IRR / MOIC 테이블"""
    if entry_range is None:
        entry_range = [a.entry_ev_ebitda - 2, a.entry_ev_ebitda - 1,
                       a.entry_ev_ebitda, a.entry_ev_ebitda + 1, a.entry_ev_ebitda + 2]
    if exit_range is None:
        exit_range  = [a.exit_ev_ebitda - 2, a.exit_ev_ebitda - 1,
                       a.exit_ev_ebitda, a.exit_ev_ebitda + 1, a.exit_ev_ebitda + 2]

    rows = {}
    for ex in exit_range:
        row = {}
        for en in entry_range:
            try:
                tmp = LBOAssumptions(**{**a.__dict__, "entry_ev": 0,
                                        "entry_ev_ebitda": en, "exit_ev_ebitda": ex})
                res = run_lbo(base_revenue, base_ebitda, tmp)
                irr = res.get("irr", 0) or 0
                row[f"{en:.1f}x"] = f"{irr*100:.1f}%"
            except Exception:
                row[f"{en:.1f}x"] = "N/A"
        rows[f"{ex:.1f}x Exit"] = row

    df = pd.DataFrame(rows).T
    df.index.name = "Exit \\ Entry"
    return df
