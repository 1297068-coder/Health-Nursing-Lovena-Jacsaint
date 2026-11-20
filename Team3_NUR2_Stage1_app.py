from __future__ import annotations

import io
import math
from decimal import Decimal
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

from engine import (
    average_cost,
    composed_price_model,
    compute_normal_capacity,
    default_nur2_state,
    export_snapshot_json,
    import_snapshot_json,
    money,
    replay_fixture_rows,
    seasonal_demand,
    simulate_month,
)

st.set_page_config(
    page_title="Career Venture Lab | Team3 NUR-2 (Precalculus Advanced)",
    layout="wide",
)

if "sim_state" not in st.session_state:
    st.session_state.sim_state = default_nur2_state()

state = st.session_state.sim_state

# Header & Guardrail Banner
st.title("Career Venture Lab — Stage 1 Dashboard")
st.caption(
    f"**Team:** `{state['team_id']}` | **Pathway:** `{state['pathway_id']}` ({state['business_name']}) | "
    f"**Course:** `{state['selected_course']}` | **Level:** `{state['selected_level']}` | "
    f"**Snapshot:** `{state['snapshot_id']}` (v{state['state_version']})"
)
st.info(
    "**Educational Guardrail:** This simulation models fictional, nonclinical general health education "
    "workshops only. Do not diagnose, recommend medical treatment, or enter real patient/student data."
)

tab_overview, tab_inputs, tab_math, tab_tests = st.tabs(
    [
        "1. Overview & Dated Ledger",
        "2. Inputs & Simulation Runner",
        "3. Precalculus Math Panel (Advanced)",
        "4. Stage 1 Acceptance Checks",
    ]
)

# ---------------------------------------------------------------------------
# TAB 1: OVERVIEW & DATED LEDGER
# ---------------------------------------------------------------------------
with tab_overview:
    st.subheader("Financial & Operating Snapshot")
    normal_cap = compute_normal_capacity(
        Decimal(str(state["inputs"]["staff_hours"])),
        Decimal(str(state["inputs"]["hours_per_unit"])),
        int(state["inputs"]["venue_seats"]),
    )
    var_unit = sum((money(v) for v in state["variable_costs"].values()), Decimal("0.00"))
    fix_month = sum((money(v) for v in state["fixed_costs"].values()), Decimal("0.00"))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Current Cash", f"${money(state['current_cash']):,.2f}")
    c2.metric("Monthly Seat Capacity", f"{normal_cap} seats")
    c3.metric("Base Price / Variable Cost", f"${money(state['inputs']['base_price'])} / ${var_unit}")
    c4.metric("Monthly Fixed Expense", f"${fix_month:,.2f}")

    st.markdown("### Dated Event Ledger (Actual Simulated Runs)")
    if state["ledger"]:
        df_ledger = pd.DataFrame(state["ledger"])
        st.dataframe(df_ledger, use_container_width=True)
        csv_bytes = df_ledger.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download Ledger CSV",
            data=csv_bytes,
            file_name=f"{state['team_id']}_{state['pathway_id']}_ledger_v{state['state_version']}.csv",
            mime="text/csv",
        )
    else:
        st.write("No monthly simulation runs committed yet. Use Tab 2 to run a month or replay `monthly_fixture.csv`.")

    st.divider()
    st.markdown("### Durable State Persistence (Save / Load JSON)")
    col_save, col_load = st.columns(2)
    with col_save:
        json_str = export_snapshot_json(state)
        st.download_button(
            "Save Snapshot JSON",
            data=json_str.encode("utf-8"),
            file_name=f"{state['team_id']}_{state['pathway_id']}_{state['snapshot_id']}.json",
            mime="application/json",
        )
        if st.button("Reset Simulation to Post-Startup Baseline ($4,000 Cash)"):
            st.session_state.sim_state = default_nur2_state()
            st.rerun()

    with col_load:
        uploaded_json = st.file_uploader("Restore Snapshot JSON", type=["json"])
        if uploaded_json is not None:
            if st.button("Validate & Import JSON"):
                try:
                    raw = uploaded_json.read().decode("utf-8")
                    restored = import_snapshot_json(
                        raw,
                        expected_team_id=state["team_id"],
                        current_state_version=int(state["state_version"]),
                    )
                    st.session_state.sim_state = restored
                    st.success(f"Restored snapshot `{restored['snapshot_id']}` (v{restored['state_version']}).")
                    st.rerun()
                except ValueError as err:
                    st.error(f"Import Rejected: {err}")

# ---------------------------------------------------------------------------
# TAB 2: INPUTS & SIMULATION RUNNER
# ---------------------------------------------------------------------------
with tab_inputs:
    st.subheader("NUR-2 Editable Parameters & Cost Lines")
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.markdown("**Capacity & Demand Inputs**")
        new_price = st.number_input("Base Price ($/seat)", min_value=1.0, value=float(state["inputs"]["base_price"]), step=1.0)
        new_d0 = st.number_input("Baseline Monthly Demand (D0)", min_value=0, value=int(state["inputs"]["D0"]), step=5)
        new_hours = st.number_input("Educator Staff Hours/Month", min_value=0.0, value=float(state["inputs"]["staff_hours"]), step=1.0)
        new_hpu = st.number_input("Hours per Workshop Seat", min_value=0.1, value=float(state["inputs"]["hours_per_unit"]), step=0.1)
        new_seats = st.number_input("Venue Seat Limit/Month", min_value=0, value=int(state["inputs"]["venue_seats"]), step=5)
        new_noshow = st.slider("No-Show Rate [0, 1]", min_value=0.0, max_value=1.0, value=float(state["inputs"]["no_show_rate"]), step=0.05)

    with col_b:
        st.markdown("**Variable Costs ($/attended seat)**")
        v_edu = st.number_input("Educator Delivery ($)", min_value=0.0, value=float(state["variable_costs"]["educator_delivery"]), step=0.5)
        v_mat = st.number_input("Workshop Materials ($)", min_value=0.0, value=float(state["variable_costs"]["materials"]), step=0.5)
        v_cln = st.number_input("Cleaning Consumables ($)", min_value=0.0, value=float(state["variable_costs"]["cleaning_consumables"]), step=0.5)

    with col_c:
        st.markdown("**Fixed Monthly Costs ($/month)**")
        f_ven = st.number_input("Venue Rental ($)", min_value=0.0, value=float(state["fixed_costs"]["venue"]), step=10.0)
        f_sof = st.number_input("Scheduling Software ($)", min_value=0.0, value=float(state["fixed_costs"]["scheduling_software"]), step=10.0)
        f_acc = st.number_input("Accessibility Support ($)", min_value=0.0, value=float(state["fixed_costs"]["accessibility_support"]), step=10.0)
        f_adm = st.number_input("Admin & Insurance ($)", min_value=0.0, value=float(state["fixed_costs"]["admin_insurance_assumption"]), step=10.0)

    if st.button("Save Parameter Edits"):
        state["inputs"]["base_price"] = str(money(new_price))
        state["inputs"]["D0"] = int(new_d0)
        state["inputs"]["staff_hours"] = str(new_hours)
        state["inputs"]["hours_per_unit"] = str(new_hpu)
        state["inputs"]["venue_seats"] = int(new_seats)
        state["inputs"]["no_show_rate"] = str(new_noshow)
        state["variable_costs"] = {
            "educator_delivery": str(money(v_edu)),
            "materials": str(money(v_mat)),
            "cleaning_consumables": str(money(v_cln)),
        }
        state["fixed_costs"] = {
            "venue": str(money(f_ven)),
            "scheduling_software": str(money(f_sof)),
            "accessibility_support": str(money(f_acc)),
            "admin_insurance_assumption": str(money(f_adm)),
        }
        st.success("Parameters updated (scenarios do not modify the dated ledger until committed below).")

    st.divider()
    st.markdown("### Run Single Simulated Month (Normal Mode)")
    r1, r2, r3, r4 = st.columns(4)
    run_month_str = r1.text_input("Simulation Month (YYYY-MM)", value="2027-01")
    run_requested = r2.number_input("Requested Workshop Seats", min_value=0, value=int(state["inputs"]["D0"]), step=1)
    run_ad_cost = r3.number_input("Approved Campaign Spend ($)", min_value=0.0, value=0.0, step=25.0)
    run_id_str = r4.text_input("Unique Run ID", value=f"run-{state['state_version'] + 1:03d}")

    if st.button("Commit Monthly Run to Ledger"):
        try:
            entry = simulate_month(
                state,
                month=run_month_str,
                requested=int(run_requested),
                run_id=run_id_str,
                ad_cost=money(run_ad_cost),
            )
            st.success(
                f"Committed `{entry['transaction_id']}`: Sold {entry['sold']} seats | "
                f"Revenue ${entry['revenue']} | Profit ${entry['operating_profit']} | "
                f"Closing Cash ${entry['closing_cash']}"
            )
        except ValueError as exc:
            st.error(str(exc))

    st.divider()
    st.markdown("### Fixture-Test Mode (`sample_data/monthly_fixture.csv`)")
    st.warning(
        "**Fixture Mode Notice:** Replaying `monthly_fixture.csv` resets to post-startup baseline ($4,000 cash) "
        "and applies explicit `capacity_override` values to verify ledger math. Do not mix fixture runs with normal runs."
    )
    fixture_path = Path("sample_data/monthly_fixture.csv")
    if fixture_path.exists():
        df_fix = pd.read_csv(fixture_path)
        st.dataframe(df_fix, use_container_width=True)
        if st.button("Reset & Replay 3-Month Acceptance Fixture"):
            fresh = default_nur2_state()
            replay_fixture_rows(fresh, df_fix.to_dict(orient="records"))
            st.session_state.sim_state = fresh
            st.success("Replayed 3-month fixture cleanly! Check Tab 1 Ledger to inspect results.")
            st.rerun()

# ---------------------------------------------------------------------------
# TAB 3: PRECALCULUS MATH PANEL (ADVANCED)
# ---------------------------------------------------------------------------
with tab_math:
    st.subheader("Precalculus Math Skills & Challenge Level Panel")
    cap_now = compute_normal_capacity(
        Decimal(str(state["inputs"]["staff_hours"])),
        Decimal(str(state["inputs"]["hours_per_unit"])),
        int(state["inputs"]["venue_seats"]),
    )
    p0_now = float(state["inputs"]["base_price"])
    d0_now = int(state["inputs"]["D0"])
    v_now = float(sum((money(v) for v in state["variable_costs"].values()), Decimal("0.00")))
    f_now = float(sum((money(v) for v in state["fixed_costs"].values()), Decimal("0.00")))

    mode_choice = st.radio(
        "Inspect Precalculus Progression Task (Current Approved Level: Advanced):",
        [
            "Foundation: Average Cost Rational Function A(q)",
            "Applied: Composed Demand, Revenue, Cost & Piecewise Profit P(p)",
            "Advanced: Seasonal Trigonometric Demand D(t) & Capacity Clipping",
        ],
    )

    if mode_choice.startswith("Foundation"):
        st.markdown(
            f"""
            - **Course / Skill / Level:** Precalculus | Rational Functions & Asymptotes | Foundation
            - **Equations:** $C(q) = {f_now:.0f} + {v_now:.0f}q$ and $A(q) = \frac{{{f_now:.0f}}}{{q}} + {v_now:.0f}$
            - **Domain & Units:** $0 < q \le {cap_now}$ attended workshop seats/month; $A(q)$ in USD/seat.
            - **Asymptotes:** Vertical asymptote at $q = 0$ ($A(0)$ is undefined); horizontal asymptote at $y = {v_now:.2f}$/seat.
            - **Interpretation Prompt:** Why does $A(q)$ decrease rapidly as attendance rises toward capacity {cap_now}, and why is $q = 0$ excluded?
            """
        )
        q_vals = np.linspace(1, max(1, cap_now), 100)
        a_vals = f_now / q_vals + v_now

        fig, ax = plt.subplots(figsize=(7, 3.8))
        ax.plot(q_vals, a_vals, label=f"A(q) = {f_now:.0f}/q + {v_now:.0f}", color="#1f77b4", linewidth=2)
        ax.axhline(v_now, color="#d95f02", linestyle="--", label=f"Horizontal Asymptote y = ${v_now:.2f}")
        ax.axvline(0, color="#7570b3", linestyle=":", label="Vertical Asymptote q = 0 (Undefined)")
        ax.set_xlabel("Attended Workshop Seats q (seats/month)")
        ax.set_ylabel("Average Cost A(q) ($/seat)")
        ax.set_title(f"Team3 NUR-2 Average Cost Curve (Snapshot {state['snapshot_id']}, 0 < q <= {cap_now})")
        ax.legend()
        ax.grid(True, alpha=0.3)
        st.pyplot(fig)

        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight")
        st.download_button("Download Foundation Graph (PNG)", buf.getvalue(), "nur2_foundation_avg_cost.png", "image/png")

        sample_qs = [q for q in [1, 5, 10, 20, 30, 40, 50, cap_now] if 1 <= q <= cap_now]
        df_f = pd.DataFrame(
            [{"Seats (q)": q, "Total Cost C(q) ($)": f_now + v_now * q, "Average Cost A(q) ($/seat)": float(average_cost(q, money(f_now), money(v_now)))} for q in sorted(set(sample_qs))]
        )
        st.dataframe(df_f, use_container_width=True)

    elif mode_choice.startswith("Applied"):
        bp_price = p0_now * (2.0 - cap_now / d0_now) if d0_now > 0 else 0.0
        st.markdown(
            f"""
            - **Course / Skill / Level:** Precalculus | Function Composition & Piecewise Models | Applied
            - **Equations:** $q(p) = \max(0, {2*d0_now} - {d0_now/p0_now:.2f}p)$, $s(p) = \min({cap_now}, q(p))$, $R(p) = p \cdot s(p)$, $C(s(p)) = {f_now:.0f} + {v_now:.0f}s(p)$, $P(p) = R(p) - C(s(p))$
            - **Price Domain & Breakpoint:** $0 \le p \le {2*p0_now:.2f}$ USD/seat; capacity breakpoint at $p = \${bp_price:.2f}$.
            - **Interpretation Prompt:** How does the capacity cap ($s \le {cap_now}$) alter the profit curve for prices below $\${bp_price:.2f}$?
            """
        )
        prices = np.linspace(0, 2 * p0_now, 101)
        rows_app = [composed_price_model(float(p), cap_now, p0_now, float(d0_now), v_now, f_now) for p in prices]
        df_app = pd.DataFrame(rows_app)

        fig, ax = plt.subplots(figsize=(7, 3.8))
        ax.plot(df_app["price"], df_app["revenue"], label="Revenue R(p)", linestyle="--", color="#1b9e77")
        ax.plot(df_app["price"], df_app["cost"], label="Total Cost C(s(p))", linestyle=":", color="#d95f02")
        ax.plot(df_app["price"], df_app["profit"], label="Continuous Profit P(p)", linewidth=2.2, color="#7570b3")
        ax.axhline(0, color="black", linewidth=0.8)
        ax.axvline(bp_price, color="#e7298a", linestyle="-.", label=f"Capacity Breakpoint p = ${bp_price:.2f}")
        ax.set_xlabel("Workshop Seat Price p ($/seat)")
        ax.set_ylabel("Monthly Dollars ($)")
        ax.set_title(f"Team3 NUR-2 Composed Profit & Capacity Breakpoint (Snapshot {state['snapshot_id']})")
        ax.legend()
        ax.grid(True, alpha=0.3)
        st.pyplot(fig)

        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight")
        st.download_button("Download Applied Graph (PNG)", buf.getvalue(), "nur2_applied_composed_profit.png", "image/png")

        test_prices = [15.0, 20.0, 25.0, 30.0, 35.0, 40.0]
        df_table = pd.DataFrame([composed_price_model(p, cap_now, p0_now, float(d0_now), v_now, f_now) for p in test_prices])
        st.dataframe(df_table, use_container_width=True)

    else:
        st.markdown(
            f"""
            - **Course / Skill / Level:** Precalculus | Sinusoidal Modeling & Domain Constraints | Advanced
            - **Equation:** $D(t) = {d0_now} \left(1 + 0.20 \sin\left(\frac{{2\pi(t - 1)}}{{12}}\right)\right)$ for month index $t \in \{{1, 2, \dots, 12\}}$
            - **Assumptions & Limits:** Period = 12 months, amplitude = $0.20 D_0 = {0.2*d0_now:.0f}$ seats, peak at $t=4$ ($1.2 D_0 = {1.2*d0_now:.0f}$), trough at $t=10$ ($0.8 D_0 = {0.8*d0_now:.0f}$). Assumed teaching seasonality; extrapolation beyond 12 months requires empirical data.
            - **Interpretation Prompt:** In which months does capacity ({cap_now} seats) clip seasonal demand, creating unserved demand?
            """
        )
        months_t = list(range(1, 13))
        rows_adv = []
        for t in months_t:
            d_cont = seasonal_demand(t, d0_now)
            d_int = math.floor(d_cont)
            realized = min(cap_now, d_int)
            rows_adv.append(
                {
                    "Month Index (t)": t,
                    "Continuous Seasonal Demand D(t)": round(d_cont, 2),
                    "Integer Requested Seats": d_int,
                    "Capacity Limit": cap_now,
                    "Realized Sales (Clipped)": realized,
                    "Unserved Demand": max(0, d_int - realized),
                }
            )
        df_adv = pd.DataFrame(rows_adv)

        fig, ax = plt.subplots(figsize=(7, 3.8))
        ax.plot(df_adv["Month Index (t)"], df_adv["Continuous Seasonal Demand D(t)"], marker="o", label="Continuous Seasonal Demand D(t)", color="#1f77b4")
        ax.bar(df_adv["Month Index (t)"], df_adv["Realized Sales (Clipped)"], alpha=0.45, label="Realized Sales (Clipped at Capacity)", color="#1b9e77")
        ax.axhline(cap_now, color="#d95f02", linestyle="--", label=f"Monthly Capacity = {cap_now} seats")
        ax.set_xticks(months_t)
        ax.set_xlabel("Month Index t (1 = Jan, 4 = Apr Peak, 10 = Oct Trough)")
        ax.set_ylabel("Workshop Seats")
        ax.set_title(f"Team3 NUR-2 Seasonal Demand vs. Capacity Clipping (Snapshot {state['snapshot_id']})")
        ax.legend()
        ax.grid(True, alpha=0.3)
        st.pyplot(fig)

        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight")
        st.download_button("Download Advanced Seasonal Graph (PNG)", buf.getvalue(), "nur2_advanced_seasonal.png", "image/png")
        st.dataframe(df_adv, use_container_width=True)
        st.download_button(
            "Download Seasonal Projection Table (CSV)",
            df_adv.to_csv(index=False).encode("utf-8"),
            "nur2_advanced_seasonal_table.csv",
            "text/csv",
        )

# ---------------------------------------------------------------------------
# TAB 4: STAGE 1 ACCEPTANCE CHECKS
# ---------------------------------------------------------------------------
with tab_tests:
    st.subheader("Stage 1 Functional & Mathematical Acceptance Checks")
    st.write("Run `pytest` in your terminal or click below to execute live in-app verification checks.")
    if st.button("Run Stage 1 Verification Suite"):
        checks = []
        # 1. Fixture replay
        s_fix = default_nur2_state()
        df_f = pd.read_csv("sample_data/monthly_fixture.csv")
        res = replay_fixture_rows(s_fix, df_f.to_dict(orient="records"))
        fix_ok = (
            res[0]["sold"] == 60 and res[0]["closing_cash"] == "4500.00"
            and res[1]["sold"] == 60 and res[1]["closing_cash"] == "4900.00"
            and res[2]["sold"] == 45 and res[2]["closing_cash"] == "5100.00"
        )
        checks.append(("3-Month Fixture Replay", "PASS" if fix_ok else "FAIL", f"Closing cash sequence: {[r['closing_cash'] for r in res]}"))

        # 2. NUR No-Show Test
        s_ns = default_nur2_state()
        e_ns = simulate_month(s_ns, month="2027-01", requested=80, run_id="ns-test", no_show_override=Decimal("0.20"))
        ns_ok = (
            e_ns["booked"] == 60 and e_ns["attended"] == 48
            and e_ns["revenue"] == "1200.00" and e_ns["variable_expense"] == "240.00"
            and e_ns["operating_profit"] == "260.00"
        )
        checks.append(("NUR No-Show Rate 20% Test", "PASS" if ns_ok else "FAIL", f"Attended={e_ns['attended']}, Profit=${e_ns['operating_profit']}"))

        # 3. Precalculus Checks
        a60_ok = average_cost(60) == Decimal("16.67")
        seas_ok = round(seasonal_demand(4, 80), 4) == 96.0 and round(seasonal_demand(10, 80), 4) == 64.0
        checks.append(("Precalculus A(60) & Seasonal Extrema", "PASS" if (a60_ok and seas_ok) else "FAIL", f"A(60)=${average_cost(60)}, D(4)={seasonal_demand(4,80)}, D(10)={seasonal_demand(10,80)}"))

        # 4. Zero Sales Check
        s_zero = default_nur2_state()
        e_zero = simulate_month(s_zero, month="2027-01", requested=0, run_id="zero-test")
        zero_ok = e_zero["revenue"] == "0.00" and e_zero["operating_profit"] == "-700.00"
        checks.append(("Zero Sales Edge Case", "PASS" if zero_ok else "FAIL", f"Revenue=${e_zero['revenue']}, Profit=${e_zero['operating_profit']}"))

        st.table(pd.DataFrame(checks, columns=["Acceptance Test", "Status", "Evidence"]))
