"""
cost_of_capital.py
==================
Damodaran Investment Valuation — Chapter 7–8 implementation.

Source files analysed:
  ratings.xls       — three ICR→rating tables (large, small, financial firms)
  levbeta.xls       — Hamada unlever/relever + CAPM
  wacccalc.xls      — book debt → market debt PV; WACC; multi-country ERP
  capstru.xlsx      — confirmed spreads & indirect bankruptcy cost schedule

Spread table last verified: wacccalc.xls / capstru.xlsx (updated Jan 2026 vintage).

Public API
----------
synthetic_rating(ebit, interest_expense, firm_type=1)
cost_of_debt(ebit, interest_expense, rf, tax_rate, country_spread=0.0, firm_type=1)
market_value_of_debt(book_debt, interest_expense, kd_pretax, avg_maturity)
unlever_beta(beta_l, de_ratio, tax_rate)
relever_beta(beta_u, target_de, tax_rate)
cost_of_equity_capm(rf, beta, erp)
compute_wacc(ke, kd_pretax, tax_rate, equity_mv, debt_mv)
full_cost_of_capital(...)   — one-call pipeline
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# RATINGS TABLES
# ─────────────────────────────────────────────────────────────────────────────
# Three tables exactly as in wacccalc.xls / ratings.xls / capstru.xlsx.
# Each entry: (icr_lo, icr_hi, rating, default_spread)
# Spreads sourced from the Jan-2026 vintage of wacccalc.xls.
#
# Key differences from old 2002 table:
#   • Large-firm Aaa/AAA spread = 0.40% (was 0.75%)
#   • Three tables, not one: large manufacturing, small/risky, financial-service
#   • Band boundaries differ between large and small tables
#   • D2/D spread = 19% in all three tables
# ─────────────────────────────────────────────────────────────────────────────

# Table 1 — Large manufacturing / technology / consumer firms
_LARGE_FIRM: list[tuple[float, float, str, float]] = [
    (8.50,  math.inf, "Aaa/AAA", 0.0040),
    (6.50,  8.4999,   "Aa2/AA",  0.0055),
    (5.50,  6.4999,   "A1/A+",   0.0070),
    (4.25,  5.4999,   "A2/A",    0.0078),
    (3.00,  4.2499,   "A3/A-",   0.0089),
    (2.50,  2.9999,   "Baa2/BBB",0.0111),
    (2.25,  2.4999,   "Ba1/BB+", 0.0138),
    (2.00,  2.2499,   "Ba2/BB",  0.0184),
    (1.75,  1.9999,   "B1/B+",   0.0275),
    (1.50,  1.7499,   "B2/B",    0.0321),
    (1.25,  1.4999,   "B3/B-",   0.0509),
    (0.80,  1.2499,   "Caa/CCC", 0.0885),
    (0.65,  0.7999,   "Ca2/CC",  0.1261),
    (0.20,  0.6499,   "C2/C",    0.1600),
    (-math.inf, 0.1999, "D2/D",  0.1900),
]

# Table 2 — Small / riskier firms (compressed bands, same spread scale)
_SMALL_FIRM: list[tuple[float, float, str, float]] = [
    (12.50, math.inf, "Aaa/AAA", 0.0040),
    (9.50,  12.4999,  "Aa2/AA",  0.0055),
    (7.50,  9.4999,   "A1/A+",   0.0070),
    (6.00,  7.4999,   "A2/A",    0.0078),
    (4.50,  5.9999,   "A3/A-",   0.0089),
    (4.00,  4.4999,   "Baa2/BBB",0.0111),
    (3.50,  3.9999,   "Ba1/BB+", 0.0138),
    (3.00,  3.4999,   "Ba2/BB",  0.0184),
    (2.50,  2.9999,   "B1/B+",   0.0275),
    (2.00,  2.4999,   "B2/B",    0.0321),
    (1.50,  1.9999,   "B3/B-",   0.0509),
    (1.25,  1.4999,   "C2/C",    0.0885),
    (0.80,  1.2499,   "Ca2/CC",  0.1261),
    (0.50,  0.7999,   "Caa/CCC", 0.1600),
    (-math.inf, 0.4999, "D2/D",  0.1900),
]

# Table 3 — Financial service firms (uses long-term interest coverage ratio)
_FINANCIAL_FIRM: list[tuple[float, float, str, float]] = [
    (3.00,  math.inf, "Aaa/AAA", 0.0040),
    (2.50,  2.9999,   "Aa2/AA",  0.0055),
    (2.00,  2.4999,   "A1/A+",   0.0070),
    (1.50,  1.9999,   "A2/A",    0.0078),
    (1.20,  1.4999,   "A3/A-",   0.0089),
    (0.90,  1.1999,   "Baa2/BBB",0.0111),
    (0.75,  0.8999,   "Ba1/BB+", 0.0138),
    (0.60,  0.7499,   "Ba2/BB",  0.0184),
    (0.50,  0.5999,   "B1/B+",   0.0275),
    (0.40,  0.4999,   "B2/B",    0.0321),
    (0.30,  0.3999,   "B3/B-",   0.0509),
    (0.20,  0.2999,   "Caa/CCC", 0.0885),
    (0.10,  0.1999,   "Ca2/CC",  0.1261),
    (0.05,  0.0999,   "C2/C",    0.1600),
    (-math.inf, 0.0499, "D2/D",  0.1900),
]

# Map firm_type code → table
_TABLES = {1: _LARGE_FIRM, 2: _SMALL_FIRM, 3: _FINANCIAL_FIRM}
_TABLE_NAMES = {1: "Large firm", 2: "Small/risky firm", 3: "Financial service firm"}


# ─────────────────────────────────────────────────────────────────────────────
# Data-classes for structured results
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DebtCostResult:
    firm_type: int
    icr: float
    rating: str
    company_spread: float
    country_spread: float
    total_spread: float
    rf: float
    kd_pretax: float
    tax_rate: float
    kd_aftertax: float


@dataclass
class BetaResult:
    beta_levered_input: float
    current_de: float
    tax_rate: float
    beta_unlevered: float
    target_de: float
    beta_relevered: float
    rf: float
    erp: float
    ke: float


@dataclass
class WACCResult:
    ke: float
    kd_pretax: float
    kd_aftertax: float
    tax_rate: float
    equity_mv: float
    debt_mv: float
    total_capital: float
    weight_equity: float
    weight_debt: float
    wacc: float


@dataclass
class FullCostOfCapitalResult:
    debt_cost: DebtCostResult
    beta_result: BetaResult
    market_debt: float
    wacc_result: WACCResult


# ─────────────────────────────────────────────────────────────────────────────
# ratings.xls  — synthetic rating
# ─────────────────────────────────────────────────────────────────────────────

def synthetic_rating(
    ebit: float,
    interest_expense: float,
    firm_type: int = 1,
) -> tuple[str, float]:
    """
    Look up synthetic credit rating from interest coverage ratio.

    Parameters
    ----------
    ebit             : EBIT (add back operating lease expense if relevant)
    interest_expense : Annual interest expense (long-term only for fin. firms)
    firm_type        : 1 = large manufacturing/tech  (default)
                       2 = small / riskier firm
                       3 = financial service firm

    Returns
    -------
    (rating_string, default_spread)
    """
    if interest_expense <= 0:
        icr = math.inf
    else:
        icr = ebit / interest_expense

    table = _TABLES.get(firm_type, _LARGE_FIRM)
    for (lo, hi, rating, spread) in table:
        if lo <= icr < hi:
            return rating, spread

    return "D2/D", 0.19   # fallback (negative ICR below lowest band)


def cost_of_debt(
    ebit: float,
    interest_expense: float,
    rf: float,
    tax_rate: float,
    country_spread: float = 0.0,
    firm_type: int = 1,
) -> DebtCostResult:
    """
    Damodaran Ch 8: synthetic rating → cost of debt.

    kd_pretax = rf + company_default_spread + country_spread
    kd_aftertax = kd_pretax × (1 − tax_rate)

    Parameters
    ----------
    ebit             : EBIT (adjusted for leases/R&D if applicable)
    interest_expense : Annual interest expense
    rf               : Risk-free rate (10-yr govt bond)
    tax_rate         : Marginal corporate tax rate
    country_spread   : Country default spread (from wacccalc country ERP sheet)
                       Set to 0 for US firms.
    firm_type        : 1, 2, or 3 (see synthetic_rating docstring)
    """
    if interest_expense <= 0:
        icr = math.inf
    else:
        icr = ebit / interest_expense

    rating, company_spread = synthetic_rating(ebit, interest_expense, firm_type)
    total_spread = company_spread + country_spread
    kd_pretax    = rf + total_spread
    kd_aftertax  = kd_pretax * (1 - tax_rate)

    return DebtCostResult(
        firm_type=firm_type,
        icr=icr,
        rating=rating,
        company_spread=company_spread,
        country_spread=country_spread,
        total_spread=total_spread,
        rf=rf,
        kd_pretax=kd_pretax,
        tax_rate=tax_rate,
        kd_aftertax=kd_aftertax,
    )


# ─────────────────────────────────────────────────────────────────────────────
# wacccalc.xls  — book debt → market value
# ─────────────────────────────────────────────────────────────────────────────

def market_value_of_debt(
    book_debt: float,
    interest_expense: float,
    kd_pretax: float,
    avg_maturity: float,
) -> float:
    """
    Treat all debt as a single coupon bond; compute present value.

    PV = coupon × [1 − (1+kd)^−n] / kd  +  face / (1+kd)^n

    where coupon = interest_expense, face = book_debt, n = avg_maturity.

    If kd_pretax is 0 or maturity is 0, returns book_debt unchanged.
    """
    if kd_pretax <= 0 or avg_maturity <= 0:
        return book_debt
    n = avg_maturity
    pv_coupons = interest_expense * (1 - (1 + kd_pretax) ** (-n)) / kd_pretax
    pv_face    = book_debt / (1 + kd_pretax) ** n
    return pv_coupons + pv_face


# ─────────────────────────────────────────────────────────────────────────────
# levbeta.xls  — Hamada equation
# ─────────────────────────────────────────────────────────────────────────────

def unlever_beta(beta_l: float, de_ratio: float, tax_rate: float) -> float:
    """
    Hamada equation — strip financial leverage from observed beta.

    β_u = β_L / [1 + (1 − t) × (D/E)]

    Damodaran assumes β_debt = 0 (all systematic risk in equity).
    D/E is market-value ratio.
    """
    return beta_l / (1 + (1 - tax_rate) * de_ratio)


def relever_beta(beta_u: float, target_de: float, tax_rate: float) -> float:
    """
    Re-apply financial leverage for a target D/E ratio.

    β_L = β_u × [1 + (1 − t) × (D/E)_target]
    """
    return beta_u * (1 + (1 - tax_rate) * target_de)


def blume_adjust(beta: float) -> float:
    """
    Blume (1975) mean-reversion adjustment toward 1.0.
    Used in levbeta.xls 'current beta' output column.

    β_adj = 0.33 + 0.67 × β
    """
    return 0.33 + 0.67 * beta


def cost_of_equity_capm(rf: float, beta: float, erp: float) -> float:
    """
    CAPM cost of equity.

    ke = rf + β × ERP

    Parameters
    ----------
    rf   : Risk-free rate (10-yr govt bond)
    beta : Levered beta (after re-levering if needed)
    erp  : Equity risk premium (Damodaran implied, country-adjusted)
    """
    return rf + beta * erp


def compute_beta_and_ke(
    beta_l: float,
    current_de: float,
    tax_rate: float,
    target_de: float,
    rf: float,
    erp: float,
) -> BetaResult:
    """
    Full levbeta.xls workflow: unlever → re-lever at target D/E → ke via CAPM.

    Parameters
    ----------
    beta_l     : Observed levered beta (regression or industry bottom-up)
    current_de : Current market-value D/E ratio (for unlevering)
    tax_rate   : Marginal tax rate
    target_de  : Target D/E ratio for re-levering (use current_de if unchanged)
    rf         : Risk-free rate
    erp        : Equity risk premium
    """
    beta_u  = unlever_beta(beta_l, current_de, tax_rate)
    beta_rl = relever_beta(beta_u, target_de, tax_rate)
    ke      = cost_of_equity_capm(rf, beta_rl, erp)
    return BetaResult(
        beta_levered_input=beta_l,
        current_de=current_de,
        tax_rate=tax_rate,
        beta_unlevered=beta_u,
        target_de=target_de,
        beta_relevered=beta_rl,
        rf=rf,
        erp=erp,
        ke=ke,
    )


# ─────────────────────────────────────────────────────────────────────────────
# wacccalc.xls  — WACC
# ─────────────────────────────────────────────────────────────────────────────

def compute_wacc(
    ke: float,
    kd_pretax: float,
    tax_rate: float,
    equity_mv: float,
    debt_mv: float,
) -> WACCResult:
    """
    WACC = ke × (E/V) + kd × (1−t) × (D/V)

    Always uses market-value weights (Damodaran's insistence).
    Preferred stock excluded; add separately if needed.
    """
    v = equity_mv + debt_mv
    if v <= 0:
        raise ValueError("equity_mv + debt_mv must be positive")
    we      = equity_mv / v
    wd      = debt_mv   / v
    kd_at   = kd_pretax * (1 - tax_rate)
    wacc    = ke * we + kd_at * wd

    return WACCResult(
        ke=ke,
        kd_pretax=kd_pretax,
        kd_aftertax=kd_at,
        tax_rate=tax_rate,
        equity_mv=equity_mv,
        debt_mv=debt_mv,
        total_capital=v,
        weight_equity=we,
        weight_debt=wd,
        wacc=wacc,
    )


# ─────────────────────────────────────────────────────────────────────────────
# oplease.xls  — operating lease capitalisation
# ─────────────────────────────────────────────────────────────────────────────

def capitalise_operating_leases(
    lease_commitments: list[float],
    current_lease_expense: float,
    kd_pretax: float,
) -> dict:
    """
    Convert operating lease commitments to a debt equivalent.

    Parameters
    ----------
    lease_commitments    : [yr1, yr2, yr3, yr4, yr5, beyond_total]
                           'beyond' is the lump sum from footnotes.
    current_lease_expense: Operating lease expense in the current year.
    kd_pretax            : Pre-tax cost of debt (discount rate).

    Returns
    -------
    dict with keys:
      debt_value_of_leases    : PV of all commitments
      years_beyond            : Implied years in the 'beyond' bucket
      adjusted_ebit_addback   : current_lease_expense − depreciation
      depreciation_on_asset   : straight-line depreciation on PV asset
    """
    if len(lease_commitments) < 6:
        raise ValueError("Need 6 commitments: years 1–5 + beyond lump sum")

    yr1, yr2, yr3, yr4, yr5, beyond = lease_commitments

    # Estimate years embedded in 'beyond' bucket using avg of years 1–5
    avg_annual = sum([yr1, yr2, yr3, yr4, yr5]) / 5 if any([yr1,yr2,yr3,yr4,yr5]) else current_lease_expense
    years_beyond = round(beyond / avg_annual) if avg_annual > 0 else 0

    # Annual equivalent of 'beyond'
    beyond_annual = beyond / years_beyond if years_beyond > 0 else 0

    # PV of years 1–5
    yearly_pvs = []
    for t, c in enumerate([yr1, yr2, yr3, yr4, yr5], 1):
        yearly_pvs.append(c / (1 + kd_pretax) ** t)

    # PV of the 'beyond' annuity (starts at year 6)
    if years_beyond > 0 and kd_pretax > 0:
        # PV at year 5 of annuity, then discount back 5 years
        pv_at_5 = beyond_annual * (1 - (1 + kd_pretax) ** (-years_beyond)) / kd_pretax
        pv_beyond = pv_at_5 / (1 + kd_pretax) ** 5
    else:
        pv_beyond = beyond / (1 + kd_pretax) ** 6

    debt_value = sum(yearly_pvs) + pv_beyond

    # Straight-line depreciation on the lease asset
    total_life = 5 + years_beyond
    depreciation = debt_value / total_life if total_life > 0 else debt_value

    # EBIT adjustment: add back lease expense, subtract depreciation
    adjusted_ebit_addback = current_lease_expense - depreciation

    return {
        "debt_value_of_leases": debt_value,
        "yearly_pvs": yearly_pvs,
        "pv_beyond": pv_beyond,
        "years_beyond": years_beyond,
        "depreciation_on_asset": depreciation,
        "adjusted_ebit_addback": adjusted_ebit_addback,  # add to EBIT
    }


# ─────────────────────────────────────────────────────────────────────────────
# RDConv.xls  — R&D capitalisation
# ─────────────────────────────────────────────────────────────────────────────

# Amortisable life lookup (from RDConv.xls lookup table)
RD_AMORTIZATION_LIFE: dict[str, int] = {
    "Advertising": 2, "Aerospace/Defense": 10, "Air Transport": 10,
    "Apparel": 3, "Auto & Truck": 10, "Auto Parts (OEM)": 5,
    "Auto Parts (Replacement)": 5, "Bank": 2, "Beverage (Alcoholic)": 3,
    "Beverage (Soft Drink)": 3, "Building Materials": 5, "Cable TV": 10,
    "Chemical (Basic)": 10, "Chemical (Diversified)": 10,
    "Chemical (Specialty)": 10, "Coal/Alternate Energy": 5,
    "Computer & Peripherals": 5, "Computer Software & Svcs": 3,
    "Drug": 10, "Drugstore": 3, "Educational Services": 3,
    "Electrical Equipment": 10, "Electronics": 5, "Entertainment": 3,
    "Environmental": 5, "Financial Services": 2, "Food Processing": 3,
    "Food Wholesalers": 3, "Healthcare Info Systems": 3, "Home Appliance": 5,
    "Homebuilding": 5, "Hotel/Gaming": 3, "Household Products": 3,
    "Industrial Services": 3, "Internet": 3, "Machinery": 10,
    "Medical Services": 3, "Medical Supplies": 5, "Metal Fabricating": 10,
    "Natural Gas (Distrib.)": 10, "Newspaper": 3, "Oilfield Services/Equip.": 5,
    "Packaging & Container": 5, "Paper & Forest Products": 10,
    "Petroleum (Integrated)": 5, "Petroleum (Producing)": 5,
    "Publishing": 3, "R.E.I.T.": 3, "Railroad": 5, "Recreation": 5,
    "Restaurant": 2, "Retail (Special Lines)": 2, "Retail Building Supply": 2,
    "Retail Store": 2, "Semiconductor": 5, "Semiconductor Cap Equip": 5,
    "Shoe": 3, "Steel (General)": 5, "Steel (Integrated)": 5,
    "Telecom. Equipment": 10, "Telecom. Services": 5,
    "Tobacco": 5, "Trucking/Transp. Leasing": 5, "Water Utility": 10,
}


def capitalise_rd(
    rd_history: list[float],
    amortization_life: int,
    current_ebit: float,
    current_net_income: float,
    book_equity: float,
    book_debt: float,
    current_capex: float,
    current_depreciation: float,
) -> dict:
    """
    Convert R&D from operating expense to capital asset.

    Parameters
    ----------
    rd_history           : R&D spending, from most-recent backward.
                           rd_history[0] = current year, [1] = -1yr, etc.
                           Length should equal amortization_life + 1 at most.
    amortization_life    : Years over which R&D is amortised (from lookup table)
    current_ebit         : Reported EBIT (before R&D capitalisation)
    current_net_income   : Reported net income
    book_equity          : Book value of equity
    book_debt            : Book value of debt
    current_capex        : Reported capex
    current_depreciation : Reported depreciation

    Returns
    -------
    dict with before/after comparison and adjustment amounts
    """
    n = amortization_life
    history = rd_history[:n + 1]   # current + up to n prior years

    current_rd = history[0] if history else 0

    # Build asset: unamortised portion of each past year
    rd_asset = 0.0
    amortization_this_year = 0.0
    for i, rd in enumerate(history):
        unamortised_pct = max(0, 1 - i / n)
        rd_asset += rd * unamortised_pct
        if i > 0:                        # prior years contribute amortisation
            amortization_this_year += rd / n

    # Adjustments
    adj_ebit           = current_ebit + current_rd - amortization_this_year
    adj_net_income     = current_net_income + current_rd - amortization_this_year
    adj_book_equity    = book_equity + rd_asset
    adj_invested_capital = book_equity + book_debt + rd_asset
    adj_capex          = current_capex + current_rd
    adj_depreciation   = current_depreciation + amortization_this_year

    return {
        "rd_asset":                rd_asset,
        "amortization_this_year":  amortization_this_year,
        "adjustment_to_ebit":      current_rd - amortization_this_year,
        # Before capitalisation
        "ebit_before":             current_ebit,
        "net_income_before":       current_net_income,
        "book_equity_before":      book_equity,
        "invested_capital_before": book_equity + book_debt,
        "capex_before":            current_capex,
        "depreciation_before":     current_depreciation,
        # After capitalisation
        "ebit_after":              adj_ebit,
        "net_income_after":        adj_net_income,
        "book_equity_after":       adj_book_equity,
        "invested_capital_after":  adj_invested_capital,
        "capex_after":             adj_capex,
        "depreciation_after":      adj_depreciation,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Convenience wrapper — full pipeline
# ─────────────────────────────────────────────────────────────────────────────

def full_cost_of_capital(
    # ── Financials ──────────────────────────────────────────────────────────
    ebit: float,
    interest_expense: float,
    book_debt: float,
    avg_debt_maturity: float,
    equity_market_cap: float,
    # ── Beta ────────────────────────────────────────────────────────────────
    beta_levered: float,
    # ── Market rates ────────────────────────────────────────────────────────
    rf: float,
    erp: float,
    tax_rate: float,
    # ── Optional ────────────────────────────────────────────────────────────
    country_spread: float = 0.0,
    firm_type: int = 1,
    target_de_ratio: Optional[float] = None,
) -> FullCostOfCapitalResult:
    """
    Complete ratings → levbeta → wacccalc pipeline in one call.

    Pipeline
    --------
    1. synthetic_rating(ebit, interest, firm_type) → company spread
    2. kd_pretax = rf + company_spread + country_spread
    3. market_value_of_debt(book_debt, interest, kd, maturity) → debt_mv
    4. current D/E = debt_mv / equity_mv
    5. unlever_beta → re-lever at target D/E → ke = rf + β × erp
    6. WACC = ke × (E/V) + kd × (1−t) × (D/V)

    Parameters
    ----------
    ebit               : EBIT (pre-lease/R&D adjustments if applicable)
    interest_expense   : Annual interest expense
    book_debt          : Book value of total debt
    avg_debt_maturity  : Weighted average maturity (years)
    equity_market_cap  : Market cap (shares × price)
    beta_levered       : Observed or bottom-up levered beta
    rf                 : Risk-free rate (10-yr govt bond yield)
    erp                : Equity risk premium (country-adjusted if needed)
    tax_rate           : Marginal corporate tax rate
    country_spread     : Country default spread (0 for US)
    firm_type          : 1 = large, 2 = small/risky, 3 = financial
    target_de_ratio    : Target D/E for re-levering (defaults to current)
    """
    # Step 1 + 2: cost of debt
    dc = cost_of_debt(ebit, interest_expense, rf, tax_rate, country_spread, firm_type)

    # Step 3: market value of debt
    debt_mv = market_value_of_debt(book_debt, interest_expense, dc.kd_pretax, avg_debt_maturity)

    # Step 4: D/E
    current_de = debt_mv / equity_market_cap if equity_market_cap > 0 else 0.0
    tgt_de = target_de_ratio if target_de_ratio is not None else current_de

    # Step 5: beta → ke
    br = compute_beta_and_ke(beta_levered, current_de, tax_rate, tgt_de, rf, erp)

    # Step 6: WACC
    wr = compute_wacc(br.ke, dc.kd_pretax, tax_rate, equity_market_cap, debt_mv)

    return FullCostOfCapitalResult(
        debt_cost=dc,
        beta_result=br,
        market_debt=debt_mv,
        wacc_result=wr,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Optimal capital structure helper  (capstru.xlsx logic)
# ─────────────────────────────────────────────────────────────────────────────

def optimal_capital_structure(
    ebit: float,
    ebitda: float,
    beta_unlevered: float,
    rf: float,
    erp: float,
    tax_rate: float,
    firm_value_current: float,
    reinvestment_rate: float,
    stable_growth: float,
    firm_type: int = 1,
    debt_ratios: Optional[list[float]] = None,
) -> list[dict]:
    """
    Sweep debt ratios 0–90%; find WACC-minimising / value-maximising point.

    At each debt ratio d:
      1. Dollar debt = d × firm_value
      2. Interest = dollar_debt × kd (kd from synthetic rating at that level)
      3. Pro-forma ICR = EBIT / interest → new rating → new kd
      4. Re-lever unlevered beta → new ke → new WACC
      5. Firm value = EBIT*(1-t)*(1-RIR) / WACC  (perpetuity with stable growth)

    Returns list of dicts, one per debt ratio tested.
    """
    if debt_ratios is None:
        debt_ratios = [d / 10 for d in range(10)]   # 0%, 10%, …, 90%

    results = []
    for d in debt_ratios:
        e = 1 - d
        dollar_debt = d * firm_value_current

        # Estimate interest at this debt level using current cost of debt
        # (iterate once: use current kd to estimate ICR, get new rating)
        if dollar_debt > 0:
            # seed interest from current rf + medium spread
            seed_kd = rf + 0.02
            interest_est = dollar_debt * seed_kd
            _, spread = synthetic_rating(ebit, interest_est, firm_type)
            kd = rf + spread
            interest_actual = dollar_debt * kd
            # one more iteration for accuracy
            _, spread2 = synthetic_rating(ebit, interest_actual, firm_type)
            kd = rf + spread2
        else:
            kd     = rf + 0.004   # AAA
            spread = 0.004

        # After-tax cost of debt
        de_ratio = d / e if e > 0 else math.inf
        kd_at    = kd * (1 - tax_rate)

        # Re-lever beta
        beta_l = relever_beta(beta_unlevered, de_ratio if e > 0 else 999, tax_rate)
        ke = cost_of_equity_capm(rf, beta_l, erp)

        # WACC
        wacc = ke * e + kd_at * d if e > 0 else kd_at

        # Firm value (Gordon perpetuity: FCFF / (WACC - g))
        fcff_stable = ebit * (1 - tax_rate) * (1 - reinvestment_rate)
        firm_value  = fcff_stable / (wacc - stable_growth) if wacc > stable_growth else math.inf

        results.append({
            "debt_ratio":   d,
            "equity_ratio": e,
            "dollar_debt":  dollar_debt,
            "beta_levered": beta_l,
            "ke":           ke,
            "kd_pretax":    kd,
            "kd_aftertax":  kd_at,
            "wacc":         wacc,
            "firm_value":   firm_value,
        })

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Pretty-print
# ─────────────────────────────────────────────────────────────────────────────

def print_cost_of_capital(result: FullCostOfCapitalResult) -> None:
    dc = result.debt_cost
    br = result.beta_result
    wr = result.wacc_result

    tname = _TABLE_NAMES.get(dc.firm_type, "Unknown")
    print("\n" + "=" * 58)
    print("  COST OF CAPITAL  —  Damodaran Method  (Jan-2026 spreads)")
    print("=" * 58)

    print(f"\n── Step 1: Synthetic Rating  [{tname}] ──")
    print(f"  Interest Coverage Ratio  {dc.icr:>8.2f}x")
    print(f"  Synthetic Rating         {dc.rating}")
    print(f"  Risk-free Rate           {dc.rf:.2%}")
    print(f"  Company Default Spread   {dc.company_spread:.2%}")
    if dc.country_spread:
        print(f"  Country Default Spread   {dc.country_spread:.2%}")
    print(f"  Pre-tax Cost of Debt     {dc.kd_pretax:.2%}")
    print(f"  After-tax Cost of Debt   {dc.kd_aftertax:.2%}  [t = {dc.tax_rate:.1%}]")

    print(f"\n── Step 2: Beta & Cost of Equity  (Hamada / CAPM) ──")
    print(f"  Input (Levered) Beta     {br.beta_levered_input:.3f}")
    print(f"  Current D/E              {br.current_de:.3f}")
    print(f"  Unlevered Beta           {br.beta_unlevered:.3f}")
    if abs(br.target_de - br.current_de) > 1e-6:
        print(f"  Target D/E               {br.target_de:.3f}")
    print(f"  Re-levered Beta          {br.beta_relevered:.3f}")
    print(f"  Equity Risk Premium      {br.erp:.2%}")
    print(f"  Cost of Equity (CAPM)    {br.ke:.2%}")

    print(f"\n── Step 3: Market Value of Debt ──")
    print(f"  Market Value of Debt     ${result.market_debt:>12,.0f}")

    print(f"\n── Step 4: WACC ──")
    print(f"  Equity Weight            {wr.weight_equity:.1%}")
    print(f"  Debt Weight              {wr.weight_debt:.1%}")
    print(f"  WACC                     {wr.wacc:.2%}")
    print("=" * 58 + "\n")


# ─────────────────────────────────────────────────────────────────────────────
# Demo
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("── Example 1: Large US industrial ──────────────────────")
    r1 = full_cost_of_capital(
        ebit=1_500, interest_expense=300,
        book_debt=3_000, avg_debt_maturity=5,
        equity_market_cap=12_000,
        beta_levered=1.2, rf=0.045, erp=0.055,
        tax_rate=0.25, firm_type=1,
    )
    print_cost_of_capital(r1)

    print("── Example 2: Small/risky firm ─────────────────────────")
    r2 = full_cost_of_capital(
        ebit=200, interest_expense=120,
        book_debt=800, avg_debt_maturity=4,
        equity_market_cap=500,
        beta_levered=1.8, rf=0.045, erp=0.055,
        tax_rate=0.21, firm_type=2,
    )
    print_cost_of_capital(r2)

    print("── Example 3: EM firm with country spread ──────────────")
    r3 = full_cost_of_capital(
        ebit=900, interest_expense=150,
        book_debt=2_000, avg_debt_maturity=6,
        equity_market_cap=5_000,
        beta_levered=1.1, rf=0.045, erp=0.086,  # India ERP
        tax_rate=0.34, country_spread=0.022,      # India spread
        firm_type=1,
    )
    print_cost_of_capital(r3)

    print("── Example 4: Operating lease capitalisation ───────────")
    lease = capitalise_operating_leases(
        lease_commitments=[156, 150, 145, 143, 140, 600],
        current_lease_expense=180,
        kd_pretax=0.035,
    )
    print(f"  Debt value of leases  : ${lease['debt_value_of_leases']:,.0f}")
    print(f"  EBIT addback          : ${lease['adjusted_ebit_addback']:,.0f}")
    print(f"  Depreciation on asset : ${lease['depreciation_on_asset']:,.0f}")

    print("\n── Example 5: R&D capitalisation (pharma, 10-yr life) ──")
    rd = capitalise_rd(
        rd_history=[4755, 4434, 4819, 4207, 4116, 3737, 3562, 3840, 4006, 4248, 4083],
        amortization_life=10,
        current_ebit=7231, current_net_income=3763,
        book_equity=5022, book_debt=64020,
        current_capex=998, current_depreciation=863,
    )
    print(f"  R&D asset             : ${rd['rd_asset']:,.0f}")
    print(f"  Amortisation yr       : ${rd['amortization_this_year']:,.0f}")
    print(f"  EBIT: {rd['ebit_before']:,.0f} → {rd['ebit_after']:,.0f}")
    print(f"  Invested capital: {rd['invested_capital_before']:,.0f} → {rd['invested_capital_after']:,.0f}")
