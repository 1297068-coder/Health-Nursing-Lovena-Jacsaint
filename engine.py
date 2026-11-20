from __future__ import annotations

import copy
import json
import math
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

TWO_PLACES = Decimal("0.01")


def money(value: Any) -> Decimal:
    """Convert any numeric input to a 2-decimal-place Decimal."""
    if isinstance(value, Decimal):
        d = value
    else:
        d = Decimal(str(value))
    return d.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def default_nur2_state() -> Dict[str, Any]:
    """Return the initial Stage 1 state for Team3 (Pathway NUR-2, Precalculus Advanced)."""
    return {
        "team_id": "Team3",
        "pathway_id": "NUR-2",
        "business_name": "Nurse-led health education simulation",
        "selected_course": "Precalculus",
        "selected_level": "Advanced",
        "snapshot_id": "snap-v0",
        "state_version": 0,
        "simulation_date": "2027-01-01",
        "random_seed": 2027,
        "guardrail_notice": (
            "Fictional, nonclinical general health education simulation only. "
            "No diagnosis, treatment, or real patient data."
        ),
        "startup": {
            "owner_contribution": "6000.00",
            "equipment_assets": "1500.00",
            "pre_opening_expense": "500.00",
            "opening_inventory": "0.00",
            "opening_cash": "4000.00",
            "retained_earnings": "-500.00",
        },
        "inputs": {
            "base_price": "25.00",
            "D0": 80,
            "staff_hours": "30.0",
            "hours_per_unit": "0.5",
            "venue_seats": 60,
            "no_show_rate": "0.00",
            "satisfaction_mean": "4.0",
            "refund_amount": "0.00",
            "loan_principal": "0.00",
            "interest": "0.00",
            "additional_capex": "0.00",
            "new_owner_cash": "0.00",
            "loan_cash": "0.00",
        },
        "variable_costs": {
            "educator_delivery": "2.00",
            "materials": "2.00",
            "cleaning_consumables": "1.00",
        },
        "fixed_costs": {
            "venue": "250.00",
            "scheduling_software": "100.00",
            "accessibility_support": "200.00",
            "admin_insurance_assumption": "150.00",
        },
        "current_cash": "4000.00",
        "completed_run_ids": [],
        "ledger": [],
    }


def compute_normal_capacity(staff_hours: Decimal, hours_per_unit: Decimal, venue_seats: int) -> int:
    if hours_per_unit <= Decimal("0"):
        raise ValueError("hours_per_unit must be > 0")
    if staff_hours < Decimal("0") or venue_seats < 0:
        raise ValueError("staff_hours and venue_seats must be >= 0")
    staff_cap = int(math.floor(staff_hours / hours_per_unit))
    return min(staff_cap, int(venue_seats))


def simulate_month(
    state: Dict[str, Any],
    *,
    month: str,
    requested: int,
    run_id: str,
    ad_cost: Decimal = Decimal("0.00"),
    capacity_override: Optional[int] = None,
    price_override: Optional[Decimal] = None,
    no_show_override: Optional[Decimal] = None,
) -> Dict[str, Any]:
    """
    Execute one deterministic monthly period and append to the dated ledger.
    Protects against duplicate run_id execution.
    """
    if not run_id or not run_id.strip():
        raise ValueError("run_id is required")
    if run_id in state["completed_run_ids"]:
        raise ValueError(f"Duplicate run_id rejected: '{run_id}' has already been executed.")
    if requested < 0:
        raise ValueError("requested units must be >= 0")

    inputs = state["inputs"]
    price = money(price_override if price_override is not None else inputs["base_price"])
    if price <= Decimal("0.00"):
        raise ValueError("price must be > 0")

    no_show_rate = Decimal(str(no_show_override if no_show_override is not None else inputs["no_show_rate"]))
    if not (Decimal("0") <= no_show_rate <= Decimal("1")):
        raise ValueError("no_show_rate must be in [0, 1]")

    marketing = money(ad_cost)
    if marketing < Decimal("0.00"):
        raise ValueError("ad_cost / marketing must be >= 0")

    if capacity_override is not None:
        if capacity_override < 0:
            raise ValueError("capacity_override must be >= 0")
        capacity = int(capacity_override)
        mode = "FIXTURE_OVERRIDE"
    else:
        capacity = compute_normal_capacity(
            Decimal(str(inputs["staff_hours"])),
            Decimal(str(inputs["hours_per_unit"])),
            int(inputs["venue_seats"]),
        )
        mode = "NORMAL"

    booked = min(int(requested), capacity)
    attended = int(math.floor(Decimal(booked) * (Decimal("1") - no_show_rate)))
    sold = attended
    unserved_demand = max(0, int(requested) - booked)

    variable_per_unit = sum((money(v) for v in state["variable_costs"].values()), Decimal("0.00"))
    fixed_expense = sum((money(v) for v in state["fixed_costs"].values()), Decimal("0.00"))

    revenue = money(price * Decimal(sold))
    variable_expense = money(variable_per_unit * Decimal(sold))
    total_operating_expense = money(variable_expense + fixed_expense + marketing)
    operating_profit = money(revenue - total_operating_expense)

    refund_amount = money(inputs.get("refund_amount", "0.00"))
    interest = money(inputs.get("interest", "0.00"))
    loan_principal = money(inputs.get("loan_principal", "0.00"))
    additional_capex = money(inputs.get("additional_capex", "0.00"))
    new_owner_cash = money(inputs.get("new_owner_cash", "0.00"))
    loan_cash = money(inputs.get("loan_cash", "0.00"))

    net_profit = money(operating_profit - refund_amount - interest)
    opening_cash = money(state["current_cash"])
    ending_cash = money(
        opening_cash
        + revenue
        - refund_amount
        - variable_expense
        - fixed_expense
        - marketing
        - interest
        - loan_principal
        - additional_capex
        + new_owner_cash
        + loan_cash
    )

    new_version = int(state["state_version"]) + 1
    snapshot_id = f"snap-v{new_version}"

    entry = {
        "transaction_id": f"TXN-{new_version:04d}-{run_id}",
        "run_id": run_id,
        "month": month,
        "date": f"{month}-28",
        "mode": mode,
        "requested": int(requested),
        "capacity": capacity,
        "booked": booked,
        "attended": attended,
        "sold": sold,
        "unserved_demand": unserved_demand,
        "unit_price": str(price),
        "revenue": str(revenue),
        "variable_expense": str(variable_expense),
        "fixed_expense": str(fixed_expense),
        "marketing_expense": str(marketing),
        "total_expense": str(total_operating_expense),
        "operating_profit": str(operating_profit),
        "net_profit": str(net_profit),
        "opening_cash": str(opening_cash),
        "closing_cash": str(ending_cash),
        "state_version": new_version,
    }

    state["current_cash"] = str(ending_cash)
    state["state_version"] = new_version
    state["snapshot_id"] = snapshot_id
    state["simulation_date"] = entry["date"]
    state["completed_run_ids"].append(run_id)
    state["ledger"].append(entry)
    return entry


def replay_fixture_rows(state: Dict[str, Any], rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Replay rows from monthly_fixture.csv using explicit capacity_override."""
    results = []
    for idx, row in enumerate(rows, start=1):
        month = str(row["month"]).strip()
        requested = int(row["requested"])
        cap_override = int(row["capacity_override"])
        ad_cost = money(row["ad_cost"])
        entry = simulate_month(
            state,
            month=month,
            requested=requested,
            run_id=f"fixture-{month}-{idx}",
            ad_cost=ad_cost,
            capacity_override=cap_override,
        )
        results.append(entry)
    return results


# --- Precalculus Course Adapter Functions (NUR-2) ---


def total_cost(q: Decimal | float | int, fixed_cost: Decimal = Decimal("700.00"), var_cost: Decimal = Decimal("5.00")) -> Decimal:
    """Foundation: C(q) = F + v*q for 0 < q <= capacity."""
    q_dec = Decimal(str(q))
    if q_dec <= Decimal("0"):
        raise ValueError("Domain error: q must be > 0 for C(q) and A(q).")
    return money(fixed_cost + var_cost * q_dec)


def average_cost(q: Decimal | float | int, fixed_cost: Decimal = Decimal("700.00"), var_cost: Decimal = Decimal("5.00")) -> Decimal:
    """Foundation: A(q) = F/q + v for 0 < q <= capacity. Undefined at q = 0 (vertical asymptote)."""
    q_dec = Decimal(str(q))
    if q_dec <= Decimal("0"):
        raise ValueError("Undefined at q = 0 (vertical asymptote). Practical domain is 0 < q <= capacity.")
    return money((fixed_cost / q_dec) + var_cost)


def composed_price_model(
    p: float,
    capacity: int = 60,
    p0: float = 25.0,
    d0: float = 80.0,
    v: float = 5.0,
    f: float = 700.0,
) -> Dict[str, float]:
    """
    Applied: Compose q(p) = max(0, 2*D0 - (D0/p0)*p), s(p) = min(capacity, q(p)),
    R(p) = p*s(p), C(s(p)) = F + v*s(p), P(p) = R(p) - C(s(p)) on 0 <= p <= 2*p0.
    """
    slope = d0 / p0  # 80 / 25 = 3.2 for NUR-2
    q_p = max(0.0, 2.0 * d0 - slope * p)
    s_p = min(float(capacity), q_p)
    r_p = p * s_p
    c_p = f + v * s_p
    profit_p = r_p - c_p
    breakpoint_p = p0 * (2.0 - float(capacity) / d0)
    return {
        "price": p,
        "demand_q": q_p,
        "completed_s_continuous": s_p,
        "completed_s_integer": math.floor(s_p),
        "revenue": r_p,
        "cost": c_p,
        "profit": profit_p,
        "capacity_breakpoint_p": breakpoint_p,
    }


def seasonal_demand(t: int, d0: int = 80) -> float:
    """
    Advanced: Seasonal trigonometric demand model
    D(t) = D0 * (1 + 0.20 * sin(2 * pi * (t - 1) / 12))
    Peak at t = 4 (1.2 * D0 = 96), minimum at t = 10 (0.8 * D0 = 64).
    """
    return float(d0) * (1.0 + 0.20 * math.sin(2.0 * math.pi * (t - 1) / 12.0))


# --- JSON Snapshot Save / Restore with Version & Team Checks ---


def export_snapshot_json(state: Dict[str, Any]) -> str:
    payload = copy.deepcopy(state)
    return json.dumps(payload, indent=2)


def import_snapshot_json(raw_json: str, expected_team_id: str, current_state_version: int) -> Dict[str, Any]:
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON format: {exc}") from exc

    required_keys = {
        "team_id",
        "pathway_id",
        "selected_course",
        "selected_level",
        "snapshot_id",
        "state_version",
        "current_cash",
        "inputs",
        "variable_costs",
        "fixed_costs",
        "ledger",
        "completed_run_ids",
    }
    missing = required_keys - set(data.keys())
    if missing:
        raise ValueError(f"Snapshot missing required fields: {sorted(missing)}")

    if data["team_id"] != expected_team_id:
        raise ValueError(
            f"Team ID mismatch: expected '{expected_team_id}', got '{data['team_id']}'."
        )

    incoming_version = int(data["state_version"])
    if incoming_version < int(current_state_version):
        raise ValueError(
            f"Stale snapshot rejected: incoming state_version v{incoming_version} "
            f"is older than current v{current_state_version}."
        )

    if money(data["current_cash"]) < Decimal("0.00"):
        raise ValueError("Invalid negative cash balance in snapshot.")

    return data
