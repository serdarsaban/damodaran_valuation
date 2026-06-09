"""
optimal_capital_structure.py
============================
Damodaran Investment Valuation — Chapter 15 (Optimal Capital Structure)

Source: capstru.xlsx (Disney 2023 reference case)

Key features extracted from the actual spreadsheet:
  - Three rating tables (large / small-risky / infrastructure-utility)
  - Jan-2026 spreads (confirmed from Default Spreads and Ratios sheet)
  - Indirect bankruptcy cost haircuts by rating band (Drop in EBITDA column)
  - Interest deduction constraint: EBITDA × 30% cap (BEAT/thin-cap rules)
  - Unlevered beta → re-lever → ke at each debt ratio
  - Firm value = FCFF perpetuity at each WACC
  - Repurchase price worksheet: implied value per share after debt-for-equity swap

Reference case: Disney (Feb 2023)
  Current D/(D+E) = 19.66%, Optimal = 20.0%
  Current WACC = 9.567%, Optimal WACC = 9.521%
  Current EV = $216,465m, Optimal EV = $218,233m
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Rating tables with bankruptcy cost haircuts
# Sourced from capstru.xlsx → Default Spreads and Ratios sheet
# Tuple: (icr_lo, icr_hi, rating, spread, ebitda_drop)
# ebitda_drop: fraction by which EBITDA falls at this rating
#   (indirect bankruptcy cost — customers/suppliers reduce business)
# ─────────────────────────────────────────────────────────────────────────────

# Table 1 — Large non-financial firms
_LARGE: list[tuple] = [
    (8.50,  1e9,   "Aaa/AAA", 0.00400, 0.00),
    (6.50,  8.50,  "Aa2/AA",  0.00551, 0.00),
    (5.50,  6.50,  "A1/A+",   0.00700, 0.00),
    (4.25,  5.50,  "A2/A",    0.00775, 0.00),
    (3.00,  4.25,  "A3/A-",   0.00887, -0.02),
    (2.50,  3.00,  "Baa2/BBB",0.01111, -0.10),
    (2.25,  2.50,  "Ba1/BB+", 0.01383, -0.20),
    (2.00,  2.25,  "Ba2/BB",  0.01839, -0.20),
    (1.75,  2.00,  "B1/B+",   0.02753, -0.20),
    (1.50,  1.75,  "B2/B",    0.03210, -0.20),
    (1.25,  1.50,  "B3/B-",   0.05090, -0.25),
    (0.80,  1.25,  "Caa/CCC", 0.08850, -0.40),
    (0.65,  0.80,  "Ca2/CC",  0.12610, -0.40),
    (0.20,  0.65,  "C2/C",    0.16000, -0.40),
    (-1e9,  0.20,  "D2/D",    0.19000, -0.50),
]

# Table 2 — Small / riskier firms
_SMALL: list[tuple] = [
    (12.50, 1e9,   "Aaa/AAA", 0.00400, 0.00),
    (9.50,  12.50, "Aa2/AA",  0.00551, 0.00),
    (7.50,  9.50,  "A1/A+",   0.00700, 0.00),
    (6.00,  7.50,  "A2/A",    0.00775, 0.00),
    (4.50,  6.00,  "A3/A-",   0.00887, -0.02),
    (4.00,  4.50,  "Baa2/BBB",0.01111, -0.10),
    (3.50,  4.00,  "Ba1/BB+", 0.01383, -0.20),
    (3.00,  3.50,  "Ba2/BB",  0.01839, -0.20),
    (2.50,  3.00,  "B1/B+",   0.02753, -0.20),
    (2.00,  2.50,  "B2/B",    0.03210, -0.20),
    (1.50,  2.00,  "B3/B-",   0.05090, -0.25),
    (1.25,  1.50,  "Caa/CCC", 0.08850, -0.40),
    (0.80,  1.25,  "Ca2/CC",  0.12610, -0.40),
    (0.50,  0.80,  "C2/C",    0.16000, -0.40),
    (-1e9,  0.50,  "D2/D",    0.19000, -0.50),
]

# Table 3 — Infrastructure / utilities
_INFRA: list[tuple] = [
    (4.50,  1e9,   "Aaa/AAA", 0.00450, 0.00),
    (4.00,  4.50,  "Aa2/AA",  0.00600, 0.00),
    (3.50,  4.00,  "A1/A+",   0.00770, 0.00),
    (3.00,  3.50,  "A2/A",    0.00850, 0.00),
    (2.25,  3.00,  "A3/A-",   0.00950, -0.02),
    (2.00,  2.25,  "Baa2/BBB",0.01200, -0.10),
    (1.80,  2.00,  "Ba1/BB+", 0.01550, -0.20),
    (1.60,  1.80,  "Ba2/BB",  0.01830, -0.20),
    (1.40,  1.60,  "B1/B+",   0.02610, -0.20),
    (1.20,  1.40,  "B2/B",    0.03000, -0.20),
    (1.00,  1.20,  "B3/B-",   0.04420, -0.25),
    (0.75,  1.00,  "Caa/CCC", 0.07280, -0.40),
    (0.50,  0.75,  "Ca2/CC",  0.10100, -0.40),
    (0.20,  0.50,  "C2/C",    0.15500, -0.40),
    (-1e9,  0.20,  "D2/D",    0.19000, -0.50),
]

_TABLES = {1: _LARGE, 2: _SMALL, 3: _INFRA}
_TABLE_NAMES = {1: "Large non-financial", 2: "Small/risky", 3: "Infrastructure/utility"}


# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DebtRatioResult:
    debt_ratio: float           # D/(D+E) tested
    dollar_debt: float
    beta_levered: float
    ke: float
    icr: float                  # interest coverage ratio
    rating: str
    kd_pretax: float
    kd_aftertax: float
    ebitda_adjusted: float      # after indirect bankruptcy cost haircut
    ebit_adjusted: float
    tax_rate_effective: float   # may be lower if interest deduction limited
    wacc: float
    firm_value: float           # Gordon perpetuity at this WACC


@dataclass
class OptimalCapitalStructureResult:
    company: str
    # Summary
    current_debt_ratio: float
    optimal_debt_ratio: float
    current_wacc: float
    optimal_wacc: float
    current_firm_value: float
    optimal_firm_value: float
    value_gain: float
    # Repurchase analysis
    shares_outstanding: float
    current_price: float
    optimal_price_per_share: float
    new_debt_issued: float
    shares_repurchased: float
    # Full sweep
    sweep: list[DebtRatioResult]
    # Inputs
    inputs: dict = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Core functions
# ─────────────────────────────────────────────────────────────────────────────

def _lookup_rating(icr: float, firm_type: int) -> tuple[str, float, float]:
    """Return (rating, spread, ebitda_drop) for a given ICR."""
    table = _TABLES.get(firm_type, _LARGE)
    for (lo, hi, rating, spread, drop) in table:
        if lo <= icr < hi:
            return rating, spread, drop
    return "D2/D", 0.19, -0.50


def _effective_tax_rate(
    taxable_income: float,
    interest: float,
    ebitda: float,
    marginal_tax: float,
    interest_limit_pct: float,   # 0.30 for EBITDA cap (BEAT rules)
    apply_limit: bool = False,
) -> float:
    """
    Compute effective tax rate after interest deduction constraints.
    If interest > interest_limit_pct × EBITDA, the excess is non-deductible.
    Source: capstru.xlsx row 68 — 'Tax rate for debt tax benefits (Interest limit)'
    """
    if not apply_limit or interest_limit_pct <= 0:
        return marginal_tax
    max_deductible = interest_limit_pct * ebitda
    if interest <= max_deductible:
        return marginal_tax
    # Fraction of interest that IS deductible
    deductible_frac = max_deductible / interest if interest > 0 else 0
    return marginal_tax * deductible_frac


def optimal_capital_structure(
    # ── Core financials ─────────────────────────────────────────────────────
    ebitda: float,              # Current EBITDA (adjusted for leases if needed)
    depreciation: float,        # Current D&A
    ebit: float,                # = EBITDA - Depreciation (can differ if non-cash items)
    interest_expense: float,    # Current interest expense
    tax_rate: float,            # Marginal tax rate
    # ── Market data ─────────────────────────────────────────────────────────
    equity_mv: float,           # Current market cap
    debt_mv: float,             # Current market value of debt
    beta_levered: float,        # Current levered beta
    rf: float,                  # Risk-free rate
    erp: float,                 # Equity risk premium
    # ── Valuation anchor ────────────────────────────────────────────────────
    fcff: float,                # Current FCFF (for perpetuity firm value)
    g_stable: float,            # Stable growth rate
    # ── Options ─────────────────────────────────────────────────────────────
    firm_type: int = 1,
    apply_bankruptcy_costs: bool = True,
    apply_interest_limit: bool = False,
    interest_limit_pct: float = 0.30,
    # For repurchase analysis
    shares_outstanding: float = 0.0,
    current_price: float = 0.0,
    cash: float = 0.0,
    # Override current rating cost of debt (if known actual rate differs from synthetic)
    lock_current_kd: Optional[float] = None,
    company: str = "Company",
    debt_ratios: Optional[list[float]] = None,
) -> OptimalCapitalStructureResult:
    """
    Sweep debt ratios and find WACC-minimising / value-maximising capital structure.

    At each D/(D+E) ratio:
      1. Compute dollar debt and interest expense
      2. If indirect bankruptcy costs active: haircut EBITDA by rating-band drop
      3. Compute pro-forma ICR → synthetic rating → kd
      4. Apply interest deduction limit if active → effective tax rate
      5. Re-lever beta → ke → WACC
      6. Firm value = FCFF / (WACC − g)  [perpetuity with stable growth]

    Source: capstru.xlsx → Optimal CS Worksheet
    """
    if debt_ratios is None:
        debt_ratios = [d / 10 for d in range(11)]   # 0% to 100% in 10% steps

    # Always include the actual current debt ratio for accurate current WACC
    actual_current_dr = debt_mv / (equity_mv + debt_mv) if (equity_mv + debt_mv) > 0 else 0
    if not any(abs(d - actual_current_dr) < 0.001 for d in debt_ratios):
        debt_ratios = sorted(set(list(debt_ratios) + [actual_current_dr]))

    enterprise_value = equity_mv + debt_mv

    # Current unlevered beta
    current_de = debt_mv / equity_mv if equity_mv > 0 else 0
    beta_u = beta_levered / (1 + (1 - tax_rate) * current_de)

    # Adjusted EBITDA baseline (normalise for seasonality)
    ebitda_adjusted_base = ebitda

    # Use g_stable directly as perpetuity growth rate.
    # Using g_implied from EV/FCFF breaks for high-growth firms where
    # g_implied can exceed WACC at some debt ratios, giving infinite firm values.
    g_implied = g_stable

    sweep: list[DebtRatioResult] = []
    best_wacc = math.inf
    best_value = -math.inf

    for d in debt_ratios:
        e = 1.0 - d
        if e <= 0:
            continue

        dollar_debt = d * enterprise_value
        de_ratio    = d / e

        # ── Step 1: Estimate pro-forma interest ──────────────────────────
        # Seed with current kd to get first ICR estimate, then iterate once
        if lock_current_kd and d == (debt_mv / enterprise_value if enterprise_value > 0 else 0):
            kd_seed = lock_current_kd
        else:
            # Use rf + medium spread as seed
            kd_seed = rf + 0.015
        interest_proforma = dollar_debt * kd_seed

        # ── Step 2: Indirect bankruptcy costs ────────────────────────────
        if apply_bankruptcy_costs and interest_proforma > 0:
            icr_seed = ebit / interest_proforma if interest_proforma > 0 else 1e9
            _, _, drop = _lookup_rating(icr_seed, firm_type)
            ebitda_adj = ebitda_adjusted_base * (1 + drop)
            ebit_adj   = ebitda_adj - depreciation
        else:
            ebitda_adj = ebitda_adjusted_base
            ebit_adj   = ebit

        # ── Step 3: Actual ICR and rating ────────────────────────────────
        # Special case: zero debt → infinite ICR → best rating
        if dollar_debt == 0:
            icr_final = math.inf
            rating, spread, drop_actual = _LARGE[0][2], _LARGE[0][3], _LARGE[0][4]
            kd_pretax = rf + spread
        else:
            icr_actual = ebit_adj / interest_proforma if interest_proforma > 0 else 1e9
            rating, spread, drop_actual = _lookup_rating(icr_actual, firm_type)
            kd_pretax = rf + spread
            # One refinement iteration with actual kd
            interest_actual  = dollar_debt * kd_pretax
            icr_final        = ebit_adj / interest_actual if interest_actual > 0 else 1e9
            # Lock current kd at actual rate if this is the current debt ratio
            if lock_current_kd and abs(d - debt_mv/enterprise_value) < 0.01:
                kd_pretax = lock_current_kd
            else:
                rating, spread, drop_actual = _lookup_rating(icr_final, firm_type)
                kd_pretax = rf + spread

        if apply_bankruptcy_costs:
            ebitda_adj = ebitda_adjusted_base * (1 + drop_actual)
            ebit_adj   = ebitda_adj - depreciation

        # ── Step 4: Effective tax rate (interest deduction limit) ─────────
        t_eff = _effective_tax_rate(
            taxable_income=ebit_adj - dollar_debt * kd_pretax,
            interest=dollar_debt * kd_pretax,
            ebitda=ebitda_adj,
            marginal_tax=tax_rate,
            interest_limit_pct=interest_limit_pct,
            apply_limit=apply_interest_limit,
        )
        kd_aftertax = kd_pretax * (1 - t_eff)

        # ── Step 5: Beta and ke ───────────────────────────────────────────
        beta_l = beta_u * (1 + (1 - tax_rate) * de_ratio)
        ke     = rf + beta_l * erp

        # ── Step 6: WACC and firm value ───────────────────────────────────
        wacc = ke * e + kd_aftertax * d
        if wacc > g_implied:
            firm_val = fcff * (1 + g_implied) / (wacc - g_implied)
        else:
            firm_val = math.inf  # WACC ≤ g is degenerate

        sweep.append(DebtRatioResult(
            debt_ratio=d,
            dollar_debt=dollar_debt,
            beta_levered=beta_l,
            ke=ke,
            icr=icr_final,
            rating=rating,
            kd_pretax=kd_pretax,
            kd_aftertax=kd_aftertax,
            ebitda_adjusted=ebitda_adj,
            ebit_adjusted=ebit_adj,
            tax_rate_effective=t_eff,
            wacc=wacc,
            firm_value=firm_val,
        ))

    # ── Find optimal ──────────────────────────────────────────────────────────
    valid = [r for r in sweep if r.firm_value != math.inf]
    if not valid:
        raise ValueError("No valid debt ratios — check that WACC > g_stable for at least one ratio")

    optimal = max(valid, key=lambda r: r.firm_value)
    actual_dr = debt_mv / enterprise_value if enterprise_value > 0 else 0
    current_row = min(sweep, key=lambda r: abs(r.debt_ratio - actual_dr))

    # ── Repurchase analysis ───────────────────────────────────────────────────
    # At optimal: issue new debt → repurchase shares at current price
    # Remaining shares are worth more because EV rose
    new_debt = optimal.dollar_debt - debt_mv
    shares_repurchased = new_debt / current_price if current_price > 0 else 0
    shares_remaining   = shares_outstanding - shares_repurchased
    equity_at_optimal  = optimal.firm_value - optimal.dollar_debt + cash
    price_optimal      = equity_at_optimal / shares_remaining if shares_remaining > 0 else 0

    return OptimalCapitalStructureResult(
        company=company,
        current_debt_ratio=debt_mv / enterprise_value,
        optimal_debt_ratio=optimal.debt_ratio,
        current_wacc=current_row.wacc,
        optimal_wacc=optimal.wacc,
        current_firm_value=current_row.firm_value,
        optimal_firm_value=optimal.firm_value,
        value_gain=optimal.firm_value - current_row.firm_value,
        shares_outstanding=shares_outstanding,
        current_price=current_price,
        optimal_price_per_share=price_optimal,
        new_debt_issued=max(0, new_debt),
        shares_repurchased=max(0, shares_repurchased),
        sweep=sweep,
        inputs=dict(
            ebitda=ebitda, depreciation=depreciation, ebit=ebit,
            interest_expense=interest_expense, tax_rate=tax_rate,
            equity_mv=equity_mv, debt_mv=debt_mv,
            beta_levered=beta_levered, rf=rf, erp=erp,
            fcff=fcff, g_stable=g_stable,
            firm_type=firm_type,
            apply_bankruptcy_costs=apply_bankruptcy_costs,
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Self-test — Disney 2023 reference case from capstru.xlsx
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("── Disney 2023 — capstru.xlsx reference case ──────────────")
    # All values from the Inputs and Optimal CS Worksheet sheets
    result = optimal_capital_structure(
        ebitda=11_767,
        depreciation=5_200,
        ebit=6_567,
        interest_expense=1_653,
        tax_rate=0.25,
        equity_mv=183_230,
        debt_mv=44_850,
        beta_levered=1.02,
        rf=0.039,
        erp=0.0661,
        fcff=4_812.25,
        g_stable=0.039,          # spreadsheet uses rf as stable growth
        firm_type=1,
        apply_bankruptcy_costs=False,   # Disney input: No indirect costs
        shares_outstanding=1_826.82,
        current_price=100.3,
        cash=11_615,
        company="Disney",
        debt_ratios=[d/10 for d in range(11)],
    )

    print(f"\n  Current D/(D+E):  {result.current_debt_ratio:.2%}   ref: 19.66%")
    print(f"  Optimal D/(D+E):  {result.optimal_debt_ratio:.2%}   ref: 20.0%")
    print(f"  Current WACC:     {result.current_wacc:.4%}  ref: 9.567%")
    print(f"  Optimal WACC:     {result.optimal_wacc:.4%}  ref: 9.521%")
    print(f"  Value gain:       ${result.value_gain:,.0f}m  ref: $1,768m")

    print(f"\n  Sweep:")
    print(f"  {'D/(D+E)':>8} {'Rating':>10} {'kd':>7} {'ke':>7} {'WACC':>8} {'Firm Value':>14}")
    print(f"  {'-'*60}")
    for r in result.sweep:
        marker = " ◀ optimal" if abs(r.debt_ratio - result.optimal_debt_ratio) < 0.01 else (
                 " ◀ current" if abs(r.debt_ratio - result.current_debt_ratio) < 0.02 else "")
        print(f"  {r.debt_ratio:>8.0%} {r.rating:>10} {r.kd_pretax:>7.2%} "
              f"{r.ke:>7.2%} {r.wacc:>8.4%} {r.firm_value:>14,.0f}{marker}")

    assert abs(result.optimal_debt_ratio - 0.20) < 0.05, "Optimal D/C mismatch"
    assert result.optimal_wacc < result.current_wacc, "Optimal WACC should be lower"
    print("\n✓ Disney reference case passed")
