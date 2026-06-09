"""
report_generator.py
===================
Generates a complete self-contained HTML report — identical in depth to
what the Streamlit pages show, not a summary.

Runs all 6 modules in full:
  Module 01 — Cost of Capital (full step-by-step)
  Module 02 — FCFF 2-stage (full year-by-year table)
  Module 03 — Growth (all 3 approaches + TV checks + sensitivity)
  Module 04 — Relative Valuation (equity + firm multiples + implied prices)
  Module 05 — Optimal Capital Structure (full sweep table + charts data)
  Module 06 — Special Cases (EVA, distressed, normalised earnings)
"""

from __future__ import annotations
import math
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional

import sys
sys.path.insert(0, '/home/claude')

from data_fetcher import CompanyData
from cost_of_capital import full_cost_of_capital
from fcff_models import fcff_2stage
from growth_models import estimate_growth, terminal_value_gordon, benchmark_vs_industry
from relative_valuation import (justified_equity_multiples, justified_firm_multiples,
                                 score_multiple, INDUSTRY_MULTIPLES)
from optimal_capital_structure import optimal_capital_structure
from special_cases import eva_valuation, distressed_firm_value, default_probability_from_rating


@dataclass
class ReportAssumptions:
    g_high:         float = 0.0    # 0 = auto from growth module
    n_high:         int   = 5
    g_stable:       float = 0.03
    stable_roc:     float = 0.12
    payout_high:    float = 0.0    # 0 = auto FCFE/NI ratio
    payout_stable:  float = 0.0
    net_margin:     float = 0.0    # 0 = auto from live data
    erp:            float = 0.055
    run_ocs:        bool  = True


# ── HTML helpers ──────────────────────────────────────────────────────────────

def _pct(v, d=2): return f"{v:.{d}%}" if v is not None else "N/A"
def _usd(v, d=0): return f"${v:,.{d}f}m" if v is not None else "N/A"
def _num(v, d=2): return f"{v:,.{d}f}" if v is not None else "N/A"
def _x(v, d=1):   return f"{v:.{d}f}×" if v is not None else "N/A"

def _sc(score):
    if score >= 7: return "#22c55e"
    if score >= 4: return "#f59e0b"
    return "#ef4444"

def _badge(score, text):
    c = _sc(score)
    short = text[:80] + "…" if len(text) > 80 else text
    return f'<span style="display:inline-block;padding:3px 10px;border-radius:20px;font-size:0.78rem;font-weight:500;background:{c}22;color:{c};border:1px solid {c}44">{score}/10 — {short}</span>'

def _scores_row(scores: list) -> str:
    """scores: list of (score, text) tuples"""
    badges = " &nbsp; ".join(_badge(s, t) for s, t in scores)
    return f'<div style="margin:10px 0">{badges}</div>'

def _scorecard(scores: dict) -> str:
    """scores: {label: (score, text)} — renders a mini scorecard"""
    rows = ""
    composite = sum(s for s,_ in scores.values()) / len(scores) if scores else 0
    for label, (score, text) in scores.items():
        c = _sc(score)
        bar = int(score * 10)
        rows += (f'<div style="margin-bottom:12px">'
                 f'<div style="display:flex;justify-content:space-between;margin-bottom:3px">'
                 f'<span style="font-size:0.85rem;color:#cbd5e1">{label}</span>'
                 f'<span style="font-size:0.85rem;color:{c};font-weight:500">{score}/10</span></div>'
                 f'<div style="background:#1e293b;border-radius:4px;height:7px">'
                 f'<div style="background:{c};width:{bar}%;height:7px;border-radius:4px"></div></div>'
                 f'<div style="font-size:0.75rem;color:#64748b;margin-top:2px">{text[:70]}</div></div>')
    return (f'<div style="background:#0f172a;border:1px solid #1e293b;border-radius:10px;padding:20px 24px;margin:16px 0">'
            f'<div style="font-size:0.68rem;text-transform:uppercase;letter-spacing:2px;color:#475569;margin-bottom:4px">Composite Score</div>'
            f'<div style="font-size:2.5rem;font-family:DM Serif Display,serif;color:#f1f5f9;margin-bottom:16px">{composite:.1f}<span style="font-size:1rem;color:#64748b"> / 10</span></div>'
            f'{rows}</div>')

# Scoring functions mirroring the pages
def _score_wacc(w):
    p=w*100
    if p<5: return 9,"Very low — well below market norms"
    elif p<7: return 8,"Low — below typical 7–9% range"
    elif p<9: return 7,"Average — within 7–9% for most US firms"
    elif p<11: return 5,"Above average — higher than market median"
    elif p<14: return 3,"High — elevated financing costs"
    else: return 1,"Very high — typical only for distressed firms"

def _score_icr(icr):
    if icr==math.inf or icr>12.5: return 10,"Exceptional — Aaa/AAA equivalent"
    elif icr>8.5: return 9,"Excellent — Aa2/AA equivalent"
    elif icr>5.5: return 8,"Strong — A-range rating"
    elif icr>3.0: return 6,"Adequate — BBB to A− range"
    elif icr>2.0: return 4,"Weak — BB range"
    elif icr>1.25: return 2,"Stressed — B range"
    else: return 1,"Distressed"

def _score_beta(b):
    if b<0.5: return 9,"Defensive"
    elif b<0.8: return 8,"Low volatility"
    elif b<1.1: return 7,"Market-rate risk"
    elif b<1.4: return 5,"Moderately elevated"
    elif b<1.8: return 3,"High beta"
    else: return 1,"Very high beta"

def _score_ke(ke):
    p=ke*100
    if p<7: return 9,"Very low cost of equity"
    elif p<9: return 8,"Below average"
    elif p<11: return 7,"Average — 9–11% range"
    elif p<13: return 5,"Above average"
    elif p<16: return 3,"High"
    else: return 1,"Very high"

def _score_tv(tv_pct):
    if tv_pct<.50: return 9,"Low TV dependence — most value from near-term cash flows"
    elif tv_pct<.65: return 7,"Moderate — typical for stable businesses"
    elif tv_pct<.80: return 5,"High — sensitive to stable-growth assumptions"
    else: return 3,"Very high (>80%) — treat assumptions with care"

def _score_mos(price, value):
    if price<=0 or value<=0: return 5,"No price provided"
    r=value/price
    if r>1.5: return 10,f"Large margin of safety — value is {r:.1f}× price"
    elif r>1.2: return 8,f"Good — {r:.1f}× price"
    elif r>0.9: return 6,f"Fairly valued — {r:.1f}× price"
    elif r>0.7: return 4,f"Mild overvaluation"
    else: return 2,f"Significant overvaluation"

def _score_roc(roc, wacc):
    ex=roc-wacc
    if ex>.15: return 9,f"ROC {ex:.1%} above WACC — exceptional value creation"
    elif ex>.05: return 8,f"Healthy {ex:.1%} excess return"
    elif ex>0: return 6,f"Marginal {ex:.1%} excess return"
    elif ex>-.03: return 4,"ROC ≈ WACC — value neutral"
    else: return 2,f"ROC {abs(ex):.1%} below WACC — destroying value"

def _score_distress(p):
    if p<.01: return 9,f"Negligible risk ({p:.2%})"
    elif p<.05: return 7,f"Low risk ({p:.2%})"
    elif p<.15: return 5,f"Moderate risk ({p:.2%})"
    elif p<.35: return 3,f"High risk ({p:.2%})"
    else: return 1,f"Very high risk ({p:.2%})"

def _score_mult(multiple_type, value, industry=None):
    from relative_valuation import score_multiple
    s, t, _ = score_multiple(multiple_type, value, industry)
    return s, t

def _section(title, subtitle=""):
    sub = f'<p style="color:#64748b;font-size:0.9rem;margin:4px 0 0">{subtitle}</p>' if subtitle else ""
    return f'<div style="margin:48px 0 20px;padding-bottom:12px;border-bottom:2px solid #1e3a5f"><h2 style="font-family:\'DM Serif Display\',serif;font-size:1.6rem;color:#f1f5f9;margin:0">{title}</h2>{sub}</div>'

def _subsection(title):
    return f'<h3 style="color:#e2e8f0;font-size:1.1rem;margin:24px 0 10px">{title}</h3>'

def _metrics(*items):
    def _card(m):
        l, v = m[0], m[1]
        note = m[2] if len(m) > 2 and m[2] else ""
        note_html = f'<div style="font-size:0.75rem;color:#64748b;margin-top:2px">{note}</div>' if note else ""
        return (f'<div style="background:#0f172a;border:1px solid #1e293b;border-radius:10px;'
                f'padding:16px 20px;flex:1;min-width:130px">'
                f'<div style="font-size:0.68rem;text-transform:uppercase;letter-spacing:2px;'
                f'color:#475569;margin-bottom:4px">{l}</div>'
                f'<div style="font-size:1.6rem;font-family:\'DM Serif Display\',serif;'
                f'color:#f1f5f9;letter-spacing:-0.5px">{v}</div>{note_html}</div>')
    cells = "".join(_card(m) for m in items)
    return f'<div style="display:flex;gap:10px;flex-wrap:wrap;margin:14px 0">{cells}</div>'

def _formula(formula, note="", source=""):
    s = f'<div style="font-size:0.7rem;color:#475569;margin-top:8px">📚 {source}</div>' if source else ""
    n = f'<div style="color:#94a3b8;margin-top:6px;font-size:0.85rem">{note}</div>' if note else ""
    return f'<div style="background:#1e293b;border-left:3px solid #3b82f6;border-radius:0 8px 8px 0;padding:14px 18px;margin:12px 0;font-family:monospace;font-size:0.88rem;color:#7dd3fc">{formula}{n}{s}</div>'

def _box(text, colour="#3b82f6"):
    return f'<div style="background:{colour}11;border-left:3px solid {colour};border-radius:0 8px 8px 0;padding:12px 16px;color:#cbd5e1;font-size:0.87rem;margin:10px 0;line-height:1.7">{text}</div>'

def _table(headers, rows, highlight=-1):
    th = "".join(f'<th style="padding:8px 12px;text-align:left;font-size:0.78rem;font-weight:500;color:#64748b;border-bottom:1px solid #1e293b">{h}</th>' for h in headers)
    tr = "".join(f'<tr style="background:{"#14532d22" if i==highlight else "#0f172a" if i%2==0 else "#111827"}">'+"".join(f'<td style="padding:8px 12px;font-size:0.85rem;color:#cbd5e1;border-bottom:1px solid #1e293b1a">{c}</td>' for c in row)+"</tr>" for i,row in enumerate(rows))
    return f'<table style="width:100%;border-collapse:collapse;margin:12px 0;border-radius:8px;overflow:hidden"><thead><tr style="background:#1e293b">{th}</tr></thead><tbody>{tr}</tbody></table>'

def _warn(text): return f'<div style="background:#292524;border:1px solid #78350f;border-radius:8px;padding:12px 16px;color:#fde68a;font-size:0.85rem;margin:10px 0">⚠ {text}</div>'
def _ok(text):   return f'<div style="background:#14532d22;border:1px solid #22c55e44;border-radius:8px;padding:12px 16px;color:#86efac;font-size:0.85rem;margin:10px 0">✓ {text}</div>'


# ── Full section renderers ─────────────────────────────────────────────────────

def _render_coc(d, coc):
    dc=coc.debt_cost; br=coc.beta_result; wr=coc.wacc_result
    from cost_of_capital import _TABLE_NAMES
    html  = _section("Module 01 — Cost of Capital", "Ch 7–8 · ratings.xls · levbeta.xls · wacccalc.xls")
    html += _subsection(f"Step 1 — Synthetic Credit Rating [{_TABLE_NAMES.get(dc.firm_type,'Large firm')}]")
    html += _formula(f"ICR = EBIT / Interest = {d.ebit:,.0f} / {d.interest_expense:,.0f} = {dc.icr:.2f}×  →  {dc.rating}  →  spread {dc.company_spread:.2%}", source="Damodaran Ch 8 p.183; ratings.xls")
    html += _metrics(("ICR", f"{dc.icr:.2f}×" if dc.icr<999 else "∞"), ("Rating", dc.rating), ("Company Spread", _pct(dc.company_spread)), ("Pre-tax kd", _pct(dc.kd_pretax)), ("After-tax kd", _pct(dc.kd_aftertax)))
    html += _box(f"kd = rf + spread = {dc.rf:.2%} + {dc.company_spread:.2%}{(' + ' + _pct(dc.country_spread) + ' country') if dc.country_spread else ''} = <strong>{dc.kd_pretax:.2%}</strong>  →  after-tax = {dc.kd_pretax:.2%} × (1−{dc.tax_rate:.2%}) = <strong>{dc.kd_aftertax:.2%}</strong>")

    html += _subsection("Step 2 — Beta & Cost of Equity")
    html += _formula(f"β_u = {br.beta_levered_input:.3f} / [1 + (1−{br.tax_rate:.2%})×{br.current_de:.4f}] = {br.beta_unlevered:.3f}<br>ke = {br.rf:.2%} + {br.beta_relevered:.3f} × {br.erp:.2%} = {br.ke:.2%}", source="Damodaran Ch 8 p.170; levbeta.xls")
    html += _metrics(("Unlevered β", f"{br.beta_unlevered:.3f}"), ("Re-levered β", f"{br.beta_relevered:.3f}"), ("Risk-free Rate", _pct(br.rf)), ("ERP", _pct(br.erp)), ("Cost of Equity", _pct(br.ke)))

    html += _subsection("Step 3 — Market Value of Debt & WACC")
    html += _formula(f"MV(Debt) = {d.interest_expense:,.0f}×annuity({dc.kd_pretax:.2%},5) + {d.book_debt:,.0f}/(1+{dc.kd_pretax:.2%})⁵ = {coc.market_debt:,.0f}<br>WACC = {br.ke:.2%}×{wr.weight_equity:.0%} + {dc.kd_aftertax:.2%}×{wr.weight_debt:.0%} = {wr.wacc:.2%}", source="Damodaran Ch 8 p.194–195; wacccalc.xls")
    html += _metrics(("Book Debt", _usd(d.book_debt)), ("Market Debt", _usd(coc.market_debt)), ("Equity Weight", _pct(wr.weight_equity,0)), ("Debt Weight", _pct(wr.weight_debt,0)), ("WACC", _pct(wr.wacc), f"ke×{wr.weight_equity:.0%} + kd×{wr.weight_debt:.0%}"))
    # Scorecard
    scores = {
        "WACC":              _score_wacc(wr.wacc),
        "Cost of Equity":    _score_ke(br.ke),
        "Interest Coverage": _score_icr(dc.icr),
        "Beta":              _score_beta(br.beta_relevered),
    }
    html += _scorecard(scores)
    return html


def _render_growth(d, g, tv, wacc_val=0.09):
    html  = _section("Module 03 — Growth & Terminal Value", "Ch 11–12 · chgrowth.xls")
    html += _subsection("Three Growth Approaches")
    html += _formula(f"g(firm) = ROC × RIR = {g.roc:.2%} × {g.reinvestment_rate:.2%} = {g.fundamental_growth_firm:.2%}<br>g(equity) = ROE × Retention = {g.roe:.2%} × {g.retention_ratio:.2%} = {g.fundamental_growth_equity:.2%}", source="Damodaran Ch 11 p.278")
    html += _table(["Approach","Growth Rate","Basis"],[
        ["Fundamental (firm)",   _pct(g.fundamental_growth_firm),   "ROC × Reinvestment Rate"],
        ["Fundamental (equity)", _pct(g.fundamental_growth_equity), "ROE × Retention Ratio"],
        ["Historical EPS CAGR",  _pct(g.historical_eps_cagr) if g.historical_eps_cagr else "N/A", "Geometric mean"],
        ["Analyst estimate",     _pct(g.analyst_growth) if g.analyst_growth else "N/A", "Consensus"],
        ["Recommended blend",    _pct(g.recommended_growth), g.recommended_basis],
    ], 4)
    html += _box(f"Recommended growth: <strong>{_pct(g.recommended_growth)}</strong> — {g.recommended_basis}")
    # ROC score
    s_roc,t_roc = _score_roc(g.roc, wacc_val if wacc_val else 0.09)
    html += _scores_row([(s_roc, f"ROC {g.roc:.2%} vs WACC — {t_roc}")])

    if tv:
        html += _subsection("Terminal Value Consistency Checks")
        for v in tv.checks.values():
            colour = "#22c55e" if v["pass"] else "#ef4444"
            html += f'<div style="padding:10px 14px;border-radius:6px;margin:6px 0;font-size:0.85rem;background:{colour}11;color:{colour}">{"✓" if v["pass"] else "✗"} <strong>{v["label"]}:</strong> {v["detail"]}</div>'

        html += _subsection("Terminal Value Sensitivity (±2pp around base case)")
        g_vals = sorted(set(k[0] for k in tv.sensitivity))
        r_vals = sorted(set(k[1] for k in tv.sensitivity))
        rows = []
        for g2 in g_vals:
            row = [f"{g2:.2%}"]
            for r2 in r_vals: row.append(f"${tv.sensitivity.get((g2,r2)):,.0f}" if tv.sensitivity.get((g2,r2)) else "—")
            rows.append(row)
        html += _table(["g \\ WACC"] + [f"{r2:.2%}" for r2 in r_vals], rows)
    return html


def _render_fcff(d, r, price=0):
    tv_pct = r.pv_terminal_value / r.value_of_firm if r.value_of_firm > 0 else 0
    html  = _section("Module 02 — Cash Flow Valuation (FCFF 2-stage)", "Ch 10, 15 · fcff2st.xls · fcffginzu.xlsx")
    g_used = r.inputs.get("g_high", 0)
    n_used = r.inputs.get("n_high", 5)
    g_s_used = r.inputs.get("g_stable", 0.03)
    wacc_s_used = r.inputs.get("wacc_stable", 0)
    rir_s_used = g_s_used / r.inputs.get("stable_roc", 0.12) if r.inputs.get("stable_roc") else 0
    html += _formula(
        f"FCFF = EBIT×(1−t) − Net_CapEx − ΔWC<br>"
        f"Value_Firm = Σ PV(FCFF_1..{n_used}) + PV(TV)<br>"
        f"Value_Equity = Value_Firm − Debt + Cash",
        note=f"High-growth rate: <strong>{g_used:.2%}</strong> (auto from growth module) · "
             f"Stable rate: <strong>{g_s_used:.2%}</strong> · "
             f"Stable RIR: <strong>{rir_s_used:.1%}</strong> (= g/ROC = {g_s_used:.2%}/{r.inputs.get('stable_roc',0.12):.2%}) · "
             f"Stable WACC: <strong>{wacc_s_used:.2%}</strong>",
        source="Damodaran Ch 10 p.247; Ch 15 p.375"
    )

    year_rows = [[str(row.year), _usd(row.ebit,0), _usd(row.nopat,0),
                  _usd(row.net_capex,0), _usd(row.delta_wc,0),
                  _pct(row.reinvestment_rate,0), _usd(row.fcff,0),
                  _pct(row.wacc), _usd(row.pv_fcff,0)] for row in r.yearly]
    html += _table(["Year","EBIT","NOPAT","Net CapEx","ΔWC","RIR","FCFF","WACC","PV(FCFF)"], year_rows)

    html += _metrics(
        ("PV FCFFs (1–n)", _usd(r.pv_fcff_highgrowth,0)),
        ("Terminal FCFF",  _usd(r.terminal_fcff,0)),
        ("Terminal Value", _usd(r.terminal_value,0)),
        ("PV Terminal",    _usd(r.pv_terminal_value,0), f"TV = {tv_pct:.0%} of firm"),
    )
    html += _box(
        f"PV FCFFs: <strong>{_usd(r.pv_fcff_highgrowth,0)}</strong><br>"
        f"+ PV Terminal: <strong>{_usd(r.pv_terminal_value,0)}</strong><br>"
        f"= Firm: <strong>{_usd(r.value_of_firm,0)}</strong><br>"
        f"− Debt: {_usd(r.debt_mv,0)} + Cash: {_usd(r.cash,0)}<br>"
        f"= Equity: <strong>{_usd(r.value_of_equity,0)}</strong> ÷ {r.shares:,.0f}m shares"
        f" = <strong style='color:#3b82f6;font-size:1.05rem'>${r.value_per_share:.2f} / share</strong>"
    )
    if tv_pct > 0.75: html += _warn(f"Terminal value is {tv_pct:.0%} of firm value — highly sensitive to WACC and g assumptions.")
    else: html += _ok(f"Terminal value dependency {tv_pct:.0%} — within acceptable range.")
    # Scores
    s_tv,t_tv = _score_tv(tv_pct)
    # Margin of safety vs market price
    badge_list = [(s_tv, t_tv)]
    if price > 0:
        s_m,t_m = _score_mos(price, r.value_per_share)
        badge_list.append((s_m, t_m))
    html += _scores_row(badge_list)
    return html


def _render_multiples(d, eq_m, fm):
    html = _section("Module 04 — Relative Valuation", "Ch 17–21 · eqmult.xls · firmmult.xls")
    price = d.price or 0

    if eq_m:
        html += _subsection("Equity Multiples (2-stage DDM)")
        html += _formula("PE = PV(FCFE stream)/EPS₁    PBV = PE × ROE    PS = PE × net_margin    PEG = PE/(g×100)", source="Damodaran Ch 17–19; eqmult.xls")
        rows = [
            ["PE (forward)",  _x(eq_m.pe_forward),  f"${eq_m.implied_price_pe:.2f}" if eq_m.implied_price_pe else "N/A", f"{(eq_m.implied_price_pe/price-1)*100:+.1f}%" if eq_m.implied_price_pe and price else "—"],
            ["PE (trailing)", _x(eq_m.pe_trailing),  "—", "—"],
            ["PBV",           _x(eq_m.pbv,2),        f"${eq_m.implied_price_pbv:.2f}" if eq_m.implied_price_pbv else "N/A", f"{(eq_m.implied_price_pbv/price-1)*100:+.1f}%" if eq_m.implied_price_pbv and price else "—"],
            ["PS (forward)",  _x(eq_m.ps_forward,2), f"${eq_m.implied_price_ps:.2f}" if eq_m.implied_price_ps else "N/A", f"{(eq_m.implied_price_ps/price-1)*100:+.1f}%" if eq_m.implied_price_ps and price else "—"],
            ["PEG",           _x(eq_m.peg,2) if eq_m.peg else "N/A", "—", "—"],
        ]
        html += _table(["Multiple","Justified","Implied Price","vs Market"], rows)
        html += _box(f"ROE (high growth implied): {eq_m.roe_high:.2%} | ROE (stable): {eq_m.roe_stable:.2%}<br>PBV of {eq_m.pbv:.2f}× {'justified — ROE > ke' if eq_m.roe_high > eq_m.ke_high else 'unjustified — ROE < ke'}")
        s_pe,t_pe = _score_mult("pe",  eq_m.pe_forward)
        s_pb,t_pb = _score_mult("pbv", eq_m.pbv)
        s_pg,t_pg = _score_mult("peg", eq_m.peg or 0)
        html += _scores_row([(s_pe,f"PE {eq_m.pe_forward:.1f}× — {t_pe}"),
                              (s_pb,f"PBV {eq_m.pbv:.2f}× — {t_pb}"),
                              (s_pg,f"PEG {eq_m.peg:.2f}× — {t_pg}" if eq_m.peg else (0,"PEG N/A"))])

    if fm:
        html += _subsection("Firm Multiples (2-stage FCFF)")
        html += _formula("EV/EBIT_fwd = EV/NOPAT × (1−t)    EV/Sales = EV/NOPAT × margin    EV/IC = EV/NOPAT × ROIC", source="Damodaran Ch 20; firmmult.xls")
        # Derive implied equity price from each EV
        def _ev_to_price(ev):
            if not ev or ev <= 0: return "—"
            eq = ev - d.book_debt + d.cash
            p = eq / d.shares if d.shares > 0 else 0
            vs = f" → ${p:.2f}/share" if p > 0 else ""
            return f"{_usd(ev,0)}{vs}"

        rows = [
            ["EV/EBIT (forward)",  _x(fm.ev_ebit_forward),   _ev_to_price(fm.implied_ev_from_ebit)],
            ["EV/EBIT (trailing)", _x(fm.ev_ebit_trailing),  "—"],
            ["EV/Sales (forward)", _x(fm.ev_sales_forward),  _ev_to_price(fm.implied_ev_from_sales)],
            ["EV/IC",              _x(fm.ev_ic),              _ev_to_price(fm.implied_ev_from_ic)],
        ]
        html += _table(["Multiple","Justified","Implied EV"], rows)
        html += _box(f"ROIC (high growth): {fm.roic_high:.2%} | ROIC (stable): {fm.roic_stable:.2%}<br>EV/IC = {fm.ev_ic:.2f}× — {'value creation: ROIC > WACC' if fm.roic_high > fm.wacc_high else 'value destruction: ROIC < WACC'}")
    # Scores for firm multiples
    if fm:
        s_ev,t_ev = _score_mult("ev_sales", fm.ev_sales_forward)
        html += _scores_row([(s_ev, f"EV/Sales {fm.ev_sales_forward:.1f}× — {t_ev}")])
    return html


def _render_ocs(d, ocs):
    html  = _section("Module 05 — Optimal Capital Structure", "Ch 15 · capstru.xlsx")
    html += _metrics(
        ("Current D/(D+E)", _pct(ocs.current_debt_ratio,1)),
        ("Optimal D/(D+E)", _pct(ocs.optimal_debt_ratio,1)),
        ("Current WACC",    _pct(ocs.current_wacc)),
        ("Optimal WACC",    _pct(ocs.optimal_wacc), f"Δ = {(ocs.optimal_wacc-ocs.current_wacc)*100:+.2f}pp"),
        ("Value Gain",      _usd(ocs.value_gain,0)),
    )
    direction = "over-levered" if ocs.current_debt_ratio > ocs.optimal_debt_ratio else "under-levered"
    action = "reduce debt" if direction == "over-levered" else "issue debt and repurchase shares"
    html += _box(f"{d.name} is currently <strong>{direction}</strong>. Recommended: <strong>{action}</strong>.")

    opt_idx = next((i for i,r in enumerate(ocs.sweep) if abs(r.debt_ratio-ocs.optimal_debt_ratio)<0.001), -1)
    rows = []
    for r in ocs.sweep:
        tag = " ◀ OPTIMAL" if abs(r.debt_ratio-ocs.optimal_debt_ratio)<0.001 else (" ◀ current" if abs(r.debt_ratio-ocs.current_debt_ratio)<0.005 else "")
        rows.append([f"{r.debt_ratio:.0%}{tag}", r.rating, _pct(r.kd_pretax), _pct(r.ke), _pct(r.wacc), _usd(r.firm_value,0) if r.firm_value<1e12 else "∞"])
    html += _table(["D/(D+E)","Rating","kd","ke","WACC","Firm Value"], rows, opt_idx)
    return html


def _render_special(d, coc, fcff_result=None):
    from special_cases import financial_firm_excess_returns, normalise_earnings

    wacc_val = coc.wacc_result.wacc if coc else 0.09
    ke_val   = coc.beta_result.ke   if coc else 0.10
    ic       = d.book_equity + d.book_debt
    nopat    = d.ebit * (1 - d.tax_rate)
    roc      = nopat / ic if ic > 0 else 0
    eva_curr = nopat - wacc_val * ic

    html  = _section("Module 06 — Special Cases", "Ch 21, 22, 30, 32 · fcffeva.xls · fcffsimpleginzu.xlsx")

    # ── EVA ──────────────────────────────────────────────────────────────────
    html += _subsection("1. EVA (Economic Value Added)")
    html += _formula(
        f"EVA = NOPAT − WACC × Invested_Capital<br>"
        f"    = {nopat:,.0f} − {wacc_val:.2%} × {ic:,.0f}<br>"
        f"    = <strong>{eva_curr:,.0f}</strong>  ({'positive — value creation' if eva_curr>0 else 'negative — value destruction'})",
        note=f"= (ROC − WACC) × IC = ({roc:.2%} − {wacc_val:.2%}) × {ic:,.0f}",
        source="Damodaran Ch 32 p.799; fcffeva.xls"
    )
    html += _metrics(
        ("NOPAT", _usd(nopat,0)),
        ("WACC Charge", _usd(wacc_val*ic,0)),
        ("EVA", _usd(eva_curr,0)),
        ("ROC", _pct(roc)),
        ("Excess Return", f"{(roc-wacc_val)*100:+.2f}pp"),
    )
    s_roc,t_roc = _score_roc(roc, wacc_val)
    html += _scores_row([(s_roc, t_roc)])
    html += (_ok(f"Positive EVA of {_usd(eva_curr,0)} — earns {roc:.2%} on capital vs {wacc_val:.2%} cost. Every dollar invested creates value.")
             if eva_curr > 0 else
             _warn(f"Negative EVA of {_usd(eva_curr,0)} — ROC {roc:.2%} is below WACC {wacc_val:.2%}. Growth at current returns destroys value."))

    # Forward EVA projection — ROC declines linearly from current to stable (12%)
    html += _subsection("EVA — 5-Year Projection")
    stable_roc_ev = 0.12
    html += _box(
        f"NOPAT grows at 10% p.a. ROC declines from {roc:.2%} toward stable ROC of {stable_roc_ev:.2%} "
        f"as competition erodes excess returns (Damodaran Ch 12: ROC → WACC in perpetuity)."
    )
    eva_rows = []
    nopat_t = nopat; ic_prev = ic
    for t in range(1,6):
        nopat_t  *= 1.10
        # ROC declines linearly: year t ROC = current + t/5*(stable-current)
        roc_t     = roc + (t/5)*(stable_roc_ev - roc)
        ic_t      = nopat_t / roc_t if roc_t > 0 else ic_prev
        eva_t     = nopat_t - wacc_val * ic_t
        eva_rows.append([f"Year {t}", _usd(nopat_t,0), f"{roc_t:.2%}", _usd(wacc_val*ic_t,0), _usd(eva_t,0)])
        ic_prev   = ic_t
    html += _table(["Year","NOPAT","ROC","WACC Charge","EVA"], eva_rows)

    # ── Distress ──────────────────────────────────────────────────────────────
    html += _subsection("2. Distressed Firm Analysis")
    rating = coc.debt_cost.rating if coc else "Baa2/BBB"
    rating_simple = ("AAA" if "AAA" in rating else "AA" if "AA" in rating else
                     "A" if "/A" in rating and "BBB" not in rating else
                     "BBB" if "BBB" in rating else "BB" if "BB" in rating else
                     "B" if "/B" in rating else "CCC/C")
    html += _formula(
        f"Adjusted_Value = GC_Value × (1 − p_default) + Distress_Sale × p_default",
        source="Damodaran Ch 22 p.556; Ch 30 p.727; Moody's default data"
    )
    # Use FCFF model firm value as going-concern if available, else fall back to market
    if fcff_result and fcff_result.value_of_firm > 0:
        gc_val = fcff_result.value_of_firm
    else:
        gc_val = d.equity_market_cap + d.book_debt
    distress_val = d.book_debt * 0.6
    rows_dist = []
    for years in [1,3,5]:
        p = default_probability_from_rating(rating_simple, years)
        dist = distressed_firm_value(gc_val, d.book_debt, p, distress_val, d.shares, d.cash)
        rows_dist.append([
            f"{years}yr", _pct(p),
            f"${dist.value_per_share_gc:.2f}",
            f"${dist.value_per_share_adjusted:.2f}",
            f"{(1-dist.value_per_share_adjusted/dist.value_per_share_gc)*100:.1f}%" if dist.value_per_share_gc>0 else "N/A",
        ])
    html += _table(["Horizon","Default Prob","GC Value/Share","Adjusted Value/Share","Haircut"], rows_dist)
    p5 = default_probability_from_rating(rating_simple, 5)
    s_dist,t_dist = _score_distress(p5)
    html += _scores_row([(s_dist, f"5-year default probability {p5:.2%} — {t_dist}")])
    html += _box(f"Synthetic rating: <strong>{rating}</strong> (→ {rating_simple} for Moody's lookup)<br>"
                 f"Distress sale value assumed at 60% of book debt = {_usd(distress_val,0)}")

    # ── Financial firm ────────────────────────────────────────────────────────
    html += _subsection("3. Financial Firm — Excess Returns Model")
    html += _formula(
        "Value = Book_Equity + PV[(ROE − ke) × Book_Equity]",
        note="For banks/insurers where debt is raw material, not capital",
        source="Damodaran Ch 21 p.519"
    )
    roe_curr = d.net_income / d.book_equity if d.book_equity > 0 else 0
    try:
        ff = financial_firm_excess_returns(
            book_equity=d.book_equity,
            roe_high=roe_curr, ke_high=ke_val, g_high=0.08, n_high=5,
            roe_stable=max(ke_val*1.05, 0.08), ke_stable=ke_val*0.9, g_stable=0.03,
            shares=d.shares,
        )
        pbv = ff.value_of_equity / ff.book_equity if ff.book_equity > 0 else 0
        html += _metrics(
            ("Book Equity", _usd(ff.book_equity,0)),
            ("ROE (current)", _pct(roe_curr)),
            ("ke", _pct(ke_val)),
            ("Excess Return", f"{(roe_curr-ke_val)*100:+.2f}pp"),
            ("PV Excess Returns", _usd(ff.pv_excess_returns,0)),
            ("Equity Value", _usd(ff.value_of_equity,0)),
            ("PBV", f"{pbv:.2f}×"),
        )
        s_er,t_er = _score_roc(roe_curr, ke_val)
        html += _scores_row([(s_er, t_er)])
        html += _box(
            f"If valued as a financial firm: equity value = {_usd(ff.value_of_equity,0)} ({pbv:.2f}× book).<br>"
            f"{"ROE {:.2%} > ke {:.2%} — justified premium to book.".format(roe_curr, ke_val) if roe_curr > ke_val else "ROE {:.2%} < ke {:.2%} — should trade below book.".format(roe_curr, ke_val)}"
        )
    except Exception as e:
        html += _warn(f"Financial firm model: {e}")

    # ── Earnings normalisation ────────────────────────────────────────────────
    html += _subsection("4. Earnings Normalisation")
    html += _formula(
        "Method 1: Average of last N years<br>"
        "Method 2: Avg historical margin × current revenue  (preferred)<br>"
        "Method 3: Industry/historical ROA × current assets",
        source="Damodaran Ch 22 p.541"
    )
    curr_margin = d.net_income/d.revenue if d.revenue > 0 else 0
    if d.historical_eps and d.shares and d.shares > 0:
        # Convert per-share EPS to total NI ($m) by multiplying by shares
        hist_ni = [e * d.shares for e in d.historical_eps]
        avg_ni  = sum(hist_ni) / len(hist_ni)
        # Use historical revenue if available and same length, else estimate
        if d.historical_revenue and len(d.historical_revenue) == len(d.historical_eps):
            hist_rev = d.historical_revenue
        else:
            # Estimate revenue series by back-calculating from current
            hist_rev = [d.revenue * (0.85 ** (len(d.historical_eps)-i)) for i in range(len(d.historical_eps))]
        margins  = [ni/r for ni,r in zip(hist_ni, hist_rev) if r > 0]
        avg_mg   = sum(margins)/len(margins) if margins else curr_margin
        norm_mg  = avg_mg * d.revenue
        html += _table(["Method","Earnings","Margin","vs Current"],[
            ["Current (reported)",        _usd(d.net_income,0), _pct(curr_margin), "—"],
            ["Avg historical earnings",   _usd(avg_ni,0),       "—",
             f"{(avg_ni/d.net_income-1)*100:+.1f}%" if d.net_income else "—"],
            ["Avg hist margin × curr rev",_usd(norm_mg,0),      _pct(avg_mg),
             f"{(norm_mg/d.net_income-1)*100:+.1f}%" if d.net_income else "—"],
        ])
        if d.net_income and abs(norm_mg - d.net_income) / d.net_income > 0.15:
            html += _warn(
                f"Current net margin {_pct(curr_margin)} differs from historical avg {_pct(avg_mg)} "
                f"by more than 15% — consider using normalised earnings for valuation."
            )
        else:
            html += _ok(
                f"Earnings broadly in line with historical average "
                f"({_pct(curr_margin)} current vs {_pct(avg_mg)} historical avg margin)."
            )
    else:
        html += _box("Insufficient historical data for earnings normalisation.")
    return html


def _render_cover(d, coc, g, fcff, eq_m, fm, a):
    date = datetime.now().strftime("%d %B %Y")
    price = d.price or 0
    wacc_str = _pct(coc.wacc_result.wacc) if coc else "N/A"
    ke_str   = _pct(coc.beta_result.ke)   if coc else "N/A"
    g_str    = _pct(g.recommended_growth) if g else "N/A"

    implied = {}
    if fcff and fcff.value_per_share: implied["FCFF (2-stage DCF)"] = fcff.value_per_share
    if eq_m and eq_m.implied_price_pe: implied["PE multiple"] = eq_m.implied_price_pe
    if eq_m and eq_m.implied_price_pbv: implied["PBV multiple"] = eq_m.implied_price_pbv
    if fm and fm.implied_ev_from_ebit:
        eq = fm.implied_ev_from_ebit - d.book_debt + d.cash
        implied["EV/EBIT multiple"] = eq/d.shares if d.shares>0 else 0
    if fm and fm.implied_ev_from_sales:
        eq = fm.implied_ev_from_sales - d.book_debt + d.cash
        implied["EV/Sales multiple"] = eq/d.shares if d.shares>0 else 0

    avg = sum(implied.values())/len(implied) if implied else 0
    premium = (price/avg - 1) if avg > 0 and price > 0 else None
    sent = "Potentially undervalued" if premium and premium < -0.15 else ("Potentially overvalued" if premium and premium > 0.15 else "Broadly fairly valued")
    sent_col = "#22c55e" if "under" in sent else ("#ef4444" if "over" in sent else "#f59e0b")

    impl_rows = "".join(
        f'<tr><td style="padding:6px 12px;color:#94a3b8;font-size:0.85rem">{k}</td>'
        f'<td style="padding:6px 12px;color:#f1f5f9;font-size:0.9rem;font-weight:500">${v:.2f}</td>'
        f'<td style="padding:6px 12px;font-size:0.85rem;color:{"#86efac" if v>price else "#fca5a5"}">'
        f'{"↑" if v>price else "↓"} {abs(v/price-1)*100:.1f}% {"upside" if v>price else "downside"}</td></tr>'
        for k,v in implied.items() if v>0 and price>0
    ) if price else ""

    return f'''
<div style="background:linear-gradient(135deg,#0f172a 0%,#1e3a5f 100%);border-radius:16px;padding:48px;margin-bottom:40px">
  <div style="font-size:0.75rem;text-transform:uppercase;letter-spacing:3px;color:#3b82f6;margin-bottom:8px">Damodaran Investment Valuation Toolkit</div>
  <h1 style="font-family:'DM Serif Display',serif;font-size:2.8rem;color:#f1f5f9;margin:0 0 4px;letter-spacing:-1px">{d.name}</h1>
  <div style="font-size:1rem;color:#64748b;margin-bottom:4px">{d.ticker} · {date} · Data: {d.source}</div>
  <div style="font-size:0.8rem;color:#475569">Based on: Aswath Damodaran, <em>Investment Valuation</em> 2nd Ed. · Spreads: Jan 2026</div>
</div>

<div style="margin:40px 0 20px;padding-bottom:12px;border-bottom:2px solid #1e3a5f">
  <h2 style="font-family:'DM Serif Display',serif;font-size:1.6rem;color:#f1f5f9;margin:0">Executive Summary</h2>
</div>

{_metrics(("Current Price", f"${price:.2f}" if price else "N/A"), ("Avg Implied Value", f"${avg:.2f}" if avg else "N/A", f"{premium*100:+.1f}% vs price" if premium is not None else ""), ("WACC", wacc_str), ("Cost of Equity", ke_str), ("Recommended Growth", g_str))}

<div style="background:#0f172a;border:1px solid #1e293b;border-radius:10px;padding:16px 20px;margin:16px 0">
  <div style="font-size:0.75rem;text-transform:uppercase;letter-spacing:2px;color:#475569;margin-bottom:12px">Implied Value by Method</div>
  <table style="width:100%;border-collapse:collapse">
    <thead><tr>
      <th style="text-align:left;padding:6px 12px;color:#64748b;font-size:0.78rem;border-bottom:1px solid #1e293b">Method</th>
      <th style="text-align:left;padding:6px 12px;color:#64748b;font-size:0.78rem;border-bottom:1px solid #1e293b">Implied Price</th>
      <th style="text-align:left;padding:6px 12px;color:#64748b;font-size:0.78rem;border-bottom:1px solid #1e293b">vs Market</th>
    </tr></thead>
    <tbody>{impl_rows}</tbody>
  </table>
  <div style="margin-top:12px;padding:10px 14px;background:{sent_col}22;border-radius:6px;color:{sent_col};font-size:0.88rem;font-weight:500">{sent}</div>
</div>'''


def _render_audit(d, g_use=0, wacc_v=0, a=None):
    rows = [
        ["Company name",        d.name,                     "yfinance info"],
        ["EBIT",                _usd(d.ebit,0),              "yfinance financials"],
        ["Interest expense",    _usd(d.interest_expense,0),  "yfinance financials"],
        ["Net income",          _usd(d.net_income,0),        "yfinance financials"],
        ["Revenue",             _usd(d.revenue,0),           "yfinance financials"],
        ["EBITDA",              _usd(d.ebitda,0),            "yfinance derived"],
        ["Book debt",           _usd(d.book_debt,0),         "yfinance balance_sheet"],
        ["Book equity",         _usd(d.book_equity,0),       "yfinance balance_sheet"],
        ["Cash",                _usd(d.cash,0),              "yfinance balance_sheet"],
        ["Total assets",        _usd(d.total_assets,0),      "yfinance balance_sheet"],
        ["CapEx",               _usd(d.capex,0),             "yfinance cashflow"],
        ["Depreciation",        _usd(d.depreciation,0),      "yfinance cashflow"],
        ["Net CapEx",           _usd(d.capex-d.depreciation,0), "derived: CapEx − Depr"],
        ["ΔWorking Capital",    _usd(d.delta_wc,0),          "yfinance cashflow"],
        ["FCFF (current)",      _usd(d.fcff,0),              "derived: NOPAT − Net CapEx − ΔWC"],
        ["Market cap",          _usd(d.equity_market_cap,0), "yfinance info"],
        ["Beta (levered)",      f"{d.beta_levered:.3f}",     "yfinance info"],
        ["Stock price",         f"${d.price:.2f}" if d.price else "N/A", "yfinance info"],
        ["Shares outstanding",  f"{d.shares:,.0f}m",         "yfinance info"],
        ["EPS (trailing)",      f"${d.eps:.2f}" if d.eps else "N/A", "yfinance info"],
        ["Risk-free rate",      _pct(d.rf),                  "FRED DGS10"],
        ["Equity risk premium", _pct(d.erp),                 "Damodaran (Jan 2026)"],
        ["Tax rate",            _pct(d.tax_rate),            "yfinance derived"],
        ["Avg debt maturity",   f"{d.avg_debt_maturity:.0f} years", "EDGAR / default"],
        ["Firm type",           {1:"Large firm",2:"Small/risky",3:"Financial"}.get(d.firm_type,""), ""],
        ["Data source",         d.source,                    ""],
        ["Growth rate (FCFF)",  _pct(g_use) if g_use else "auto",  "From growth module blend"],
        ["Stable WACC (TV)",    _pct(wacc_v*0.95) if wacc_v else "N/A",  "WACC × 0.95 for terminal period"],
        ["Stable RIR (TV)",     f"{a.g_stable/a.stable_roc:.1%}" if (a and a.stable_roc) else "N/A",  f"g/ROC = {a.g_stable:.2%}/{a.stable_roc:.2%}" if a else ""],
    ]
    err = f'<div style="background:#292524;border:1px solid #78350f;border-radius:8px;padding:12px;color:#fde68a;font-size:0.85rem;margin:10px 0">⚠ Data warnings: {" · ".join(d.fetch_errors[:4])}</div>' if d.fetch_errors else ""
    return (_section("Data Audit Trail", "All inputs used in this report — every value, its source, and how it flows into calculations")
            + err + _table(["Input","Value","Source"], rows)
            + f'<div style="font-size:0.8rem;color:#475569;margin-top:8px">Report generated: {datetime.now().strftime("%d %b %Y %H:%M UTC")} · Methodology: Damodaran, Investment Valuation 2nd Ed. (2002) · Spreads: Jan-2026 vintage</div>')


def generate_report(d: CompanyData, a: Optional[ReportAssumptions] = None) -> str:
    if a is None: a = ReportAssumptions()
    errors = []

    # Module 01
    coc = None
    try:
        coc = full_cost_of_capital(ebit=d.ebit, interest_expense=d.interest_expense,
            book_debt=d.book_debt, avg_debt_maturity=d.avg_debt_maturity,
            equity_market_cap=d.equity_market_cap, beta_levered=d.beta_levered,
            rf=d.rf, erp=a.erp, tax_rate=d.tax_rate,
            country_spread=d.country_spread, firm_type=d.firm_type)
    except Exception as e: errors.append(f"CoC: {e}")

    wacc_v = coc.wacc_result.wacc if coc else 0.09
    ke_v   = coc.beta_result.ke   if coc else 0.10

    # Module 03: Growth
    g_result = tv_result = None
    try:
        g_result = estimate_growth(ebit=d.ebit, tax_rate=d.tax_rate,
            net_capex=d.capex-d.depreciation, delta_wc=d.delta_wc,
            book_equity=d.book_equity, book_debt=d.book_debt,
            net_income=d.net_income, dividends=0,
            historical_eps=d.historical_eps or None,
            historical_rev=d.historical_revenue or None)
        tv_result = terminal_value_gordon(max(d.fcff,1), wacc_v, a.g_stable, a.stable_roc)
    except Exception as e: errors.append(f"Growth: {e}")

    g_rec = g_result.recommended_growth if g_result else (a.g_high or 0.10)
    g_use = a.g_high if a.g_high > 0 else max(g_rec, 0.03)

    # Module 02: FCFF
    fcff_result = None
    try:
        wc_pct = d.delta_wc / d.revenue if d.revenue > 0 else 0.02
        fcff_result = fcff_2stage(
            ebit=d.ebit, tax_rate=d.tax_rate, capex=d.capex, depreciation=d.depreciation,
            delta_wc=d.delta_wc, revenues=d.revenue,
            wacc_high=wacc_v, g_high=g_use, n_high=a.n_high,
            g_stable=a.g_stable, wacc_stable=wacc_v*0.95, stable_roc=a.stable_roc,
            wc_pct_rev=wc_pct, debt_mv=d.book_debt, cash=d.cash, shares=d.shares)
    except Exception as e: errors.append(f"FCFF: {e}")

    # Module 04: Multiples
    eq_m = fm = None
    try:
        d_ratio = d.book_debt/(d.book_equity+d.book_debt) if (d.book_equity+d.book_debt)>0 else 0.2
        eq_reinv = (1-d_ratio)*((d.capex-d.depreciation)+d.delta_wc)
        payout_h = a.payout_high if a.payout_high > 0 else max(0.0, min(0.95, 1.0 - eq_reinv/d.net_income)) if d.net_income>0 else 0.5
        payout_s = a.payout_stable if a.payout_stable > 0 else min(0.80, payout_h*1.2)
        net_mg   = a.net_margin if a.net_margin > 0 else d.net_income/d.revenue if d.revenue>0 else 0.10
        eq_m = justified_equity_multiples(
            g_high=g_use, payout_high=payout_h, ke_high=ke_v, n=a.n_high,
            g_stable=a.g_stable, payout_stable=payout_s, ke_stable=ke_v*0.9,
            net_margin=net_mg,
            book_equity_per_share=d.book_equity/d.shares if d.shares>0 else 1,
            eps_next_year=d.eps*(1+g_use) if d.eps else 1,
            revenues_next_year=d.revenue/d.shares*(1+g_use) if d.shares>0 else 0)
        rir_h = max(0.05, (d.capex-d.depreciation+d.delta_wc)/(d.ebit*(1-d.tax_rate))) if d.ebit>0 else 0.4
        fm = justified_firm_multiples(
            g_high=g_use, rir_high=rir_h, wacc_high=wacc_v,
            margin_high=d.ebit*(1-d.tax_rate)/d.revenue if d.revenue>0 else 0.15,
            n=a.n_high, g_stable=a.g_stable, rir_stable=a.g_stable/a.stable_roc,
            wacc_stable=wacc_v*0.95, margin_stable=net_mg, tax_rate=d.tax_rate,
            nopat_next_year=d.ebit*(1-d.tax_rate)*(1+g_use),
            invested_capital=d.book_equity+d.book_debt,
            revenues_next_year=d.revenue*(1+g_use))
    except Exception as e: errors.append(f"Multiples: {e}")

    # Module 05: OCS
    # Use g_stable directly (not g_implied) to avoid infinite firm values for
    # high-growth firms where FCFF/EV << WACC. This matches capstru.xlsx approach.
    ocs = None
    try:
        if a.run_ocs and d.fcff > 0 and d.equity_market_cap > 0:
            ocs = optimal_capital_structure(
                ebitda=d.ebitda or d.ebit+d.depreciation, depreciation=d.depreciation, ebit=d.ebit,
                interest_expense=d.interest_expense, tax_rate=d.tax_rate,
                equity_mv=d.equity_market_cap, debt_mv=d.book_debt,
                beta_levered=d.beta_levered, rf=d.rf, erp=a.erp,
                fcff=d.fcff, g_stable=a.g_stable, firm_type=d.firm_type,
                apply_bankruptcy_costs=True,
                shares_outstanding=d.shares, current_price=d.price,
                cash=d.cash, company=d.name)
    except Exception as e: errors.append(f"OCS: {e}")

    # Render
    body = _render_cover(d, coc, g_result, fcff_result, eq_m, fm, a)
    if errors: body += "".join(_warn(f"Module error: {e}") for e in errors)
    if coc:        body += _render_coc(d, coc)
    if g_result:   body += _render_growth(d, g_result, tv_result, wacc_v)
    if fcff_result:body += _render_fcff(d, fcff_result, d.price)
    if eq_m or fm: body += _render_multiples(d, eq_m, fm)
    if ocs:        body += _render_ocs(d, ocs)
    if coc:        body += _render_special(d, coc, fcff_result)
    body += _render_audit(d, g_use, wacc_v, a)

    return f'''<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{d.ticker} — Damodaran Valuation</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box}} body{{background:#0a0f1e;color:#cbd5e1;font-family:'DM Sans',sans-serif;font-size:15px;line-height:1.6;margin:0;padding:0}}
.container{{max-width:1000px;margin:0 auto;padding:48px 32px}} h1,h2,h3{{font-family:'DM Serif Display',serif}}
@media print{{body{{background:white;color:#1a1a1a}}.container{{padding:20px}}}}
</style></head><body><div class="container">
{body}
<div style="margin-top:60px;padding-top:20px;border-top:1px solid #1e293b;font-size:0.75rem;color:#334155;text-align:center">
Aswath Damodaran, <em>Investment Valuation</em> 2nd Ed., Wiley Finance, 2002 · For educational purposes only
</div></div></body></html>'''


if __name__ == "__main__":
    from data_fetcher import _make_placeholder
    d = _make_placeholder("AAPL")
    d.ebitda = d.ebit + d.depreciation
    d.fcff = d.ebit*(1-d.tax_rate) - (d.capex-d.depreciation) - d.delta_wc
    d.historical_eps = [3.5, 4.2, 5.0, 6.1, 7.4]
    html = generate_report(d)
    with open("/tmp/test_report.html","w") as f: f.write(html)
    print(f"OK — {len(html):,} bytes")
    for s in ["Module 01","Module 02","Module 03","Module 04","Module 05","Module 06","Data Audit"]:
        print(f"  {'✓' if s in html else '✗'} {s}")
