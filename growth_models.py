"""
growth_models.py
================
Damodaran Investment Valuation — Chapters 11–12

Implements:
  - Three growth estimation approaches (Ch 11)
  - Terminal value models and consistency checks (Ch 12)
  - Industry benchmark distributions (from fcffsimpleginzu.xlsx)

Sources: chgrowth.xls, fcffsimpleginzu.xlsx (Input Stat Distributions sheet),
         fcffginzu.xlsx (Diagnostics sheet)
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Industry distribution data
# Extracted from fcffsimpleginzu.xlsx → Input Stat Distributions sheet
# Columns: industry, count, rev_g_q1, rev_g_med, rev_g_q3,
#          margin_q1, margin_med, margin_q3,
#          s2c_q1, s2c_med, s2c_q3,
#          wacc_q1, wacc_med, wacc_q3,
#          beta_q1, beta_med, beta_q3,
#          d2c_q1, d2c_med, d2c_q3
# ─────────────────────────────────────────────────────────────────────────────

INDUSTRY_DATA: dict[str, dict] = {
    "Advertising":              {"rev_g": (0.011, 0.059, 0.158), "margin": (-0.066, 0.037, 0.098), "s2c": (0.964, 2.408, 6.030), "wacc": (0.088, 0.093, 0.095), "beta": (0.560, 1.138, 1.835), "d2c": (0.016, 0.116, 0.347)},
    "Aerospace/Defense":        {"rev_g": (0.080, 0.143, 0.284), "margin": (-0.029, 0.066, 0.106), "s2c": (1.175, 2.167, 3.870), "wacc": (0.083, 0.087, 0.090), "beta": (0.492, 0.918, 1.432), "d2c": (0.022, 0.148, 0.370)},
    "Air Transport":             {"rev_g": (0.035, 0.063, 0.104), "margin": (0.017, 0.045, 0.074), "s2c": (0.778, 1.271, 2.009), "wacc": (0.079, 0.087, 0.096), "beta": (0.567, 1.017, 1.629), "d2c": (0.093, 0.310, 0.553)},
    "Auto & Truck":              {"rev_g": (0.016, 0.067, 0.186), "margin": (-0.223, 0.023, 0.068), "s2c": (0.747, 1.580, 3.428), "wacc": (0.083, 0.093, 0.103), "beta": (0.475, 0.959, 1.680), "d2c": (0.035, 0.184, 0.433)},
    "Bank (Money Center)":       {"rev_g": (0.028, 0.056, 0.110), "margin": (0.000, 0.000, 0.000), "s2c": (0.000, 0.000, 0.000), "wacc": (0.080, 0.088, 0.097), "beta": (0.484, 0.880, 1.336), "d2c": (0.000, 0.000, 0.000)},
    "Beverage (Alcoholic)":      {"rev_g": (-0.011, 0.023, 0.057), "margin": (0.017, 0.079, 0.152), "s2c": (0.513, 0.945, 1.746), "wacc": (0.083, 0.089, 0.096), "beta": (0.375, 0.726, 1.181), "d2c": (0.023, 0.162, 0.381)},
    "Beverage (Soft)":           {"rev_g": (0.027, 0.055, 0.122), "margin": (0.010, 0.101, 0.185), "s2c": (0.760, 1.576, 2.850), "wacc": (0.083, 0.088, 0.093), "beta": (0.369, 0.734, 1.178), "d2c": (0.019, 0.147, 0.361)},
    "Business & Consumer Svcs":  {"rev_g": (0.023, 0.068, 0.133), "margin": (-0.004, 0.051, 0.107), "s2c": (0.949, 2.013, 4.291), "wacc": (0.086, 0.092, 0.098), "beta": (0.483, 0.965, 1.567), "d2c": (0.010, 0.121, 0.333)},
    "Chemical (Basic)":          {"rev_g": (0.019, 0.081, 0.162), "margin": (0.000, 0.044, 0.093), "s2c": (0.694, 1.385, 2.590), "wacc": (0.085, 0.092, 0.099), "beta": (0.502, 0.987, 1.611), "d2c": (0.026, 0.194, 0.432)},
    "Chemical (Specialty)":      {"rev_g": (0.026, 0.086, 0.156), "margin": (0.009, 0.072, 0.134), "s2c": (0.745, 1.558, 3.032), "wacc": (0.085, 0.091, 0.097), "beta": (0.480, 0.940, 1.524), "d2c": (0.019, 0.152, 0.373)},
    "Computer Services":         {"rev_g": (0.042, 0.082, 0.144), "margin": (0.001, 0.059, 0.120), "s2c": (1.084, 2.485, 5.873), "wacc": (0.086, 0.092, 0.098), "beta": (0.507, 1.001, 1.616), "d2c": (0.007, 0.099, 0.297)},
    "Computers/Peripherals":     {"rev_g": (0.042, 0.125, 0.265), "margin": (-0.024, 0.063, 0.149), "s2c": (1.025, 2.428, 6.167), "wacc": (0.086, 0.093, 0.101), "beta": (0.537, 1.077, 1.747), "d2c": (0.007, 0.099, 0.302)},
    "Drugs (Biotechnology)":     {"rev_g": (0.002, 0.153, 0.542), "margin": (-6.605, -0.277, 0.133), "s2c": (0.366, 1.422, 5.090), "wacc": (0.087, 0.095, 0.105), "beta": (0.554, 1.118, 1.843), "d2c": (0.006, 0.090, 0.306)},
    "Drugs (Pharmaceutical)":    {"rev_g": (0.039, 0.104, 0.189), "margin": (-0.141, 0.074, 0.193), "s2c": (0.662, 1.836, 5.177), "wacc": (0.084, 0.090, 0.098), "beta": (0.445, 0.865, 1.385), "d2c": (0.012, 0.135, 0.365)},
    "Electrical Equipment":      {"rev_g": (0.066, 0.158, 0.273), "margin": (-0.041, 0.063, 0.135), "s2c": (0.854, 1.910, 4.199), "wacc": (0.085, 0.092, 0.100), "beta": (0.491, 0.981, 1.603), "d2c": (0.012, 0.125, 0.340)},
    "Electronics (General)":     {"rev_g": (0.055, 0.123, 0.251), "margin": (-0.052, 0.058, 0.139), "s2c": (0.809, 1.894, 4.391), "wacc": (0.085, 0.092, 0.100), "beta": (0.502, 1.005, 1.638), "d2c": (0.013, 0.129, 0.349)},
    "Engineering/Construction":  {"rev_g": (0.032, 0.080, 0.156), "margin": (0.007, 0.049, 0.095), "s2c": (1.117, 2.420, 5.319), "wacc": (0.085, 0.091, 0.098), "beta": (0.505, 0.990, 1.604), "d2c": (0.016, 0.147, 0.366)},
    "Entertainment":             {"rev_g": (0.026, 0.074, 0.176), "margin": (-0.233, 0.042, 0.121), "s2c": (0.593, 1.361, 3.216), "wacc": (0.085, 0.091, 0.099), "beta": (0.483, 0.968, 1.572), "d2c": (0.013, 0.139, 0.381)},
    "Food Processing":           {"rev_g": (0.020, 0.054, 0.115), "margin": (0.014, 0.071, 0.131), "s2c": (0.672, 1.324, 2.524), "wacc": (0.083, 0.088, 0.094), "beta": (0.409, 0.790, 1.264), "d2c": (0.025, 0.176, 0.398)},
    "Food Wholesalers":          {"rev_g": (0.028, 0.044, 0.077), "margin": (0.005, 0.022, 0.048), "s2c": (1.786, 3.593, 7.576), "wacc": (0.083, 0.088, 0.093), "beta": (0.388, 0.749, 1.194), "d2c": (0.021, 0.145, 0.339)},
    "Healthcare Products":       {"rev_g": (0.045, 0.110, 0.233), "margin": (-0.531, 0.066, 0.172), "s2c": (0.614, 1.656, 4.555), "wacc": (0.085, 0.091, 0.099), "beta": (0.466, 0.926, 1.499), "d2c": (0.011, 0.130, 0.363)},
    "Healthcare Support Svcs":   {"rev_g": (0.032, 0.068, 0.149), "margin": (-0.026, 0.048, 0.109), "s2c": (0.957, 2.076, 4.639), "wacc": (0.084, 0.090, 0.097), "beta": (0.459, 0.903, 1.455), "d2c": (0.018, 0.164, 0.406)},
    "Homebuilding":              {"rev_g": (-0.008, 0.056, 0.114), "margin": (0.014, 0.074, 0.126), "s2c": (0.489, 0.814, 1.317), "wacc": (0.083, 0.089, 0.096), "beta": (0.468, 0.909, 1.451), "d2c": (0.027, 0.192, 0.433)},
    "Hotel/Gaming":              {"rev_g": (0.033, 0.072, 0.125), "margin": (0.000, 0.084, 0.162), "s2c": (0.335, 0.660, 1.193), "wacc": (0.083, 0.090, 0.098), "beta": (0.452, 0.915, 1.504), "d2c": (0.033, 0.254, 0.530)},
    "Household Products":        {"rev_g": (0.015, 0.059, 0.135), "margin": (-0.017, 0.071, 0.149), "s2c": (0.691, 1.446, 2.879), "wacc": (0.082, 0.088, 0.094), "beta": (0.398, 0.779, 1.248), "d2c": (0.018, 0.149, 0.369)},
    "Machinery":                 {"rev_g": (0.031, 0.080, 0.161), "margin": (0.000, 0.074, 0.139), "s2c": (0.772, 1.581, 3.079), "wacc": (0.084, 0.090, 0.097), "beta": (0.479, 0.943, 1.527), "d2c": (0.018, 0.148, 0.366)},
    "Metals & Mining":           {"rev_g": (0.061, 0.124, 0.236), "margin": (0.000, 0.078, 0.199), "s2c": (0.300, 0.680, 1.670), "wacc": (0.086, 0.093, 0.103), "beta": (0.535, 1.071, 1.757), "d2c": (0.024, 0.202, 0.482)},
    "Oil/Gas (Production)":      {"rev_g": (-0.044, 0.048, 0.233), "margin": (-0.328, 0.104, 0.302), "s2c": (0.237, 0.545, 1.260), "wacc": (0.085, 0.093, 0.103), "beta": (0.499, 1.009, 1.667), "d2c": (0.030, 0.218, 0.493)},
    "Packaging & Container":     {"rev_g": (0.002, 0.057, 0.104), "margin": (0.014, 0.072, 0.124), "s2c": (0.774, 1.450, 2.595), "wacc": (0.083, 0.089, 0.095), "beta": (0.450, 0.882, 1.404), "d2c": (0.035, 0.230, 0.479)},
    "Power":                     {"rev_g": (-0.004, 0.036, 0.079), "margin": (0.055, 0.123, 0.210), "s2c": (0.233, 0.452, 0.779), "wacc": (0.079, 0.085, 0.092), "beta": (0.317, 0.637, 1.038), "d2c": (0.124, 0.384, 0.591)},
    "Publishing & Newspapers":   {"rev_g": (-0.006, 0.034, 0.059), "margin": (-0.051, 0.057, 0.129), "s2c": (0.620, 1.340, 2.786), "wacc": (0.084, 0.090, 0.097), "beta": (0.445, 0.887, 1.434), "d2c": (0.023, 0.178, 0.425)},
    "R.E.I.T.":                  {"rev_g": (-0.012, 0.030, 0.087), "margin": (0.186, 0.413, 0.656), "s2c": (0.133, 0.239, 0.408), "wacc": (0.078, 0.083, 0.089), "beta": (0.295, 0.589, 0.959), "d2c": (0.133, 0.385, 0.580)},
    "Restaurant/Dining":         {"rev_g": (0.036, 0.075, 0.130), "margin": (-0.004, 0.073, 0.140), "s2c": (0.575, 1.125, 2.075), "wacc": (0.083, 0.089, 0.096), "beta": (0.447, 0.882, 1.416), "d2c": (0.021, 0.183, 0.437)},
    "Retail (General)":          {"rev_g": (0.028, 0.063, 0.104), "margin": (0.003, 0.043, 0.088), "s2c": (1.099, 2.217, 4.436), "wacc": (0.083, 0.089, 0.096), "beta": (0.461, 0.909, 1.463), "d2c": (0.016, 0.148, 0.379)},
    "Semiconductor":             {"rev_g": (0.074, 0.180, 0.322), "margin": (-0.150, 0.116, 0.265), "s2c": (0.687, 1.695, 4.227), "wacc": (0.086, 0.094, 0.103), "beta": (0.561, 1.130, 1.848), "d2c": (0.008, 0.107, 0.321)},
    "Software (Entertainment)":  {"rev_g": (0.048, 0.127, 0.269), "margin": (-0.192, 0.092, 0.251), "s2c": (0.957, 2.620, 7.706), "wacc": (0.086, 0.093, 0.101), "beta": (0.533, 1.071, 1.749), "d2c": (0.006, 0.088, 0.283)},
    "Steel (General)":           {"rev_g": (0.017, 0.082, 0.201), "margin": (0.000, 0.054, 0.117), "s2c": (0.516, 1.106, 2.296), "wacc": (0.084, 0.092, 0.101), "beta": (0.498, 1.002, 1.650), "d2c": (0.024, 0.185, 0.434)},
    "Telecom (Wireless)":        {"rev_g": (0.025, 0.079, 0.172), "margin": (-0.116, 0.078, 0.194), "s2c": (0.275, 0.581, 1.218), "wacc": (0.082, 0.089, 0.097), "beta": (0.440, 0.888, 1.450), "d2c": (0.047, 0.285, 0.565)},
    "Telecom. Services":         {"rev_g": (0.012, 0.057, 0.134), "margin": (-0.023, 0.094, 0.208), "s2c": (0.302, 0.637, 1.297), "wacc": (0.081, 0.087, 0.095), "beta": (0.397, 0.795, 1.296), "d2c": (0.052, 0.290, 0.560)},
}

INDUSTRY_NAMES = sorted(INDUSTRY_DATA.keys())


# ─────────────────────────────────────────────────────────────────────────────
# Result types
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class GrowthResult:
    # Historical growth
    historical_eps_cagr:   Optional[float]
    historical_rev_cagr:   Optional[float]
    # Analyst estimate
    analyst_growth:        Optional[float]
    # Fundamental — FCFF (firm-based)
    roc:                   float
    reinvestment_rate:     float
    fundamental_growth_firm: float
    # Fundamental — FCFE (equity-based)
    roe:                   float
    retention_ratio:       float
    fundamental_growth_equity: float
    # Blended recommendation
    recommended_growth:    float
    recommended_basis:     str
    # Industry context
    industry:              Optional[str]
    industry_rev_g_median: Optional[float]


@dataclass
class TerminalValueResult:
    # Inputs
    fcff_or_fcfe_final_year: float
    discount_rate: float          # WACC or ke
    g_stable: float
    # Computed
    terminal_value: float
    # Consistency checks
    checks: dict
    # Sensitivity table: {(g, wacc): terminal_value}
    sensitivity: dict


# ─────────────────────────────────────────────────────────────────────────────
# Chapter 11 — Growth estimation
# ─────────────────────────────────────────────────────────────────────────────

def historical_growth(
    values: list[float],
    method: str = "geometric",
) -> Optional[float]:
    """
    Compute historical growth rate from a time series.

    Parameters
    ----------
    values : list of annual values (oldest first), minimum 2 values
    method : "geometric" (CAGR, preferred) or "arithmetic" (simple average)

    Returns
    -------
    Annual growth rate, or None if cannot be computed.

    Damodaran preference: geometric mean for volatile series.
    Arithmetic mean overstates expected growth when returns are volatile.
    Source: Ch 11, p.271
    """
    values = [v for v in values if v is not None]
    if len(values) < 2:
        return None

    if method == "geometric":
        # CAGR: (end/start)^(1/n) - 1
        start, end = values[0], values[-1]
        n = len(values) - 1
        if start <= 0 or end <= 0:
            return None
        return (end / start) ** (1 / n) - 1

    else:  # arithmetic
        rates = [(values[i] / values[i-1]) - 1
                 for i in range(1, len(values))
                 if values[i-1] != 0]
        return sum(rates) / len(rates) if rates else None


def fundamental_growth_firm(
    ebit: float,
    tax_rate: float,
    net_capex: float,
    delta_wc: float,
    book_equity: float,
    book_debt: float,
) -> tuple[float, float, float]:
    """
    Fundamental growth for FCFF models: g = ROC × Reinvestment_Rate

    ROC = NOPAT / Invested_Capital
    Reinvestment_Rate = (Net_CapEx + ΔWC) / NOPAT

    Returns: (roc, reinvestment_rate, g)
    Source: Damodaran, Ch 11, p.278
    """
    nopat = ebit * (1 - tax_rate)
    invested_capital = book_equity + book_debt
    roc = nopat / invested_capital if invested_capital > 0 else 0
    reinvestment = net_capex + delta_wc
    rir = reinvestment / nopat if nopat > 0 else 0
    g = roc * rir
    return roc, rir, g


def fundamental_growth_equity(
    net_income: float,
    dividends: float,
    book_equity: float,
) -> tuple[float, float, float]:
    """
    Fundamental growth for FCFE/DDM models: g = ROE × Retention_Ratio

    ROE = Net_Income / Book_Equity
    Retention_Ratio = (Net_Income - Dividends) / Net_Income = 1 - Payout

    Returns: (roe, retention_ratio, g)
    Source: Damodaran, Ch 11, p.276
    """
    roe = net_income / book_equity if book_equity > 0 else 0
    retention = (net_income - dividends) / net_income if net_income > 0 else 0
    retention = max(0, min(1, retention))
    g = roe * retention
    return roe, retention, g


def blended_growth(
    historical_cagr: Optional[float],
    analyst_estimate: Optional[float],
    fundamental: float,
    weights: tuple[float, float, float] = (0.25, 0.50, 0.25),
) -> tuple[float, str]:
    """
    Blend three growth estimates with weights.
    Default: 25% historical, 50% analyst (if available), 25% fundamental.
    If no analyst estimate: 40% historical, 60% fundamental.

    Source: Damodaran, Ch 11, p.284 — recommends weighting toward
    analyst estimates in the near term, fundamentals for long term.
    """
    avail = []
    labels = []

    if historical_cagr is not None and analyst_estimate is not None:
        w_hist, w_anal, w_fund = weights
        blended = w_hist * historical_cagr + w_anal * analyst_estimate + w_fund * fundamental
        basis = f"{w_hist:.0%} historical + {w_anal:.0%} analyst + {w_fund:.0%} fundamental"
    elif historical_cagr is not None:
        blended = 0.40 * historical_cagr + 0.60 * fundamental
        basis = "40% historical + 60% fundamental (no analyst estimate)"
    elif analyst_estimate is not None:
        blended = 0.60 * analyst_estimate + 0.40 * fundamental
        basis = "60% analyst + 40% fundamental (no historical)"
    else:
        blended = fundamental
        basis = "100% fundamental (only estimate available)"

    return blended, basis


def estimate_growth(
    # Fundamentals
    ebit: float,
    tax_rate: float,
    net_capex: float,
    delta_wc: float,
    book_equity: float,
    book_debt: float,
    net_income: float,
    dividends: float,
    # Historical series (optional)
    historical_eps: Optional[list[float]] = None,
    historical_rev: Optional[list[float]] = None,
    # Analyst estimate (optional)
    analyst_growth: Optional[float] = None,
    # Industry context
    industry: Optional[str] = None,
) -> GrowthResult:
    """
    Full Ch 11 growth estimation: all three approaches + blend.
    """
    # Historical
    hist_eps = historical_growth(historical_eps) if historical_eps else None
    hist_rev = historical_growth(historical_rev) if historical_rev else None
    hist = hist_eps if hist_eps is not None else hist_rev

    # Fundamental — firm
    roc, rir, g_firm = fundamental_growth_firm(ebit, tax_rate, net_capex, delta_wc,
                                                book_equity, book_debt)
    # Fundamental — equity
    roe, retention, g_equity = fundamental_growth_equity(net_income, dividends, book_equity)

    # Blend (use firm-based fundamental as primary)
    g_blend, basis = blended_growth(hist, analyst_growth, g_firm)

    # Industry context
    ind_med = None
    if industry and industry in INDUSTRY_DATA:
        ind_med = INDUSTRY_DATA[industry]["rev_g"][1]  # median

    return GrowthResult(
        historical_eps_cagr=hist_eps,
        historical_rev_cagr=hist_rev,
        analyst_growth=analyst_growth,
        roc=roc,
        reinvestment_rate=rir,
        fundamental_growth_firm=g_firm,
        roe=roe,
        retention_ratio=retention,
        fundamental_growth_equity=g_equity,
        recommended_growth=g_blend,
        recommended_basis=basis,
        industry=industry,
        industry_rev_g_median=ind_med,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Chapter 12 — Terminal value
# ─────────────────────────────────────────────────────────────────────────────

def terminal_value_gordon(
    cash_flow_final_year: float,
    discount_rate: float,
    g_stable: float,
    stable_roc: Optional[float] = None,
    tax_rate: float = 0.25,
) -> TerminalValueResult:
    """
    Gordon Growth Model terminal value.

    TV = CF_{n+1} / (r - g)

    If stable_roc is provided, reinvestment in the terminal year is derived
    from fundamentals: RIR = g/ROC, CF_{n+1} = NOPAT_{n+1} × (1 - g/ROC)

    Parameters
    ----------
    cash_flow_final_year : FCFF or FCFE in the final explicit forecast year
    discount_rate        : WACC (FCFF) or ke (FCFE)
    g_stable             : Perpetual growth rate
    stable_roc           : If provided, used to compute fundamental RIR
    tax_rate             : Used only if stable_roc provided (FCFF context)

    Source: Damodaran, Ch 12, p.303
    """
    if discount_rate <= g_stable:
        raise ValueError(f"Discount rate ({discount_rate:.2%}) must exceed g_stable ({g_stable:.2%})")

    # Terminal year cash flow
    if stable_roc is not None and stable_roc > 0:
        rir_stable = g_stable / stable_roc
        cf_terminal = cash_flow_final_year * (1 + g_stable) * (1 - rir_stable)
    else:
        cf_terminal = cash_flow_final_year * (1 + g_stable)

    tv = cf_terminal / (discount_rate - g_stable)

    # Consistency checks
    checks = run_terminal_value_checks(g_stable, discount_rate, stable_roc)

    # Sensitivity table: g from -1% to +1% around g_stable, r from -1% to +1% around discount_rate
    sensitivity = {}
    g_range = [g_stable + dg for dg in (-0.02, -0.01, 0, 0.01, 0.02)]
    r_range  = [discount_rate + dr for dr in (-0.02, -0.01, 0, 0.01, 0.02)]
    for g in g_range:
        for r in r_range:
            if r > g:
                if stable_roc and stable_roc > 0:
                    rir = g / stable_roc
                    cf = cash_flow_final_year * (1 + g) * (1 - rir)
                else:
                    cf = cash_flow_final_year * (1 + g)
                sensitivity[(round(g, 4), round(r, 4))] = cf / (r - g)
            else:
                sensitivity[(round(g, 4), round(r, 4))] = None

    return TerminalValueResult(
        fcff_or_fcfe_final_year=cash_flow_final_year,
        discount_rate=discount_rate,
        g_stable=g_stable,
        terminal_value=tv,
        checks=checks,
        sensitivity=sensitivity,
    )


def run_terminal_value_checks(
    g_stable: float,
    discount_rate: float,
    stable_roc: Optional[float] = None,
    rf: float = 0.045,
    gdp_growth: float = 0.025,  # long-run real GDP + inflation
) -> dict:
    """
    Damodaran's consistency checklist for terminal value assumptions.
    Source: Ch 12, p.307 — "What can go wrong with terminal value"
    """
    checks = {}

    # 1. g_stable ≤ risk-free rate (nominal GDP growth proxy)
    checks["g_le_rf"] = {
        "pass": g_stable <= rf,
        "label": "g ≤ risk-free rate",
        "detail": f"g = {g_stable:.2%}, rf = {rf:.2%}. " +
                  ("✓ Consistent — stable growth cannot exceed the long-run risk-free rate." if g_stable <= rf
                   else "✗ Problem — a firm cannot grow faster than the economy in perpetuity."),
    }

    # 2. g_stable ≤ nominal GDP growth (stricter check)
    checks["g_le_gdp"] = {
        "pass": g_stable <= gdp_growth + 0.02,  # allow some buffer
        "label": "g reasonable vs GDP growth",
        "detail": f"Long-run nominal GDP ≈ {gdp_growth:.1%}–{gdp_growth+0.02:.1%}. " +
                  ("✓ Reasonable." if g_stable <= gdp_growth + 0.02
                   else f"✗ g = {g_stable:.2%} implies the firm eventually becomes larger than the economy."),
    }

    # 3. ROC in stable period should converge toward WACC
    if stable_roc is not None:
        excess_return = stable_roc - discount_rate
        checks["roc_vs_wacc"] = {
            "pass": abs(excess_return) < 0.04,
            "label": "ROC ≈ WACC in stable period",
            "detail": (f"Stable ROC = {stable_roc:.2%}, WACC = {discount_rate:.2%}, "
                      f"excess return = {excess_return:+.2%}. " +
                      ("✓ Consistent — competition erodes excess returns over time." if abs(excess_return) < 0.04
                       else ("✗ ROC >> WACC: firm creates value indefinitely — only possible with durable competitive advantage."
                             if excess_return > 0.04
                             else "✗ ROC << WACC: firm destroys value indefinitely — consider whether operations would be wound down."))),
        }

    # 4. Discount rate in stable period should reflect mature firm risk
    checks["wacc_stable_reasonable"] = {
        "pass": 0.06 <= discount_rate <= 0.14,
        "label": "Discount rate in reasonable range for stable firm",
        "detail": (f"Stable discount rate = {discount_rate:.2%}. " +
                  ("✓ In the 6–14% range typical for mature firms." if 0.06 <= discount_rate <= 0.14
                   else ("✗ Very low — check if beta and ERP have been adjusted down appropriately."
                         if discount_rate < 0.06
                         else "✗ Very high — a stable firm typically has lower risk than the high-growth period."))),
    }

    return checks


# ─────────────────────────────────────────────────────────────────────────────
# Industry benchmarking helper
# ─────────────────────────────────────────────────────────────────────────────

def benchmark_vs_industry(
    industry: str,
    rev_growth: float,
    ebit_margin: float,
    sales_to_capital: float,
    wacc: float,
) -> dict:
    """
    Compare firm inputs against industry quartile distribution.
    Returns a dict of {metric: {value, q1, median, q3, percentile_label}}

    Source: fcffsimpleginzu.xlsx → Input Stat Distributions sheet
    """
    if industry not in INDUSTRY_DATA:
        return {}

    d = INDUSTRY_DATA[industry]

    def percentile_label(val, q1, med, q3):
        if val < q1:   return "bottom quartile"
        elif val < med: return "2nd quartile"
        elif val < q3:  return "3rd quartile"
        else:           return "top quartile"

    rg = d["rev_g"]
    mg = d["margin"]
    s2c = d["s2c"]
    wc  = d["wacc"]

    return {
        "revenue_growth": {
            "value": rev_growth, "q1": rg[0], "median": rg[1], "q3": rg[2],
            "position": percentile_label(rev_growth, *rg),
        },
        "ebit_margin": {
            "value": ebit_margin, "q1": mg[0], "median": mg[1], "q3": mg[2],
            "position": percentile_label(ebit_margin, *mg),
        },
        "sales_to_capital": {
            "value": sales_to_capital, "q1": s2c[0], "median": s2c[1], "q3": s2c[2],
            "position": percentile_label(sales_to_capital, *s2c),
        },
        "wacc": {
            "value": wacc, "q1": wc[0], "median": wc[1], "q3": wc[2],
            "position": percentile_label(wacc, *wc),
        },
    }


if __name__ == "__main__":
    print("── Growth estimation ───────────────────────────────")
    g = estimate_growth(
        ebit=5186, tax_rate=0.285, net_capex=924, delta_wc=499,
        book_equity=12000, book_debt=1822, net_income=3200, dividends=800,
        historical_eps=[2.1, 2.4, 2.8, 3.1, 3.6],
        analyst_growth=0.12, industry="Food Processing",
    )
    print(f"  ROC:              {g.roc:.2%}")
    print(f"  Reinvestment rate:{g.reinvestment_rate:.2%}")
    print(f"  Fundamental g:    {g.fundamental_growth_firm:.2%}")
    print(f"  Historical EPS:   {g.historical_eps_cagr:.2%}" if g.historical_eps_cagr else "  Historical: N/A")
    print(f"  Analyst:          {g.analyst_growth:.2%}" if g.analyst_growth else "  Analyst: N/A")
    print(f"  Recommended:      {g.recommended_growth:.2%} ({g.recommended_basis})")
    print(f"  Industry median:  {g.industry_rev_g_median:.2%}" if g.industry_rev_g_median else "")

    print("\n── Terminal value consistency checks ───────────────")
    tv = terminal_value_gordon(
        cash_flow_final_year=8288, discount_rate=0.096,
        g_stable=0.04, stable_roc=0.12,
    )
    print(f"  Terminal value: ${tv.terminal_value:,.0f}")
    for k, v in tv.checks.items():
        status = "✓" if v["pass"] else "✗"
        print(f"  {status} {v['label']}: {v['detail'][:80]}")

    print("\n── Industry benchmark ───────────────────────────────")
    bm = benchmark_vs_industry("Food Processing", 0.08, 0.14, 1.8, 0.088)
    for metric, data in bm.items():
        print(f"  {metric}: {data['value']:.2%} — {data['position']} "
              f"(Q1:{data['q1']:.2%} / Med:{data['median']:.2%} / Q3:{data['q3']:.2%})")
