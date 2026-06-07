"""
fcff_models.py
==============
Damodaran Investment Valuation — Chapters 9, 10, 14, 15

Implements all six cash-flow models from the spreadsheet files:

  FCFF models (discount at WACC → firm value → equity value per share)
    fcff_stable      — fcffst.xls    single-stage Gordon growth
    fcff_2stage      — fcff2st.xls   high-growth + stable terminal
    fcff_3stage      — fcff3st.xls   high-growth + linear transition + stable

  FCFE models (discount at ke → equity value per share directly)
    fcfe_stable      — fcfest.xls    single-stage Gordon growth
    fcfe_2stage      — fcfeginzu.xls high-growth + stable terminal
    fcfe_3stage      — fcfeginzu.xls (3-stage mode) with linear transition

Key formulas
------------
FCFF = EBIT × (1−t) − Net_CapEx − ΔWorking_Capital
     = NOPAT − Reinvestment

FCFE = Net_Income − Net_CapEx × (1−δ) − ΔWC × (1−δ)
     = NI − (1−δ) × Reinvestment
  where δ = debt financing ratio (new debt / total reinvestment)

Reinvestment_Rate (FCFF) = (Net_CapEx + ΔWC) / NOPAT
Equity_Reinvestment_Rate = (Net_CapEx + ΔWC − Net_Debt_Issued) / Net_Income
Fundamental_Growth (firm) = ROC  × Reinvestment_Rate
Fundamental_Growth (equity) = ROE × Equity_Reinvestment_Rate

Terminal_Value = FCFF_{n+1} / (WACC − g_stable)   [FCFF model]
              = FCFE_{n+1} / (ke   − g_stable)     [FCFE model]

Value_of_Firm = PV(FCFFs) + PV(Terminal_Value)
Value_of_Equity = Value_of_Firm − Debt_MV + Cash
Value_per_Share = Value_of_Equity / Shares

Sources
-------
Damodaran, Investment Valuation 2nd Ed, Ch 9 (cash flows), Ch 10 (FCFF),
Ch 14 (FCFE models), Ch 15 (FCFF/WACC models)
Spreadsheets: fcffst.xls, fcff2st.xls, fcff3st.xls, fcfest.xls, fcfeginzu.xls
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Shared result types
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class YearlyFCFF:
    year: int
    ebit: float
    nopat: float          # EBIT × (1−t)
    net_capex: float      # CapEx − Depreciation
    delta_wc: float       # Change in working capital
    reinvestment: float   # net_capex + delta_wc
    reinvestment_rate: float
    fcff: float
    wacc: float
    discount_factor: float
    pv_fcff: float


@dataclass
class YearlyFCFE:
    year: int
    net_income: float
    net_capex: float
    delta_wc: float
    net_debt_issued: float       # new debt − debt repaid
    equity_reinvestment: float   # net_capex + delta_wc − net_debt_issued
    equity_reinv_rate: float
    fcfe: float
    ke: float
    discount_factor: float
    pv_fcfe: float


@dataclass
class FCFFValuationResult:
    model: str                          # "stable" | "2stage" | "3stage"
    yearly: list[YearlyFCFF]
    terminal_fcff: float
    terminal_value: float
    pv_terminal_value: float
    pv_fcff_highgrowth: float
    value_of_firm: float
    cash: float
    debt_mv: float
    options_value: float
    value_of_equity: float
    shares: float
    value_per_share: float
    # inputs echo
    inputs: dict = field(default_factory=dict)


@dataclass
class FCFEValuationResult:
    model: str
    yearly: list[YearlyFCFE]
    terminal_fcfe: float
    terminal_value: float
    pv_terminal_value: float
    pv_fcfe_highgrowth: float
    value_of_equity_ops: float
    cash: float
    options_value: float
    value_of_equity: float
    shares: float
    value_per_share: float
    inputs: dict = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────

def fundamental_growth_fcff(roc: float, reinvestment_rate: float) -> float:
    """g = ROC × Reinvestment_Rate  (Ch 11, Damodaran)"""
    return roc * reinvestment_rate


def fundamental_growth_fcfe(roe: float, equity_reinv_rate: float) -> float:
    """g = ROE × Equity_Reinvestment_Rate  (Ch 11)"""
    return roe * equity_reinv_rate


def reinvestment_rate_from_growth(g: float, roc: float) -> float:
    """RIR = g / ROC  — used in stable terminal period"""
    return g / roc if roc > 0 else 0.0


def equity_reinv_rate_from_growth(g: float, roe: float) -> float:
    """Equity_RIR = g / ROE"""
    return g / roe if roe > 0 else 0.0


def pv_factor(discount_rate: float, year: int, prev_factor: float = None) -> float:
    """Cumulative discount factor: 1/(1+r)^t, computed iteratively."""
    if prev_factor is None:
        return 1.0 / (1 + discount_rate) ** year
    return prev_factor / (1 + discount_rate)


# ─────────────────────────────────────────────────────────────────────────────
# FCFF — Stable growth  (fcffst.xls)
# ─────────────────────────────────────────────────────────────────────────────

def fcff_stable(
    ebit: float,
    tax_rate: float,
    capex: float,
    depreciation: float,
    delta_wc: float,
    wacc: float,
    g: float,
    # optional override for stable-period reinvestment
    stable_roc: Optional[float] = None,
    capex_depr_ratio: Optional[float] = None,
    # equity bridge
    debt_mv: float = 0.0,
    cash: float = 0.0,
    shares: float = 1.0,
    options_value: float = 0.0,
) -> FCFFValuationResult:
    """
    Single-stage FCFF Gordon Growth model.  fcffst.xls

    If stable_roc is provided, reinvestment in the terminal year is derived
    from fundamentals: RIR = g / ROC, so FCFF = NOPAT × (1 − g/ROC).
    Otherwise FCFF is computed from the explicit capex/depr/wc inputs.

    If capex_depr_ratio is provided (e.g. 1.25 = capex is 125% of depr),
    net_capex = depreciation × (capex_depr_ratio − 1).
    """
    if wacc <= g:
        raise ValueError(f"WACC ({wacc:.2%}) must exceed stable growth rate ({g:.2%})")

    nopat = ebit * (1 - tax_rate)

    # Net capex
    if capex_depr_ratio is not None:
        net_capex = depreciation * (capex_depr_ratio - 1)
    else:
        net_capex = capex - depreciation

    # FCFF in current year
    fcff_0 = nopat - net_capex - delta_wc

    # Year-1 FCFF (grown by g)
    if stable_roc is not None:
        rir = reinvestment_rate_from_growth(g, stable_roc)
        nopat_1 = nopat * (1 + g)
        fcff_1 = nopat_1 * (1 - rir)
    else:
        fcff_1 = fcff_0 * (1 + g)

    terminal_value = fcff_1 / (wacc - g)

    # No high-growth years; terminal value IS the firm value (discounted 0 periods)
    # (stable model: value = next-year FCFF capitalised)
    value_of_firm = terminal_value

    value_of_equity = value_of_firm - debt_mv + cash - options_value
    vps = value_of_equity / shares if shares > 0 else 0.0

    rir_current = (net_capex + delta_wc) / nopat if nopat > 0 else 0.0
    row = YearlyFCFF(
        year=1, ebit=ebit * (1 + g), nopat=nopat * (1 + g),
        net_capex=net_capex * (1 + g), delta_wc=delta_wc * (1 + g),
        reinvestment=(net_capex + delta_wc) * (1 + g),
        reinvestment_rate=rir_current,
        fcff=fcff_1, wacc=wacc, discount_factor=1.0,
        pv_fcff=fcff_1,
    )

    return FCFFValuationResult(
        model="stable",
        yearly=[row],
        terminal_fcff=fcff_1,
        terminal_value=terminal_value,
        pv_terminal_value=terminal_value,
        pv_fcff_highgrowth=0.0,
        value_of_firm=value_of_firm,
        cash=cash, debt_mv=debt_mv, options_value=options_value,
        value_of_equity=value_of_equity,
        shares=shares, value_per_share=vps,
        inputs=dict(ebit=ebit, tax_rate=tax_rate, capex=capex,
                    depreciation=depreciation, delta_wc=delta_wc,
                    wacc=wacc, g=g, stable_roc=stable_roc),
    )


# ─────────────────────────────────────────────────────────────────────────────
# FCFF — 2-stage  (fcff2st.xls)
# ─────────────────────────────────────────────────────────────────────────────

def fcff_2stage(
    ebit: float,
    tax_rate: float,
    capex: float,
    depreciation: float,
    delta_wc: float,
    revenues: float,
    wacc_high: float,
    g_high: float,
    n_high: int,
    g_stable: float,
    wacc_stable: Optional[float] = None,
    # stable period reinvestment
    stable_roc: float = 0.12,
    # capex/depr grow with earnings unless overridden
    capex_growth: Optional[float] = None,
    depr_growth: Optional[float] = None,
    wc_pct_rev: Optional[float] = None,    # working capital as % of revenues
    rev_growth_stable: Optional[float] = None,
    # equity bridge
    debt_mv: float = 0.0,
    cash: float = 0.0,
    shares: float = 1.0,
    options_value: float = 0.0,
) -> FCFFValuationResult:
    """
    2-stage FCFF model.  fcff2st.xls

    High-growth period: EBIT grows at g_high; capex/depr/WC grow at same
    rate unless separate rates provided. WACC stays at wacc_high.

    Stable period: reinvestment computed from fundamentals (RIR = g_stable/ROC).
    """
    if wacc_stable is None:
        wacc_stable = wacc_high
    if wacc_stable <= g_stable:
        raise ValueError(f"Stable WACC ({wacc_stable:.2%}) must exceed g_stable ({g_stable:.2%})")

    # Defaults
    cg = capex_growth if capex_growth is not None else g_high
    dg = depr_growth  if depr_growth  is not None else g_high
    wc_pct = wc_pct_rev if wc_pct_rev is not None else (delta_wc / revenues if revenues > 0 else 0)
    rev_g_stable = rev_growth_stable if rev_growth_stable is not None else g_stable

    rows: list[YearlyFCFF] = []
    cum_factor = 1.0
    pv_sum = 0.0

    ebit_t    = ebit
    capex_t   = capex
    depr_t    = depreciation
    rev_t     = revenues

    for t in range(1, n_high + 1):
        ebit_t    *= (1 + g_high)
        capex_t   *= (1 + cg)
        depr_t    *= (1 + dg)
        rev_t     *= (1 + g_high)

        nopat_t   = ebit_t * (1 - tax_rate)
        net_capex = capex_t - depr_t
        dwc_t     = wc_pct * rev_t * g_high   # increment in WC = wc% × rev × growth
        reinv     = net_capex + dwc_t
        rir       = reinv / nopat_t if nopat_t > 0 else 0
        fcff_t    = nopat_t - reinv

        cum_factor = pv_factor(wacc_high, t)
        pv_t       = fcff_t * cum_factor
        pv_sum    += pv_t

        rows.append(YearlyFCFF(
            year=t, ebit=ebit_t, nopat=nopat_t,
            net_capex=net_capex, delta_wc=dwc_t,
            reinvestment=reinv, reinvestment_rate=rir,
            fcff=fcff_t, wacc=wacc_high,
            discount_factor=cum_factor, pv_fcff=pv_t,
        ))

    # Terminal year FCFF — from fundamentals
    ebit_n1   = ebit_t * (1 + g_stable)
    nopat_n1  = ebit_n1 * (1 - tax_rate)
    rir_stable = reinvestment_rate_from_growth(g_stable, stable_roc)
    fcff_n1   = nopat_n1 * (1 - rir_stable)

    terminal_value    = fcff_n1 / (wacc_stable - g_stable)
    pv_terminal       = terminal_value * pv_factor(wacc_high, n_high)

    value_of_firm     = pv_sum + pv_terminal
    value_of_equity   = value_of_firm - debt_mv + cash - options_value
    vps               = value_of_equity / shares if shares > 0 else 0.0

    return FCFFValuationResult(
        model="2stage",
        yearly=rows,
        terminal_fcff=fcff_n1,
        terminal_value=terminal_value,
        pv_terminal_value=pv_terminal,
        pv_fcff_highgrowth=pv_sum,
        value_of_firm=value_of_firm,
        cash=cash, debt_mv=debt_mv, options_value=options_value,
        value_of_equity=value_of_equity,
        shares=shares, value_per_share=vps,
        inputs=dict(ebit=ebit, tax_rate=tax_rate, g_high=g_high,
                    n_high=n_high, wacc_high=wacc_high,
                    g_stable=g_stable, wacc_stable=wacc_stable,
                    stable_roc=stable_roc),
    )


# ─────────────────────────────────────────────────────────────────────────────
# FCFF — 3-stage  (fcff3st.xls)
# ─────────────────────────────────────────────────────────────────────────────

def fcff_3stage(
    revenues: float,
    ebit: float,
    capex: float,
    depreciation: float,
    delta_wc: float,
    tax_rate: float,
    # high growth
    rev_growth_high: float,
    target_ebit_margin: float,      # pre-tax; converges during transition
    current_ebit_margin: Optional[float] = None,
    n_high: int = 5,
    debt_ratio_high: float = 0.0,   # for WACC during high growth
    capex_growth_high: Optional[float] = None,
    wc_pct_rev: float = 0.075,
    # cost of capital high growth
    wacc_high: float = 0.12,
    # stable
    g_stable: float = 0.06,
    stable_roc: float = 0.12,
    stable_ebit_margin: Optional[float] = None,
    wacc_stable: Optional[float] = None,
    debt_ratio_stable: float = 0.05,
    # transition: WACC linearly interpolates high→stable over years n_high+1 to n_high+n_transition
    n_transition: int = 5,
    # equity bridge
    debt_mv: float = 0.0,
    cash: float = 0.0,
    shares: float = 1.0,
    options_value: float = 0.0,
) -> FCFFValuationResult:
    """
    3-stage FCFF model.  fcff3st.xls

    Stage 1 (years 1..n_high):
      Revenue grows at rev_growth_high; EBIT margin linearly moves from
      current_ebit_margin toward target_ebit_margin.
      CapEx/Depr grow at rev_growth_high unless overridden.
      WC = wc_pct_rev × revenues.

    Stage 2 (years n_high+1 .. n_high+n_transition):
      Revenue growth linearly declines from rev_growth_high to g_stable.
      EBIT margin continues to converge to stable_ebit_margin.
      WACC linearly declines from wacc_high to wacc_stable.

    Stage 3: terminal value from fundamentals at year n_high+n_transition.
    """
    if wacc_stable is None:
        wacc_stable = wacc_high
    if wacc_stable <= g_stable:
        raise ValueError(f"Stable WACC must exceed g_stable")

    if current_ebit_margin is None:
        current_ebit_margin = ebit / revenues if revenues > 0 else 0.05
    if stable_ebit_margin is None:
        stable_ebit_margin = target_ebit_margin
    if capex_growth_high is None:
        capex_growth_high = rev_growth_high

    n_total = n_high + n_transition
    rows: list[YearlyFCFF] = []
    cum_factor = 1.0
    pv_sum = 0.0

    rev_t   = revenues
    capex_t = capex
    depr_t  = depreciation

    for t in range(1, n_total + 1):
        # Revenue growth: linear decline from rev_growth_high → g_stable after n_high
        if t <= n_high:
            g_t = rev_growth_high
        else:
            step = (t - n_high) / n_transition
            g_t  = rev_growth_high + step * (g_stable - rev_growth_high)

        rev_t *= (1 + g_t)

        # EBIT margin: linear convergence over full n_total periods
        frac = t / n_total
        margin_t = current_ebit_margin + frac * (stable_ebit_margin - current_ebit_margin)
        ebit_t   = rev_t * margin_t
        nopat_t  = ebit_t * (1 - tax_rate)

        # CapEx / Depreciation
        if t <= n_high:
            capex_t *= (1 + capex_growth_high)
            depr_t  *= (1 + capex_growth_high)
        else:
            capex_t *= (1 + g_t)
            depr_t  *= (1 + g_t)
        net_capex = capex_t - depr_t

        # Working capital change = wc_pct × rev × g (increment)
        dwc_t = wc_pct_rev * rev_t * g_t

        reinv   = net_capex + dwc_t
        rir     = reinv / nopat_t if nopat_t > 0 else 0
        fcff_t  = nopat_t - reinv

        # WACC: linear decline from wacc_high → wacc_stable over transition
        if t <= n_high:
            wacc_t = wacc_high
        else:
            step   = (t - n_high) / n_transition
            wacc_t = wacc_high + step * (wacc_stable - wacc_high)

        cum_factor = pv_factor(wacc_t, 1, cum_factor)
        pv_t       = fcff_t * cum_factor
        pv_sum    += pv_t

        rows.append(YearlyFCFF(
            year=t, ebit=ebit_t, nopat=nopat_t,
            net_capex=net_capex, delta_wc=dwc_t,
            reinvestment=reinv, reinvestment_rate=rir,
            fcff=fcff_t, wacc=wacc_t,
            discount_factor=cum_factor, pv_fcff=pv_t,
        ))

    # Terminal value
    last = rows[-1]
    ebit_n1  = last.ebit * (1 + g_stable)
    nopat_n1 = ebit_n1 * (1 - tax_rate)
    rir_s    = reinvestment_rate_from_growth(g_stable, stable_roc)
    fcff_n1  = nopat_n1 * (1 - rir_s)

    terminal_value  = fcff_n1 / (wacc_stable - g_stable)
    pv_terminal     = terminal_value * cum_factor   # use same cum factor as last year

    value_of_firm   = pv_sum + pv_terminal
    value_of_equity = value_of_firm - debt_mv + cash - options_value
    vps             = value_of_equity / shares if shares > 0 else 0.0

    return FCFFValuationResult(
        model="3stage",
        yearly=rows,
        terminal_fcff=fcff_n1,
        terminal_value=terminal_value,
        pv_terminal_value=pv_terminal,
        pv_fcff_highgrowth=pv_sum,
        value_of_firm=value_of_firm,
        cash=cash, debt_mv=debt_mv, options_value=options_value,
        value_of_equity=value_of_equity,
        shares=shares, value_per_share=vps,
        inputs=dict(revenues=revenues, ebit=ebit,
                    rev_growth_high=rev_growth_high, n_high=n_high,
                    n_transition=n_transition, g_stable=g_stable,
                    wacc_high=wacc_high, wacc_stable=wacc_stable,
                    stable_roc=stable_roc),
    )


# ─────────────────────────────────────────────────────────────────────────────
# FCFE — Stable growth  (fcfest.xls)
# ─────────────────────────────────────────────────────────────────────────────

def fcfe_stable(
    net_income: float,
    capex: float,
    depreciation: float,
    delta_wc: float,
    debt_ratio: float,   # δ: proportion of reinvestment financed by new debt
    ke: float,
    g: float,
    # optional: recompute reinvestment from ROE
    roe: Optional[float] = None,
    # equity bridge
    cash: float = 0.0,
    shares: float = 1.0,
    options_value: float = 0.0,
) -> FCFEValuationResult:
    """
    Stable-growth FCFE model.  fcfest.xls

    FCFE = NI − (CapEx − Depr) × (1−δ) − ΔWC × (1−δ)
         = NI − (1−δ) × [Net_CapEx + ΔWC]

    If roe is provided, reinvestment rate is derived from fundamentals:
      Equity_RIR = g / ROE, FCFE = NI × (1 − g/ROE)
    """
    if ke <= g:
        raise ValueError(f"ke ({ke:.2%}) must exceed g ({g:.2%})")

    net_capex = capex - depreciation
    reinv     = net_capex + delta_wc

    if roe is not None:
        erir  = equity_reinv_rate_from_growth(g, roe)
        fcfe_0 = net_income * (1 - erir)
    else:
        fcfe_0 = net_income - (1 - debt_ratio) * reinv

    fcfe_1 = fcfe_0 * (1 + g)
    tv     = fcfe_1 / (ke - g)

    net_debt = debt_ratio * reinv
    erir_act = ((1 - debt_ratio) * reinv) / net_income if net_income > 0 else 0

    row = YearlyFCFE(
        year=1, net_income=net_income * (1 + g),
        net_capex=net_capex * (1 + g), delta_wc=delta_wc * (1 + g),
        net_debt_issued=net_debt * (1 + g),
        equity_reinvestment=(1 - debt_ratio) * reinv * (1 + g),
        equity_reinv_rate=erir_act,
        fcfe=fcfe_1, ke=ke, discount_factor=1.0, pv_fcfe=fcfe_1,
    )

    value_of_equity = tv + cash - options_value
    vps = value_of_equity / shares if shares > 0 else 0.0

    return FCFEValuationResult(
        model="stable",
        yearly=[row],
        terminal_fcfe=fcfe_1,
        terminal_value=tv,
        pv_terminal_value=tv,
        pv_fcfe_highgrowth=0.0,
        value_of_equity_ops=tv,
        cash=cash, options_value=options_value,
        value_of_equity=value_of_equity,
        shares=shares, value_per_share=vps,
        inputs=dict(net_income=net_income, capex=capex,
                    depreciation=depreciation, delta_wc=delta_wc,
                    debt_ratio=debt_ratio, ke=ke, g=g, roe=roe),
    )


# ─────────────────────────────────────────────────────────────────────────────
# FCFE — 2-stage  (fcfeginzu.xls, 2-stage mode)
# ─────────────────────────────────────────────────────────────────────────────

def fcfe_2stage(
    net_income: float,
    capex: float,
    depreciation: float,
    delta_wc: float,
    debt_ratio: float,
    ke_high: float,
    g_high: float,
    n_high: int,
    g_stable: float,
    ke_stable: Optional[float] = None,
    # stable-period reinvestment
    roe_stable: float = 0.10,
    # optional: derive high-growth reinvestment from ROE
    roe_high: Optional[float] = None,
    # equity bridge
    cash: float = 0.0,
    shares: float = 1.0,
    options_value: float = 0.0,
) -> FCFEValuationResult:
    """
    2-stage FCFE model.  fcfeginzu.xls (high-growth + stable terminal)

    High growth: NI grows at g_high, reinvestment from inputs or ROE.
    Stable: reinvestment from ROE fundamentals (Equity_RIR = g/ROE).
    """
    if ke_stable is None:
        ke_stable = ke_high
    if ke_stable <= g_stable:
        raise ValueError(f"ke_stable must exceed g_stable")

    rows: list[YearlyFCFE] = []
    cum_factor = 1.0
    pv_sum = 0.0

    ni_t    = net_income
    capex_t = capex
    depr_t  = depreciation
    dwc_t   = delta_wc

    for t in range(1, n_high + 1):
        ni_t    *= (1 + g_high)
        capex_t *= (1 + g_high)
        depr_t  *= (1 + g_high)
        dwc_t   *= (1 + g_high)

        net_capex  = capex_t - depr_t
        reinv      = net_capex + dwc_t
        net_debt   = debt_ratio * reinv
        eq_reinv   = (1 - debt_ratio) * reinv

        if roe_high is not None:
            erir = equity_reinv_rate_from_growth(g_high, roe_high)
            fcfe_t = ni_t * (1 - erir)
        else:
            fcfe_t = ni_t - eq_reinv

        erir_act  = eq_reinv / ni_t if ni_t > 0 else 0
        cum_factor = pv_factor(ke_high, t)
        pv_t       = fcfe_t * cum_factor
        pv_sum    += pv_t

        rows.append(YearlyFCFE(
            year=t, net_income=ni_t,
            net_capex=net_capex, delta_wc=dwc_t,
            net_debt_issued=net_debt,
            equity_reinvestment=eq_reinv,
            equity_reinv_rate=erir_act,
            fcfe=fcfe_t, ke=ke_high,
            discount_factor=cum_factor, pv_fcfe=pv_t,
        ))

    # Terminal value
    ni_n1    = ni_t * (1 + g_stable)
    erir_s   = equity_reinv_rate_from_growth(g_stable, roe_stable)
    fcfe_n1  = ni_n1 * (1 - erir_s)
    tv       = fcfe_n1 / (ke_stable - g_stable)
    pv_tv    = tv * pv_factor(ke_high, n_high)

    val_ops         = pv_sum + pv_tv
    value_of_equity = val_ops + cash - options_value
    vps             = value_of_equity / shares if shares > 0 else 0.0

    return FCFEValuationResult(
        model="2stage",
        yearly=rows,
        terminal_fcfe=fcfe_n1,
        terminal_value=tv,
        pv_terminal_value=pv_tv,
        pv_fcfe_highgrowth=pv_sum,
        value_of_equity_ops=val_ops,
        cash=cash, options_value=options_value,
        value_of_equity=value_of_equity,
        shares=shares, value_per_share=vps,
        inputs=dict(net_income=net_income, g_high=g_high, n_high=n_high,
                    ke_high=ke_high, g_stable=g_stable, ke_stable=ke_stable,
                    roe_stable=roe_stable),
    )


# ─────────────────────────────────────────────────────────────────────────────
# FCFE — 3-stage  (fcfeginzu.xls, 3-stage mode)
# ─────────────────────────────────────────────────────────────────────────────

def fcfe_3stage(
    net_income: float,
    capex: float,
    depreciation: float,
    delta_wc: float,
    debt_ratio: float,
    ke_high: float,
    g_high: float,
    n_high: int,
    g_stable: float,
    n_transition: int = 5,
    ke_stable: Optional[float] = None,
    roe_high: Optional[float] = None,
    roe_stable: float = 0.10,
    # equity bridge
    cash: float = 0.0,
    shares: float = 1.0,
    options_value: float = 0.0,
) -> FCFEValuationResult:
    """
    3-stage FCFE model.  fcfeginzu.xls (3-stage mode)

    Stage 1 (1..n_high): constant high growth g_high.
    Stage 2 (n_high+1 .. n_high+n_transition): growth and ke linearly
      decline from high to stable values.
    Stage 3: terminal value from fundamentals.
    """
    if ke_stable is None:
        ke_stable = ke_high
    if ke_stable <= g_stable:
        raise ValueError("ke_stable must exceed g_stable")

    n_total = n_high + n_transition
    rows: list[YearlyFCFE] = []
    cum_factor = 1.0
    pv_sum = 0.0

    ni_t    = net_income
    capex_t = capex
    depr_t  = depreciation
    dwc_t   = delta_wc

    for t in range(1, n_total + 1):
        if t <= n_high:
            g_t  = g_high
            ke_t = ke_high
        else:
            step = (t - n_high) / n_transition
            g_t  = g_high  + step * (g_stable  - g_high)
            ke_t = ke_high + step * (ke_stable - ke_high)

        ni_t    *= (1 + g_t)
        capex_t *= (1 + g_t)
        depr_t  *= (1 + g_t)
        dwc_t   *= (1 + g_t)

        net_capex = capex_t - depr_t
        reinv     = net_capex + dwc_t
        net_debt  = debt_ratio * reinv
        eq_reinv  = (1 - debt_ratio) * reinv

        if roe_high is not None:
            # blend roe during transition
            if t <= n_high:
                roe_t = roe_high
            else:
                step  = (t - n_high) / n_transition
                roe_t = roe_high + step * (roe_stable - roe_high)
            erir   = equity_reinv_rate_from_growth(g_t, roe_t)
            fcfe_t = ni_t * (1 - erir)
        else:
            fcfe_t   = ni_t - eq_reinv

        erir_act   = eq_reinv / ni_t if ni_t > 0 else 0
        cum_factor = pv_factor(ke_t, 1, cum_factor)
        pv_t       = fcfe_t * cum_factor
        pv_sum    += pv_t

        rows.append(YearlyFCFE(
            year=t, net_income=ni_t,
            net_capex=net_capex, delta_wc=dwc_t,
            net_debt_issued=net_debt,
            equity_reinvestment=eq_reinv,
            equity_reinv_rate=erir_act,
            fcfe=fcfe_t, ke=ke_t,
            discount_factor=cum_factor, pv_fcfe=pv_t,
        ))

    last      = rows[-1]
    ni_n1     = last.net_income * (1 + g_stable)
    erir_s    = equity_reinv_rate_from_growth(g_stable, roe_stable)
    fcfe_n1   = ni_n1 * (1 - erir_s)
    tv        = fcfe_n1 / (ke_stable - g_stable)
    pv_tv     = tv * cum_factor

    val_ops         = pv_sum + pv_tv
    value_of_equity = val_ops + cash - options_value
    vps             = value_of_equity / shares if shares > 0 else 0.0

    return FCFEValuationResult(
        model="3stage",
        yearly=rows,
        terminal_fcfe=fcfe_n1,
        terminal_value=tv,
        pv_terminal_value=pv_tv,
        pv_fcfe_highgrowth=pv_sum,
        value_of_equity_ops=val_ops,
        cash=cash, options_value=options_value,
        value_of_equity=value_of_equity,
        shares=shares, value_per_share=vps,
        inputs=dict(net_income=net_income, g_high=g_high, n_high=n_high,
                    n_transition=n_transition, ke_high=ke_high,
                    g_stable=g_stable, ke_stable=ke_stable,
                    roe_stable=roe_stable),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Pretty-print helpers
# ─────────────────────────────────────────────────────────────────────────────

def print_fcff_result(r: FCFFValuationResult) -> None:
    print(f"\n{'='*60}")
    print(f"  FCFF VALUATION — {r.model.upper()} GROWTH MODEL")
    print(f"{'='*60}")
    if r.yearly:
        print(f"\n{'Yr':>3} {'EBIT':>10} {'NOPAT':>10} {'NetCapEx':>10} "
              f"{'ΔWC':>8} {'FCFF':>10} {'WACC':>7} {'PV':>10}")
        print("-" * 72)
        for row in r.yearly:
            print(f"{row.year:>3} {row.ebit:>10,.0f} {row.nopat:>10,.0f} "
                  f"{row.net_capex:>10,.0f} {row.delta_wc:>8,.0f} "
                  f"{row.fcff:>10,.0f} {row.wacc:>7.2%} {row.pv_fcff:>10,.0f}")

    print(f"\n  PV of high-growth FCFFs  : {r.pv_fcff_highgrowth:>12,.0f}")
    print(f"  Terminal FCFF            : {r.terminal_fcff:>12,.0f}")
    print(f"  Terminal Value           : {r.terminal_value:>12,.0f}")
    print(f"  PV of Terminal Value     : {r.pv_terminal_value:>12,.0f}")
    print(f"  ─────────────────────────────────────────")
    print(f"  Value of Firm            : {r.value_of_firm:>12,.0f}")
    print(f"  − Debt (MV)              : {r.debt_mv:>12,.0f}")
    print(f"  + Cash                   : {r.cash:>12,.0f}")
    if r.options_value:
        print(f"  − Options value          : {r.options_value:>12,.0f}")
    print(f"  Value of Equity          : {r.value_of_equity:>12,.0f}")
    print(f"  ÷ Shares                 : {r.shares:>12,.0f}")
    print(f"  Value per Share          : {r.value_per_share:>12,.2f}")
    print(f"{'='*60}\n")


def print_fcfe_result(r: FCFEValuationResult) -> None:
    print(f"\n{'='*60}")
    print(f"  FCFE VALUATION — {r.model.upper()} GROWTH MODEL")
    print(f"{'='*60}")
    if r.yearly:
        print(f"\n{'Yr':>3} {'Net Inc':>10} {'FCFE':>10} {'ke':>7} {'PV':>10}")
        print("-" * 45)
        for row in r.yearly:
            print(f"{row.year:>3} {row.net_income:>10,.0f} {row.fcfe:>10,.0f} "
                  f"{row.ke:>7.2%} {row.pv_fcfe:>10,.0f}")

    print(f"\n  PV of high-growth FCFEs  : {r.pv_fcfe_highgrowth:>12,.0f}")
    print(f"  Terminal FCFE            : {r.terminal_fcfe:>12,.0f}")
    print(f"  Terminal Value           : {r.terminal_value:>12,.0f}")
    print(f"  PV of Terminal Value     : {r.pv_terminal_value:>12,.0f}")
    print(f"  ─────────────────────────────────────────")
    print(f"  Value of Equity (ops)    : {r.value_of_equity_ops:>12,.0f}")
    print(f"  + Cash                   : {r.cash:>12,.0f}")
    print(f"  Value of Equity          : {r.value_of_equity:>12,.0f}")
    print(f"  ÷ Shares                 : {r.shares:>12,.0f}")
    print(f"  Value per Share          : {r.value_per_share:>12,.2f}")
    print(f"{'='*60}\n")


# ─────────────────────────────────────────────────────────────────────────────
# Self-test — validate against spreadsheet reference values
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":

    print("── FCFF Stable (fcffst.xls reference: firm value ≈ 13,148) ──")
    r1 = fcff_stable(
        ebit=1535, tax_rate=0.36, capex=550, depreciation=400,
        delta_wc=160, wacc=0.10769, g=0.05,
        capex_depr_ratio=1.25,
        debt_mv=0, cash=0, shares=1,
    )
    print_fcff_result(r1)
    assert abs(r1.value_of_firm - 13148) < 50, f"Got {r1.value_of_firm:.0f}"
    print("✓ FCFF stable matches reference")

    print("── FCFF 2-stage (fcff2st.xls reference: equity/share ≈ 66.78) ──")
    r2 = fcff_2stage(
        ebit=5186, tax_rate=0.2849, capex=2152, depreciation=1228,
        delta_wc=499, revenues=16701,
        wacc_high=0.09617, g_high=0.10563, n_high=5,
        g_stable=0.06, wacc_stable=0.09617,
        stable_roc=0.12,
        wc_pct_rev=0.22484,
        debt_mv=1822, cash=500, shares=993.57, options_value=1500,
    )
    print_fcff_result(r2)
    assert abs(r2.value_per_share - 66.78) < 5, f"Got {r2.value_per_share:.2f}"
    print("✓ FCFF 2-stage matches reference")

    print("── FCFF 3-stage (fcff3st.xls reference: equity/share ≈ 44.01) ──")
    r3 = fcff_3stage(
        revenues=12406, ebit=855, capex=233, depreciation=298,
        delta_wc=115, tax_rate=0.36,
        rev_growth_high=0.30, target_ebit_margin=0.30,
        current_ebit_margin=0.06892,
        n_high=5, n_transition=5,
        wacc_high=0.13375, wacc_stable=0.1255,
        g_stable=0.06, stable_roc=0.12,
        stable_ebit_margin=0.25,
        wc_pct_rev=0.075,
        debt_mv=0, cash=850, shares=1500, options_value=1500,
    )
    print_fcff_result(r3)
    assert abs(r3.value_per_share - 44.01) < 6, f"Got {r3.value_per_share:.2f}"
    print("✓ FCFF 3-stage matches reference")

    print("── FCFE Stable (fcfest.xls reference: equity value ≈ 40.97/share) ──")
    r4 = fcfe_stable(
        net_income=5.45, capex=2.0, depreciation=1.747,
        delta_wc=0.6, debt_ratio=0.2997,
        ke=0.1305, g=0.06, roe=0.12,
        cash=0, shares=1,
    )
    print_fcfe_result(r4)
    assert abs(r4.value_per_share - 40.97) < 1, f"Got {r4.value_per_share:.2f}"
    print("✓ FCFE stable matches reference")

    print("── FCFE 2-stage (fcfeginzu.xls reference: value/share ≈ 18.92) ──")
    r5 = fcfe_2stage(
        net_income=437.405,          # non-cash NI (excl. interest on cash)
        capex=315.5, depreciation=255.5,
        delta_wc=106, debt_ratio=0.209,
        ke_high=0.09556, g_high=0.09783, n_high=10,
        g_stable=0.04, ke_stable=0.09556,
        roe_stable=0.10,
        roe_high=0.32591,
        cash=398.8, shares=398.03, options_value=0,
    )
    print_fcfe_result(r5)
    assert abs(r5.value_per_share - 18.92) < 4, f"Got {r5.value_per_share:.2f}"
    print("✓ FCFE 2-stage matches reference")

    print("\nAll tests passed ✓")
