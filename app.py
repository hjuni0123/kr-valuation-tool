"""
KR Valuation Tool — IB · Research · VC 포트폴리오급 가치평가 자동화
DART API · DCF · Scenario · LBO · Comps · Unit Economics · PDF Export
"""
import os, sys
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError:
    pass

sys.path.insert(0, os.path.dirname(__file__))

from src.data.dart_api import (
    search_company, get_multi_year_financials,
    get_shares_outstanding, _load_corp_list,
)
from src.data.market_data import get_current_price, get_market_cap_from_shares
from src.models.dcf import (
    DCFAssumptions, run_dcf, sensitivity_analysis,
    estimate_cost_of_equity, calculate_wacc, compute_wacc_from_beta,
)
from src.models.scenario import ScenarioSet, run_scenarios, scenario_summary_df
from src.models.lbo import LBOAssumptions, run_lbo, lbo_sensitivity
from src.models.unit_economics import UnitEconomicsInputs, compute_unit_economics
from src.data.peer_comps import fetch_peer_multiples, comps_stats
from src.charts.football_field import build_football_field, build_waterfall_chart
from src.charts.excel_export import build_excel_model

# ── 페이지 설정 ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="KR Valuation Tool",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.main-title{font-size:1.9rem;font-weight:800;color:#003366;margin-bottom:0}
.sub-title{font-size:.88rem;color:#777;margin-top:0;margin-bottom:6px}
.section-hd{font-size:1.05rem;font-weight:700;color:#003366;
    border-bottom:2px solid #003366;padding-bottom:3px;
    margin-top:20px;margin-bottom:8px}
.kpi-box{background:#f0f4f8;border-left:4px solid #003366;
    padding:10px 14px;border-radius:6px;margin-bottom:6px}
.verdict-buy{background:#d4edda;border-left:5px solid #28a745;
    padding:14px;border-radius:6px}
.verdict-hold{background:#fff3cd;border-left:5px solid #ffc107;
    padding:14px;border-radius:6px}
.verdict-sell{background:#f8d7da;border-left:5px solid #dc3545;
    padding:14px;border-radius:6px}
div[data-testid="stMetricValue"]{font-size:1.25rem!important;color:#003366!important}
</style>
""", unsafe_allow_html=True)


# ── API 키 ─────────────────────────────────────────────────────────────────
def _get_key(inp=""):
    if inp: return inp
    try: return st.secrets["DART_API_KEY"]
    except Exception: pass
    return os.getenv("DART_API_KEY", "")

# 시작 시 secrets에서 키 자동 주입 (Streamlit Cloud 배포 대응)
_boot_key = _get_key()
if _boot_key:
    os.environ["DART_API_KEY"] = _boot_key

def sv(val, default=0.0):
    try:
        v = float(val); return default if v != v else v
    except: return default

def fv(val, unit="억", d="N/A"):
    try:
        v = float(val); return f"{v:,.0f}{unit}" if v==v else d
    except: return d


# ── 헤더 ─────────────────────────────────────────────────────────────────
st.markdown('<p class="main-title">📊 KR Valuation Tool</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-title">Goldman Sachs 방식 · DCF + 3-Scenario · LBO · Trading Comps · VC Unit Economics · 한국 상장사 DART 자동화</p>', unsafe_allow_html=True)
st.divider()

# ── 사이드바 ──────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ 설정")
    dart_key_input = st.text_input("DART API Key (선택)", type="password",
                                   help="비워두면 secrets.toml 자동 로드")
    st.divider()
    st.header("🔍 기업 검색")
    company_name   = st.text_input("기업명", placeholder="예: 카카오, 삼성전자, 기업은행")
    search_btn     = st.button("검색", use_container_width=True, type="primary")
    analysis_years = st.multiselect("재무제표 연도",
                                    [2025,2024,2023,2022,2021,2020],
                                    default=[2024,2023,2022])
    fs_raw = st.radio("재무제표 기준", ["연결(CFS)","별도(OFS)"], horizontal=True)
    fs_div_code = "CFS" if "연결" in fs_raw else "OFS"

# ── 세션 상태 ─────────────────────────────────────────────────────────────
_defaults = dict(search_results=None, selected_corp=None, financials=None,
                 ticker="", corp_code="", shares=None, mkt_cap=0.0, cur_price=None,
                 dcf_result=None, scenario_result=None, lbo_result=None,
                 peer_df=pd.DataFrame(), assumptions=None, comps_eq_val=0.0)
for k, v in _defaults.items():
    if k not in st.session_state: st.session_state[k] = v

# ── 검색 ─────────────────────────────────────────────────────────────────
if search_btn and company_name:
    key = _get_key(dart_key_input)
    if not key:
        st.sidebar.error("DART API Key가 없습니다.")
    else:
        os.environ["DART_API_KEY"] = key
        with st.spinner(f"'{company_name}' 검색 중..."):
            r = search_company(company_name)
        if r.empty: st.sidebar.error("검색 결과 없음")
        else:
            st.session_state.search_results = r
            st.session_state.selected_corp  = None

if st.session_state.search_results is not None:
    df_r    = st.session_state.search_results
    opts    = [f"{r['corp_name']} ({r['stock_code']})" for _,r in df_r.iterrows()]
    sel     = st.sidebar.selectbox("기업 선택", opts)
    corp_row = df_r.iloc[opts.index(sel)]

    if st.sidebar.button("재무데이터 불러오기", use_container_width=True, type="secondary"):
        key = _get_key(dart_key_input)
        os.environ["DART_API_KEY"] = key
        with st.spinner("DART 재무제표 로딩 중..."):
            fin_df = get_multi_year_financials(corp_row["corp_code"], analysis_years, fs_div_code)
        if fin_df.empty:
            st.sidebar.error("재무 데이터 없음. 연도를 바꿔보세요.")
        else:
            ticker = corp_row["stock_code"]
            with st.spinner("주가·주식수 조회 중..."):
                shares    = get_shares_outstanding(corp_row["corp_code"],
                                                   max(analysis_years) if analysis_years else 2024)
                cur_price = get_current_price(ticker)
                mkt_cap   = get_market_cap_from_shares(ticker, shares) if shares else None
            for k, v in [("financials", fin_df), ("selected_corp", corp_row),
                          ("ticker", ticker), ("corp_code", corp_row["corp_code"]),
                          ("shares", shares), ("cur_price", cur_price),
                          ("mkt_cap", mkt_cap or 0.0),
                          ("dcf_result", None), ("scenario_result", None),
                          ("lbo_result", None), ("peer_df", pd.DataFrame())]:
                st.session_state[k] = v

# ═══════════════════════════════════════════════════════════════════════════
if st.session_state.financials is None:
    st.markdown("""
### 사용 방법
1. 왼쪽에서 **기업명 검색** → 선택 → **재무데이터 불러오기**
2. 각 탭에서 순서대로 분석 진행
3. **PDF/Excel 탭**에서 포트폴리오용 결과물 다운로드
""")
    c1,c2,c3,c4 = st.columns(4)
    c1.info("**DCF + Scenario**\nBull/Base/Bear 3케이스\n확률가중 가치 산출")
    c2.info("**LBO 분석**\nEntry→Exit IRR/MOIC\n최대 인수 배수 계산")
    c3.info("**Trading Comps**\n동종업계 자동 멀티플\nEV/EBITDA, P/E, P/B")
    c4.info("**VC Unit Economics**\nLTV/CAC, Rule of 40\n코호트 분석")
    st.stop()

# ═══════════════════════════════════════════════════════════════════════════
#  데이터 준비
# ═══════════════════════════════════════════════════════════════════════════
corp      = st.session_state.selected_corp
fin       = st.session_state.financials
ticker    = st.session_state.ticker
cur_price = st.session_state.cur_price
auto_mkt  = st.session_state.mkt_cap

latest_year = fin.index[-1]
latest      = fin.loc[latest_year]

base_rev    = sv(latest.get("revenue"))
oper_inc    = sv(latest.get("operating_income"))
depr        = sv(latest.get("depreciation"), base_rev * 0.05)
base_ebitda = oper_inc + depr if (oper_inc + depr) > 0 else base_rev * 0.15
long_debt   = sv(latest.get("long_term_debt"))
short_debt  = sv(latest.get("short_term_debt"))
cash_val    = sv(latest.get("cash"))
total_assets = sv(latest.get("total_assets"))
total_liab   = sv(latest.get("total_liabilities"))
total_eq     = sv(latest.get("total_equity"))

liab_ratio   = total_liab / total_assets if total_assets > 0 else 0
is_financial = liab_ratio > 0.85
calc_net_debt = long_debt + short_debt - cash_val
default_nd   = 0.0 if is_financial else calc_net_debt

# 시총
if auto_mkt and auto_mkt > 0:
    mkt_cap = auto_mkt
else:
    mkt_cap = 0.0

default_wacc = 0.10
if mkt_cap > 0 and base_rev > 0:
    debt    = long_debt + short_debt
    int_exp = sv(latest.get("interest_expense"))
    kd      = (int_exp / debt) if debt > 0 else 0.05
    ke      = estimate_cost_of_equity(beta=1.0)
    default_wacc = max(0.07, min(round(calculate_wacc(mkt_cap, debt, ke, kd), 3), 0.18))

# ── 기업 개요 헤더 ────────────────────────────────────────────────────────
st.markdown(f'<p class="section-hd">{corp["corp_name"]} ({ticker}) — 기업 개요</p>',
            unsafe_allow_html=True)

if is_financial:
    st.warning(f"⚠️ **금융업 감지** (부채비율 {liab_ratio*100:.0f}%) — 순차입금 = 0 적용. "
               "DCF 결과는 참고용, 실무에서는 P/B · ROE-DDM 병행 권장.")

if not auto_mkt or auto_mkt == 0:
    st.warning("시가총액 자동 조회 실패")
    mkt_cap = st.number_input("시가총액 직접 입력 (억원)", 0.0, step=100.0, key="mkt_cap_manual")

with st.expander("⚙️ 순차입금 조정", expanded=False):
    nd_c1, nd_c2 = st.columns([3,1])
    net_debt = nd_c1.number_input("순차입금 (억원)", value=float(round(default_nd,0)),
                                  step=100.0, key="net_debt_input")
    nd_c2.caption(f"자동계산: {calc_net_debt:,.0f}억")

c1,c2,c3,c4,c5 = st.columns(5)
c1.metric("현재 주가",          f"₩{cur_price:,.0f}" if cur_price else "N/A")
c2.metric("시가총액",            fv(mkt_cap))
c3.metric(f"매출({latest_year})", fv(latest.get("revenue")))
c4.metric(f"영업이익({latest_year})", fv(latest.get("operating_income")))
c5.metric(f"순이익({latest_year})",   fv(latest.get("net_income")))

with st.expander("📋 재무제표 원본 (억원)", expanded=False):
    lmap = {"revenue":"매출액","operating_income":"영업이익","net_income":"순이익",
            "total_assets":"총자산","total_liabilities":"총부채","total_equity":"자본",
            "cash":"현금","cfo":"영업CF"}
    show = fin[[c for c in lmap if c in fin.columns]].rename(columns=lmap)
    st.dataframe(show.style.format(lambda x: f"{x:,.0f}" if pd.notna(x) else "N/A"),
                 use_container_width=True)

# ── 역사적 재무 추이 차트 ─────────────────────────────────────────────────
_hist_years = [str(y) for y in fin.index]
_rev   = [sv(fin.loc[y, "revenue"])          if "revenue"          in fin.columns else 0 for y in fin.index]
_op    = [sv(fin.loc[y, "operating_income"]) if "operating_income" in fin.columns else 0 for y in fin.index]
_ni    = [sv(fin.loc[y, "net_income"])       if "net_income"       in fin.columns else 0 for y in fin.index]
_depr  = [sv(fin.loc[y, "depreciation"], _rev[i]*0.05 if _rev[i] else 0)
          if "depreciation" in fin.columns else _rev[i]*0.05
          for i, y in enumerate(fin.index)]
_ebitda_margin = [
    (_op[i] + _depr[i]) / _rev[i] * 100 if _rev[i] > 0 else 0
    for i in range(len(_rev))
]

fig_hist = go.Figure()
fig_hist.add_trace(go.Bar(
    name="Revenue", x=_hist_years, y=_rev,
    marker_color="#003366", opacity=0.85,
    text=[f"{v:,.0f}" for v in _rev], textposition="outside",
    textfont_size=9,
))
fig_hist.add_trace(go.Bar(
    name="Operating Income", x=_hist_years, y=_op,
    marker_color="#0066CC", opacity=0.85,
))
fig_hist.add_trace(go.Bar(
    name="Net Income", x=_hist_years, y=_ni,
    marker_color="#66B2FF", opacity=0.85,
))
fig_hist.add_trace(go.Scatter(
    name="EBITDA Margin (%)", x=_hist_years, y=_ebitda_margin,
    mode="lines+markers+text",
    line=dict(color="#CC3300", width=2.5),
    marker=dict(size=7),
    text=[f"{v:.1f}%" for v in _ebitda_margin], textposition="top center",
    textfont_size=9,
    yaxis="y2",
))
fig_hist.update_layout(
    title=dict(text="Historical Financial Performance (억원)", font_size=14),
    barmode="group",
    xaxis=dict(title="Year", tickfont_size=11),
    yaxis=dict(title="억원", showgrid=True, gridcolor="#EFEFEF"),
    yaxis2=dict(title="EBITDA Margin (%)", overlaying="y", side="right",
                showgrid=False, ticksuffix="%", range=[0, max(_ebitda_margin)*2+5] if any(_ebitda_margin) else [0,50]),
    plot_bgcolor="white", paper_bgcolor="white",
    legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0),
    height=340,
    margin=dict(t=60, b=40, l=60, r=60),
)
st.plotly_chart(fig_hist, use_container_width=True)

st.divider()

# ═══════════════════════════════════════════════════════════════════════════
#  8탭 메인 레이아웃
# ═══════════════════════════════════════════════════════════════════════════
tabs = st.tabs([
    "📦 사업부별 매출",
    "📈 DCF + 시나리오",
    "⚽ Football Field",
    "🏦 LBO 분석",
    "📊 Trading Comps",
    "🚀 VC Unit Economics",
    "📌 투자 결론",
    "📥 Export",
])
tab_seg, tab_dcf, tab_ff, tab_lbo, tab_comps, tab_vc, tab_verdict, tab_export = tabs

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 1: 사업부별 매출 추정
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_seg:
    st.markdown('<p class="section-hd">사업부별 매출 추정 (Segmented Revenue Projection)</p>',
                unsafe_allow_html=True)
    st.caption("각 사업부 이름을 기업에 맞게 수정하세요. 합계가 DCF Base Revenue로 반영됩니다.")

    use_pq = st.checkbox("P×Q 분해 모드 (단가 성장 + 물량 성장 분리 입력)", value=False)
    n_seg  = st.number_input("사업부 수", 1, 6, 3, step=1)

    segments = []
    total_seg_rev = 0.0

    for i in range(int(n_seg)):
        st.markdown(f"**사업부 {i+1}**")
        col_a, col_b = st.columns([2,2])
        seg_name = col_a.text_input("사업부명",
            value=f"사업부 {i+1}", key=f"sn_{i}",
            help="예: 기업대출/가계대출(은행), 반도체/가전(삼성), 광고/커머스(카카오)")
        default_base = round(base_rev / n_seg, 0) if base_rev > 0 else 0.0
        seg_rev = col_b.number_input("Base 매출 (억원)", value=default_base,
                                     step=10.0, key=f"sr_{i}")

        growths = []
        if use_pq:
            gcols = st.columns(5)
            for j in range(5):
                with gcols[j]:
                    st.caption(f"Y{j+1}")
                    pg = st.number_input("P(%)", value=3.0, step=0.5,
                                         key=f"pg_{i}_{j}", format="%.1f")
                    qg = st.number_input("Q(%)", value=7.0, step=0.5,
                                         key=f"qg_{i}_{j}", format="%.1f")
                    comb = (1+pg/100)*(1+qg/100)-1
                    st.caption(f"합: **{comb*100:.1f}%**")
                    growths.append(comb)
        else:
            gcols = st.columns(5)
            defs  = [10,9,8,7,6]
            for j in range(5):
                g = gcols[j].number_input(f"Y{j+1}(%)", value=float(defs[j]),
                                          step=1.0, key=f"sg_{i}_{j}", format="%.1f")
                growths.append(g/100)

        segments.append({"name": seg_name, "revenue": seg_rev, "growths": growths})
        total_seg_rev += seg_rev
        st.divider()

    # 합계 프리뷰 테이블
    prev_revs = [total_seg_rev]
    for yr in range(5):
        yr_rev = sum(s["revenue"] * np.prod([1+s["growths"][k] for k in range(yr+1)])
                     for s in segments)
        prev_revs.append(yr_rev)
    st.dataframe(
        pd.DataFrame([prev_revs], columns=["Base"]+[f"Y+{i}" for i in range(1,6)],
                     index=["Total Revenue (억원)"]).style.format("{:,.0f}"),
        use_container_width=True)

    use_segments = st.checkbox("DCF에 세그먼트 합계 반영", value=True)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 2: DCF + Scenario Analysis
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_dcf:
    st.markdown('<p class="section-hd">DCF 분석 + Bull / Base / Bear Scenario</p>',
                unsafe_allow_html=True)
    col_l, col_r = st.columns([1, 2])

    with col_l:
        proj_years = st.slider("프로젝션 기간", 3, 7, 5)

        if use_segments and total_seg_rev > 0:
            dcf_base_rev = total_seg_rev
            seg_t = total_seg_rev
            g_defs = [max(-10, min(60, round(
                sum(s["revenue"]/seg_t*s["growths"][yr] for s in segments)*100
            ))) for yr in range(5)]
            st.info(f"Base Revenue: 세그먼트 합계 **{total_seg_rev:,.0f}억원**")
        else:
            dcf_base_rev = base_rev
            g_defs = [10,9,8,7,6]

        st.markdown("**① 매출 성장률 (Base)**")
        g1=st.slider("Y1(%)",-10,60,g_defs[0])/100
        g2=st.slider("Y2(%)",-10,50,g_defs[1])/100
        g3=st.slider("Y3(%)",-10,40,g_defs[2])/100
        g4=st.slider("Y4(%)",-10,30,g_defs[3])/100
        g5=st.slider("Y5(%)",-10,25,g_defs[4])/100

        st.markdown("**② 수익성 (영업레버리지)**")
        default_em = max(1, int(base_ebitda/base_rev*100) if base_rev>0 else 15)
        ebitda_pct  = st.slider("기준 EBITDA 마진(%)", 1, 60, default_em)/100
        margin_exp  = st.slider("연간 마진 개선(bps)", -100, 300, 50)/10000
        capex_life  = st.slider("CapEx 내용연수(년)", 0, 10, 5)

        st.markdown("**③ WACC**")
        with st.expander("레버드 베타 → CAPM 계산기", expanded=False):
            w1, w2 = st.columns(2)
            ul_beta = w1.number_input("Unlevered Beta", 0.1, 3.0, 0.8, 0.05)
            rf_rate = w1.number_input("Rf(%)", 0.0, 10.0, 3.5, 0.1)/100
            erp_val = w2.number_input("ERP(%)", 1.0, 15.0, 6.0, 0.1)/100
            kd_val  = w2.number_input("Kd(%)", 1.0, 15.0, 5.0, 0.1)/100
            if mkt_cap > 0:
                wc = compute_wacc_from_beta(ul_beta, mkt_cap, net_debt,
                                            kd_val, 0.22, rf_rate, erp_val)
                st.success(f"β_L={wc['levered_beta']:.3f} | Ke={wc['cost_of_equity']*100:.2f}% | **WACC={wc['wacc']*100:.2f}%**")

        wacc_pct = st.slider("WACC(%)", 6, 20, int(default_wacc*100))/100
        tgr_pct  = st.slider("Terminal 성장률(%)", 0, 5, 2)/100
        t_method = st.radio("Terminal Value", ["Gordon Growth","Exit Multiple"], horizontal=True)
        exit_mult= st.slider("Exit EV/EBITDA", 5, 25, 10) if t_method=="Exit Multiple" else 10

        st.markdown("**④ Scenario 조정**")
        bull_mult  = st.slider("Bull 성장 배율", 1.0, 3.0, 1.5, 0.1)
        bear_mult  = st.slider("Bear 성장 배율", 0.1, 1.0, 0.5, 0.1)
        bull_marg  = st.slider("Bull 마진 조정(bps)", 0, 500, 300)/10000
        bear_marg  = st.slider("Bear 마진 조정(bps)", -500, 0, -300)/10000

    assumptions = DCFAssumptions(
        projection_years=proj_years,
        revenue_growth_rates=[g1,g2,g3,g4,g5],
        ebitda_margin=ebitda_pct,
        margin_expansion_annual=margin_exp,
        capex_useful_life=capex_life,
        wacc=wacc_pct,
        terminal_growth_rate=tgr_pct,
        terminal_method="gordon" if t_method=="Gordon Growth" else "exit_multiple",
        exit_multiple=exit_mult,
    )
    st.session_state.assumptions = assumptions

    dcf_result = scenario_result = None
    ev_dcf = eq_dcf = 0.0

    if dcf_base_rev > 0:
        dcf_ebitda = dcf_base_rev * ebitda_pct
        base_da    = sv(latest.get("depreciation"), dcf_base_rev*0.05)
        dcf_result = run_dcf(dcf_base_rev, dcf_ebitda, net_debt, assumptions, base_da=base_da)
        ev_dcf = sv(dcf_result["enterprise_value"])
        eq_dcf = sv(dcf_result["equity_value"])
        st.session_state.dcf_result = dcf_result

        # Scenario
        sc_set = ScenarioSet(
            growth_multipliers=[bear_mult, 1.0, bull_mult],
            margin_deltas=[bear_marg, 0.0, bull_marg],
            wacc_deltas=[0.01, 0.0, -0.01],
            tgr_deltas=[-0.005, 0.0, 0.005],
        )
        scenario_result = run_scenarios(dcf_base_rev, dcf_ebitda, net_debt,
                                        assumptions, sc_set, base_da=base_da)
        st.session_state.scenario_result = scenario_result

        with col_r:
            st.markdown("**DCF Base 결과**")
            r1,r2,r3 = st.columns(3)
            r1.metric("EV",           f"{ev_dcf:,.0f}억")
            r2.metric("Equity Value", f"{eq_dcf:,.0f}억")
            r3.metric("TV 비중",       f"{dcf_result['tv_pct']:.1f}%")

            st.plotly_chart(build_waterfall_chart(dcf_result), use_container_width=True)

            # Scenario 요약
            st.markdown("**Scenario Analysis (Bull / Base / Bear)**")
            sc_df = scenario_summary_df(scenario_result)
            pw    = scenario_result["probability_weighted_equity"]

            def _color_scenario(val):
                s = str(val)
                if "Bull" in s: return "color: #28a745; font-weight:bold"
                if "Bear" in s: return "color: #dc3545; font-weight:bold"
                if "확률가중" in s: return "background:#003366;color:white;font-weight:bold"
                return ""
            st.dataframe(
                sc_df.style.applymap(_color_scenario, subset=["시나리오"])
                           .format({"EV (억원)": "{:,.0f}", "Equity Value (억)": "{:,.0f}"}),
                use_container_width=True, hide_index=True
            )

            if mkt_cap > 0:
                pw_upside = (pw - mkt_cap)/mkt_cap*100
                st.info(f"확률가중 Equity {pw:,.0f}억 | 현재 시총 대비 **{pw_upside:+.1f}%**")

        with st.expander("🔬 민감도 분석 (WACC × TGR)", expanded=True):
            sens = sensitivity_analysis(dcf_base_rev, dcf_ebitda, net_debt, assumptions)
            mid_r = f"{tgr_pct*100:.1f}%"
            mid_c = f"{wacc_pct*100:.1f}%"
            styled = sens.style.format("{:,.0f}억")
            if mid_r in sens.index and mid_c in sens.columns:
                styled = styled.map(
                    lambda _: "background:#003366;color:white;font-weight:bold",
                    subset=pd.IndexSlice[[mid_r],[mid_c]]
                )
            st.dataframe(styled, use_container_width=True)
    else:
        with col_r:
            st.warning("매출 데이터 없음. 사업부 탭에서 Base 매출을 입력해주세요.")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 3: Football Field (전체 시나리오 통합)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_ff:
    st.markdown('<p class="section-hd">Football Field Chart — 전체 밸류에이션 범위</p>',
                unsafe_allow_html=True)

    pc1,pc2,pc3 = st.columns(3)
    peer_low  = pc1.number_input("피어 EV/EBITDA Low",   value=6.0, step=0.5)
    peer_mid  = pc2.number_input("피어 EV/EBITDA Median", value=10.0, step=0.5)
    peer_high = pc3.number_input("피어 EV/EBITDA High",  value=14.0, step=0.5)

    dcf_result    = st.session_state.dcf_result
    scenario_result = st.session_state.scenario_result

    if dcf_result and scenario_result:
        ebitda_fc = dcf_base_rev * ebitda_pct if dcf_base_rev > 0 else base_ebitda
        comps_low  = peer_low  * ebitda_fc - net_debt
        comps_mid  = peer_mid  * ebitda_fc - net_debt
        comps_high = peer_high * ebitda_fc - net_debt

        sc_vals = {n: scenario_result["scenarios"][n]["equity_value"]
                   for n in ["Bear","Base","Bull"]}

        ranges = {
            "Bear Case DCF":    (sc_vals["Bear"]*0.95, sc_vals["Bear"]*1.05),
            "Base Case DCF":    (sc_vals["Base"]*0.95, sc_vals["Base"]*1.05),
            "Bull Case DCF":    (sc_vals["Bull"]*0.95, sc_vals["Bull"]*1.05),
            "EV/EBITDA Comps":  (comps_low, comps_high),
        }
        ff = build_football_field(ranges, mkt_cap if mkt_cap>0 else None)
        st.plotly_chart(ff, use_container_width=True)

        # 통합 요약
        sum_data = [
            ("Bear Case DCF",     sc_vals["Bear"]),
            ("Base Case DCF",     sc_vals["Base"]),
            ("Bull Case DCF",     sc_vals["Bull"]),
            ("확률가중 DCF",       scenario_result["probability_weighted_equity"]),
            ("EV/EBITDA Low",     comps_low),
            ("EV/EBITDA Median",  comps_mid),
            ("EV/EBITDA High",    comps_high),
            ("현재 시총",          mkt_cap),
        ]
        sum_df = pd.DataFrame(sum_data, columns=["방법론","Equity Value (억원)"])
        sum_df["Equity Value (억원)"] = sum_df["Equity Value (억원)"].apply(
            lambda x: f"{x:,.0f}" if x and x==x else "N/A")
        st.dataframe(sum_df, use_container_width=True, hide_index=True)
    else:
        st.info("DCF 탭에서 분석을 먼저 실행해주세요.")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 4: LBO 분석
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_lbo:
    st.markdown('<p class="section-hd">LBO 분석 (Leveraged Buyout)</p>', unsafe_allow_html=True)
    st.caption("PE 펀드 관점의 인수·운영·엑싯 수익률 분석")

    la, lb = st.columns([1,2])
    with la:
        st.markdown("**Entry 가정**")
        lbo_entry_mult = st.number_input("Entry EV/EBITDA (배수)", 6.0, 25.0,
                                         float(mkt_cap/base_ebitda+net_debt/base_ebitda)
                                         if base_ebitda>0 and mkt_cap>0 else 10.0,
                                         0.5)
        lbo_eq_pct = st.slider("자기자본 비율(%)", 20, 60, 40)/100
        lbo_sr_pct = st.slider("Senior Debt 비율(% of EV)", 30, 60, 50)/100
        lbo_mz_pct = st.slider("Mezz Debt 비율(% of EV)", 0, 20, 10)/100
        lbo_sr_rate= st.number_input("Senior 금리(%)", 3.0, 12.0, 5.5, 0.1)/100
        lbo_mz_rate= st.number_input("Mezz 금리(%)", 6.0, 18.0, 10.0, 0.1)/100

        st.markdown("**Exit 가정**")
        lbo_exit_yr  = st.slider("보유 기간(년)", 3, 7, 5)
        lbo_exit_mult= st.number_input("Exit EV/EBITDA (배수)", 5.0, 25.0, 10.0, 0.5)

        run_lbo_btn = st.button("LBO 계산", type="primary")

    # lbo_a는 항상 정의 (민감도 테이블에서 재사용)
    lbo_a = LBOAssumptions(
        entry_ev_ebitda      = lbo_entry_mult,
        equity_pct           = lbo_eq_pct,
        senior_pct           = lbo_sr_pct,
        mezz_pct             = lbo_mz_pct,
        senior_rate          = lbo_sr_rate,
        mezz_rate            = lbo_mz_rate,
        exit_year            = lbo_exit_yr,
        exit_ev_ebitda       = lbo_exit_mult,
        revenue_growth_rates = [g1,g2,g3,g4,g5],
        ebitda_margin        = ebitda_pct,
    )

    with lb:
        if run_lbo_btn or st.session_state.lbo_result:
            if run_lbo_btn and base_ebitda > 0:
                lbo_res = run_lbo(base_rev if dcf_base_rev==0 else dcf_base_rev,
                                  base_ebitda, lbo_a)
                st.session_state.lbo_result = lbo_res

            lbo_res = st.session_state.lbo_result
            if lbo_res and "error" not in lbo_res:
                irr_val  = lbo_res.get("irr") or 0
                moic_val = lbo_res.get("moic", 0)

                irr_color = "#28a745" if irr_val>=0.20 else ("#ffc107" if irr_val>=0.15 else "#dc3545")
                m1,m2,m3,m4 = st.columns(4)
                m1.metric("Entry EV", f"{lbo_res['entry_ev']:,.0f}억")
                m2.metric("Exit EV",  f"{lbo_res['exit_ev']:,.0f}억")
                m3.metric("MOIC",     f"{moic_val:.2f}x")
                m4.metric("IRR",      f"{irr_val*100:.1f}%")

                # 자본구조 파이
                fig_pie = go.Figure(go.Pie(
                    labels=["자기자본","Senior","Mezz"],
                    values=[lbo_res["equity_in"], lbo_res["senior"], lbo_res["mezz"]],
                    hole=0.4, marker_colors=["#003366","#0066CC","#66B2FF"]
                ))
                fig_pie.update_layout(title="Entry 자본구조", height=280,
                                      margin=dict(t=40,b=0,l=0,r=0),
                                      showlegend=True)
                st.plotly_chart(fig_pie, use_container_width=True)

                # 운영 모델
                st.markdown("**연도별 운영 모델**")
                op = lbo_res["operating_df"][["연도","매출","EBITDA","이자비용","순이익","FCFE"]].set_index("연도")
                st.dataframe(op.style.format("{:,.0f}"), use_container_width=True)

                # 최대 인수 배수 테이블
                st.markdown("**Target IRR별 최대 인수 가능 Entry Multiple**")
                max_mults = lbo_res.get("max_entry_mults", {})
                if max_mults:
                    st.dataframe(pd.DataFrame([max_mults]), use_container_width=True, hide_index=True)

                # 민감도
                st.markdown("**Exit × Entry Multiple → IRR**")
                try:
                    sens_lbo = lbo_sensitivity(
                        base_rev if dcf_base_rev==0 else dcf_base_rev,
                        base_ebitda, lbo_a
                    )
                    st.dataframe(sens_lbo, use_container_width=True)
                except Exception as e:
                    st.caption(f"민감도 계산 오류: {e}")
        else:
            st.info("왼쪽에서 가정 설정 후 **LBO 계산** 버튼을 누르세요.")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 5: Trading Comps (동종업계 자동 멀티플)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_comps:
    st.markdown('<p class="section-hd">Trading Comps — 동종업계 멀티플 비교</p>',
                unsafe_allow_html=True)

    st.subheader("피어 기업 수동 추가")
    st.caption("DART에서 동종업계 기업명을 검색해 직접 추가하거나, 아래에 EV/EBITDA를 수동으로 입력하세요.")

    peer_name_inp = st.text_input("피어 기업명 검색", key="peer_search_inp",
                                  placeholder="예: NAVER, SK텔레콤, 넷마블")

    if st.button("피어 기업 조회 및 추가", key="peer_add_btn"):
        if peer_name_inp:
            key = _get_key(dart_key_input)
            os.environ["DART_API_KEY"] = key
            with st.spinner(f"{peer_name_inp} 재무 데이터 수집 중..."):
                pr = search_company(peer_name_inp)
            if not pr.empty:
                pr_corp = pr.iloc[0]
                year_to_fetch = max(analysis_years) if analysis_years else 2023
                with st.spinner("멀티플 계산 중..."):
                    new_df = fetch_peer_multiples(
                        [(pr_corp["corp_code"], pr_corp["corp_name"], pr_corp["stock_code"])],
                        year=year_to_fetch
                    )
                if not new_df.empty:
                    existing = st.session_state.peer_df
                    st.session_state.peer_df = pd.concat([existing, new_df], ignore_index=True).drop_duplicates("기업명")
                    st.success(f"{pr_corp['corp_name']} 추가 완료")
                else:
                    st.warning("멀티플 계산 실패 (재무 데이터 부족)")
            else:
                st.warning("검색 결과 없음")

    # 피어 테이블 표시
    peer_df = st.session_state.peer_df
    if not peer_df.empty:
        st.markdown("**피어 그룹 멀티플**")
        st.dataframe(peer_df, use_container_width=True, hide_index=True)
        st.markdown("**피어 요약 통계**")
        st.dataframe(comps_stats(peer_df), use_container_width=True)

        # 대상 기업 implied value
        st.markdown("**대상 기업 Implied Equity Value (피어 Median 기준)**")
        ebitda_fc = dcf_base_rev * ebitda_pct if dcf_base_rev>0 else base_ebitda
        numeric   = peer_df[["EV/EBITDA","EV/Revenue","P/E"]].apply(pd.to_numeric, errors="coerce")
        implied_rows = []
        for col in numeric.columns:
            med = numeric[col].median()
            if pd.notna(med) and med > 0:
                if "EV/" in col:
                    metric = ebitda_fc if "EBITDA" in col else base_rev
                    impl_ev = med * metric
                    impl_eq = impl_ev - net_debt
                elif col == "P/E":
                    impl_eq = med * sv(latest.get("net_income"))
                else:
                    impl_eq = 0
                if impl_eq > 0:
                    implied_rows.append({
                        "방법론": f"{col} (피어 Median {med:.1f}x)",
                        "Implied Equity (억)": f"{impl_eq:,.0f}",
                        "vs 현재 시총": f"{(impl_eq-mkt_cap)/mkt_cap*100:+.1f}%" if mkt_cap>0 else "N/A"
                    })
        if implied_rows:
            st.dataframe(pd.DataFrame(implied_rows), use_container_width=True, hide_index=True)
    else:
        st.info("위에서 피어 기업을 검색해 추가하거나, Football Field 탭에서 EV/EBITDA를 수동 입력하세요.")

    # 수동 피어 입력 (백업)
    with st.expander("✏️ EV/EBITDA 수동 입력 (피어 데이터 없을 때)", expanded=peer_df.empty):
        c1,c2,c3 = st.columns(3)
        peer_low_m  = c1.number_input("Low",    value=6.0, step=0.5, key="pm_low")
        peer_mid_m  = c2.number_input("Median", value=10.0, step=0.5, key="pm_mid")
        peer_high_m = c3.number_input("High",   value=14.0, step=0.5, key="pm_high")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 6: VC Unit Economics
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_vc:
    st.markdown('<p class="section-hd">VC Unit Economics — LTV/CAC · Rule of 40 · 코호트</p>',
                unsafe_allow_html=True)
    st.caption("플랫폼·SaaS·구독 비즈니스 투자 시 핵심 지표")

    v1, v2 = st.columns([1, 2])
    with v1:
        st.markdown("**고객 지표**")
        vc_cac     = st.number_input("CAC (원/고객)", value=50000, step=1000)
        vc_arpu    = st.number_input("ARPU 월 (원/고객)", value=30000, step=1000)
        vc_churn   = st.slider("월간 Churn(%)", 0.5, 20.0, 3.0, 0.5)/100
        vc_gm      = st.slider("Gross Margin(%)", 10, 95, 70)/100

        st.markdown("**성장 지표**")
        vc_rev_growth = st.slider("YoY 매출 성장률(%)", -20, 200, 40)/100
        vc_ebitda_m   = st.slider("EBITDA Margin(%)", -50, 50, -10)/100
        vc_arr        = st.number_input("ARR (억원, 0이면 자동)", value=0.0, step=10.0)
        vc_new_cust   = st.number_input("월 신규 고객수", value=1000, step=100)

    ue_inp = UnitEconomicsInputs(
        cac=vc_cac, arpu_monthly=vc_arpu, monthly_churn=vc_churn,
        gross_margin=vc_gm, revenue_growth_yoy=vc_rev_growth,
        ebitda_margin=vc_ebitda_m, arr=vc_arr, monthly_new_customers=vc_new_cust,
    )
    ue = compute_unit_economics(ue_inp)

    with v2:
        st.markdown("**핵심 지표**")
        m1,m2,m3,m4 = st.columns(4)
        m1.metric("LTV/CAC",       f"{ue['ltv_cac']:.2f}x",  ue["ltv_cac_grade"])
        m2.metric("CAC Payback",   f"{ue['payback_months']:.1f}M", ue["payback_grade"])
        m3.metric("Rule of 40",    f"{ue['rule_of_40']:.1f}", ue["r40_grade"])
        m4.metric("Avg Lifetime",  f"{ue['avg_lifetime_mo']:.1f}M")

        # 등급 설명
        grade_color = "verdict-buy" if ue["ltv_cac"] >= 3 else \
                      ("verdict-hold" if ue["ltv_cac"] >= 1 else "verdict-sell")
        st.markdown(f"""
<div class="{grade_color}">
<b>LTV = {ue['ltv']:,.0f}원</b> | CAC = {ue['cac']:,.0f}원 | <b>LTV/CAC = {ue['ltv_cac']:.2f}x</b><br>
월 Churn {vc_churn*100:.1f}% → 평균 고객 유지 {ue['avg_lifetime_mo']:.1f}개월<br>
{'✅ 건전한 Unit Economics' if ue['ltv_cac']>=3 else ('⚠️ 개선 필요' if ue['ltv_cac']>=1 else '🚨 위험: LTV < CAC')}
</div>""", unsafe_allow_html=True)

        st.markdown("**코호트 분석 (가입 후 월별 잔존율 & CAC 회수)**")
        st.dataframe(ue["cohort_df"].head(18).set_index("Month"),
                     use_container_width=True)

        if ue.get("magic_number"):
            st.metric("Magic Number", f"{ue['magic_number']:.2f}",
                      "Good (>0.75)" if ue["magic_number"]>0.75 else "주의 (<0.75)")

        # Rule of 40 게이지
        r40 = ue["rule_of_40"]
        fig_r40 = go.Figure(go.Indicator(
            mode="gauge+number",
            value=r40,
            gauge={"axis":{"range":[-20,80]},
                   "bar":{"color": "#003366"},
                   "steps":[
                       {"range":[-20,20],"color":"#f8d7da"},
                       {"range":[20,40],"color":"#fff3cd"},
                       {"range":[40,80],"color":"#d4edda"},
                   ],
                   "threshold":{"line":{"color":"red","width":2},"value":40}},
            title={"text":"Rule of 40"},
        ))
        fig_r40.update_layout(height=220, margin=dict(t=30,b=10,l=20,r=20))
        st.plotly_chart(fig_r40, use_container_width=True)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 7: 투자 결론
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_verdict:
    st.markdown('<p class="section-hd">📌 Investment Verdict</p>', unsafe_allow_html=True)

    dcf_result      = st.session_state.dcf_result
    scenario_result = st.session_state.scenario_result

    if dcf_result and scenario_result and mkt_cap > 0:
        eq_base = sv(dcf_result.get("equity_value"))
        pw_eq   = sv(scenario_result.get("probability_weighted_equity"))
        ev_base = sv(dcf_result.get("enterprise_value"))

        dcf_up = (eq_base - mkt_cap)/mkt_cap*100
        pw_up  = (pw_eq  - mkt_cap)/mkt_cap*100

        # 피어 comps upside
        peer_df = st.session_state.peer_df
        pm_mid  = peer_mid_m if peer_df.empty else (
            peer_df["EV/EBITDA"].apply(pd.to_numeric, errors="coerce").median() or peer_mid_m)
        ebitda_fc = dcf_base_rev*ebitda_pct if dcf_base_rev>0 else base_ebitda
        comps_eq  = pm_mid * ebitda_fc - net_debt
        comps_up  = (comps_eq - mkt_cap)/mkt_cap*100 if mkt_cap>0 else 0
        st.session_state["comps_eq_val"] = comps_eq

        avg_up = (pw_up*0.6 + comps_up*0.4)

        if avg_up >= 20:   grade, icon, css = "BUY (Outperform)",      "🟢", "verdict-buy"
        elif avg_up >= -10: grade, icon, css = "HOLD (Market Perform)", "🟡", "verdict-hold"
        else:               grade, icon, css = "SELL (Underperform)",   "🔴", "verdict-sell"

        ev_mult = ev_base/ebitda_fc if ebitda_fc>0 else 0
        lbo_res = st.session_state.lbo_result

        st.markdown(f"""
<div class="{css}">
<h2>{icon} {grade}</h2>

| 지표 | 수치 |
|------|------|
| 현재 시총 | {mkt_cap:,.0f}억원 |
| DCF Base Equity | {eq_base:,.0f}억원 ({dcf_up:+.1f}%) |
| DCF 확률가중 Equity | {pw_eq:,.0f}억원 ({pw_up:+.1f}%) |
| EV/EBITDA Comps | {comps_eq:,.0f}억원 ({comps_up:+.1f}%) |
| 종합 업사이드 (60% DCF·40% Comps) | **{avg_up:+.1f}%** |
| DCF implied EV/EBITDA | {ev_mult:.1f}x |
{"| LBO IRR | " + f"{(lbo_res.get('irr') or 0)*100:.1f}% |" if lbo_res and 'error' not in lbo_res else ""}

**투자 논거 (Investment Thesis)**

① **DCF**: WACC {wacc_pct*100:.1f}%, TGR {tgr_pct*100:.1f}% 기준 Base Equity **{eq_base:,.0f}억**, 업사이드 **{dcf_up:+.1f}%**.
확률가중 시 **{pw_eq:,.0f}억** ({pw_up:+.1f}%). Terminal Value가 EV의 {dcf_result['tv_pct']:.0f}%로
{'장기 성장 기대 의존도 높음 → TGR 가정 보수적 검토 필요' if dcf_result['tv_pct']>70 else '현금흐름 가시성 양호'}.

② **Trading Comps**: 피어 EV/EBITDA {pm_mid:.1f}x 적용 시 **{comps_eq:,.0f}억** ({comps_up:+.1f}%).
현재 implied multiple {ev_mult:.1f}x — 피어 대비 {'프리미엄 (성장성·수익성 우위 논거 필요)' if ev_mult>pm_mid else '디스카운트 (저평가 or 펀더멘털 약화)' }.

③ **리스크 요인**: WACC +1%p 충격 시 Equity 하락 가능. Bull/Bear spread
{abs(scenario_result['scenarios']['Bull']['equity_value'] - scenario_result['scenarios']['Bear']['equity_value']):,.0f}억으로
가정 변화에 따른 밸류에이션 불확실성 상당함.
</div>
""", unsafe_allow_html=True)
    elif dcf_result:
        st.info("시가총액을 입력하면 투자 결론이 자동 생성됩니다.")
    else:
        st.info("DCF 탭 분석을 먼저 완료해주세요.")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 8: Export (Excel + PDF)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_export:
    st.markdown('<p class="section-hd">Export — Excel 수식 모델 + PDF 1-Page Summary</p>',
                unsafe_allow_html=True)

    col_xl, col_pdf = st.columns(2)

    with col_xl:
        st.markdown("**📊 Excel — 수식 살아있는 DCF 모델**")
        st.markdown("""
- **Assumptions** 시트: 노란셀 편집 → 전체 수식 자동 갱신
- **Segments** 시트: 사업부별 매출 수식 연결
- **DCF Model**: NOPAT → FCF → PV → EV → Equity 전 과정 수식
- **Sensitivity**: WACC × TGR 테이블
- **Summary**: 핵심 결과 1장
        """)
        if st.button("📥 Excel 생성", type="primary"):
            dcf_result = st.session_state.dcf_result
            if not dcf_result:
                st.error("DCF 탭을 먼저 실행해주세요.")
            else:
                with st.spinner("Excel 생성 중..."):
                    segs = segments if (use_segments and total_seg_rev>0) else None
                    buf = build_excel_model(
                        corp_name=corp["corp_name"], fin_df=fin,
                        assumptions=assumptions, dcf_result=dcf_result,
                        net_debt=net_debt, mkt_cap=mkt_cap, segments=segs,
                    )
                st.download_button(
                    f"📊 {corp['corp_name']}_DCF모델.xlsx",
                    buf,
                    file_name=f"{corp['corp_name']}_valuation_model.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

    with col_pdf:
        st.markdown("**📄 PDF — 1-Page Investment Summary**")
        st.markdown("""
- 투자등급 (BUY/HOLD/SELL)
- DCF Base + 확률가중 Equity
- Scenario 요약 테이블
- LBO IRR/MOIC (LBO 실행 시)
- 면접·PT용 1장 출력
        """)
        if st.button("📄 PDF 생성", type="primary"):
            dcf_result      = st.session_state.dcf_result
            scenario_result = st.session_state.scenario_result
            lbo_result      = st.session_state.lbo_result

            if not dcf_result or not scenario_result:
                st.error("DCF + Scenario 탭을 먼저 실행해주세요.")
            else:
                try:
                    from src.charts.pdf_report import build_pdf_summary, FPDF_AVAILABLE
                    if not FPDF_AVAILABLE:
                        st.error("fpdf2 미설치: 터미널에서 `pip install fpdf2` 실행 후 재시작하세요.")
                    else:
                        eq_b = sv(dcf_result.get("equity_value"))
                        pw_e = sv(scenario_result.get("probability_weighted_equity"))
                        avg_up_val = (pw_e - mkt_cap)/mkt_cap*100 if mkt_cap>0 else 0
                        if avg_up_val>=20: vrd="BUY"
                        elif avg_up_val>=-10: vrd="HOLD"
                        else: vrd="SELL"

                        with st.spinner("PDF 생성 중..."):
                            buf = build_pdf_summary(
                                corp_name=corp["corp_name"], ticker=ticker,
                                cur_price=cur_price, mkt_cap=mkt_cap,
                                dcf_result=dcf_result,
                                scenario_result=scenario_result,
                                lbo_result=lbo_result,
                                mkt_cap_comps=st.session_state.get("comps_eq_val", 0),
                                verdict=vrd, upside_pct=avg_up_val,
                                assumptions_summary={"wacc":wacc_pct,"tgr":tgr_pct},
                                fin_summary={
                                    "revenue":      sv(latest.get("revenue")),
                                    "operating_income": sv(latest.get("operating_income")),
                                    "net_income":   sv(latest.get("net_income")),
                                    "ebitda_margin": base_ebitda/base_rev if base_rev>0 else 0,
                                },
                            )
                        st.download_button(
                            f"📄 {corp['corp_name']}_InvestmentSummary.pdf",
                            buf,
                            file_name=f"{corp['corp_name']}_investment_summary.pdf",
                            mime="application/pdf",
                        )
                except Exception as e:
                    st.error(f"PDF 오류: {e}")
