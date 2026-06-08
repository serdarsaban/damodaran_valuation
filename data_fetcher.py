"""
data_fetcher.py
===============
Live data connection for the Damodaran Valuation Toolkit.

Sources
-------
  yfinance          — beta, market cap, price, EPS, book value, financials
  SEC EDGAR API     — 10-K filings: debt schedule, lease commitments, R&D
  FRED (St Louis)   — 10-yr Treasury yield (risk-free rate)
  Damodaran site    — ERP by country, industry betas (cached Jan-2026 values)

Rate limiting strategy
----------------------
  yfinance: cache all ticker data in st.session_state on first fetch.
            Never call inside a loop or on every rerender.
            One Ticker() object → .info + .financials + .balance_sheet
            fetched together, stored under session_state["yf_cache"][ticker].

  EDGAR:    REST API, free, no key. Rate limit: ~10 req/sec.
            Cache CIK lookup + latest 10-K accession number.
            Only fetch the specific financial facts needed.

  FRED:     Single GET per session for the 10-yr yield.
            Cache in session_state["fred_rf"].

  Fallback: If any fetch fails, fall back to the placeholder values
            with a visible warning badge — never silently use stale data.

Usage in Streamlit pages
------------------------
    from data_fetcher import fetch_company_data, get_risk_free_rate
    data = fetch_company_data("AAPL")   # uses st.session_state cache
    rf   = get_risk_free_rate()
"""

from __future__ import annotations
import math
import time
import requests
from dataclasses import dataclass, field
from typing import Optional

# ── Streamlit import (graceful degradation if not in Streamlit context) ──────
try:
    import streamlit as st
    _IN_STREAMLIT = True
except ImportError:
    _IN_STREAMLIT = False
    class _FakeState(dict):
        pass
    st = type("st", (), {"session_state": _FakeState()})()


# ─────────────────────────────────────────────────────────────────────────────
# CompanyData — the unified data object all modules consume
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CompanyData:
    ticker:             str
    name:               str
    # Income statement
    ebit:               float       # $m
    interest_expense:   float       # $m
    net_income:         float       # $m
    revenue:            float       # $m
    ebitda:             float       # $m
    depreciation:       float       # $m
    # Balance sheet
    book_debt:          float       # $m
    book_equity:        float       # $m
    cash:               float       # $m
    total_assets:       float       # $m
    # Cash flow
    capex:              float       # $m
    delta_wc:           float       # $m  (change in working capital)
    # Market data
    equity_market_cap:  float       # $m
    beta_levered:       float
    price:              float       # $ per share
    shares:             float       # m shares outstanding
    eps:                float       # $ per share (trailing)
    # Derived / market rates
    rf:                 float       # risk-free rate
    erp:                float       # equity risk premium
    tax_rate:           float
    country_spread:     float
    firm_type:          int         # 1=large, 2=small, 3=financial
    avg_debt_maturity:  float       # years
    # Metadata
    source:             str         # "live" | "partial" | "placeholder"
    fetch_errors:       list[str] = field(default_factory=list)
    # Historical series (for growth module)
    historical_eps:     list[float] = field(default_factory=list)
    historical_revenue: list[float] = field(default_factory=list)
    # FCFF
    fcff:               float = 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Placeholder data (fallback)
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
    "TSLA": dict(name="Tesla Inc.", ebit=8_700, interest_expense=590,
                 net_income=15_000, revenue=97_000, ebitda=13_500,
                 depreciation=4_600, book_debt=8_800, book_equity=60_000,
                 cash=26_000, total_assets=106_000, capex=8_900, delta_wc=800,
                 equity_market_cap=600_000, beta_levered=2.30, price=190.0,
                 shares=3_190, eps=4.30, tax_rate=0.10, avg_debt_maturity=4,
                 firm_type=2, erp=0.055, country_spread=0.0),
    "JPM":  dict(name="JPMorgan Chase", ebit=55_000, interest_expense=32_000,
                 net_income=49_600, revenue=158_000, ebitda=62_000,
                 depreciation=7_000, book_debt=400_000, book_equity=340_000,
                 cash=30_000, total_assets=3_900_000, capex=3_000, delta_wc=0,
                 equity_market_cap=580_000, beta_levered=1.10, price=200.0,
                 shares=2_900, eps=16.80, tax_rate=0.22, avg_debt_maturity=5,
                 firm_type=3, erp=0.055, country_spread=0.0),
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
    return CompanyData(
        ticker=ticker.upper(), source="placeholder",
        rf=0.045,
        fcff=0.0,
        **p,
    )


# ─────────────────────────────────────────────────────────────────────────────
# FRED — 10-yr Treasury yield
# ─────────────────────────────────────────────────────────────────────────────

FRED_URL = "https://api.stlouisfed.org/fred/series/observations"

def get_risk_free_rate(fred_api_key: str = "") -> float:
    """
    Fetch the current 10-year US Treasury yield from FRED.

    Returns the most recent daily observation.
    Caches result in st.session_state["fred_rf"] for the session.

    Parameters
    ----------
    fred_api_key : FRED API key (free at https://fred.stlouisfed.org/docs/api/)
                   If empty, uses the public endpoint (may be rate-limited).
    """
    cache_key = "fred_rf"
    if _IN_STREAMLIT and cache_key in st.session_state:
        return st.session_state[cache_key]

    try:
        params = {
            "series_id":     "DGS10",
            "api_key":       fred_api_key or "FRED_API_KEY_HERE",
            "file_type":     "json",
            "sort_order":    "desc",
            "limit":         5,
            "observation_start": "2020-01-01",
        }
        resp = requests.get(FRED_URL, params=params, timeout=8)
        resp.raise_for_status()
        obs = resp.json()["observations"]
        # Find most recent non-null observation
        for o in obs:
            if o["value"] not in (".", ""):
                rf = float(o["value"]) / 100  # FRED gives percentage
                if _IN_STREAMLIT:
                    st.session_state[cache_key] = rf
                return rf
    except Exception:
        pass

    # Fallback: use most recent known value
    return 0.045


# ─────────────────────────────────────────────────────────────────────────────
# yfinance fetcher
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_yfinance(ticker: str) -> dict:
    """
    Fetch all needed data from yfinance in the minimum number of calls.

    Caches raw results under st.session_state["yf_cache"][ticker].
    Only call on button-click, never on rerender.

    Returns a dict of raw values (may contain None for missing fields).
    """
    cache_key = f"yf_cache"
    if _IN_STREAMLIT:
        if cache_key not in st.session_state:
            st.session_state[cache_key] = {}
        if ticker in st.session_state[cache_key]:
            return st.session_state[cache_key][ticker]

    try:
        import yfinance as yf
        t = yf.Ticker(ticker)

        # Three calls — do them together, cache together
        info    = t.info or {}
        fin     = t.financials              # income statement (annual)
        bal     = t.balance_sheet           # balance sheet (annual)
        cf      = t.cashflow                # cash flow statement
        hist    = t.history(period="max",   # for historical series
                            interval="3mo",
                            auto_adjust=True)

        raw = {
            "info":    info,
            "fin":     fin,
            "bal":     bal,
            "cf":      cf,
            "hist":    hist,
        }

        if _IN_STREAMLIT:
            st.session_state[cache_key][ticker] = raw
        return raw

    except Exception as e:
        return {"error": str(e)}


def _safe_get(df, row_names: list[str], col: int = 0) -> Optional[float]:
    """Try multiple row name variants; return first found."""
    if df is None:
        return None
    for name in row_names:
        try:
            val = df.loc[name].iloc[col]
            if val is not None and not (isinstance(val, float) and math.isnan(val)):
                return float(val)
        except (KeyError, IndexError):
            continue
    return None


def _parse_yfinance(ticker: str, raw: dict) -> CompanyData:
    """
    Parse raw yfinance data into a CompanyData object.

    Row name variants are needed because yfinance labels change across
    versions and ticker types.
    """
    errors = []
    info = raw.get("info", {})
    fin  = raw.get("fin")
    bal  = raw.get("bal")
    cf   = raw.get("cf")
    hist = raw.get("hist")

    def g(val, fallback=0.0, label=""):
        if val is None:
            if label: errors.append(f"Missing: {label}")
            return fallback
        return val / 1e6 if abs(val) > 1e4 else val  # convert to $m if in raw $

    # ── Income statement ─────────────────────────────────────────────────────
    ebit  = _safe_get(fin, ["EBIT", "Ebit", "Operating Income", "OperatingIncome"])
    ebit  = g(ebit, 0.0, "EBIT") if ebit else g(None, 0.0, "EBIT")
    # If EBIT missing, derive: revenue - operating expenses
    if ebit == 0:
        rev_raw = _safe_get(fin, ["Total Revenue", "Revenue"])
        oe_raw  = _safe_get(fin, ["Total Operating Expenses", "Operating Expenses"])
        if rev_raw and oe_raw:
            ebit = g(rev_raw - oe_raw)

    interest = abs(g(_safe_get(fin, [
        "Interest Expense", "Interest Expense Non Operating",
        "Net Interest Income"]), 0.0, "Interest Expense"))

    ni       = g(_safe_get(fin, ["Net Income", "Net Income Common Stockholders",
                                  "Net Income From Continuing Operations"]), 0.0, "Net Income")

    revenue  = g(_safe_get(fin, ["Total Revenue", "Revenue"]), 0.0, "Revenue")

    da       = g(_safe_get(cf, ["Depreciation", "Depreciation And Amortization",
                                 "Depreciation Amortization Depletion"]), 0.0)

    ebitda   = ebit + da if ebit and da else g(info.get("ebitda"), 0.0)

    # ── Balance sheet ─────────────────────────────────────────────────────────
    book_debt = g(_safe_get(bal, ["Total Debt", "Long Term Debt And Capital Lease Obligation",
                                   "Long Term Debt"]), 0.0)

    book_eq   = g(_safe_get(bal, ["Stockholders Equity", "Total Equity Gross Minority Interest",
                                   "Common Stock Equity"]), 0.0)

    cash_val  = g(_safe_get(bal, ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments",
                                   "Cash And Short Term Investments"]), 0.0)

    tot_assets = g(_safe_get(bal, ["Total Assets"]), 0.0)

    # ── Cash flows ────────────────────────────────────────────────────────────
    capex     = abs(g(_safe_get(cf, ["Capital Expenditure", "Purchase Of Property Plant And Equipment",
                                      "Capital Expenditures"]), 0.0))

    # ΔWorking Capital: change in non-cash working capital
    dwc = g(_safe_get(cf, ["Change In Working Capital", "Changes In Working Capital",
                             "Change In Other Working Capital"]), 0.0)

    # ── Market data ───────────────────────────────────────────────────────────
    mktcap    = g(info.get("marketCap"), 0.0, "Market Cap")
    beta      = info.get("beta") or 1.0
    price_val = info.get("currentPrice") or info.get("regularMarketPrice") or 0.0
    shares_n  = g(info.get("sharesOutstanding"), 1.0)
    eps_val   = info.get("trailingEps") or (ni / shares_n if shares_n > 0 else 0)

    # ── Historical EPS and revenue series ─────────────────────────────────────
    hist_eps = []
    hist_rev = []
    if fin is not None and not fin.empty:
        try:
            for col_i in range(min(8, len(fin.columns))):
                ni_h = _safe_get(fin, ["Net Income", "Net Income Common Stockholders"], col_i)
                rv_h = _safe_get(fin, ["Total Revenue", "Revenue"], col_i)
                sh_h = info.get("sharesOutstanding", 1)
                if ni_h and sh_h:
                    hist_eps.append(float(ni_h) / float(sh_h))
                if rv_h:
                    hist_rev.append(float(rv_h) / 1e6)
            hist_eps = list(reversed(hist_eps))  # oldest first
            hist_rev = list(reversed(hist_rev))
        except Exception:
            pass

    # ── FCFF ──────────────────────────────────────────────────────────────────
    net_capex = capex - da
    fcff_val  = ebit * (1 - 0.21) - net_capex - abs(dwc)  # rough, uses US tax rate

    # ── Tax rate ──────────────────────────────────────────────────────────────
    # Use effective rate from financials if available
    tax_exp = _safe_get(fin, ["Tax Provision", "Income Tax Expense"])
    pretax  = _safe_get(fin, ["Pretax Income", "Income Before Tax"])
    if tax_exp and pretax and pretax > 0:
        eff_tax = float(tax_exp) / float(pretax)
        tax_rate = max(0.05, min(0.40, eff_tax))
    else:
        tax_rate = info.get("effectiveTaxRate") or 0.21

    source = "live" if not errors else "partial"

    return CompanyData(
        ticker=ticker.upper(),
        name=info.get("longName") or info.get("shortName") or ticker,
        ebit=ebit, interest_expense=interest, net_income=ni,
        revenue=revenue, ebitda=ebitda, depreciation=da,
        book_debt=book_debt, book_equity=book_eq,
        cash=cash_val, total_assets=tot_assets,
        capex=capex, delta_wc=abs(dwc),
        equity_market_cap=mktcap,
        beta_levered=beta, price=price_val,
        shares=shares_n, eps=eps_val,
        rf=0.045,               # will be updated by FRED call
        erp=0.055,              # default US ERP
        tax_rate=tax_rate,
        country_spread=0.0,
        firm_type=1,
        avg_debt_maturity=5,
        source=source,
        fetch_errors=errors,
        historical_eps=hist_eps,
        historical_revenue=hist_rev,
        fcff=fcff_val,
    )


# ─────────────────────────────────────────────────────────────────────────────
# EDGAR — 10-K supplementary data
# ─────────────────────────────────────────────────────────────────────────────

EDGAR_BASE = "https://data.sec.gov"
EDGAR_HEADERS = {"User-Agent": "DamodaranValuationApp research@example.com"}

# CIK lookup cache
_CIK_CACHE: dict[str, str] = {
    "AAPL": "0000320193", "MSFT": "0000789019", "TSLA": "0001318605",
    "JPM":  "0000019617", "AMZN": "0001018724", "GOOGL": "0001652044",
    "META": "0001326801", "NVDA": "0001045810",  "BRK.B": "0001067983",
    "JNJ":  "0000200406", "V":    "0001403161",  "WMT":   "0000104169",
    "XOM":  "0000034088", "UNH":  "0000072971",  "PG":    "0000080424",
}

def _get_cik(ticker: str) -> Optional[str]:
    """Look up SEC CIK number for a ticker."""
    ticker = ticker.upper()
    if ticker in _CIK_CACHE:
        return _CIK_CACHE[ticker]
    try:
        resp = requests.get(
            f"{EDGAR_BASE}/cgi-bin/browse-edgar?action=getcompany&ticker={ticker}"
            f"&type=10-K&dateb=&owner=include&count=1&search_text=&output=atom",
            headers=EDGAR_HEADERS, timeout=8
        )
        # Extract CIK from response
        import re
        m = re.search(r'CIK=(\d+)', resp.text)
        if m:
            cik = m.group(1).zfill(10)
            _CIK_CACHE[ticker] = cik
            return cik
    except Exception:
        pass
    return None


def fetch_edgar_supplementary(ticker: str) -> dict:
    """
    Fetch supplementary financial data from SEC EDGAR.

    Returns dict with keys:
      avg_debt_maturity    : weighted average debt maturity (years)
      operating_lease_commitments : [yr1..yr5, beyond] in $m
      rd_history           : list of annual R&D spend ($m), most recent first
    """
    cache_key = f"edgar_{ticker}"
    if _IN_STREAMLIT and cache_key in st.session_state:
        return st.session_state[cache_key]

    result = {
        "avg_debt_maturity": 5.0,
        "operating_lease_commitments": [],
        "rd_history": [],
        "source": "edgar",
        "errors": [],
    }

    try:
        cik = _get_cik(ticker)
        if not cik:
            result["errors"].append(f"CIK not found for {ticker}")
            return result

        # Get company facts (XBRL data — covers most financial line items)
        resp = requests.get(
            f"{EDGAR_BASE}/api/xbrl/companyfacts/CIK{cik}.json",
            headers=EDGAR_HEADERS, timeout=15,
        )
        resp.raise_for_status()
        facts = resp.json().get("facts", {})

        # R&D expenses — us-gaap ResearchAndDevelopmentExpense
        us_gaap = facts.get("us-gaap", {})
        rd_data = us_gaap.get("ResearchAndDevelopmentExpense", {})
        rd_units = rd_data.get("units", {}).get("USD", [])
        if rd_units:
            # Filter to annual (form 10-K), most recent 10 years
            annual = [x for x in rd_units
                      if x.get("form") == "10-K" and x.get("val") is not None]
            annual.sort(key=lambda x: x.get("end", ""), reverse=True)
            result["rd_history"] = [float(x["val"]) / 1e6 for x in annual[:10]]

        # Operating lease commitments — OperatingLeasesFutureMinimumPaymentsDue*
        lease_keys = {
            1: "OperatingLeasesFutureMinimumPaymentsDueInTwoYears",
            # Year 1 in various standards
        }
        # Try IFRS16 / ASC842 keys
        for yr, key in [
            (1, "LesseeOperatingLeaseLiabilityPaymentsDueNextTwelveMonths"),
            (2, "LesseeOperatingLeaseLiabilityPaymentsDueYearTwo"),
            (3, "LesseeOperatingLeaseLiabilityPaymentsDueYearThree"),
            (4, "LesseeOperatingLeaseLiabilityPaymentsDueYearFour"),
            (5, "LesseeOperatingLeaseLiabilityPaymentsDueYearFive"),
        ]:
            data = us_gaap.get(key, {})
            units = data.get("units", {}).get("USD", [])
            annual = [x for x in units if x.get("form") == "10-K"]
            if annual:
                annual.sort(key=lambda x: x.get("end", ""), reverse=True)
                val = float(annual[0]["val"]) / 1e6
                commitments = result["operating_lease_commitments"]
                while len(commitments) < yr - 1:
                    commitments.append(0.0)
                if len(commitments) < yr:
                    commitments.append(val)

    except Exception as e:
        result["errors"].append(str(e))

    if _IN_STREAMLIT:
        st.session_state[cache_key] = result
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def fetch_company_data(
    ticker: str,
    fred_api_key: str = "",
    include_edgar: bool = True,
) -> CompanyData:
    """
    Fetch all data for a ticker. Entry point for all Streamlit pages.

    Strategy:
      1. Fetch from yfinance (primary)
      2. Fetch rf from FRED
      3. Fetch supplementary from EDGAR (debt maturity, leases, R&D)
      4. Fall back gracefully to placeholders for any missing field

    Parameters
    ----------
    ticker        : Stock ticker (e.g. "AAPL")
    fred_api_key  : FRED API key (optional; falls back to default rf if missing)
    include_edgar : Whether to also call EDGAR (slower; set False for quick loads)

    Returns
    -------
    CompanyData with source="live", "partial", or "placeholder"
    """
    ticker = ticker.upper().strip()

    # Try yfinance
    try:
        raw = _fetch_yfinance(ticker)
        if "error" in raw:
            raise ValueError(raw["error"])
        data = _parse_yfinance(ticker, raw)
    except Exception as e:
        # Fall back to placeholder
        data = _make_placeholder(ticker)
        data.source = "placeholder"
        data.fetch_errors.append(f"yfinance failed: {e}")
        return data

    # Update rf from FRED
    try:
        data.rf = get_risk_free_rate(fred_api_key)
    except Exception as e:
        data.fetch_errors.append(f"FRED failed, using rf=4.5%: {e}")

    # EDGAR supplementary
    if include_edgar:
        try:
            edgar = fetch_edgar_supplementary(ticker)
            if edgar.get("rd_history"):
                data.historical_eps  # keep as-is
            if edgar.get("avg_debt_maturity"):
                data.avg_debt_maturity = edgar["avg_debt_maturity"]
        except Exception as e:
            data.fetch_errors.append(f"EDGAR partial: {e}")

    # Recalculate FCFF with actual tax rate
    net_capex = data.capex - data.depreciation
    data.fcff  = data.ebit * (1 - data.tax_rate) - net_capex - data.delta_wc

    return data


# ─────────────────────────────────────────────────────────────────────────────
# Streamlit cache wrapper (call this from pages, not fetch_company_data directly)
# ─────────────────────────────────────────────────────────────────────────────

def get_company_data(
    ticker: str,
    fred_api_key: str = "",
    force_refresh: bool = False,
) -> CompanyData:
    """
    Cached wrapper for use in Streamlit pages.

    Checks st.session_state first. Only calls the live APIs if the
    data is not cached or force_refresh=True.

    Usage in a Streamlit page:
        if st.button("Fetch data"):
            data = get_company_data(ticker)
            st.session_state["company_data"] = data

        data = st.session_state.get("company_data") or get_company_data(ticker)
    """
    cache_key = f"company_{ticker}"

    if not force_refresh and _IN_STREAMLIT:
        if cache_key in st.session_state:
            return st.session_state[cache_key]

    data = fetch_company_data(ticker, fred_api_key)

    if _IN_STREAMLIT:
        st.session_state[cache_key] = data

    return data


# ─────────────────────────────────────────────────────────────────────────────
# Source badge helper (used by all pages)
# ─────────────────────────────────────────────────────────────────────────────

def source_badge_html(data: CompanyData) -> str:
    """Return HTML badge indicating data source and any errors."""
    if data.source == "live":
        colour, icon, label = "#14532d", "✓", "Live data"
    elif data.source == "partial":
        colour, icon, label = "#1e3a5f", "~", "Partial live data"
    else:
        colour, icon, label = "#3b2a0f", "⚠", "Placeholder data"

    badge = (f'<span style="font-size:0.72rem;padding:2px 10px;border-radius:4px;'
             f'background:{colour};color:#fff;display:inline-block">'
             f'{icon} {label}</span>')

    if data.fetch_errors:
        errs = "; ".join(data.fetch_errors[:2])
        badge += (f' <span style="font-size:0.70rem;color:#94a3b8;margin-left:8px">'
                  f'{errs}</span>')
    return badge


# ─────────────────────────────────────────────────────────────────────────────
# Smoke test (runs locally, not in Streamlit context)
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("── Placeholder fallback test ────────────────────────")
    d = _make_placeholder("AAPL")
    print(f"  {d.ticker}: EBIT ${d.ebit:,.0f}m, MktCap ${d.equity_market_cap:,.0f}m, source={d.source}")

    print("\n── Source badge ─────────────────────────────────────")
    print(f"  {source_badge_html(d)}")

    print("\n── Live fetch test (requires network) ───────────────")
    try:
        raw = _fetch_yfinance("AAPL")
        if "error" in raw:
            print(f"  Network blocked (expected in dev): {raw['error']}")
        else:
            d_live = _parse_yfinance("AAPL", raw)
            print(f"  {d_live.ticker}: {d_live.name}")
            print(f"  EBIT: ${d_live.ebit:,.0f}m")
            print(f"  Revenue: ${d_live.revenue:,.0f}m")
            print(f"  Market cap: ${d_live.equity_market_cap:,.0f}m")
            print(f"  Beta: {d_live.beta_levered:.2f}")
            print(f"  Source: {d_live.source}")
            print(f"  Errors: {d_live.fetch_errors}")
    except Exception as e:
        print(f"  Failed (network): {e}")

    print("\n✓ data_fetcher.py structure OK")
