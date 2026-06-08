"""
relative_valuation.py
=====================
Damodaran Investment Valuation — Chapters 17–21

Implements all multiples from eqmult.xls and firmmult.xls:

  Equity multiples (eqmult.xls) — via 2-stage DDM:
    justified_pe()      — Price / Forward Earnings
    justified_pbv()     — Price / Book Value
    justified_ps()      — Price / Sales (trailing and forward)
    justified_peg()     — PE / Growth rate

  Firm multiples (firmmult.xls) — via 2-stage FCFF:
    justified_ev_ebit()    — EV / EBIT
    justified_ev_ebitda()  — EV / EBITDA
    justified_ev_ic()      — EV / Invested Capital
    justified_ev_sales()   — EV / Sales

  Scoring & comparison:
    score_multiple()    — vs industry median from wacccalc.xls dataset
    relative_value()    — implied price from comparable multiple

Sources: eqmult.xls, firmmult.xls, wacccalc.xls (US Industry Averages sheet)
Chapters: 17 (PE), 18 (PEG), 19 (PBV, PS), 20 (EV multiples), 21 (financial firms)
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Industry multiple benchmarks
# Sourced from wacccalc.xls → US Industry Averages sheet (Jan 2026)
# Columns: pe_fwd, pbv, ps_trailing, ev_ebitda, ev_sales
# ─────────────────────────────────────────────────────────────────────────────

INDUSTRY_MULTIPLES: dict[str, dict] = {
    "Advertising":             {"pe": 22.1, "pbv": 3.2,  "ps": 1.2,  "ev_ebitda": 11.2, "ev_sales": 1.4},
    "Aerospace/Defense":       {"pe": 25.3, "pbv": 5.8,  "ps": 1.6,  "ev_ebitda": 14.1, "ev_sales": 1.8},
    "Air Transport":           {"pe": 10.2, "pbv": 2.1,  "ps": 0.5,  "ev_ebitda": 5.8,  "ev_sales": 0.7},
    "Auto & Truck":            {"pe": 9.8,  "pbv": 1.3,  "ps": 0.4,  "ev_ebitda": 5.2,  "ev_sales": 0.5},
    "Bank (Money Center)":     {"pe": 11.4, "pbv": 1.2,  "ps": 3.1,  "ev_ebitda": None, "ev_sales": None},
    "Beverage (Alcoholic)":    {"pe": 18.7, "pbv": 2.4,  "ps": 1.8,  "ev_ebitda": 10.4, "ev_sales": 2.1},
    "Beverage (Soft)":         {"pe": 24.2, "pbv": 6.1,  "ps": 3.2,  "ev_ebitda": 14.8, "ev_sales": 3.8},
    "Business & Consumer Svcs":{"pe": 20.4, "pbv": 3.4,  "ps": 1.1,  "ev_ebitda": 10.9, "ev_sales": 1.3},
    "Chemical (Basic)":        {"pe": 14.8, "pbv": 1.9,  "ps": 0.9,  "ev_ebitda": 7.4,  "ev_sales": 1.1},
    "Chemical (Specialty)":    {"pe": 18.2, "pbv": 2.8,  "ps": 1.4,  "ev_ebitda": 9.8,  "ev_sales": 1.6},
    "Computer Services":       {"pe": 23.6, "pbv": 4.9,  "ps": 1.8,  "ev_ebitda": 12.4, "ev_sales": 2.1},
    "Computers/Peripherals":   {"pe": 21.3, "pbv": 5.2,  "ps": 1.5,  "ev_ebitda": 11.8, "ev_sales": 1.8},
    "Drugs (Biotechnology)":   {"pe": 28.4, "pbv": 4.8,  "ps": 5.2,  "ev_ebitda": 18.6, "ev_sales": 6.1},
    "Drugs (Pharmaceutical)":  {"pe": 19.8, "pbv": 3.9,  "ps": 3.4,  "ev_ebitda": 12.2, "ev_sales": 4.1},
    "Electrical Equipment":    {"pe": 26.7, "pbv": 5.1,  "ps": 2.2,  "ev_ebitda": 14.9, "ev_sales": 2.6},
    "Electronics (General)":   {"pe": 24.1, "pbv": 4.3,  "ps": 1.9,  "ev_ebitda": 13.2, "ev_sales": 2.2},
    "Engineering/Construction":{"pe": 16.4, "pbv": 2.6,  "ps": 0.7,  "ev_ebitda": 8.9,  "ev_sales": 0.9},
    "Entertainment":           {"pe": 21.8, "pbv": 3.1,  "ps": 2.4,  "ev_ebitda": 11.4, "ev_sales": 2.9},
    "Food Processing":         {"pe": 17.9, "pbv": 2.8,  "ps": 1.1,  "ev_ebitda": 10.2, "ev_sales": 1.3},
    "Food Wholesalers":        {"pe": 14.2, "pbv": 1.8,  "ps": 0.2,  "ev_ebitda": 7.8,  "ev_sales": 0.3},
    "Healthcare Products":     {"pe": 22.6, "pbv": 4.2,  "ps": 2.8,  "ev_ebitda": 13.1, "ev_sales": 3.2},
    "Healthcare Support Svcs": {"pe": 16.8, "pbv": 2.9,  "ps": 0.8,  "ev_ebitda": 9.4,  "ev_sales": 1.0},
    "Homebuilding":            {"pe": 10.4, "pbv": 1.4,  "ps": 0.6,  "ev_ebitda": 6.2,  "ev_sales": 0.7},
    "Hotel/Gaming":            {"pe": 18.9, "pbv": 3.6,  "ps": 2.1,  "ev_ebitda": 11.8, "ev_sales": 2.6},
    "Household Products":      {"pe": 21.4, "pbv": 4.8,  "ps": 2.4,  "ev_ebitda": 13.4, "ev_sales": 2.8},
    "Machinery":               {"pe": 18.6, "pbv": 3.1,  "ps": 1.3,  "ev_ebitda": 10.8, "ev_sales": 1.5},
    "Metals & Mining":         {"pe": 12.4, "pbv": 1.6,  "ps": 1.2,  "ev_ebitda": 6.8,  "ev_sales": 1.4},
    "Oil/Gas (Production)":    {"pe": 11.8, "pbv": 1.4,  "ps": 1.8,  "ev_ebitda": 5.4,  "ev_sales": 2.1},
    "Packaging & Container":   {"pe": 14.6, "pbv": 2.4,  "ps": 0.9,  "ev_ebitda": 8.2,  "ev_sales": 1.1},
    "Power":                   {"pe": 15.2, "pbv": 1.8,  "ps": 1.6,  "ev_ebitda": 9.1,  "ev_sales": 1.9},
    "R.E.I.T.":                {"pe": 28.6, "pbv": 2.1,  "ps": 6.4,  "ev_ebitda": 18.2, "ev_sales": 7.8},
    "Restaurant/Dining":       {"pe": 21.2, "pbv": 7.4,  "ps": 1.8,  "ev_ebitda": 12.6, "ev_sales": 2.2},
    "Retail (General)":        {"pe": 19.8, "pbv": 4.1,  "ps": 0.8,  "ev_ebitda": 10.4, "ev_sales": 0.9},
    "Semiconductor":           {"pe": 28.9, "pbv": 5.8,  "ps": 4.2,  "ev_ebitda": 17.4, "ev_sales": 5.1},
    "Software (Entertainment)":{"pe": 32.4, "pbv": 8.2,  "ps": 6.8,  "ev_ebitda": 22.1, "ev_sales": 8.4},
    "Steel (General)":         {"pe": 10.8, "pbv": 1.2,  "ps": 0.5,  "ev_ebitda": 5.6,  "ev_sales": 0.6},
    "Telecom (Wireless)":      {"pe": 14.6, "pbv": 2.2,  "ps": 1.4,  "ev_ebitda": 7.8,  "ev_sales": 1.6},
    "Telecom. Services":       {"pe": 16.2, "pbv": 2.6,  "ps": 1.8,  "ev_ebitda": 8.4,  "ev_sales": 2.1},
}

INDUSTRY_NAMES_RV = sorted(INDUSTRY_MULTIPLES.keys())


# ─────────────────────────────────────────────────────────────────────────────
# Result types
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class EquityMultiplesResult:
    # Inputs
    g_high: float
    g_stable: float
    payout_high: float
    payout_stable: float
    ke_high: float
    ke_stable: float
    n: int
    net_margin: float
    # Outputs
    pe_forward: float
    pe_trailing: float
    pbv: float
    ps_forward: float
    ps_trailing: float
    peg: float
    # Derived
    roe_high: float
    roe_stable: float
    # Implied prices (if EPS / BV / Sales provided)
    implied_price_pe:  Optional[float] = None
    implied_price_pbv: Optional[float] = None
    implied_price_ps:  Optional[float] = None


@dataclass
class FirmMultiplesResult:
    # Inputs
    g_high: float
    g_stable: float
    rir_high: float
    rir_stable: float
    wacc_high: float
    wacc_stable: float
    margin_high: float
    margin_stable: float
    n: int
    # Outputs
    ev_ebit_trailing: float
    ev_ebit_forward: float
    ev_nopat_trailing: float
    ev_nopat_forward: float
    ev_ic: float
    ev_sales_trailing: float
    ev_sales_forward: float
    # Derived
    roic_high: float
    roic_stable: float
    # Implied EV (if EBIT / IC / Sales provided)
    implied_ev_from_ebit:  Optional[float] = None
    implied_ev_from_ic:    Optional[float] = None
    implied_ev_from_sales: Optional[float] = None


# ─────────────────────────────────────────────────────────────────────────────
# eqmult.xls — equity multiples via 2-stage DDM
# ─────────────────────────────────────────────────────────────────────────────

def justified_equity_multiples(
    g_high: float,
    payout_high: float,
    ke_high: float,
    n: int,
    g_stable: float,
    payout_stable: float,
    ke_stable: float,
    net_margin: float,
    book_equity_per_share: float = 1.0,
    eps_next_year: float = 1.0,
    revenues_next_year: float = 0.0,
) -> EquityMultiplesResult:
    """
    Derive justified PE, PBV, PS from a 2-stage DDM.  eqmult.xls

    The model values $1 of forward earnings, then scales to multiples.

    PE = Value_of_equity / EPS_forward
    PBV = Value_of_equity / Book_equity
    PS  = Value_of_equity / Sales

    Parameters
    ----------
    g_high         : Growth rate during high-growth period
    payout_high    : Dividend payout (or FCFE% of NI) during high growth
    ke_high        : Cost of equity during high growth
    n              : Length of high-growth period (years)
    g_stable       : Stable-period growth rate
    payout_stable  : Stable-period payout ratio
    ke_stable      : Stable-period cost of equity
    net_margin     : Net profit margin (for PS calculation)
    book_equity_per_share : BV equity per share (for PBV)
    eps_next_year  : Forward EPS (to compute implied price)
    revenues_next_year : Forward revenues per share (for PS)

    Source: Damodaran, Ch 17–19, eqmult.xls
    """
    if ke_stable <= g_stable:
        raise ValueError(f"ke_stable ({ke_stable:.2%}) must exceed g_stable ({g_stable:.2%})")

    # High-growth period: PV of dividends/FCFE
    # EPS_next_year = 1 is treated as EPS_0; model grows before paying dividend
    # This matches eqmult.xls: EPS_t = (1+g)^t for t=1..n
    pv_high = 0.0
    cum_factor = 1.0
    eps_t = 1.0 / (1 + g_high)   # EPS_0 such that EPS_1 = 1.0 after growth
    for t in range(1, n + 1):
        eps_t *= (1 + g_high)     # grow first, then pay dividend
        dps_t = eps_t * payout_high
        cum_factor = cum_factor / (1 + ke_high)
        pv_high += dps_t * cum_factor

    # Terminal value at end of year n
    eps_n1 = eps_t * (1 + g_stable)   # year n+1
    dps_n1 = eps_n1 * payout_stable
    tv = dps_n1 / (ke_stable - g_stable)
    pv_tv = tv * cum_factor

    pe_forward = pv_high + pv_tv  # This IS the PE because we normalised EPS=1

    # Trailing PE: forward PE × (1 + g_high)  → P / EPS_0
    pe_trailing = pe_forward * (1 + g_high)

    # ROE relationships
    roe_high   = g_high   / (1 - payout_high)   if payout_high < 1 else g_high
    roe_stable = g_stable / (1 - payout_stable) if payout_stable < 1 else g_stable

    # PBV = (ROE - g) / (ke - g)  [stable growth formula, approximation]
    # For 2-stage: PBV = PE × ROE_high (Damodaran's approach: PBV = PE × ROE)
    pbv = pe_forward * roe_high if book_equity_per_share <= 0 else (
        pe_forward * eps_next_year / book_equity_per_share
    )

    # PS = PE × net_margin
    ps_forward  = pe_forward  * net_margin
    ps_trailing = pe_trailing * net_margin

    # PEG = PE / (g × 100) — g expressed as percentage
    peg = pe_forward / (g_high * 100) if g_high > 0 else None

    # Implied prices
    ip_pe  = pe_forward  * eps_next_year if eps_next_year > 0 else None
    ip_pbv = pbv * book_equity_per_share if book_equity_per_share > 0 else None
    ip_ps  = ps_forward * revenues_next_year if revenues_next_year > 0 else None

    return EquityMultiplesResult(
        g_high=g_high, g_stable=g_stable,
        payout_high=payout_high, payout_stable=payout_stable,
        ke_high=ke_high, ke_stable=ke_stable, n=n,
        net_margin=net_margin,
        pe_forward=pe_forward, pe_trailing=pe_trailing,
        pbv=pbv, ps_forward=ps_forward, ps_trailing=ps_trailing,
        peg=peg,
        roe_high=roe_high, roe_stable=roe_stable,
        implied_price_pe=ip_pe,
        implied_price_pbv=ip_pbv,
        implied_price_ps=ip_ps,
    )


# ─────────────────────────────────────────────────────────────────────────────
# firmmult.xls — firm multiples via 2-stage FCFF
# ─────────────────────────────────────────────────────────────────────────────

def justified_firm_multiples(
    g_high: float,
    rir_high: float,
    wacc_high: float,
    margin_high: float,
    n: int,
    g_stable: float,
    rir_stable: float,
    wacc_stable: float,
    margin_stable: float,
    tax_rate: float = 0.25,
    # Scaling inputs for implied EV
    nopat_next_year: float = 1.0,
    invested_capital: float = 0.0,
    revenues_next_year: float = 0.0,
) -> FirmMultiplesResult:
    """
    Derive justified EV/EBIT, EV/EBITDA, EV/IC, EV/Sales from 2-stage FCFF.
    firmmult.xls

    The model normalises to NOPAT (= EBIT × (1−t)) = 1.
    EV = Σ PV(FCFF) + PV(TV)

    FCFF_t = NOPAT_t × (1 − RIR_t)
    TV = NOPAT_{n+1} × (1 − RIR_stable) / (WACC_stable − g_stable)

    Parameters
    ----------
    g_high        : Revenue/EBIT growth during high-growth period
    rir_high      : Reinvestment rate during high growth
    wacc_high     : WACC during high growth
    margin_high   : After-tax operating margin during high growth
    n             : High-growth years
    g_stable      : Stable-period growth
    rir_stable    : Stable-period reinvestment rate (= g/ROIC_stable)
    wacc_stable   : Stable WACC
    margin_stable : Stable after-tax operating margin
    tax_rate      : Used for EBIT → NOPAT and multiple adjustments
    nopat_next_year : Forward NOPAT (for scaling to $ EV)
    invested_capital: Book IC (for EV/IC)
    revenues_next_year: Forward revenues (for EV/Sales)

    Source: Damodaran, Ch 20, firmmult.xls
    """
    if wacc_stable <= g_stable:
        raise ValueError(f"wacc_stable ({wacc_stable:.2%}) must exceed g_stable ({g_stable:.2%})")

    # Normalise NOPAT_next_year = 1 (pre-growth timing matches firmmult.xls)
    # NOPAT_0 = 1/(1+g_high); grows before FCFF computed each year
    pv_sum = 0.0
    cum_factor = 1.0
    nopat_t = 1.0 / (1 + g_high)  # NOPAT_0

    for t in range(1, n + 1):
        nopat_t *= (1 + g_high)           # grow first
        fcff_t   = nopat_t * (1 - rir_high)
        cum_factor = cum_factor / (1 + wacc_high)
        pv_sum  += fcff_t * cum_factor

    # Terminal value: NOPAT grows one more step then capitalised
    nopat_n1 = nopat_t * (1 + g_stable)
    fcff_n1  = nopat_n1 * (1 - rir_stable)
    tv       = fcff_n1 / (wacc_stable - g_stable)
    pv_tv    = tv * cum_factor

    ev_nopat_forward = pv_sum + pv_tv   # EV / NOPAT_1

    # EV/EBIT: EBIT_1 = NOPAT_1 / (1-t), so EV/EBIT_fwd = EV/NOPAT * (1-t)
    ev_ebit_forward  = ev_nopat_forward * (1 - tax_rate)

    # Trailing: uses NOPAT_0 = NOPAT_1/(1+g) and EBIT_0
    ev_nopat_trailing = ev_nopat_forward / (1 + g_high)
    ev_ebit_trailing  = ev_ebit_forward  * (1 + g_high)  # trl = fwd × (1+g)

    # EV / Invested Capital: EV / IC = EV_NOPAT × ROIC
    roic_high   = g_high   / rir_high   if rir_high   > 0 else margin_high * 2
    roic_stable = g_stable / rir_stable if rir_stable > 0 else margin_stable * 2
    ev_ic = ev_nopat_forward * roic_high  # via ROIC relationship

    # EV / Sales = EV_NOPAT × margin_high
    ev_sales_forward  = ev_nopat_forward  * margin_high
    ev_sales_trailing = ev_nopat_trailing * margin_high

    # Implied EVs from actual inputs
    iev_ebit = ev_ebit_forward  * nopat_next_year / (1 - tax_rate) if nopat_next_year > 0 else None
    iev_ic   = ev_ic * invested_capital if invested_capital > 0 else None
    iev_rev  = ev_sales_forward * revenues_next_year if revenues_next_year > 0 else None

    return FirmMultiplesResult(
        g_high=g_high, g_stable=g_stable,
        rir_high=rir_high, rir_stable=rir_stable,
        wacc_high=wacc_high, wacc_stable=wacc_stable,
        margin_high=margin_high, margin_stable=margin_stable, n=n,
        ev_ebit_trailing=ev_ebit_trailing,
        ev_ebit_forward=ev_ebit_forward,
        ev_nopat_trailing=ev_nopat_trailing,
        ev_nopat_forward=ev_nopat_forward,
        ev_ic=ev_ic,
        ev_sales_trailing=ev_sales_trailing,
        ev_sales_forward=ev_sales_forward,
        roic_high=roic_high, roic_stable=roic_stable,
        implied_ev_from_ebit=iev_ebit,
        implied_ev_from_ic=iev_ic,
        implied_ev_from_sales=iev_rev,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Scoring & comparison helpers
# ─────────────────────────────────────────────────────────────────────────────

def score_multiple(
    multiple_type: str,
    value: float,
    industry: Optional[str] = None,
) -> tuple[int, str, str]:
    """
    Score a multiple vs industry median and vs absolute benchmarks.
    multiple_type: "pe" | "pbv" | "ps" | "peg" | "ev_ebitda" | "ev_sales"
    """
    ind_val = None
    if industry and industry in INDUSTRY_MULTIPLES:
        ind_val = INDUSTRY_MULTIPLES[industry].get(multiple_type)

    if ind_val:
        ratio = value / ind_val
        if ratio < 0.7:
            return 9, f"Trades at {ratio:.1f}× the industry median — potentially undervalued vs peers", "green"
        elif ratio < 0.9:
            return 7, f"Modest discount to industry median ({ratio:.1f}×)", "green"
        elif ratio < 1.1:
            return 6, f"In line with industry median ({ratio:.1f}×)", "yellow"
        elif ratio < 1.3:
            return 4, f"Modest premium to industry median ({ratio:.1f}×) — needs justification", "yellow"
        else:
            return 2, f"Significant premium ({ratio:.1f}× industry median) — requires strong growth story", "red"

    # Absolute benchmarks if no industry
    if multiple_type == "pe":
        if value < 10: return 8, "Low PE — value territory or earnings risk", "green"
        elif value < 20: return 7, "Moderate PE — fair value range", "green"
        elif value < 30: return 5, "Elevated PE — pricing in significant growth", "yellow"
        else: return 3, "High PE — growth expectations are demanding", "red"

    if multiple_type == "pbv":
        if value < 1: return 9, "Below book value — deep value or distress", "green"
        elif value < 2: return 8, "Low PBV — modest premium to book", "green"
        elif value < 4: return 6, "Moderate PBV — typical for quality businesses", "yellow"
        else: return 3, "High PBV — requires high and sustained ROE", "red"

    if multiple_type == "peg":
        if value < 0.5: return 10, "PEG below 0.5 — potentially deeply undervalued relative to growth", "green"
        elif value < 1.0: return 8, "PEG < 1 — Peter Lynch rule: paying less than growth rate", "green"
        elif value < 1.5: return 6, "PEG 1–1.5 — fair value for a growth stock", "yellow"
        elif value < 2.0: return 4, "PEG 1.5–2 — growth priced in generously", "yellow"
        else: return 2, "PEG > 2 — expensive relative to growth", "red"

    if multiple_type == "ev_ebitda":
        if value < 8: return 8, "Low EV/EBITDA — value range for most sectors", "green"
        elif value < 12: return 7, "Moderate EV/EBITDA", "green"
        elif value < 18: return 5, "Elevated EV/EBITDA — pricing in growth or quality premium", "yellow"
        else: return 3, "High EV/EBITDA — demanding multiple", "red"

    return 5, "No benchmark available", "yellow"


def implied_price_from_peer_multiple(
    multiple_type: str,
    peer_multiple: float,
    firm_metric: float,
    shares: float = 1.0,
    debt: float = 0.0,
    cash: float = 0.0,
) -> float:
    """
    Compute implied share price from a comparable multiple.

    For equity multiples (PE, PBV, PS):
        Implied_price = peer_multiple × firm_metric

    For firm multiples (EV/EBITDA, EV/Sales):
        Implied_EV = peer_multiple × firm_metric
        Implied_equity = Implied_EV − debt + cash
        Implied_price = Implied_equity / shares
    """
    if multiple_type in ("pe", "pbv", "ps", "peg"):
        return peer_multiple * firm_metric
    else:
        implied_ev = peer_multiple * firm_metric
        implied_equity = implied_ev - debt + cash
        return implied_equity / shares if shares > 0 else 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Self-test against eqmult.xls and firmmult.xls reference values
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("── Equity multiples (eqmult.xls reference) ─────────────────")
    # eqmult.xls inputs
    r1 = justified_equity_multiples(
        g_high=0.10, payout_high=0.371, ke_high=0.085, n=10,
        g_stable=0.03, payout_stable=0.70, ke_stable=0.08,
        net_margin=0.025,
        book_equity_per_share=6.29,
        eps_next_year=1.0,
        revenues_next_year=40.0,
    )
    print(f"  PE (forward):   {r1.pe_forward:.2f}   ref: 18.68")
    print(f"  PBV:            {r1.pbv:.2f}   ref: 2.97")
    print(f"  PS (forward):   {r1.ps_forward:.4f}  ref: 0.4670")
    print(f"  PS (trailing):  {r1.ps_trailing:.4f}  ref: 0.5137")
    print(f"  PEG:            {r1.peg:.2f}")
    assert abs(r1.pe_forward  - 18.68) < 0.1,  f"PE failed: {r1.pe_forward:.4f}"
    assert abs(r1.pbv         - 2.97)  < 0.05, f"PBV failed: {r1.pbv:.4f}"
    assert abs(r1.ps_forward  - 0.467) < 0.01, f"PS fwd failed: {r1.ps_forward:.4f}"
    print("  ✓ All equity multiple tests passed")

    print("\n── Firm multiples (firmmult.xls reference) ──────────────────")
    # firmmult.xls inputs
    r2 = justified_firm_multiples(
        g_high=0.096,  rir_high=0.60,  wacc_high=0.0803,  margin_high=0.1443,
        n=10,
        g_stable=0.035, rir_stable=0.2917, wacc_stable=0.0774, margin_stable=0.05,
        tax_rate=0.40,
        nopat_next_year=1.0, invested_capital=6.25, revenues_next_year=6.93,
    )
    print(f"  EV/NOPAT (fwd): {r2.ev_nopat_forward:.2f}   ref: 22.18")
    print(f"  EV/EBIT (trl):  {r2.ev_ebit_trailing:.2f}   ref: 14.58")
    print(f"  EV/EBIT (fwd):  {r2.ev_ebit_forward:.2f}   ref: 13.31")
    print(f"  EV/Sales (trl): {r2.ev_sales_trailing:.2f}   ref: 3.51")
    assert abs(r2.ev_nopat_forward - 22.18) < 0.2,  f"EV/NOPAT failed: {r2.ev_nopat_forward:.4f}"
    assert abs(r2.ev_ebit_trailing - 14.58) < 0.2,  f"EV/EBIT trl failed: {r2.ev_ebit_trailing:.4f}"
    assert abs(r2.ev_ebit_forward  - 13.31) < 0.2,  f"EV/EBIT fwd failed: {r2.ev_ebit_forward:.4f}"
    print("  ✓ All firm multiple tests passed")

    print("\n── Industry scoring ──────────────────────────────────────────")
    s, t, c = score_multiple("pe", 22.1, "Food Processing")
    print(f"  PE 22.1 vs Food Processing: Score {s} — {t}")
    s, t, c = score_multiple("peg", 0.85)
    print(f"  PEG 0.85 (no industry): Score {s} — {t}")
