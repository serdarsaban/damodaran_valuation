"""
data_fetcher.py
===============
Data layer for the Damodaran Valuation Toolkit.

Priority order:
  1. SEC EDGAR XBRL API  — all financial statement data (free, no key, 10 req/s)
  2. FRED                — risk-free rate / 10-yr Treasury (free, API key optional)
  3. yfinance            — price, market cap, beta ONLY (3 fields, retry on throttle)
  4. Damodaran industry  — beta fallback from wacccalc.xls Industry Averages (Jan 2026)
  5. User input          — price and market cap can be entered manually on home page
  6. Placeholder         — clearly flagged if all else fails

EDGAR covers:
  EBIT, interest, net income, revenue, depreciation, book debt, book equity,
  cash, total assets, capex, delta_wc, shares, EPS, tax rate

yfinance used only for:
  price (currentPrice), market_cap (marketCap), beta — with retry + fallback
"""

from __future__ import annotations
import math
import time
import json
import requests
from dataclasses import dataclass, field
from typing import Optional

try:
    import streamlit as st
    _IN_STREAMLIT = True
except ImportError:
    _IN_STREAMLIT = False
    class _FakeSS(dict): pass
    st = type("st", (), {"session_state": _FakeSS()})()


# ─────────────────────────────────────────────────────────────────────────────
# Damodaran Industry Beta Table
# Source: wacccalc.xls → Industry Averages (US) sheet (Jan 2026)
# Columns: unlevered_beta, levered_beta, tax_rate
# ─────────────────────────────────────────────────────────────────────────────

INDUSTRY_BETAS: dict[str, dict] = {
    "Advertising":                       {"unlevered": 0.8264, "levered": 1.1813, "tax": 0.3348},
    "Aerospace/Defense":                 {"unlevered": 1.0580, "levered": 1.1599, "tax": 0.2827},
    "Air Transport":                     {"unlevered": 0.6108, "levered": 0.9786, "tax": 0.1689},
    "Apparel":                           {"unlevered": 0.8600, "levered": 0.9927, "tax": 0.2809},
    "Auto & Truck":                      {"unlevered": 0.5901, "levered": 1.0950, "tax": 0.0621},
    "Auto Parts":                        {"unlevered": 1.1437, "levered": 1.3482, "tax": 0.2543},
    "Bank (Money Center)":               {"unlevered": 0.3377, "levered": 0.8068, "tax": 0.3066},
    "Banks (Regional)":                  {"unlevered": 0.3722, "levered": 0.5261, "tax": 0.2766},
    "Beverage (Alcoholic)":              {"unlevered": 0.8944, "levered": 1.0555, "tax": 0.2599},
    "Beverage (Soft)":                   {"unlevered": 0.9755, "levered": 1.1375, "tax": 0.2438},
    "Broadcasting":                      {"unlevered": 0.8334, "levered": 1.2962, "tax": 0.3110},
    "Brokerage & Investment Banking":    {"unlevered": 0.4114, "levered": 1.1595, "tax": 0.2782},
    "Building Materials":                {"unlevered": 0.9278, "levered": 1.1159, "tax": 0.2317},
    "Business & Consumer Services":      {"unlevered": 0.9963, "levered": 1.1938, "tax": 0.3562},
    "Cable TV":                          {"unlevered": 0.6955, "levered": 0.9130, "tax": 0.3420},
    "Chemical (Basic)":                  {"unlevered": 0.7528, "levered": 0.9351, "tax": 0.3210},
    "Chemical (Diversified)":            {"unlevered": 0.9872, "levered": 1.1728, "tax": 0.2586},
    "Chemical (Specialty)":              {"unlevered": 0.9128, "levered": 1.0259, "tax": 0.2758},
    "Computer Services":                 {"unlevered": 0.9858, "levered": 1.1596, "tax": 0.2031},
    "Computers/Peripherals":             {"unlevered": 1.1719, "levered": 1.2106, "tax": 0.2537},
    "Drugs (Biotechnology)":             {"unlevered": 1.0616, "levered": 1.1041, "tax": 0.2011},
    "Drugs (Pharmaceutical)":            {"unlevered": 0.9493, "levered": 1.0272, "tax": 0.1942},
    "Education":                         {"unlevered": 0.9468, "levered": 1.1274, "tax": 0.2981},
    "Electrical Equipment":              {"unlevered": 1.1429, "levered": 1.2377, "tax": 0.3177},
    "Electronics (Consumer & Office)":   {"unlevered": 1.3786, "levered": 1.3721, "tax": 0.2505},
    "Electronics (General)":             {"unlevered": 1.0143, "levered": 1.0278, "tax": 0.2675},
    "Engineering/Construction":          {"unlevered": 1.1910, "levered": 1.3073, "tax": 0.3458},
    "Entertainment":                     {"unlevered": 0.9861, "levered": 1.2057, "tax": 0.2915},
    "Environmental & Waste Services":    {"unlevered": 0.9416, "levered": 1.2844, "tax": 0.4282},
    "Farming/Agriculture":               {"unlevered": 0.5791, "levered": 0.8433, "tax": 0.3192},
    "Food Processing":                   {"unlevered": 0.8237, "levered": 0.9938, "tax": 0.3063},
    "Food Wholesalers":                  {"unlevered": 1.2573, "levered": 1.4130, "tax": 0.3678},
    "Green & Renewable Energy":          {"unlevered": 0.6763, "levered": 1.3197, "tax": 0.2438},
    "Healthcare Products":               {"unlevered": 0.9042, "levered": 0.9893, "tax": 0.2558},
    "Healthcare Support Services":       {"unlevered": 0.9078, "levered": 1.0538, "tax": 0.3853},
    "Healthcare Information Technology": {"unlevered": 0.8363, "levered": 0.9498, "tax": 0.2262},
    "Homebuilding":                      {"unlevered": 0.9204, "levered": 1.2865, "tax": 0.3135},
    "Hospitals/Healthcare Facilities":   {"unlevered": 0.5889, "levered": 0.9728, "tax": 0.2246},
    "Hotel/Gaming":                      {"unlevered": 0.8285, "levered": 1.1808, "tax": 0.1802},
    "Household Products":                {"unlevered": 0.9101, "levered": 1.0279, "tax": 0.2766},
    "Information Services":              {"unlevered": 1.0446, "levered": 1.1150, "tax": 0.3025},
    "Insurance (General)":               {"unlevered": 0.8039, "levered": 1.0293, "tax": 0.2645},
    "Insurance (Life)":                  {"unlevered": 0.7538, "levered": 1.0418, "tax": 0.2666},
    "Insurance (Prop/Cas.)":             {"unlevered": 0.6929, "levered": 0.8291, "tax": 0.2861},
    "Investments & Asset Management":    {"unlevered": 0.7287, "levered": 1.0982, "tax": 0.1587},
    "Machinery":                         {"unlevered": 1.1124, "levered": 1.2266, "tax": 0.2895},
    "Metals & Mining":                   {"unlevered": 0.9052, "levered": 1.2809, "tax": 0.3352},
    "Oil/Gas (Integrated)":              {"unlevered": 0.7643, "levered": 0.8078, "tax": 0.3764},
    "Oil/Gas (Production and Exploration)": {"unlevered": 0.9142, "levered": 1.2667, "tax": 0.4146},
    "Oil/Gas Distribution":              {"unlevered": 0.6690, "levered": 0.9642, "tax": 0.1753},
    "Oilfield Services/Equipment":       {"unlevered": 1.3188, "levered": 1.5433, "tax": 0.2868},
    "Packaging & Container":             {"unlevered": 0.6951, "levered": 0.9472, "tax": 0.2661},
    "Paper/Forest Products":             {"unlevered": 0.5950, "levered": 0.8355, "tax": 0.1943},
    "Power":                             {"unlevered": 0.5285, "levered": 0.8294, "tax": 0.3068},
    "Publishing & Newspapers":           {"unlevered": 0.8830, "levered": 1.1471, "tax": 0.1816},
    "R.E.I.T.":                          {"unlevered": 0.4266, "levered": 0.7860, "tax": 0.0223},
    "Real Estate (Development)":         {"unlevered": 0.8189, "levered": 1.0216, "tax": 0.6982},
    "Real Estate (General/Diversified)": {"unlevered": 1.4750, "levered": 1.8190, "tax": 0.2079},
    "Real Estate (Operations & Svcs)":   {"unlevered": 0.8949, "levered": 1.3023, "tax": 0.2241},
    "Recreation":                        {"unlevered": 0.9865, "levered": 1.2118, "tax": 0.2319},
    "Restaurant/Dining":                 {"unlevered": 0.7393, "levered": 0.8927, "tax": 0.3298},
    "Retail (Automotive)":               {"unlevered": 0.8463, "levered": 1.1754, "tax": 0.3653},
    "Retail (Building Supply)":          {"unlevered": 1.2904, "levered": 1.4423, "tax": 0.3706},
    "Retail (General)":                  {"unlevered": 0.8506, "levered": 1.0321, "tax": 0.3419},
    "Retail (Grocery and Food)":         {"unlevered": 0.7473, "levered": 1.0483, "tax": 0.3511},
    "Retail (Online)":                   {"unlevered": 1.3923, "levered": 1.3952, "tax": 0.2234},
    "Retail (Special Lines)":            {"unlevered": 0.8460, "levered": 1.0744, "tax": 0.3582},
    "Semiconductor":                     {"unlevered": 1.1684, "levered": 1.2145, "tax": 0.2175},
    "Semiconductor Equipment":           {"unlevered": 1.1738, "levered": 1.2331, "tax": 0.2029},
    "Software (Entertainment)":          {"unlevered": 1.1318, "levered": 1.1151, "tax": 0.1235},
    "Software (Internet)":               {"unlevered": 1.2936, "levered": 1.2862, "tax": 0.3506},
    "Software (System & Application)":   {"unlevered": 1.0611, "levered": 1.1039, "tax": 0.2252},
    "Steel":                             {"unlevered": 0.9037, "levered": 1.3130, "tax": 0.3032},
    "Telecom (Wireless)":                {"unlevered": 0.5087, "levered": 1.1501, "tax": 0.2178},
    "Telecom. Equipment":                {"unlevered": 1.1970, "levered": 1.2426, "tax": 0.1918},
    "Telecom. Services":                 {"unlevered": 0.6911, "levered": 1.0685, "tax": 0.3114},
    "Tobacco":                           {"unlevered": 0.9450, "levered": 1.0856, "tax": 0.3247},
    "Transportation":                    {"unlevered": 0.7652, "levered": 0.8571, "tax": 0.3584},
    "Transportation (Railroads)":        {"unlevered": 0.9200, "levered": 1.0476, "tax": 0.3699},
    "Trucking":                          {"unlevered": 0.9173, "levered": 1.3243, "tax": 0.3923},
    "Utility (General)":                 {"unlevered": 0.4191, "levered": 0.5924, "tax": 0.3127},
    "Utility (Water)":                   {"unlevered": 0.7663, "levered": 1.0855, "tax": 0.3171},
    "Total Market":                      {"unlevered": 0.7040, "levered": 1.0641, "tax": 0.2809},
}

INDUSTRY_NAMES_BETA = sorted(k for k in INDUSTRY_BETAS if k != "Total Market")


# ─────────────────────────────────────────────────────────────────────────────
# CompanyData
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CompanyData:
    ticker:             str
    name:               str
    ebit:               float
    interest_expense:   float
    net_income:         float
    revenue:            float
    ebitda:             float
    depreciation:       float
    book_debt:          float
    book_equity:        float
    cash:               float
    total_assets:       float
    capex:              float
    delta_wc:           float
    equity_market_cap:  float
    beta_levered:       float
    price:              float
    shares:             float
    eps:                float
    rf:                 float
    erp:                float
    tax_rate:           float
    country_spread:     float
    firm_type:          int
    avg_debt_maturity:  float
    source:                str
    fetch_errors:          list[str] = field(default_factory=list)
    historical_eps:        list[float] = field(default_factory=list)
    historical_revenue:    list[float] = field(default_factory=list)
    fcff:                  float = 0.0
    beta_source:           str = "yfinance"
    industry:              Optional[str] = None
    tax_rate_prior_year:   Optional[float] = None   # for anomaly detection
    tax_rate_anomaly:      bool = False              # True if rate swung >10pp


# ─────────────────────────────────────────────────────────────────────────────
# Placeholders
# ─────────────────────────────────────────────────────────────────────────────

PLACEHOLDERS: dict[str, dict] = {
    "AAPL": dict(name="Apple Inc.", ebit=115_000, interest_expense=3_900,
                 net_income=97_000, revenue=391_000, ebitda=130_000,
                 depreciation=11_100, book_debt=111_000, book_equity=62_000,
                 cash=65_000, total_assets=352_000, capex=10_700, delta_wc=1_200,
                 equity_market_cap=2_800_000, beta_levered=1.24, price=185.0,
                 shares=15_400, eps=6.13, tax_rate=0.15, avg_debt_maturity=5,
                 firm_type=1, erp=0.055, country_spread=0.0),
    "MSFT": dict(name="Microsoft Corp.", ebit=88_500, interest_expense=1_900,
                 net_income=72_000, revenue=212_000, ebitda=100_000,
                 depreciation=14_000, book_debt=60_000, book_equity=206_000,
                 cash=80_000, total_assets=411_000, capex=28_000, delta_wc=2_000,
                 equity_market_cap=3_100_000, beta_levered=0.90, price=415.0,
                 shares=7_430, eps=9.70, tax_rate=0.13, avg_debt_maturity=6,
                 firm_type=1, erp=0.055, country_spread=0.0),
    "META": dict(name="Meta Platforms, Inc.", ebit=87_097, interest_expense=1_165,
                 net_income=60_458, revenue=200_966, ebitda=105_713,
                 depreciation=18_616, book_debt=83_897, book_equity=217_243,
                 cash=35_873, total_assets=366_021, capex=69_691, delta_wc=885,
                 equity_market_cap=1_487_478, beta_levered=1.229, price=585.99,
                 shares=2_196, eps=27.51, tax_rate=0.2964, avg_debt_maturity=5,
                 firm_type=1, erp=0.055, country_spread=0.0),
}

def _make_placeholder(ticker: str) -> CompanyData:
    p = PLACEHOLDERS.get(ticker.upper(), dict(
        name=f"{ticker.upper()} (placeholder)",
        ebit=1_500, interest_expense=300, net_income=1_000, revenue=10_000,
        ebitda=2_000, depreciation=400, book_debt=3_000, book_equity=5_000,
        cash=500, total_assets=9_000, capex=550, delta_wc=160,
        equity_market_cap=12_000, beta_levered=1.2, price=50.0,
        shares=240, eps=4.0, tax_rate=0.25, avg_debt_maturity=5,
        firm_type=1, erp=0.055, country_spread=0.0,
    ))
    return CompanyData(ticker=ticker.upper(), source="placeholder", rf=0.045,
                       fcff=0.0, beta_source="placeholder", **p)


# ─────────────────────────────────────────────────────────────────────────────
# EDGAR XBRL — financial statement data
# ─────────────────────────────────────────────────────────────────────────────

EDGAR_BASE    = "https://data.sec.gov"
EDGAR_HEADERS = {"User-Agent": "DamodaranValuationApp research@damodaran.app"}

_CIK_CACHE: dict[str, str] = {
    "AAPL": "0000320193", "MSFT": "0000789019", "TSLA": "0001318605",
    "META": "0001326801", "AMZN": "0001018724", "GOOGL": "0001652044",
    "NVDA": "0001045810", "JPM":  "0000019617", "V":    "0001403161",
    "JNJ":  "0000200406", "WMT":  "0000104169", "XOM":  "0000034088",
    "BRK.B":"0001067983", "UNH":  "0000072971", "PG":   "0000080424",
    "MA":   "0001141391", "HD":   "0000354950", "ABBV": "0001551152",
    "CVX":  "0000093410", "MRK":  "0000310158", "LLY":  "0000059478",
    "ADBE": "0000796343", "CRM":  "0001108524", "ORCL": "0001341439",
    "NFLX": "0001065280", "INTC": "0000050863", "AMD":  "0000002488",
    "QCOM": "0000804328", "TXN":  "0000097476", "AVGO": "0001730168",
}

def _get_cik(ticker: str) -> Optional[str]:
    ticker = ticker.upper()
    if ticker in _CIK_CACHE:
        return _CIK_CACHE[ticker]
    try:
        # EDGAR company search API
        resp = requests.get(
            f"{EDGAR_BASE}/cgi-bin/browse-edgar",
            params={"action":"getcompany","ticker":ticker,"type":"10-K",
                    "dateb":"","owner":"include","count":"1","output":"atom"},
            headers=EDGAR_HEADERS, timeout=10,
        )
        import re
        m = re.search(r'CIK=(\d+)', resp.text)
        if m:
            cik = m.group(1).zfill(10)
            _CIK_CACHE[ticker] = cik
            return cik
    except Exception:
        pass
    return None

def _get_xbrl_fact(facts: dict, *concept_names: str, form: str = "10-K",
                   annual: bool = True) -> Optional[float]:
    """
    Return the most recent full-year value for any of the given XBRL concepts.

    Strategy (priority order):
    1. 10-K with fp="FY" — most reliable; prefer if available and more recent
       than the four-quarter sum.
    2. Sum of four most recent non-overlapping quarterly periods, each covering
       exactly ~3 months (start→end span 80–100 days). This is the TTM fallback
       for companies without a recent 10-K/FY record in EDGAR.

    The 80–100 day span filter is the key guard: it ensures we sum four genuine
    single quarters rather than any multi-quarter cumulative fact (e.g. a 9-month
    YTD value with fp=Q3 would span ~270 days and is excluded).
    """
    from datetime import datetime as _dt

    us_gaap = facts.get("us-gaap", {})
    ifrs    = facts.get("ifrs-full", {})

    for name in concept_names:
        for ns in [us_gaap, ifrs]:
            data  = ns.get(name, {})
            units = data.get("units", {}).get("USD", [])
            if not units:
                continue

            # ── Priority 1: 10-K with fp=FY ──────────────────────────────────
            fy = [x for x in units
                  if x.get("form") == "10-K"
                  and x.get("fp")   == "FY"
                  and x.get("val")  is not None]
            fy_val  = None
            fy_end  = ""
            if fy:
                fy.sort(key=lambda x: x.get("end", ""), reverse=True)
                fy_val = float(fy[0]["val"])
                fy_end = fy[0].get("end", "")

            # ── Priority 2: sum four non-overlapping single quarters (TTM) ───
            # Filter to records that have both start and end dates and span 80–100 days
            q_candidates = []
            for x in units:
                if x.get("val") is None:
                    continue
                start_s = x.get("start", "")
                end_s   = x.get("end",   "")
                if not (start_s and end_s):
                    continue
                try:
                    start_d = _dt.strptime(start_s, "%Y-%m-%d")
                    end_d   = _dt.strptime(end_s,   "%Y-%m-%d")
                    span    = (end_d - start_d).days
                    if 80 <= span <= 100:
                        q_candidates.append((end_s, float(x["val"])))
                except ValueError:
                    continue

            ttm_val  = None
            ttm_end  = ""
            if len(q_candidates) >= 4:
                # De-duplicate by end date (keep first occurrence per date)
                seen: dict[str, float] = {}
                for end_s, val in sorted(q_candidates, key=lambda x: x[0], reverse=True):
                    if end_s not in seen:
                        seen[end_s] = val
                sorted_ends = sorted(seen.keys(), reverse=True)
                if len(sorted_ends) >= 4:
                    ttm_val = sum(seen[e] for e in sorted_ends[:4])
                    ttm_end = sorted_ends[0]  # most recent quarter end

            # Return whichever is more recent: 10-K/FY or TTM
            if fy_val is not None and ttm_val is not None:
                return fy_val if fy_end >= ttm_end else ttm_val
            if fy_val is not None:
                return fy_val
            if ttm_val is not None:
                return ttm_val

    return None

def _get_xbrl_shares(facts: dict) -> Optional[float]:
    """
    Get diluted weighted-average shares outstanding in millions.

    Priority:
    1. WeightedAverageNumberOfDilutedSharesOutstanding (10-K, fp=FY)
       — the exact denominator used in diluted EPS; correct for valuation.
    2. WeightedAverageNumberOfSharesOutstandingBasic (basic, fallback)
    3. NI / EPS_diluted (derived, last resort)

    CommonStockSharesOutstanding is intentionally NOT used: it is the
    balance-sheet share count at period end, not the weighted average.
    For multi-class companies (META, GOOGL, AMZN) it typically returns
    only one share class, understating the true diluted count by 2–3×.
    """
    us_gaap = facts.get("us-gaap", {})

    def _annual_shares(concept: str) -> Optional[float]:
        data  = us_gaap.get(concept, {})
        units = data.get("units", {}).get("shares", [])
        fy    = [x for x in units
                 if x.get("form") == "10-K"
                 and x.get("fp")   == "FY"
                 and x.get("val")  is not None]
        if fy:
            fy.sort(key=lambda x: x.get("end", ""), reverse=True)
            return float(fy[0]["val"]) / 1e6
        return None

    # Method 1: diluted weighted-average (preferred)
    v = _annual_shares("WeightedAverageNumberOfDilutedSharesOutstanding")
    if v and 10 < v < 500_000:
        return v

    # Method 2: basic weighted-average
    v = _annual_shares("WeightedAverageNumberOfSharesOutstandingBasic")
    if v and 10 < v < 500_000:
        return v

    # Method 3: derive from NI / EPS_diluted
    ni_data  = us_gaap.get("NetIncomeLoss", {}).get("units", {}).get("USD", [])
    eps_data = us_gaap.get("EarningsPerShareDiluted", {}).get("units", {}).get("USD/shares", [])
    ni_fy    = [x for x in ni_data  if x.get("form") == "10-K" and x.get("fp") == "FY"]
    eps_fy   = [x for x in eps_data if x.get("form") == "10-K" and x.get("fp") == "FY"]
    if ni_fy and eps_fy:
        ni_fy.sort(key=lambda x: x.get("end", ""),  reverse=True)
        eps_fy.sort(key=lambda x: x.get("end", ""), reverse=True)
        ni_val  = float(ni_fy[0]["val"])
        eps_val = float(eps_fy[0]["val"])
        if eps_val != 0 and abs(eps_val) > 0.01:
            v = ni_val / eps_val / 1e6
            if 10 < v < 500_000:
                return v

    return None


def _check_share_consistency(shares_m: float, market_cap_usd: float,
                              price: float) -> Optional[str]:
    """
    Consistency check: |market_cap / price − reported_shares| / reported_shares > 5%
    returns a warning string, else None.
    Catches multi-class share undercounts before they inflate VPS.
    """
    if not (shares_m and market_cap_usd and price and price > 0):
        return None
    implied_shares_m = (market_cap_usd / 1e6) / price
    error = abs(implied_shares_m - shares_m) / shares_m
    if error > 0.05:
        return (
            f"Share count inconsistency: EDGAR reports {shares_m:,.0f}m shares but "
            f"market_cap / price implies {implied_shares_m:,.0f}m "
            f"(divergence {error:.0%}). "
            f"Possible multi-class undercount (e.g. Class A only). "
            f"Using market_cap / price as diluted share count."
        )
    return None

def _get_xbrl_fact_sourced(facts: dict, *concept_names: str) -> tuple:
    """
    Same as _get_xbrl_fact but returns (value, source_label).
    source_label is "10-K/FY YYYY-MM-DD" or "TTM (4Q to YYYY-MM-DD)".
    """
    from datetime import datetime as _dt
    us_gaap = facts.get("us-gaap", {})
    ifrs    = facts.get("ifrs-full", {})

    for name in concept_names:
        for ns in [us_gaap, ifrs]:
            data  = ns.get(name, {})
            units = data.get("units", {}).get("USD", [])
            if not units:
                continue

            fy = [x for x in units
                  if x.get("form") == "10-K"
                  and x.get("fp") == "FY"
                  and x.get("val") is not None]
            fy_val, fy_end = None, ""
            if fy:
                fy.sort(key=lambda x: x.get("end", ""), reverse=True)
                fy_val = float(fy[0]["val"])
                fy_end = fy[0].get("end", "")

            q_candidates = []
            for x in units:
                if x.get("val") is None: continue
                start_s, end_s = x.get("start",""), x.get("end","")
                if not (start_s and end_s): continue
                try:
                    span = (_dt.strptime(end_s,"%Y-%m-%d") - _dt.strptime(start_s,"%Y-%m-%d")).days
                    if 80 <= span <= 100:
                        q_candidates.append((end_s, float(x["val"])))
                except ValueError:
                    continue

            ttm_val, ttm_end = None, ""
            if len(q_candidates) >= 4:
                seen: dict[str, float] = {}
                for e, v in sorted(q_candidates, key=lambda x: x[0], reverse=True):
                    if e not in seen: seen[e] = v
                ends = sorted(seen.keys(), reverse=True)
                if len(ends) >= 4:
                    ttm_val = sum(seen[e] for e in ends[:4])
                    ttm_end = ends[0]

            if fy_val is not None and ttm_val is not None:
                if fy_end >= ttm_end:
                    return fy_val, f"10-K/FY {fy_end}"
                else:
                    return ttm_val, f"TTM (4Q to {ttm_end})"
            if fy_val is not None:
                return fy_val, f"10-K/FY {fy_end}"
            if ttm_val is not None:
                return ttm_val, f"TTM (4Q to {ttm_end})"

    return None, "not found"


def fetch_from_edgar(ticker: str) -> dict:
    """
    Fetch all financial statement data from EDGAR XBRL.
    Returns raw dict; caller converts to CompanyData.
    Caches in session_state.
    """
    cache_key = f"edgar_{ticker}"
    if _IN_STREAMLIT and cache_key in st.session_state:
        return st.session_state[cache_key]

    errors = []
    result = {"source": "edgar", "errors": errors, "ticker": ticker,
              "data_notes": []}   # ← collects TTM warnings

    try:
        cik = _get_cik(ticker)
        if not cik:
            errors.append(f"CIK not found for {ticker}")
            return result

        resp = requests.get(
            f"{EDGAR_BASE}/api/xbrl/companyfacts/CIK{cik}.json",
            headers=EDGAR_HEADERS, timeout=20,
        )
        resp.raise_for_status()
        facts = resp.json().get("facts", {})

        g = lambda *names: _get_xbrl_fact(facts, *names)

        def gs(label, *names):
            """Fetch with source tracking; appends TTM note if applicable."""
            val, src = _get_xbrl_fact_sourced(facts, *names)
            if val is not None and "TTM" in src:
                result["data_notes"].append(
                    f"{label}: {src} — EDGAR 10-K/FY not yet indexed for most recent fiscal year. "
                    f"Value is trailing twelve months ending {src.split('to ')[-1]}. "
                    f"Consider overriding with the 10-K annual figure if available."
                )
            return val

        # Company name
        result["name"] = ticker

        # ── Income statement (use gs() to track TTM vs 10-K/FY) ─────────────
        result["ebit"] = gs("EBIT",
            "OperatingIncomeLoss",
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxes",
        )
        result["interest_expense"] = abs(gs("Interest expense",
            "InterestExpense",
            "InterestAndDebtExpense",
            "FinanceCosts",
        ) or 0)
        result["net_income"] = gs("Net income",
            "NetIncomeLoss",
            "NetIncomeLossAvailableToCommonStockholdersBasic",
            "ProfitLoss",
        )
        result["revenue"] = gs("Revenue",
            "Revenues",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "SalesRevenueNet",
            "RevenueFromContractWithCustomerIncludingAssessedTax",
        )
        result["depreciation"] = gs("Depreciation",
            "DepreciationDepletionAndAmortization",
            "DepreciationAndAmortization",
            "Depreciation",
        )
        raw_capex = gs("CapEx",
            "PaymentsToAcquirePropertyPlantAndEquipment",
            "PurchaseOfPropertyPlantAndEquipment",
            "CapitalExpendituresPurchaseOfPropertyPlantAndEquipment",
        ) or 0
        lease_payments = g(
            "FinanceLeasePrincipalPayments",
            "RepaymentsOfFinanceLeaseLiability",
        ) or 0
        result["capex"] = abs(raw_capex) + abs(lease_payments)
        result["delta_wc"] = abs(gs("ΔWC",
            "IncreaseDecreaseInOperatingCapital",
            "IncreaseDecreaseInOtherOperatingLiabilities",
            "ChangeInOperatingAssets",
        ) or 0)

        # Derived: EBITDA
        if result.get("ebit") and result.get("depreciation"):
            result["ebitda"] = result["ebit"] + result["depreciation"]

        # Tax rate
        tax_exp  = g("IncomeTaxExpenseBenefit", "CurrentIncomeTaxExpense")
        pre_tax  = g("IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                     "IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic")
        if tax_exp and pre_tax and pre_tax > 0:
            result["tax_rate"] = max(0.05, min(0.40, tax_exp / pre_tax))

        # ── Balance sheet ────────────────────────────────────────────────────
        # Financial debt ONLY: LongTermDebt + the larger of DebtCurrent or
        # ShortTermBorrowings (to avoid double-counting if they overlap).
        # Explicitly excluded: OperatingLeaseLiability,
        # OperatingLeaseLiabilityNoncurrent, OperatingLeaseLiabilityCurrent,
        # FinanceLeaseLiabilityNoncurrent, FinanceLeaseLiabilityCurrent.
        # These are balance-sheet liabilities under ASC 842 but are NOT
        # interest-bearing financial debt and must not enter the WACC or
        # capital structure calculations.
        long_term_debt  = g("LongTermDebt", "LongTermDebtNoncurrent") or 0
        debt_current    = g("DebtCurrent") or 0
        stb             = g("ShortTermBorrowings") or 0
        short_term_debt = max(debt_current, stb)   # take larger; they often overlap
        result["book_debt"] = long_term_debt + short_term_debt
        # Fallback: zero-debt companies that file no individual debt lines
        if result["book_debt"] == 0:
            notes = g("NotesPayable", "NotesPayableCurrent") or 0
            result["book_debt"] = notes

        result["book_equity"] = g(
            "StockholdersEquity",
            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
            "CommonStockholdersEquity",
        )
        result["cash"] = g(
            # Priority: cash + short-term investments (marketable securities)
            # Damodaran Ch 16: treat marketable securities as part of cash in the equity bridge
            "CashCashEquivalentsAndShortTermInvestments",
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
            "CashAndCashEquivalentsAtCarryingValue",
            "CashAndCashEquivalents",
        )
        result["total_assets"] = g("Assets")

        # Shares outstanding (in millions)
        result["shares"] = _get_xbrl_shares(facts)

        # EPS
        result["eps"] = g(
            "EarningsPerShareBasic",
            "EarningsPerShareDiluted",
        )

        # Historical series (last 5 annual EPS and Revenue for growth module)
        eps_data = (facts.get("us-gaap",{})
                    .get("EarningsPerShareBasic",{})
                    .get("units",{}).get("USD/shares",[]))
        annual_eps = [x for x in eps_data if x.get("form")=="10-K" and x.get("val")]
        annual_eps.sort(key=lambda x: x.get("end",""))
        result["historical_eps"] = [float(x["val"]) for x in annual_eps[-8:]]

        rev_data = None
        for rev_name in ["Revenues","RevenueFromContractWithCustomerExcludingAssessedTax","SalesRevenueNet"]:
            rv = facts.get("us-gaap",{}).get(rev_name,{}).get("units",{}).get("USD",[])
            if rv: rev_data = rv; break
        if rev_data:
            annual_rev = [x for x in rev_data if x.get("form")=="10-K" and x.get("val")]
            annual_rev.sort(key=lambda x: x.get("end",""))
            result["historical_revenue"] = [float(x["val"])/1e6 for x in annual_rev[-8:]]

    except Exception as e:
        errors.append(f"EDGAR fetch failed: {e}")

    if _IN_STREAMLIT:
        st.session_state[cache_key] = result
    return result


# ─────────────────────────────────────────────────────────────────────────────
# FRED — risk-free rate
# ─────────────────────────────────────────────────────────────────────────────

def get_risk_free_rate(fred_api_key: str = "") -> float:
    """10-yr Treasury from FRED. Cached per session. Falls back to 4.5%."""
    if _IN_STREAMLIT and "fred_rf" in st.session_state:
        return st.session_state["fred_rf"]
    try:
        params = {"series_id":"DGS10","api_key":fred_api_key or "FRED_KEY_HERE",
                  "file_type":"json","sort_order":"desc","limit":5}
        resp = requests.get("https://api.stlouisfed.org/fred/series/observations",
                            params=params, timeout=8)
        resp.raise_for_status()
        for o in resp.json()["observations"]:
            if o["value"] not in (".", ""):
                rf = float(o["value"]) / 100
                if _IN_STREAMLIT:
                    st.session_state["fred_rf"] = rf
                return rf
    except Exception:
        pass
    return 0.045


# ─────────────────────────────────────────────────────────────────────────────
# yfinance — price, market cap, beta ONLY (3 fields, with retry)
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_market_data_yf(ticker: str, retries: int = 2) -> dict:
    """
    Fetch only the 3 market data fields from yfinance.
    Retries once after 3-second wait if rate-limited.
    Returns dict with price, market_cap, beta (all may be None on failure).
    """
    cache_key = f"yf_market_{ticker}"
    if _IN_STREAMLIT and cache_key in st.session_state:
        return st.session_state[cache_key]

    result = {"price": None, "market_cap": None, "beta": None, "name": None, "error": None}

    for attempt in range(retries + 1):
        try:
            import yfinance as yf
            info = yf.Ticker(ticker).info or {}
            result["price"]      = info.get("currentPrice") or info.get("regularMarketPrice")
            result["market_cap"] = info.get("marketCap")
            result["beta"]       = info.get("beta")
            result["name"]       = info.get("longName") or info.get("shortName")
            if _IN_STREAMLIT:
                st.session_state[cache_key] = result
            return result
        except Exception as e:
            err = str(e)
            if "Too Many Requests" in err or "Rate" in err:
                if attempt < retries:
                    time.sleep(3)
                    continue
            result["error"] = err
            break

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def get_company_data(
    ticker:          str,
    fred_api_key:    str   = "",
    force_refresh:   bool  = False,
    # Manual overrides (used when yfinance is unavailable)
    manual_price:    float = 0.0,
    manual_mktcap:   float = 0.0,
    manual_beta:     float = 0.0,
    industry:        Optional[str] = None,
) -> CompanyData:
    """
    Fetch company data. EDGAR primary, yfinance for market data only.

    Parameters
    ----------
    ticker         : Stock ticker
    fred_api_key   : FRED API key for risk-free rate
    force_refresh  : Bypass session cache
    manual_price   : Override for stock price (if yfinance unavailable)
    manual_mktcap  : Override for market cap ($m)
    manual_beta    : Override for beta (if yfinance unavailable)
    industry       : Industry name for Damodaran beta fallback
    """
    ticker = ticker.upper().strip()
    cache_key = f"company_{ticker}"

    if not force_refresh and _IN_STREAMLIT and cache_key in st.session_state:
        return st.session_state[cache_key]

    errors: list[str] = []

    # ── Step 1: EDGAR ─────────────────────────────────────────────────────────
    edgar = fetch_from_edgar(ticker)
    errors.extend(edgar.get("errors", []))
    # Surface TTM staleness notes as warnings in the status bar
    for note in edgar.get("data_notes", []):
        errors.append(note)

    # ── Step 2: FRED ──────────────────────────────────────────────────────────
    rf = get_risk_free_rate(fred_api_key)

    # ── Step 3: yfinance (market data only) ───────────────────────────────────
    yf_data = _fetch_market_data_yf(ticker)
    if yf_data.get("error"):
        errors.append(f"yfinance: {yf_data['error']}")

    # ── Step 4: Resolve each field ────────────────────────────────────────────
    def _edgar(key, fallback=0.0):
        v = edgar.get(key)
        return float(v) / 1e6 if v is not None and abs(v) > 1e4 else (float(v) if v is not None else fallback)

    # Financial statement fields — from EDGAR
    ebit         = _edgar("ebit")
    interest     = _edgar("interest_expense")
    net_income   = _edgar("net_income")
    revenue      = _edgar("revenue")
    ebitda_v     = _edgar("ebitda") or (ebit + _edgar("depreciation"))
    depreciation = _edgar("depreciation")
    book_debt    = _edgar("book_debt")
    book_equity  = _edgar("book_equity")
    cash_v       = _edgar("cash")
    total_assets = _edgar("total_assets")
    capex        = _edgar("capex")
    delta_wc     = _edgar("delta_wc")
    tax_rate     = edgar.get("tax_rate") or 0.21
    shares_m     = _edgar("shares") or 1000.0   # already in millions from EDGAR

    # EPS from EDGAR
    eps_raw = edgar.get("eps")
    eps_v   = float(eps_raw) if eps_raw else (net_income / shares_m if shares_m > 0 else 0)

    # Historical series from EDGAR
    hist_eps = edgar.get("historical_eps", [])
    hist_rev = edgar.get("historical_revenue", [])

    # Market data — prefer manual override, then yfinance, then derived/fallback
    price_v  = manual_price  or yf_data.get("price")  or 0.0
    mktcap_v = manual_mktcap or (yf_data.get("market_cap", 0) or 0) / 1e6
    if mktcap_v == 0 and price_v > 0 and shares_m > 0:
        mktcap_v = price_v * shares_m   # derive from price × shares

    # Share count consistency check
    share_warning = _check_share_consistency(shares_m, yf_data.get("market_cap") or 0, price_v)
    if share_warning:
        # Use market_cap / price as the more reliable diluted count
        if price_v > 0 and yf_data.get("market_cap"):
            shares_m = (yf_data["market_cap"] / 1e6) / price_v
        errors.append(share_warning)
    beta_src = "yfinance"
    beta_v   = manual_beta or yf_data.get("beta") or 0.0
    if beta_v == 0:
        if industry and industry in INDUSTRY_BETAS:
            beta_v   = INDUSTRY_BETAS[industry]["levered"]
            beta_src = f"Damodaran ({industry})"
            errors.append(f"Beta from Damodaran industry avg ({industry}): {beta_v:.3f}")
        else:
            beta_v   = INDUSTRY_BETAS["Total Market"]["levered"]
            beta_src = "Damodaran (Total Market avg)"
            errors.append(f"Beta: yfinance unavailable, using total market avg {beta_v:.3f}")
    elif manual_beta:
        beta_src = "manual"

    # Company name — yfinance has better names than EDGAR
    name_v = yf_data.get("name") or ticker

    # Source classification
    if edgar.get("errors") and yf_data.get("error"):
        source = "placeholder"
    elif edgar.get("errors"):
        source = "partial (yfinance only)"
    elif yf_data.get("error") or (not manual_price and not yf_data.get("price")):
        source = "partial (EDGAR + manual market data)"
    else:
        source = "live"

    # FCFF
    net_capex = capex - depreciation
    fcff_v = ebit * (1 - tax_rate) - net_capex - delta_wc

    d = CompanyData(
        ticker=ticker, name=name_v,
        ebit=ebit, interest_expense=interest, net_income=net_income,
        revenue=revenue, ebitda=ebitda_v, depreciation=depreciation,
        book_debt=book_debt, book_equity=book_equity, cash=cash_v,
        total_assets=total_assets, capex=capex, delta_wc=delta_wc,
        equity_market_cap=mktcap_v, beta_levered=beta_v,
        price=price_v, shares=shares_m, eps=eps_v,
        rf=rf, erp=0.055,
        tax_rate=tax_rate, country_spread=0.0,
        firm_type=1, avg_debt_maturity=5,
        source=source, fetch_errors=errors,
        historical_eps=hist_eps, historical_revenue=hist_rev,
        fcff=fcff_v, beta_source=beta_src, industry=industry,
    )

    if _IN_STREAMLIT:
        st.session_state[cache_key] = d
    return d


# ─────────────────────────────────────────────────────────────────────────────
# Source badge
# ─────────────────────────────────────────────────────────────────────────────

def source_badge_html(d: CompanyData) -> str:
    colours = {
        "live":                       ("#14532d", "✓", "Live"),
        "partial (EDGAR + manual market data)": ("#1e3a5f", "~", "EDGAR + manual"),
        "partial (yfinance only)":    ("#1e3a5f", "~", "Partial"),
        "placeholder":                ("#3b2a0f", "⚠", "Placeholder"),
    }
    colour, icon, label = colours.get(d.source, ("#3b2a0f", "⚠", d.source))
    badge = (f'<span style="font-size:0.72rem;padding:2px 10px;border-radius:4px;'
             f'background:{colour};color:#fff">{icon} {label}</span>')
    beta_note = f' <span style="font-size:0.70rem;color:#94a3b8">β from {d.beta_source}</span>' if "damodaran" in d.beta_source.lower() or "manual" in d.beta_source.lower() else ""
    if d.fetch_errors:
        err = "; ".join(d.fetch_errors[:2])
        badge += f' <span style="font-size:0.70rem;color:#94a3b8">{err[:60]}</span>'
    return badge + beta_note


# ─────────────────────────────────────────────────────────────────────────────
# Smoke test
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("── Industry beta lookup ─────────────────────────────")
    for ind in ["Software (System & Application)", "Semiconductor", "Total Market"]:
        b = INDUSTRY_BETAS[ind]
        print(f"  {ind:<40} β_levered={b['levered']:.4f}  β_unlevered={b['unlevered']:.4f}")

    print("\n── Placeholder fallback ─────────────────────────────")
    d = _make_placeholder("META")
    print(f"  {d.ticker}: EBIT ${d.ebit:,.0f}m  Beta {d.beta_levered}  source={d.source}")

    print("\n── EDGAR fetch (requires network) ───────────────────")
    try:
        edgar = fetch_from_edgar("AAPL")
        if edgar.get("errors"):
            print(f"  Errors: {edgar['errors']}")
        else:
            ebit = (edgar.get("ebit") or 0) / 1e6
            rev  = (edgar.get("revenue") or 0) / 1e6
            print(f"  AAPL EBIT: ${ebit:,.0f}m  Revenue: ${rev:,.0f}m")
    except Exception as e:
        print(f"  Network blocked (expected in dev): {e}")

    print("\n✓ data_fetcher.py structure OK")
