"""PDF 1-Page Investment Summary — fpdf2, English labels (deployment-safe)"""
import io
from typing import Optional

try:
    from fpdf import FPDF
    FPDF_AVAILABLE = True
except ImportError:
    FPDF_AVAILABLE = False


def build_pdf_summary(
    corp_name: str,
    ticker: str,
    cur_price: Optional[float],
    mkt_cap: float,
    dcf_result: dict,
    scenario_result: dict,
    lbo_result: Optional[dict],
    mkt_cap_comps: float,
    verdict: str,
    upside_pct: float,
    assumptions_summary: dict,
    fin_summary: dict,
) -> io.BytesIO:
    if not FPDF_AVAILABLE:
        raise ImportError("fpdf2 not installed: pip install fpdf2")

    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=10)

    NAVY  = (0, 51, 102)
    BLACK = (0, 0, 0)
    GRAY  = (120, 120, 120)
    GREEN = (0, 128, 0)
    RED   = (180, 0, 0)
    WHITE = (255, 255, 255)

    def sc(r, g, b): pdf.set_text_color(r, g, b)

    def divider():
        pdf.set_draw_color(*NAVY)
        pdf.set_line_width(0.4)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(2)

    # ── Header ───────────────────────────────────────────────────────────────
    pdf.set_fill_color(*NAVY)
    pdf.rect(0, 0, 210, 18, 'F')
    pdf.set_font("Helvetica", "B", 13)
    sc(*WHITE)
    pdf.set_xy(10, 4)
    pdf.cell(0, 8, f"Investment Research Summary  |  {corp_name}  ({ticker})", ln=True)
    pdf.set_xy(10, 12)
    pdf.set_font("Helvetica", "", 7)
    pdf.cell(0, 4, "KR Valuation Tool  |  DART-based DCF + Comps + LBO  |  Auto-generated", ln=True)
    pdf.ln(5)

    # ── Rating box ───────────────────────────────────────────────────────────
    vc = GREEN if "BUY" in verdict else (RED if "SELL" in verdict else (180, 120, 0))
    pdf.set_fill_color(*vc)
    pdf.set_font("Helvetica", "B", 15)
    sc(*WHITE)
    pdf.set_x(10)
    pdf.cell(45, 11, verdict, fill=True, align="C")

    pdf.set_font("Helvetica", "B", 10)
    sc(*(GREEN if upside_pct >= 0 else RED))
    pdf.set_x(60)
    price_str = "N/A" if not cur_price else f"KRW {cur_price:,.0f}"
    pdf.cell(0, 11,
             f"Upside: {upside_pct:+.1f}%   |   Current Price: {price_str}"
             f"   |   Mkt Cap: {mkt_cap:,.0f} bil KRW", ln=True)
    pdf.ln(2)
    divider()

    # ── Key Financial Metrics ─────────────────────────────────────────────────
    sc(*NAVY)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 5, "Key Financial Metrics (bil KRW)", ln=True)

    pdf.set_font("Helvetica", "", 8)
    sc(*BLACK)
    cols = ["Revenue", "Operating Income", "Net Income", "EBITDA Margin"]
    vals = [
        f"{fin_summary.get('revenue', 0):,.0f}",
        f"{fin_summary.get('operating_income', 0):,.0f}",
        f"{fin_summary.get('net_income', 0):,.0f}",
        f"{fin_summary.get('ebitda_margin', 0)*100:.1f}%",
    ]
    cw = 47
    for i, (c, v) in enumerate(zip(cols, vals)):
        ln = True if i == len(cols)-1 else False
        pdf.set_x(10)
        pdf.cell(cw, 5, c, border="LTB")
        pdf.cell(cw, 5, v, border="RTB", ln=ln)
    pdf.ln(3)
    divider()

    # ── Valuation Summary ─────────────────────────────────────────────────────
    sc(*NAVY)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 5, "Valuation Summary (bil KRW)", ln=True)

    eq_base = dcf_result.get("equity_value", 0)
    pw_eq   = scenario_result.get("probability_weighted_equity", 0)

    val_lines = [
        ("DCF Base Equity Value",       f"{eq_base:,.0f}"),
        ("DCF Prob-Weighted Equity",    f"{pw_eq:,.0f}"),
        ("WACC",                         f"{assumptions_summary.get('wacc', 0)*100:.1f}%"),
        ("Terminal Growth Rate",         f"{assumptions_summary.get('tgr', 0)*100:.1f}%"),
        ("Terminal Value / EV",          f"{dcf_result.get('tv_pct', 0):.1f}%"),
        ("Current Market Cap",           f"{mkt_cap:,.0f}"),
        ("EV/EBITDA Comps Equity",       f"{mkt_cap_comps:,.0f}" if mkt_cap_comps else "N/A"),
    ]
    pdf.set_font("Helvetica", "", 8)
    sc(*BLACK)
    for label, val in val_lines:
        pdf.set_x(10)
        pdf.cell(90, 5, label)
        pdf.cell(50, 5, val, ln=True)
    pdf.ln(2)
    divider()

    # ── Scenario Analysis ─────────────────────────────────────────────────────
    sc(*NAVY)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 5, "Scenario Analysis", ln=True)

    pdf.set_font("Helvetica", "B", 8)
    sc(*BLACK)
    hdrs = ["Scenario", "Weight", "WACC", "Equity Value (bil)"]
    wds  = [38, 22, 22, 50]
    for h, w in zip(hdrs, wds):
        pdf.cell(w, 5, h, border=1, align="C")
    pdf.ln()

    pdf.set_font("Helvetica", "", 8)
    for name, res in scenario_result.get("scenarios", {}).items():
        row = [name, f"{res['weight']*100:.0f}%",
               f"{res['wacc_used']*100:.1f}%",
               f"{res['equity_value']:,.0f}"]
        for d, w in zip(row, wds):
            pdf.cell(w, 5, str(d), border=1, align="C")
        pdf.ln()

    # Prob-weighted row
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(*NAVY)
    sc(*WHITE)
    row2 = ["Prob-Weighted", "100%", "-", f"{pw_eq:,.0f}"]
    for d, w in zip(row2, wds):
        pdf.cell(w, 5, str(d), border=1, align="C", fill=True)
    pdf.ln()
    sc(*BLACK)
    pdf.ln(2)
    divider()

    # ── LBO Summary ───────────────────────────────────────────────────────────
    if lbo_result and "error" not in lbo_result:
        sc(*NAVY)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(0, 5, "LBO Analysis", ln=True)
        pdf.set_font("Helvetica", "", 8)
        sc(*BLACK)
        lbo_lines = [
            ("Entry EV (bil KRW)",  f"{lbo_result.get('entry_ev', 0):,.0f}"),
            ("Entry EV/EBITDA",     f"{lbo_result.get('entry_ev_ebitda', 0):.1f}x"),
            ("Exit EV/EBITDA",      f"{lbo_result.get('exit_ev_ebitda', 0):.1f}x"),
            ("Exit Equity (bil)",   f"{lbo_result.get('exit_equity', 0):,.0f}"),
            ("MOIC",                f"{lbo_result.get('moic', 0):.2f}x"),
            ("IRR",                 f"{(lbo_result.get('irr') or 0)*100:.1f}%"),
        ]
        for label, val in lbo_lines:
            pdf.set_x(10)
            pdf.cell(80, 5, label)
            pdf.cell(50, 5, val, ln=True)
        pdf.ln(2)
        divider()

    # ── Footer ────────────────────────────────────────────────────────────────
    pdf.set_y(-13)
    pdf.set_font("Helvetica", "I", 6.5)
    sc(*GRAY)
    pdf.cell(0, 5,
             "This report is auto-generated based on DART public filings. "
             "Do not use as sole basis for investment decisions. | KR Valuation Tool",
             align="C")

    buf = io.BytesIO(pdf.output())
    buf.seek(0)
    return buf
