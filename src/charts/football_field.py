"""Football Field Chart - Goldman Sachs 스타일 밸류에이션 범위 시각화"""
import plotly.graph_objects as go
import pandas as pd


GS_COLORS = {
    "DCF": "#003366",
    "EV/EBITDA": "#0066CC",
    "EV/EBIT": "#3399FF",
    "EV/Revenue": "#66B2FF",
    "P/E": "#99CCFF",
    "현재주가": "#CC0000",
}


def build_football_field(
    valuation_ranges: dict,
    current_equity_value: float = None,
    currency: str = "억원",
) -> go.Figure:
    """
    valuation_ranges = {
        "DCF (Base)": (low, high),
        "EV/EBITDA Comps": (low, high),
        ...
    }
    """
    methods = list(valuation_ranges.keys())
    lows = [valuation_ranges[m][0] for m in methods]
    highs = [valuation_ranges[m][1] for m in methods]
    widths = [h - l for l, h in zip(lows, highs)]

    fig = go.Figure()

    for i, method in enumerate(methods):
        color = list(GS_COLORS.values())[i % len(GS_COLORS)]
        fig.add_trace(go.Bar(
            name=method,
            y=[method],
            x=[lows[i]],
            orientation="h",
            marker_color="rgba(0,0,0,0)",
            showlegend=False,
            hoverinfo="skip",
        ))
        fig.add_trace(go.Bar(
            name=method,
            y=[method],
            x=[widths[i]],
            orientation="h",
            base=lows[i],
            marker_color=color,
            marker_line_color="white",
            marker_line_width=1,
            text=f"  {lows[i]:,.0f} ~ {highs[i]:,.0f} {currency}",
            textposition="outside",
            hovertemplate=(
                f"<b>{method}</b><br>"
                f"Low: {lows[i]:,.0f} {currency}<br>"
                f"High: {highs[i]:,.0f} {currency}<extra></extra>"
            ),
        ))

    if current_equity_value:
        fig.add_vline(
            x=current_equity_value,
            line_dash="dash",
            line_color="#CC0000",
            line_width=2,
            annotation_text=f"현재 시총<br>{current_equity_value:,.0f}",
            annotation_position="top",
            annotation_font_color="#CC0000",
        )

    fig.update_layout(
        title={
            "text": "Valuation Football Field Chart",
            "font": {"size": 20, "family": "Arial Black"},
        },
        barmode="overlay",
        xaxis_title=f"주주 가치 ({currency})",
        yaxis={"categoryorder": "array", "categoryarray": methods[::-1]},
        height=80 + len(methods) * 70,
        plot_bgcolor="white",
        paper_bgcolor="white",
        showlegend=False,
        margin={"l": 160, "r": 200, "t": 60, "b": 50},
        font={"family": "Arial, sans-serif"},
    )
    fig.update_xaxes(showgrid=True, gridcolor="#E5E5E5", zeroline=True, zerolinecolor="#CCCCCC")
    fig.update_yaxes(showgrid=False)

    return fig


def build_waterfall_chart(dcf_result: dict, currency: str = "억원") -> go.Figure:
    """DCF 구성 요소 워터폴 차트"""
    pv_fcf = dcf_result["pv_fcf_sum"]
    pv_tv = dcf_result["pv_terminal_value"]
    net_debt = dcf_result["enterprise_value"] - dcf_result["equity_value"]
    equity = dcf_result["equity_value"]

    labels = ["PV(FCF)", "PV(Terminal Value)", "EV", "(-) 순차입금", "Equity Value"]
    values = [pv_fcf, pv_tv, 0, -net_debt, 0]
    measures = ["relative", "relative", "total", "relative", "total"]
    texts = [f"{v:,.0f}" if v != 0 else "" for v in [pv_fcf, pv_tv, dcf_result["enterprise_value"], -net_debt, equity]]

    fig = go.Figure(go.Waterfall(
        orientation="v",
        measure=measures,
        x=labels,
        y=values,
        text=texts,
        textposition="outside",
        connector={"line": {"color": "#CCCCCC"}},
        increasing={"marker": {"color": "#003366"}},
        decreasing={"marker": {"color": "#CC3300"}},
        totals={"marker": {"color": "#0066CC"}},
    ))

    fig.update_layout(
        title={"text": "DCF 가치 브릿지", "font": {"size": 18}},
        yaxis_title=currency,
        plot_bgcolor="white",
        paper_bgcolor="white",
        height=400,
        showlegend=False,
    )
    return fig
