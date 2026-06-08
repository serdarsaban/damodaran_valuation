"""
report_generator.py
===================
Generates a self-contained downloadable HTML valuation report.

Runs all 6 modules from a CompanyData object, renders results into
a single annotated HTML file with:
  - Cover page with summary metrics
  - Step-by-step calculations matching the Damodaran methodology
  - Textbook formula references for every calculation
  - Comparison tables (model vs market price)
  - Source/data quality audit trail

Usage
-----
    from report_generator import generate_report
    html = generate_report(company_data, assumptions)
    # In Streamlit:
    st.download_button("Download Report", html, f"{ticker}_valuation.html", "text/html")
"""

from __future__ import annotations
import math
import json
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional

import sys
sys.path.insert(0, '/home/claude')

from data_fetcher import CompanyData
from cost_of_capital import full_cost_of_capital
from fcff_models import fcff_2stage
from growth_models import estimate_growth, terminal_value_gordon
from relative_valuation import justified_equity_multiples, justified_firm_multiples, score_multiple
from optimal_capital_structure import optimal_capital_structure


# ─────────────────────────────────────────────────────────────────────────────
# Report assumptions — user-adjustable before generating
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ReportAssumptions:
    # Growth
    g_high:          float = 0.10    # high-growth rate
    n_high:          int   = 5       # high-growth years
    g_stable:        float = 0.03    # stable growth (perpetuity)
    stable_roc:      float = 0.12    # stable ROC (for terminal RIR)
    # Multiples context
    payout_high:     float = 0.30
    payout_stable:   float = 0.60
    net_margin:      float = 0.10
    # Capital structure
    run_ocs:         bool  = True
    # ERP
    erp:             float = 0.055


# ─────────────────────────────────────────────────────────────────────────────
# HTML primitives
# ─────────────────────────────────────────────────────────────────────────────

def _pct(v, dec=2):     return f"{v:.{dec}%}" if v is not None else "N/A"
def _usd(v, dec=0):     return f"${v:,.{dec}f}m" if v is not None else "N/A"
def _num(v, dec=2):     return f"{v:,.{dec}f}" if v is not None else "N/A"
def _x(v, dec=1):       return f"{v:.{dec}f}×" if v is not None else "N/A"

def _score_colour(score: int) -> str:
    if score >= 7: return "#22c55e"
    if score >= 4: return "#f59e0b"
    return "#ef4444"

def _badge(score: int, text: str) -> str:
    c = _score_colour(score)
    return (f'<span style="display:inline-block;padding:3px 10px;border-radius:20px;'
            f'font-size:0.78rem;font-weight:500;background:{c}22;color:{c};'
            f'border:1px solid {c}44">{score}/10 — {text}</span>')

def _section(title: str, subtitle: str = "") -> str:
    sub = f'<p style="color:#64748b;font-size:0.9rem;margin:4px 0 0 0">{subtitle}</p>' if subtitle else ""
    return f'''
<div style="margin:40px 0 20px 0;padding-bottom:12px;border-bottom:2px solid #1e3a5f">
  <h2 style="font-family:\'DM Serif Display\',serif;font-size:1.6rem;color:#f1f5f9;margin:0">{title}</h2>
  {sub}
</div>'''

def _metric_row(*metrics) -> str:
    """metrics: list of (label, value, delta?) tuples"""
    cells = ""
    for m in metrics:
        label, value = m[0], m[1]
        delta = m[2] if len(m) > 2 else ""
        delta_html = f'<div style="font-size:0.75rem;color:#64748b;margin-top:2px">{delta}</div>' if delta else ""
        cells += f'''
<div style="background:#0f172a;border:1px solid #1e293b;border-radius:10px;padding:16px 20px;flex:1;min-width:140px">
  <div style="font-size:0.68rem;text-transform:uppercase;letter-spacing:2px;color:#475569;margin-bottom:4px">{label}</div>
  <div style="font-size:1.7rem;font-family:\'DM Serif Display\',serif;color:#f1f5f9;letter-spacing:-0.5px">{value}</div>
  {delta_html}
</div>'''
    return f'<div style="display:flex;gap:12px;flex-wrap:wrap;margin:16px 0">{cells}</div>'

def _formula_box(formula: str, note: str = "", source: str = "") -> str:
    src = f'<div style="font-size:0.7rem;color:#475569;margin-top:8px">📚 {source}</div>' if source else ""
    nt  = f'<div style="color:#94a3b8;margin-top:6px;font-size:0.85rem">{note}</div>' if note else ""
    return f'''
<div style="background:#1e293b;border-left:3px solid #3b82f6;border-radius:0 8px 8px 0;
     padding:14px 18px;margin:12px 0;font-family:monospace;font-size:0.9rem;color:#7dd3fc">
  {formula}
  {nt}
  {src}
</div>'''

def _table(headers: list, rows: list, highlight_row: int = -1) -> str:
    th = "".join(f'<th style="padding:8px 12px;text-align:left;font-size:0.78rem;font-weight:500;color:#64748b;border-bottom:1px solid #1e293b">{h}</th>' for h in headers)
    tr_html = ""
    for i, row in enumerate(rows):
        bg = "background:#14532d22" if i == highlight_row else ("background:#0f172a" if i % 2 == 0 else "background:#111827")
        td = "".join(f'<td style="padding:8px 12px;font-size:0.85rem;color:#cbd5e1;border-bottom:1px solid #1e293b1a">{cell}</td>' for cell in row)
        tr_html += f'<tr style="{bg}">{td}</tr>'
    return f'''
<table style="width:100%;border-collapse:collapse;margin:12px 0;border-radius:8px;overflow:hidden">
  <thead><tr style="background:#1e293b">{th}</tr></thead>
  <tbody>{tr_html}</tbody>
</table>'''

def _warn_box(text: str) -> str:
    return f'<div style="background:#292524;border:1px solid #78350f;border-radius:8px;padding:12px 16px;color:#fde68a;font-size:0.85rem;margin:10px 0">⚠ {text}</div>'

def _ok_box(text: str) -> str:
    return f'<div style="background:#14532d22;border:1px solid #22c55e44;border-radius:8px;padding:12px 16px;color:#86efac;font-size:0.85rem;margin:10px 0">✓ {text}</div>'


# ─────────────────────────────────────────────────────────────────────────────
# Report sections
# ─────────────────────────────────────────────────────────────────────────────

def _section_cover(d: CompanyData, a: ReportAssumptions, coc, g, fcff, eq_m, fm) -> str:
    date = datetime.now().strftime("%d %B %Y")
    price = d.price or 0

    # Collect implied prices
    implied = {}
    if fcff and fcff.value_per_share:
        implied["FCFF (2-stage)"] = fcff.value_per_share
    if eq_m and eq_m.implied_price_pe:
        implied["PE Multiple"] = eq_m.implied_price_pe
    if eq_m and eq_m.implied_price_pbv:
        implied["PBV Multiple"] = eq_m.implied_price_pbv
    if fm and fm.implied_ev_from_ebit:
        ev = fm.implied_ev_from_ebit
        eq = ev - d.book_debt + d.cash
        implied["EV/EBIT Multiple"] = eq / d.shares if d.shares > 0 else 0

    avg_implied = sum(implied.values()) / len(implied) if implied else 0
    premium = (price / avg_implied - 1) if avg_implied > 0 and price > 0 else None

    wacc_str = _pct(coc.wacc_result.wacc) if coc else "N/A"
    ke_str   = _pct(coc.beta_result.ke)   if coc else "N/A"
    g_str    = _pct(g.recommended_growth)  if g else "N/A"

    implied_rows = "".join(
        f'<tr><td style="padding:6px 12px;color:#94a3b8;font-size:0.85rem">{k}</td>'
        f'<td style="padding:6px 12px;color:#f1f5f9;font-size:0.9rem;font-weight:500">${v:.2f}</td>'
        f'<td style="padding:6px 12px;font-size:0.85rem;color:{"#86efac" if v > price else "#fca5a5"}">'
        f'{"↑" if v > price else "↓"} {abs(v/price-1)*100:.1f}% {"upside" if v > price else "downside"}</td></tr>'
        for k, v in implied.items() if v > 0
    ) if price > 0 else ""

    sentiment = "Potentially undervalued" if premium and premium < -0.15 else (
                "Potentially overvalued"  if premium and premium > 0.15 else
                "Broadly fairly valued")
    sent_col  = "#86efac" if "under" in sentiment else ("#fca5a5" if "over" in sentiment else "#fde68a")

    return f'''
<div style="background:linear-gradient(135deg,#0f172a 0%,#1e3a5f 100%);border-radius:16px;padding:48px;margin-bottom:40px">
  <div style="font-size:0.75rem;text-transform:uppercase;letter-spacing:3px;color:#3b82f6;margin-bottom:8px">Damodaran Investment Valuation Toolkit</div>
  <h1 style="font-family:\'DM Serif Display\',serif;font-size:2.8rem;color:#f1f5f9;margin:0 0 4px 0;letter-spacing:-1px">{d.name}</h1>
  <div style="font-size:1rem;color:#64748b;margin-bottom:4px">{d.ticker} · Valuation date: {date}</div>
  <div style="font-size:0.8rem;color:#475569">Data source: {d.source} · Based on: Aswath Damodaran, <em>Investment Valuation</em> 2nd Ed.</div>
</div>

{_section("Executive Summary", "Key metrics and implied valuation range")}

{_metric_row(
    ("Current Price", f"${price:.2f}" if price else "N/A"),
    ("Avg Implied Value", f"${avg_implied:.2f}" if avg_implied else "N/A",
     f'{premium*100:+.1f}% {"premium" if premium > 0 else "discount"} to current price' if premium is not None else ""),
    ("WACC", wacc_str),
    ("Cost of Equity", ke_str),
    ("Recommended Growth", g_str),
)}

<div style="margin:16px 0;padding:16px 20px;background:#0f172a;border:1px solid #1e293b;border-radius:10px">
  <div style="font-size:0.75rem;text-transform:uppercase;letter-spacing:2px;color:#475569;margin-bottom:12px">Implied Value by Method</div>
  <table style="width:100%;border-collapse:collapse">
    <thead><tr>
      <th style="text-align:left;padding:6px 12px;color:#64748b;font-size:0.78rem;border-bottom:1px solid #1e293b">Method</th>
      <th style="text-align:left;padding:6px 12px;color:#64748b;font-size:0.78rem;border-bottom:1px solid #1e293b">Implied Price</th>
      <th style="text-align:left;padding:6px 12px;color:#64748b;font-size:0.78rem;border-bottom:1px solid #1e293b">vs Market</th>
    </tr></thead>
    <tbody>{implied_rows}</tbody>
  </table>
  <div style="margin-top:12px;padding:10px 14px;background:{sent_col}22;border-radius:6px;color:{sent_col};font-size:0.88rem;font-weight:500">
    Overall signal: {sentiment}
  </div>
</div>'''


def _section_coc(d: CompanyData, coc) -> str:
    if not coc: return ""
    dc=coc.debt_cost; br=coc.beta_result; wr=coc.wacc_result

    from cost_of_capital import _TABLE_NAMES
    tname = _TABLE_NAMES.get(dc.firm_type,"Unknown")

    sweep_rows = ""
    # Show WACC build-up table
    return f'''
{_section("Module 01 — Cost of Capital", "Ch 7–8 · ratings.xls · levbeta.xls · wacccalc.xls")}

<h3 style="color:#e2e8f0;font-size:1.1rem;margin:20px 0 8px 0">Step 1 — Synthetic Credit Rating [{tname}]</h3>
{_formula_box("ICR = EBIT / Interest_Expense = " + _num(d.ebit) + " / " + _num(d.interest_expense) + " = " + _num(dc.icr,2) + "×",
              "Look up ICR in rating table → default spread → cost of debt",
              "Damodaran, Ch 8, p.183; ratings.xls")}
{_metric_row(
    ("ICR", f"{dc.icr:.2f}×" if dc.icr < 999 else "∞"),
    ("Rating", dc.rating),
    ("Company Spread", _pct(dc.company_spread)),
    ("Pre-tax kd", _pct(dc.kd_pretax)),
    ("After-tax kd", _pct(dc.kd_aftertax)),
)}

<h3 style="color:#e2e8f0;font-size:1.1rem;margin:20px 0 8px 0">Step 2 — Beta & Cost of Equity (Hamada / CAPM)</h3>
{_formula_box(
    "β_u = β_L / [1 + (1−t)×D/E] = " + _num(br.beta_levered_input,3) + " / [1 + (1−" + _pct(br.tax_rate,0) + ")×" + _num(br.current_de,3) + "] = " + _num(br.beta_unlevered,3) + "<br>" +
    "ke = rf + β_L × ERP = " + _pct(br.rf) + " + " + _num(br.beta_relevered,3) + " × " + _pct(br.erp) + " = " + _pct(br.ke),
    source="Damodaran, Ch 8, p.170; levbeta.xls")}
{_metric_row(
    ("Unlevered β", _num(br.beta_unlevered,3)),
    ("Re-levered β", _num(br.beta_relevered,3)),
    ("rf", _pct(br.rf)),
    ("ERP", _pct(br.erp)),
    ("Cost of Equity", _pct(br.ke)),
)}

<h3 style="color:#e2e8f0;font-size:1.1rem;margin:20px 0 8px 0">Step 3 — Market Value of Debt & WACC</h3>
{_formula_box(
    "MV(Debt) = Interest × [1−(1+kd)^−n]/kd + Book_Debt/(1+kd)^n = " + _usd(coc.market_debt) + "<br>" +
    "WACC = " + _pct(br.ke) + "×" + _pct(wr.weight_equity,0) + " + " + _pct(dc.kd_aftertax) + "×" + _pct(wr.weight_debt,0) + " = " + _pct(wr.wacc),
    source="Damodaran, Ch 8, p.194–195; wacccalc.xls")}
{_metric_row(
    ("Book Debt", _usd(d.book_debt)),
    ("Market Debt", _usd(coc.market_debt)),
    ("Equity Weight", _pct(wr.weight_equity,0)),
    ("Debt Weight", _pct(wr.weight_debt,0)),
    ("WACC", _pct(wr.wacc)),
)}'''


def _section_growth(d: CompanyData, g, tv) -> str:
    if not g: return ""
    return f'''
{_section("Module 03 — Growth & Terminal Value", "Ch 11–12 · chgrowth.xls")}

<h3 style="color:#e2e8f0;font-size:1.1rem;margin:20px 0 8px 0">Growth Estimation — Three Approaches</h3>
{_formula_box(
    "g (firm) = ROC × Reinvestment_Rate = " + _pct(g.roc) + " × " + _pct(g.reinvestment_rate) + " = " + _pct(g.fundamental_growth_firm) + "<br>" +
    "g (equity) = ROE × Retention_Ratio = " + _pct(g.roe) + " × " + _pct(g.retention_ratio) + " = " + _pct(g.fundamental_growth_equity),
    source="Damodaran, Ch 11, p.278")}
{_table(
    ["Approach", "Growth Rate", "Basis"],
    [
        ["Fundamental (firm)",   _pct(g.fundamental_growth_firm),   "ROC × RIR"],
        ["Fundamental (equity)", _pct(g.fundamental_growth_equity), "ROE × Retention"],
        ["Historical EPS CAGR",  _pct(g.historical_eps_cagr) if g.historical_eps_cagr else "N/A", "Geometric mean"],
        ["Analyst estimate",     _pct(g.analyst_growth) if g.analyst_growth else "N/A", "Consensus"],
        ["Recommended blend",    _pct(g.recommended_growth), g.recommended_basis],
    ],
    highlight_row=4,
)}

{"<h3 style='color:#e2e8f0;font-size:1.1rem;margin:20px 0 8px 0'>Terminal Value Consistency Checks</h3>" + "".join(('<div style="padding:10px 14px;border-radius:6px;margin:6px 0;font-size:0.85rem;background:' + ("#14532d22" if v["pass"] else "#7f1d1d22") + ';color:' + ("#86efac" if v["pass"] else "#fca5a5") + '">' + ("✓" if v["pass"] else "✗") + " <strong>" + v["label"] + ":</strong> " + v["detail"] + "</div>") for v in tv.checks.values()) if tv else ""}'''


def _section_fcff(d: CompanyData, fcff) -> str:
    if not fcff: return ""
    tv_pct = fcff.pv_terminal_value / fcff.value_of_firm if fcff.value_of_firm > 0 else 0

    year_rows = []
    for r in fcff.yearly:
        year_rows.append([
            str(r.year), _usd(r.ebit,0), _usd(r.nopat,0),
            _usd(r.net_capex,0), _usd(r.delta_wc,0),
            _pct(r.reinvestment_rate,0), _usd(r.fcff,0),
            _pct(r.wacc), _usd(r.pv_fcff,0),
        ])

    return f'''
{_section("Module 02 — Cash Flow Valuation (FCFF 2-stage)", "Ch 10, 15 · fcff2st.xls · fcffginzu.xlsx")}

{_formula_box(
    "FCFF = EBIT×(1−t) − Net_CapEx − ΔWC<br>Value_of_Firm = Σ PV(FCFF) + PV(TV)<br>Value_of_Equity = Value_of_Firm − Debt + Cash",
    source="Damodaran, Ch 10, p.247; Ch 15, p.375")}

{_table(
    ["Year","EBIT","NOPAT","Net CapEx","ΔWC","RIR","FCFF","WACC","PV(FCFF)"],
    year_rows,
)}

{_metric_row(
    ("PV High-Growth FCFFs", _usd(fcff.pv_fcff_highgrowth,0)),
    ("Terminal FCFF", _usd(fcff.terminal_fcff,0)),
    ("Terminal Value", _usd(fcff.terminal_value,0)),
    ("PV Terminal Value", _usd(fcff.pv_terminal_value,0), f"TV = {tv_pct:.0%} of firm value"),
)}

<div style="background:#0f172a;border:1px solid #1e293b;border-radius:10px;padding:16px 20px;margin:16px 0">
  <div style="font-size:0.78rem;color:#64748b;margin-bottom:10px;text-transform:uppercase;letter-spacing:2px">Value Bridge</div>
  <div style="font-size:0.9rem;color:#cbd5e1;line-height:2">
    PV of FCFFs: <strong style="color:#f1f5f9">{_usd(fcff.pv_fcff_highgrowth,0)}</strong><br>
    + PV Terminal Value: <strong style="color:#f1f5f9">{_usd(fcff.pv_terminal_value,0)}</strong><br>
    = Value of Firm: <strong style="color:#f1f5f9">{_usd(fcff.value_of_firm,0)}</strong><br>
    − Market Debt: <strong style="color:#fca5a5">{_usd(fcff.debt_mv,0)}</strong><br>
    + Cash: <strong style="color:#86efac">{_usd(fcff.cash,0)}</strong><br>
    = Value of Equity: <strong style="color:#f1f5f9">{_usd(fcff.value_of_equity,0)}</strong><br>
    ÷ Shares: <strong style="color:#f1f5f9">{_num(fcff.shares,0)}m</strong><br>
    = <strong style="color:#3b82f6;font-size:1.1rem">Value per Share: ${fcff.value_per_share:.2f}</strong>
  </div>
</div>

{_warn_box(f"Terminal value is {tv_pct:.0%} of total firm value. Small changes in WACC or g_stable have large impact.") if tv_pct > 0.75 else _ok_box(f"Terminal value dependency: {tv_pct:.0%} — within acceptable range.")}'''


def _section_multiples(d: CompanyData, eq_m, fm) -> str:
    if not eq_m and not fm: return ""
    html = _section("Module 04 — Relative Valuation", "Ch 17–21 · eqmult.xls · firmmult.xls")

    if eq_m:
        html += f'''
<h3 style="color:#e2e8f0;font-size:1.1rem;margin:20px 0 8px 0">Equity Multiples (2-stage DDM)</h3>
{_formula_box(
    "PE = PV(dividends/FCFE stream) / EPS₁<br>PBV = PE × ROE_high<br>PS = PE × net_margin",
    source="Damodaran, Ch 17–19; eqmult.xls")}
{_table(
    ["Multiple","Justified","Implied Price","vs Market"],
    [
        ["PE (forward)",  _x(eq_m.pe_forward),  f"${eq_m.implied_price_pe:.2f}" if eq_m.implied_price_pe else "N/A", f'{(eq_m.implied_price_pe/d.price-1)*100:+.1f}%' if eq_m.implied_price_pe and d.price else "N/A"],
        ["PBV",           _x(eq_m.pbv,2),        f"${eq_m.implied_price_pbv:.2f}" if eq_m.implied_price_pbv else "N/A", f'{(eq_m.implied_price_pbv/d.price-1)*100:+.1f}%' if eq_m.implied_price_pbv and d.price else "N/A"],
        ["PS (forward)",  _x(eq_m.ps_forward,2), f"${eq_m.implied_price_ps:.2f}" if eq_m.implied_price_ps else "N/A", f'{(eq_m.implied_price_ps/d.price-1)*100:+.1f}%' if eq_m.implied_price_ps and d.price else "N/A"],
        ["PEG",           _x(eq_m.peg,2) if eq_m.peg else "N/A", "—", "—"],
    ],
)}'''

    if fm:
        html += f'''
<h3 style="color:#e2e8f0;font-size:1.1rem;margin:20px 0 8px 0">Firm Multiples (2-stage FCFF)</h3>
{_formula_box(
    "EV/EBIT_fwd = EV / EBIT₁ = EV/NOPAT × (1−t)<br>EV/Sales = EV/NOPAT × margin",
    source="Damodaran, Ch 20; firmmult.xls")}
{_table(
    ["Multiple","Justified","Implied EV"],
    [
        ["EV/EBIT (forward)",  _x(fm.ev_ebit_forward),   _usd(fm.implied_ev_from_ebit,0) if fm.implied_ev_from_ebit else "N/A"],
        ["EV/EBIT (trailing)", _x(fm.ev_ebit_trailing),  "—"],
        ["EV/Sales (forward)", _x(fm.ev_sales_forward),  _usd(fm.implied_ev_from_sales,0) if fm.implied_ev_from_sales else "N/A"],
        ["EV/IC",              _x(fm.ev_ic),              _usd(fm.implied_ev_from_ic,0) if fm.implied_ev_from_ic else "N/A"],
    ],
)}'''
    return html


def _section_ocs(d: CompanyData, ocs) -> str:
    if not ocs: return ""
    sweep_rows = []
    for r in ocs.sweep:
        opt = abs(r.debt_ratio - ocs.optimal_debt_ratio) < 0.001
        cur = abs(r.debt_ratio - ocs.current_debt_ratio) < 0.005
        tag = " ◀ OPTIMAL" if opt else (" ◀ current" if cur else "")
        sweep_rows.append([
            f"{r.debt_ratio:.0%}{tag}", r.rating, _pct(r.kd_pretax),
            _pct(r.ke), _pct(r.wacc), _usd(r.firm_value,0),
        ])

    opt_idx = next((i for i, r in enumerate(ocs.sweep)
                    if abs(r.debt_ratio - ocs.optimal_debt_ratio) < 0.001), -1)
    return f'''
{_section("Module 05 — Optimal Capital Structure", "Ch 15 · capstru.xlsx")}

{_metric_row(
    ("Current D/(D+E)", _pct(ocs.current_debt_ratio,1)),
    ("Optimal D/(D+E)", _pct(ocs.optimal_debt_ratio,1)),
    ("Current WACC",    _pct(ocs.current_wacc)),
    ("Optimal WACC",    _pct(ocs.optimal_wacc),
     f"Δ = {(ocs.optimal_wacc-ocs.current_wacc)*100:+.2f}pp"),
    ("Value Gain",      _usd(ocs.value_gain,0)),
)}

{_table(
    ["D/(D+E)","Rating","kd","ke","WACC","Firm Value"],
    sweep_rows,
    highlight_row=opt_idx,
)}'''


def _section_data_audit(d: CompanyData) -> str:
    rows = [
        ["Company name",         d.name,                   "yfinance info"],
        ["EBIT",                 _usd(d.ebit,0),           "yfinance financials"],
        ["Interest expense",     _usd(d.interest_expense,0),"yfinance financials"],
        ["Net income",           _usd(d.net_income,0),     "yfinance financials"],
        ["Revenue",              _usd(d.revenue,0),        "yfinance financials"],
        ["Book debt",            _usd(d.book_debt,0),      "yfinance balance_sheet"],
        ["Book equity",          _usd(d.book_equity,0),    "yfinance balance_sheet"],
        ["Cash",                 _usd(d.cash,0),           "yfinance balance_sheet"],
        ["CapEx",                _usd(d.capex,0),          "yfinance cashflow"],
        ["Depreciation",         _usd(d.depreciation,0),  "yfinance cashflow"],
        ["Market cap",           _usd(d.equity_market_cap,0),"yfinance info"],
        ["Beta (levered)",       _num(d.beta_levered,3),   "yfinance info"],
        ["Stock price",          f"${d.price:.2f}" if d.price else "N/A", "yfinance info"],
        ["Risk-free rate",       _pct(d.rf),               "FRED DGS10"],
        ["Equity risk premium",  _pct(d.erp),              "Damodaran (Jan 2026)"],
        ["Tax rate",             _pct(d.tax_rate),         "yfinance derived"],
        ["Data source",          d.source,                 ""],
    ]
    err_html = ""
    if d.fetch_errors:
        err_html = _warn_box("Data warnings: " + " · ".join(d.fetch_errors[:4]))
    return f'''
{_section("Data Audit Trail", "All inputs used in this report")}
{err_html}
{_table(["Input","Value","Source"], rows)}
<div style="font-size:0.8rem;color:#475569;margin-top:8px">
  Report generated: {datetime.now().strftime("%d %b %Y %H:%M UTC")} ·
  Methodology: Damodaran, <em>Investment Valuation</em> 2nd Ed. (2002) ·
  Spreads: Jan-2026 vintage (wacccalc.xls, capstru.xlsx)
</div>'''


# ─────────────────────────────────────────────────────────────────────────────
# Main generator
# ─────────────────────────────────────────────────────────────────────────────

def generate_report(
    d: CompanyData,
    a: Optional[ReportAssumptions] = None,
) -> str:
    """
    Run all models from CompanyData and render a self-contained HTML report.

    Parameters
    ----------
    d : CompanyData from data_fetcher.get_company_data()
    a : ReportAssumptions (uses defaults if None)

    Returns
    -------
    Self-contained HTML string — write to file or pass to st.download_button
    """
    if a is None:
        a = ReportAssumptions()

    errors = []

    # ── Run all models ────────────────────────────────────────────────────────

    # Module 01: Cost of Capital
    coc = None
    try:
        coc = full_cost_of_capital(
            ebit=d.ebit, interest_expense=d.interest_expense,
            book_debt=d.book_debt, avg_debt_maturity=d.avg_debt_maturity,
            equity_market_cap=d.equity_market_cap, beta_levered=d.beta_levered,
            rf=d.rf, erp=a.erp, tax_rate=d.tax_rate,
            country_spread=d.country_spread, firm_type=d.firm_type,
        )
    except Exception as e:
        errors.append(f"Cost of Capital: {e}")

    # Module 03: Growth
    g_result = None
    tv_result = None
    try:
        g_result = estimate_growth(
            ebit=d.ebit, tax_rate=d.tax_rate,
            net_capex=d.capex - d.depreciation, delta_wc=d.delta_wc,
            book_equity=d.book_equity, book_debt=d.book_debt,
            net_income=d.net_income, dividends=0,
            historical_eps=d.historical_eps or None,
            historical_rev=d.historical_revenue or None,
        )
        wacc_for_tv = coc.wacc_result.wacc if coc else 0.09
        tv_result = terminal_value_gordon(
            cash_flow_final_year=d.fcff,
            discount_rate=wacc_for_tv,
            g_stable=a.g_stable,
            stable_roc=a.stable_roc,
        )
    except Exception as e:
        errors.append(f"Growth: {e}")

    # Module 02: FCFF 2-stage
    fcff_result = None
    try:
        wacc_h = coc.wacc_result.wacc if coc else 0.09
        fcff_result = fcff_2stage(
            ebit=d.ebit, tax_rate=d.tax_rate,
            capex=d.capex, depreciation=d.depreciation,
            delta_wc=d.delta_wc, revenues=d.revenue,
            wacc_high=wacc_h, g_high=a.g_high, n_high=a.n_high,
            g_stable=a.g_stable, wacc_stable=wacc_h * 0.95,
            stable_roc=a.stable_roc,
            wc_pct_rev=d.delta_wc / d.revenue if d.revenue > 0 else 0.05,
            debt_mv=d.book_debt, cash=d.cash, shares=d.shares,
        )
    except Exception as e:
        errors.append(f"FCFF: {e}")

    # Module 04: Multiples
    eq_m = None
    fm   = None
    try:
        ke = coc.beta_result.ke if coc else 0.10
        eq_m = justified_equity_multiples(
            g_high=a.g_high, payout_high=a.payout_high, ke_high=ke, n=a.n_high,
            g_stable=a.g_stable, payout_stable=a.payout_stable, ke_stable=ke * 0.9,
            net_margin=a.net_margin,
            book_equity_per_share=d.book_equity / d.shares if d.shares > 0 else 1,
            eps_next_year=d.eps * (1 + a.g_high) if d.eps else 1,
            revenues_next_year=d.revenue / d.shares * (1 + a.g_high) if d.shares > 0 else 0,
        )
        wacc_h = coc.wacc_result.wacc if coc else 0.09
        rir_h  = a.g_high / (a.stable_roc * 1.5) if a.stable_roc > 0 else 0.4
        fm = justified_firm_multiples(
            g_high=a.g_high, rir_high=rir_h, wacc_high=wacc_h,
            margin_high=d.ebit / d.revenue if d.revenue > 0 else 0.10,
            n=a.n_high,
            g_stable=a.g_stable, rir_stable=a.g_stable / a.stable_roc,
            wacc_stable=wacc_h * 0.95, margin_stable=a.net_margin,
            tax_rate=d.tax_rate,
            nopat_next_year=d.ebit * (1 - d.tax_rate) * (1 + a.g_high),
            invested_capital=d.book_equity + d.book_debt,
            revenues_next_year=d.revenue * (1 + a.g_high),
        )
    except Exception as e:
        errors.append(f"Multiples: {e}")

    # Module 05: Optimal Capital Structure
    ocs = None
    try:
        if a.run_ocs and coc and d.fcff > 0:
            ocs = optimal_capital_structure(
                ebitda=d.ebitda, depreciation=d.depreciation, ebit=d.ebit,
                interest_expense=d.interest_expense, tax_rate=d.tax_rate,
                equity_mv=d.equity_market_cap, debt_mv=d.book_debt,
                beta_levered=d.beta_levered, rf=d.rf, erp=a.erp,
                fcff=d.fcff, g_stable=a.g_stable,
                firm_type=d.firm_type,
                shares_outstanding=d.shares, current_price=d.price,
                cash=d.cash, company=d.name,
            )
    except Exception as e:
        errors.append(f"Optimal CS: {e}")

    # ── Render HTML ───────────────────────────────────────────────────────────
    body = ""
    body += _section_cover(d, a, coc, g_result, fcff_result, eq_m, fm)

    if errors:
        body += _warn_box("Some modules failed: " + " · ".join(errors))

    body += _section_coc(d, coc)
    body += _section_growth(d, g_result, tv_result)
    body += _section_fcff(d, fcff_result)
    body += _section_multiples(d, eq_m, fm)
    body += _section_ocs(d, ocs)
    body += _section_data_audit(d)

    # ── Wrap in full HTML doc ─────────────────────────────────────────────────
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{d.ticker} — Damodaran Valuation Report</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500&family=DM+Mono&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after {{ box-sizing: border-box; }}
    body {{
      background: #0a0f1e;
      color: #cbd5e1;
      font-family: 'DM Sans', sans-serif;
      font-size: 15px;
      line-height: 1.6;
      margin: 0;
      padding: 0;
    }}
    .container {{
      max-width: 1000px;
      margin: 0 auto;
      padding: 48px 32px;
    }}
    h1,h2,h3 {{ font-family: 'DM Serif Display', serif; }}
    a {{ color: #3b82f6; }}
    @media print {{
      body {{ background: white; color: #1a1a1a; }}
      .container {{ padding: 20px; }}
    }}
  </style>
</head>
<body>
  <div class="container">
    {body}
    <div style="margin-top:60px;padding-top:20px;border-top:1px solid #1e293b;
         font-size:0.75rem;color:#334155;text-align:center">
      Aswath Damodaran, <em>Investment Valuation: Tools and Techniques for Determining the Value of Any Asset</em>,
      2nd Edition, Wiley Finance, 2002 ·
      This report is for educational purposes only and does not constitute investment advice.
    </div>
  </div>
</body>
</html>'''


# ─────────────────────────────────────────────────────────────────────────────
# Smoke test
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from data_fetcher import _make_placeholder
    d = _make_placeholder("AAPL")
    # Give it realistic values so models don't error
    d.ebitda = d.ebit + d.depreciation
    d.fcff   = d.ebit * (1-d.tax_rate) - (d.capex - d.depreciation) - d.delta_wc
    d.historical_eps = [3.0, 3.5, 4.2, 5.0, 6.1]

    html = generate_report(d)
    with open("/tmp/test_report.html", "w") as f:
        f.write(html)
    print(f"Report generated: {len(html):,} bytes → /tmp/test_report.html")
    print("Sections present:")
    for section in ["Executive Summary","Module 01","Module 02","Module 03","Module 04","Module 05","Data Audit"]:
        print(f"  {'✓' if section in html else '✗'} {section}")
