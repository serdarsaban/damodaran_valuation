import streamlit as st
from cost_of_capital import full_cost_of_capital, print_cost_of_capital

st.title("Cost of Capital — Damodaran Method")

st.sidebar.header("Inputs")

ebit              = st.sidebar.number_input("EBIT ($m)",                value=1500.0)
interest_expense  = st.sidebar.number_input("Interest Expense ($m)",    value=300.0)
book_debt         = st.sidebar.number_input("Book Value of Debt ($m)",  value=3000.0)
avg_maturity      = st.sidebar.number_input("Avg Debt Maturity (years)",value=5.0)
equity_mv         = st.sidebar.number_input("Market Cap ($m)",          value=12000.0)
beta_levered      = st.sidebar.number_input("Levered Beta",             value=1.2)
rf                = st.sidebar.number_input("Risk-free Rate",           value=0.045, format="%.3f")
erp               = st.sidebar.number_input("Equity Risk Premium",      value=0.055, format="%.3f")
tax_rate          = st.sidebar.number_input("Marginal Tax Rate",        value=0.25,  format="%.2f")
country_spread    = st.sidebar.number_input("Country Spread (0 = US)",  value=0.0,   format="%.3f")
firm_type         = st.sidebar.selectbox("Firm Type",
                        options=[1, 2, 3],
                        format_func=lambda x: {1:"Large firm", 2:"Small/risky", 3:"Financial"}[x])

if st.sidebar.button("Calculate"):
    r = full_cost_of_capital(
        ebit=ebit, interest_expense=interest_expense,
        book_debt=book_debt, avg_debt_maturity=avg_maturity,
        equity_market_cap=equity_mv, beta_levered=beta_levered,
        rf=rf, erp=erp, tax_rate=tax_rate,
        country_spread=country_spread, firm_type=firm_type,
    )

    col1, col2, col3 = st.columns(3)
    col1.metric("WACC",              f"{r.wacc_result.wacc:.2%}")
    col2.metric("Cost of Equity",    f"{r.beta_result.ke:.2%}")
    col3.metric("Pre-tax Cost Debt", f"{r.debt_cost.kd_pretax:.2%}")

    st.subheader("Synthetic Rating")
    st.write(f"**ICR:** {r.debt_cost.icr:.2f}x → **{r.debt_cost.rating}** "
             f"(spread {r.debt_cost.company_spread:.2%})")

    st.subheader("Beta")
    st.write(f"Unlevered β: {r.beta_result.beta_unlevered:.3f} → "
             f"Re-levered β: {r.beta_result.beta_relevered:.3f}")

    st.subheader("Capital Weights")
    st.write(f"Equity {r.wacc_result.weight_equity:.1%} / "
             f"Debt {r.wacc_result.weight_debt:.1%}")
