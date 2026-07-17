"""Headless route-planning service over the public Spansh + EDSM APIs.

Backs the web MCDU's SEC F-PLN (secondary route: FUEL-SAFE <-> FAST/RISKY)
and DIR (direct-to candidates) pages without touching the game. Everything
here is pure request/response plumbing plus a small in-memory state holder;
the blocking calls are meant to be driven from the webserver through
run_in_executor (same pattern CalibrationStore/calibration uses).

Plotting profiles, normalised into one Route dict:
  * FUEL-SAFE — Spansh exact plotter (/api/generic/route): every jump is
    modelled with fuel usage, so scoop stops (must_refuel) are known; risk LOW.
  * FAST      — same exact plotter with use_supercharge=1: neutron/WD boosts
    (incl. the SCO MkII x6 drive) with the fuel model intact; risk HIGH.
  * ULTRA     — Spansh neutron plotter (/api/route): system_jumps are the
    neutron re-plot WAYPOINTS (jumps-per-leg), fuel is NOT modelled. Kept for
    very long hauls where the exact plotter is too slow; not exposed in MCDU.

The FSD constant tables below are game data (sizes/classes/optimal masses,
incl. the SCO overcharge drives and the guardian FSD boosters). The values
were verified against the Auto_Neutron reference; only the data is reused,
the code is our own.

This module never imports anything from the ED_AP core at import time (a
TYPE_CHECKING hint only), so `import RoutePlanner` stays cheap and side-effect
free. Clients take an injectable ``session`` so the offline QA can drive them
with a fake session that returns canned responses.
"""

from __future__ import annotations

import copy
import hashlib
import json
import threading
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:  # avoid importing the core at runtime
    from ED_AP import EDAutopilot


class PlotError(Exception):
    """Human-readable failure — surfaced to the client as {"type": "error"}."""


# --------------------------------------------------------------------------- #
# FSD data tables (game data; values verified against Auto_Neutron)
# --------------------------------------------------------------------------- #

# Size exponent (fuel_power) keyed by drive size.
FSD_SIZE_CONST: dict[int, float] = {2: 2.0, 3: 2.15, 4: 2.3, 5: 2.45, 6: 2.6, 7: 2.75, 8: 2.9}

# Linear constant keyed by drive class (1=E .. 5=A) for the standard drives.
FSD_CLASS_CONST: dict[int, int] = {1: 11, 2: 10, 3: 8, 4: 10, 5: 12}

# Linear constant for the SCO (overcharge) drives.
SCO_CLASS_CONST: dict[int, int] = {1: 8, 2: 12, 3: 12, 4: 12, 5: 13}

# The SCO MkII overcharge-booster drive (the single size8/A item) has its OWN
# fuel-equation constants — NOT the size-8 table values. Source: the Spansh
# exact-plotter website submission for the owner's explorer_nx SLEF build
# (job 18743748…, 2026-07-17): fuel_power=2.5025, fuel_multiplier=0.011.
# Cross-check: with these, ShipFSD max range = 78.38 LY vs EDSY's 78.41.
SCO_MKII_CLASS_CONST: dict[int, int] = {5: 11}
SCO_MKII_SIZE_CONST = 2.5025

# Default neutron supercharge multiplier; the MkII booster drive overrides it.
DEFAULT_SUPERCHARGE_MULTIPLIER = 4

# Guardian FSD booster range boost (LY), keyed by the module item id.
GUARDIAN_BOOSTER_RANGE: dict[str, float] = {
    "int_guardianfsdbooster_size1": 4.0,
    "int_guardianfsdbooster_size2": 6.0,
    "int_guardianfsdbooster_size3": 7.75,
    "int_guardianfsdbooster_size4": 9.25,
    "int_guardianfsdbooster_size5": 10.5,
}

# item-id -> (size, class, max_fuel_per_jump, optimal_mass[, supercharge_multiplier]).
# Standard hyperdrives, the SCO ("overcharge") variants, plus the single
# size8/class5 overcharge-booster MkII entry.
FSD_BASE: dict[str, tuple] = {
    # --- standard drives ---
    "int_hyperdrive_size2_class1": (2, 1, 0.60, 48),
    "int_hyperdrive_size2_class2": (2, 2, 0.60, 54),
    "int_hyperdrive_size2_class3": (2, 3, 0.60, 60),
    "int_hyperdrive_size2_class4": (2, 4, 0.80, 75),
    "int_hyperdrive_size2_class5": (2, 5, 0.90, 90),
    "int_hyperdrive_size3_class1": (3, 1, 1.20, 80),
    "int_hyperdrive_size3_class2": (3, 2, 1.20, 90),
    "int_hyperdrive_size3_class3": (3, 3, 1.20, 100),
    "int_hyperdrive_size3_class4": (3, 4, 1.50, 125),
    "int_hyperdrive_size3_class5": (3, 5, 1.80, 150),
    "int_hyperdrive_size4_class1": (4, 1, 2.00, 280),
    "int_hyperdrive_size4_class2": (4, 2, 2.00, 315),
    "int_hyperdrive_size4_class3": (4, 3, 2.00, 350),
    "int_hyperdrive_size4_class4": (4, 4, 2.50, 438),
    "int_hyperdrive_size4_class5": (4, 5, 3.00, 525),
    "int_hyperdrive_size5_class1": (5, 1, 3.30, 560),
    "int_hyperdrive_size5_class2": (5, 2, 3.30, 630),
    "int_hyperdrive_size5_class3": (5, 3, 3.30, 700),
    "int_hyperdrive_size5_class4": (5, 4, 4.10, 875),
    "int_hyperdrive_size5_class5": (5, 5, 5.00, 1050),
    "int_hyperdrive_size6_class1": (6, 1, 5.30, 960),
    "int_hyperdrive_size6_class2": (6, 2, 5.30, 1080),
    "int_hyperdrive_size6_class3": (6, 3, 5.30, 1200),
    "int_hyperdrive_size6_class4": (6, 4, 6.60, 1500),
    "int_hyperdrive_size6_class5": (6, 5, 8.00, 1800),
    "int_hyperdrive_size7_class1": (7, 1, 8.50, 1440),
    "int_hyperdrive_size7_class2": (7, 2, 8.50, 1620),
    "int_hyperdrive_size7_class3": (7, 3, 8.50, 1800),
    "int_hyperdrive_size7_class4": (7, 4, 10.60, 2250),
    "int_hyperdrive_size7_class5": (7, 5, 12.80, 2700),
    # --- overcharge (SCO) drives ---
    "int_hyperdrive_overcharge_size2_class1": (2, 1, 0.60, 60),
    "int_hyperdrive_overcharge_size2_class2": (2, 2, 0.90, 90),
    "int_hyperdrive_overcharge_size2_class3": (2, 3, 0.90, 90),
    "int_hyperdrive_overcharge_size2_class4": (2, 4, 0.90, 90),
    "int_hyperdrive_overcharge_size2_class5": (2, 5, 1.00, 100),
    "int_hyperdrive_overcharge_size3_class1": (3, 1, 1.20, 100),
    "int_hyperdrive_overcharge_size3_class2": (3, 2, 1.80, 150),
    "int_hyperdrive_overcharge_size3_class3": (3, 3, 1.80, 150),
    "int_hyperdrive_overcharge_size3_class4": (3, 4, 1.80, 150),
    "int_hyperdrive_overcharge_size3_class5": (3, 5, 1.90, 167),
    "int_hyperdrive_overcharge_size4_class1": (4, 1, 2.00, 350),
    "int_hyperdrive_overcharge_size4_class2": (4, 2, 3.00, 525),
    "int_hyperdrive_overcharge_size4_class3": (4, 3, 3.00, 525),
    "int_hyperdrive_overcharge_size4_class4": (4, 4, 3.00, 525),
    "int_hyperdrive_overcharge_size4_class5": (4, 5, 3.20, 585),
    "int_hyperdrive_overcharge_size5_class1": (5, 1, 3.30, 700),
    "int_hyperdrive_overcharge_size5_class2": (5, 2, 5.00, 1050),
    "int_hyperdrive_overcharge_size5_class3": (5, 3, 5.00, 1050),
    "int_hyperdrive_overcharge_size5_class4": (5, 4, 5.00, 1050),
    "int_hyperdrive_overcharge_size5_class5": (5, 5, 5.20, 1175),
    "int_hyperdrive_overcharge_size6_class1": (6, 1, 5.30, 1200),
    "int_hyperdrive_overcharge_size6_class2": (6, 2, 8.00, 1800),
    "int_hyperdrive_overcharge_size6_class3": (6, 3, 8.00, 1800),
    "int_hyperdrive_overcharge_size6_class4": (6, 4, 8.00, 1800),
    "int_hyperdrive_overcharge_size6_class5": (6, 5, 8.30, 2000),
    "int_hyperdrive_overcharge_size7_class1": (7, 1, 8.50, 1800),
    "int_hyperdrive_overcharge_size7_class2": (7, 2, 12.80, 2700),
    "int_hyperdrive_overcharge_size7_class3": (7, 3, 12.80, 2700),
    "int_hyperdrive_overcharge_size7_class4": (7, 4, 12.80, 2700),
    "int_hyperdrive_overcharge_size7_class5": (7, 5, 13.10, 3000),
    "int_hyperdrive_overcharge_size8_class1": (8, 1, 13.60, 2800),
    "int_hyperdrive_overcharge_size8_class2": (8, 2, 20.40, 4200),
    "int_hyperdrive_overcharge_size8_class3": (8, 3, 20.40, 4200),
    "int_hyperdrive_overcharge_size8_class4": (8, 4, 20.40, 4200),
    "int_hyperdrive_overcharge_size8_class5": (8, 5, 20.70, 4670),
    # size8/A overcharge-booster MkII: distinct linear constant + supercharge mult.
    "int_hyperdrive_overcharge_size8_class5_overchargebooster_mkii": (8, 5, 6.80, 4670, 6),
}


# --------------------------------------------------------------------------- #
# Ship / loadout -> plot parameters
# --------------------------------------------------------------------------- #

def _class_const_for(item_id: str, drive_class: int) -> int:
    """Pick the linear constant table matching the drive family (item id)."""
    if "overcharge" in item_id and "mkii" in item_id:
        table = SCO_MKII_CLASS_CONST
    elif "overcharge" in item_id:
        table = SCO_CLASS_CONST
    else:
        table = FSD_CLASS_CONST
    if drive_class not in table:
        raise PlotError(f"unknown FSD class {drive_class} for drive {item_id!r}")
    return table[drive_class]


def _guardian_boost(modules: list) -> float:
    """Range boost (LY) from a fitted guardian FSD booster, 0.0 if none."""
    for module in modules or []:
        item = (module.get("Item") or "").lower()
        if item in GUARDIAN_BOOSTER_RANGE:
            return GUARDIAN_BOOSTER_RANGE[item]
    return 0.0


def _resolve_fsd(loadout: dict) -> dict:
    """Resolve the FSD + ship masses from a raw journal Loadout event.

    Applies Engineering.Modifiers overrides (FSDOptimalMass / MaxFuelPerJump).
    Raises PlotError when the loadout has no known FSD or is missing the mass /
    fuel-capacity fields needed by the plotter.
    """
    if not isinstance(loadout, dict):
        raise PlotError("no ship loadout available (fly/outfit once to emit a Loadout event)")

    modules = loadout.get("Modules") or []
    fsd_module = None
    for module in modules:
        if (module.get("Item") or "").lower() in FSD_BASE:
            fsd_module = module
            break
    if fsd_module is None:
        raise PlotError("no frame shift drive found in the ship loadout")

    item_id = fsd_module["Item"].lower()
    base = FSD_BASE[item_id]
    size, drive_class, max_fuel, optimal_mass = base[0], base[1], float(base[2]), float(base[3])
    sc_mult = base[4] if len(base) > 4 else DEFAULT_SUPERCHARGE_MULTIPLIER

    if size not in FSD_SIZE_CONST:
        raise PlotError(f"unknown FSD size {size} for drive {item_id!r}")
    size_const = FSD_SIZE_CONST[size]
    if "overcharge" in item_id and "mkii" in item_id:
        size_const = SCO_MKII_SIZE_CONST   # MkII: own exponent, see table note
    class_const = _class_const_for(item_id, drive_class)

    # Engineering overrides (blueprints tweak optimal mass / max fuel per jump).
    engineering = fsd_module.get("Engineering") or {}
    for modifier in engineering.get("Modifiers", []) or []:
        label = modifier.get("Label")
        if label == "FSDOptimalMass" and modifier.get("Value") is not None:
            optimal_mass = float(modifier["Value"])
        elif label == "MaxFuelPerJump" and modifier.get("Value") is not None:
            max_fuel = float(modifier["Value"])

    unladen_mass = loadout.get("UnladenMass")
    fuel_capacity = loadout.get("FuelCapacity") or {}
    tank_size = fuel_capacity.get("Main")
    reserve_size = fuel_capacity.get("Reserve")
    if unladen_mass is None or tank_size is None or reserve_size is None:
        raise PlotError("loadout is missing UnladenMass / FuelCapacity fields")

    return {
        "size_const": size_const,
        "class_const": class_const,
        "supercharge_multiplier": sc_mult,
        "optimal_mass": optimal_mass,
        "max_fuel": max_fuel,
        "range_boost": _guardian_boost(modules),
        "unladen_mass": float(unladen_mass),
        "tank_size": float(tank_size),
        "internal_tank_size": float(reserve_size),
    }


def ship_plot_params(loadout: dict, cargo: float = 0.0) -> dict:
    """Build the Spansh galaxy-plotter (generic/route) form params for a ship.

    `cargo` is the LIVE cargo tonnage (Status.json) — mass changes range and
    fuel burn, so a loaded ship must not be plotted as empty. See
    design/route-planner-backend.md 2.2. Raises PlotError when the loadout
    has no FSD or is missing required fields.
    """
    r = _resolve_fsd(loadout)
    # base_mass = hull + reserve tank (the always-present fuel), per the plotter.
    base_mass = r["unladen_mass"] + r["internal_tank_size"]
    return {
        "fuel_power": r["size_const"],
        "fuel_multiplier": r["class_const"] / 1000.0,
        "optimal_mass": r["optimal_mass"],
        "supercharge_multiplier": r["supercharge_multiplier"],
        "base_mass": base_mass,
        "tank_size": r["tank_size"],
        "internal_tank_size": r["internal_tank_size"],
        "max_fuel_per_jump": r["max_fuel"],
        "range_boost": r["range_boost"],
        "cargo": round(float(cargo or 0.0), 2),
        "is_supercharged": 0,
        "use_supercharge": 0,
        "use_injections": 0,
        "exclude_secondary": 1,
    }


class ShipFSD:
    """Jump-range / fuel-cost physics for one resolved loadout.

    Single source of truth for the game's FSD equations — the validator,
    the mechanics bench and the (future) route executor must all compute
    through this class so their numbers agree.

        base range   R(fuel) = opt/mass * (1000*min(max_fuel,fuel)/class_const)**(1/power)
        full range   R_tot   = (R + boost) * supercharge      # guardian booster is a
                                                              # flat +LY, neutron/WD
                                                              # multiplies the total
        fuel cost    f(d)    = class_const/1000 * (d_eff*mass/opt)**power
                     d_eff   = d/supercharge * R/(R + boost)  # the boosted/supercharged
                                                              # LY are fuel-free

    d_eff is exact, not an approximation: a jump at the full boosted+supercharged
    range costs exactly max_fuel_per_jump. Cross-checked leg-by-leg against the
    Spansh exact plotter by tools/route_mechanics_bench.py.
    """

    def __init__(self, loadout: dict):
        r = _resolve_fsd(loadout)
        self.size_const = r["size_const"]
        self.class_const = r["class_const"]
        self.optimal_mass = r["optimal_mass"]
        self.max_fuel = r["max_fuel"]
        self.range_boost = r["range_boost"]
        self.supercharge_multiplier = r["supercharge_multiplier"]
        self.unladen_mass = r["unladen_mass"]
        self.tank_size = r["tank_size"]
        self.reserve_size = r["internal_tank_size"]

    def mass(self, fuel: float, cargo: float = 0.0) -> float:
        """Total ship mass with `fuel` t in the main tank (reserve always full)."""
        return self.unladen_mass + self.reserve_size + fuel + cargo

    def base_range(self, fuel: float, cargo: float = 0.0) -> float:
        """Unboosted range (LY) for the fuel actually in the tank."""
        usable = min(self.max_fuel, max(fuel, 0.0))
        if usable <= 0:
            return 0.0
        core = (1000.0 * usable / self.class_const) ** (1.0 / self.size_const)
        return self.optimal_mass * core / self.mass(fuel, cargo)

    def jump_range(self, fuel: float, cargo: float = 0.0, supercharge: float = 1.0) -> float:
        """Max jump distance (LY): guardian boost added, then supercharge applied."""
        return (self.base_range(fuel, cargo) + self.range_boost) * supercharge

    def fuel_cost(self, dist: float, fuel: float, cargo: float = 0.0,
                  supercharge: float = 1.0) -> float:
        """Fuel (t) burned by a jump of `dist` LY with `fuel` t aboard."""
        if dist <= 0:
            return 0.0
        base = self.base_range(fuel, cargo)
        d_eff = dist / supercharge
        if self.range_boost > 0 and base > 0:
            d_eff *= base / (base + self.range_boost)
        mass = self.mass(fuel, cargo)
        return (self.class_const / 1000.0) * (d_eff * mass / self.optimal_mass) ** self.size_const


def ship_fingerprint(loadout: dict) -> str:
    """Stable fingerprint of everything jump-physics-relevant in a loadout.

    A route remembers the fingerprint it was plotted for; the executor
    refuses to fly a plan whose ship has since changed (outfitting, another
    ship, engineering) and flags a mid-flight change. Only fields that alter
    range/fuel take part — cosmetic module changes don't invalidate a plan.
    """
    fsd_item = ""
    fsd_mods = []
    booster = ""
    for module in (loadout or {}).get("Modules") or []:
        item = (module.get("Item") or "").lower()
        if item in FSD_BASE:
            fsd_item = item
            for mod in (module.get("Engineering") or {}).get("Modifiers", []) or []:
                if mod.get("Label") in ("FSDOptimalMass", "MaxFuelPerJump"):
                    fsd_mods.append((mod["Label"], mod.get("Value")))
        elif item in GUARDIAN_BOOSTER_RANGE:
            booster = item
    key = json.dumps({
        "ship": (loadout or {}).get("Ship"),
        "unladen": (loadout or {}).get("UnladenMass"),
        "fuel": (loadout or {}).get("FuelCapacity"),
        "fsd": fsd_item,
        "mods": sorted(fsd_mods),
        "booster": booster,
    }, sort_keys=True)
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]


def ship_summary(loadout: dict) -> dict:
    """The plan's ship passport: fingerprint + the human-checkable numbers
    (shown in the MCDU so the pilot can be 100% sure what the plan assumes)."""
    fsd = ShipFSD(loadout)
    return {
        "name": (loadout or {}).get("Ship") or "?",
        "fingerprint": ship_fingerprint(loadout),
        "max_range": round(fsd.jump_range(fsd.max_fuel), 2),
        "supercharge_multiplier": fsd.supercharge_multiplier,
        "range_boost": fsd.range_boost,
        "tank": fsd.tank_size,
    }


def max_range_from_loadout(loadout: dict) -> float:
    """Fallback laden(full-tank) jump range (LY) computed from the loadout.

    Used for the FAST profile when the journal did not give us MaxJumpRange.
    """
    fsd = ShipFSD(loadout)
    if fsd.mass(fsd.tank_size) <= 0:
        raise PlotError("invalid ship mass in loadout")
    return fsd.jump_range(fsd.tank_size)


# --------------------------------------------------------------------------- #
# Route normalisation helpers
# --------------------------------------------------------------------------- #

# EDSM's Cloudflare rejects the default python-requests User-Agent with a 403,
# so every default session identifies the app explicitly.
USER_AGENT = "ED_Autopilot-RoutePlanner/1.0"


def _default_session() -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    return session


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _round(value, digits=2):
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _normalize_fast(result: dict, source: str) -> dict:
    """Neutron plotter result -> Route (ULTRA profile). system_jumps are
    WAYPOINTS: 'jumps' is the number of jumps to reach that waypoint, so total
    jumps = sum(jumps)."""
    waypoints = result.get("system_jumps") or []
    systems = []
    total_jumps = 0
    for i, wp in enumerate(waypoints):
        total_jumps += int(wp.get("jumps") or 0)
        systems.append({
            "system": wp.get("system", ""),
            "dist_ly": None if i == 0 else _round(wp.get("distance_jumped")),
            "scoopable": None,  # fuel not modelled on this profile
            "neutron": bool(wp.get("neutron_star")),
            "must_refuel": False,
        })
    destination = result.get("destination_system") or (systems[-1]["system"] if systems else "")
    return {
        "profile": "ULTRA",
        "source": result.get("source_system") or source,
        "destination": destination,
        "jumps": total_jumps,
        "dist_ly": _round(result.get("distance")),
        "scoops": None,
        "risk": "HIGH",
        "plotted_at": _now_iso(),
        "systems": systems,
    }


def _normalize_fuel_safe(result: dict, source: str,
                         profile: str = "FUEL-SAFE", risk: str = "LOW") -> dict:
    """Galaxy (exact) plotter result -> Route. 'jumps' here are EVERY jump with
    fuel usage; scoop stops are the must_refuel legs. jumps = len(systems) - 1.
    fuel_used/fuel_tank carry Spansh's own per-jump fuel model (fuel_tank is
    the level after arriving and refuelling when must_refuel is set)."""
    hops = result.get("jumps") or []
    systems = []
    scoops = 0
    total_dist = 0.0
    for i, hop in enumerate(hops):
        dist = hop.get("distance") or 0.0
        if i > 0:
            total_dist += float(dist)
        must_refuel = bool(hop.get("must_refuel"))
        if must_refuel:
            scoops += 1
        systems.append({
            "system": hop.get("name", ""),
            "dist_ly": None if i == 0 else _round(dist),
            "scoopable": bool(hop.get("is_scoopable")),
            "neutron": bool(hop.get("has_neutron")),
            "must_refuel": must_refuel,
            "fuel_used": None if i == 0 else _round(hop.get("fuel_used")),
            "fuel_tank": _round(hop.get("fuel_in_tank")),
        })
    return {
        "profile": profile,
        "source": systems[0]["system"] if systems else source,
        "destination": systems[-1]["system"] if systems else "",
        "jumps": max(len(systems) - 1, 0),
        "dist_ly": _round(total_dist),
        "scoops": scoops,
        "risk": risk,
        "plotted_at": _now_iso(),
        "systems": systems,
    }


# --------------------------------------------------------------------------- #
# API clients (injectable session for offline QA)
# --------------------------------------------------------------------------- #

class SpanshClient:
    """Spansh neutron + galaxy plotters (submit job, poll for result)."""

    FAST_URL = "https://spansh.co.uk/api/route"
    FUEL_SAFE_URL = "https://spansh.co.uk/api/generic/route"
    RESULTS_URL = "https://spansh.co.uk/api/results/"

    def __init__(self, session=None, poll_interval: float = 3.0, timeout: float = 300.0):
        self.session = session or _default_session()
        self.poll_interval = poll_interval
        self.timeout = timeout

    def _submit(self, url: str, form: dict) -> str:
        try:
            resp = self.session.post(url, data=form)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as e:  # noqa: BLE001 — surface any transport/parse error
            raise PlotError(f"route submission failed: {e}")
        job = payload.get("job") if isinstance(payload, dict) else None
        if not job:
            raise PlotError(f"route API returned no job id: {payload!r}")
        return job

    def _poll(self, job: str) -> dict:
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                resp = self.session.get(self.RESULTS_URL + job)
                resp.raise_for_status()
                payload = resp.json()
            except Exception as e:  # noqa: BLE001
                raise PlotError(f"route polling failed: {e}")

            if isinstance(payload, dict):
                result = payload.get("result")
                if result:
                    return result
                if payload.get("status") in ("failed", "error"):
                    raise PlotError(f"route plotting failed: {payload!r}")

            if time.monotonic() >= deadline:
                raise PlotError(f"route plotting timed out after {self.timeout:.0f}s")
            time.sleep(self.poll_interval)

    def plot_fast(self, source: str, dest: str, range_ly: float, efficiency: int = 60) -> dict:
        form = {"efficiency": efficiency, "range": range_ly, "from": source, "to": dest}
        job = self._submit(self.FAST_URL, form)
        return _normalize_fast(self._poll(job), source)

    def plot_fuel_safe(self, source: str, dest: str, ship_params: dict,
                       supercharge: bool = False) -> dict:
        """Exact plotter with the full ship config. supercharge=True enables
        neutron/WD boosts (the FAST profile): fuel is still fully modelled, so
        refuel stops stay known — unlike the range-only neutron plotter.

        The optimiser options mirror what the spansh.co.uk exact-plotter page
        itself submits (owner's head-to-head comparison, 2026-07-17: 28 vs 21
        jumps came from these knobs + the MkII constants): the "optimistic"
        algorithm with a 60 s optimisation budget and greedy refuelling at
        every scoopable stop. FAST additionally counts secondary stars as
        scoop/neutron candidates (exclude_secondary=0) like the website does;
        FUEL-SAFE keeps exclude_secondary=1 by design — the autopilot scoops
        the ARRIVAL star, a scoopable secondary may be minutes away."""
        form = dict(ship_params)
        form["algorithm"] = "optimistic"
        form["max_time"] = 60
        form["refuel_every_scoopable"] = 1
        if supercharge:
            form["use_supercharge"] = 1
            form["exclude_secondary"] = 0
        form["source"] = source
        form["destination"] = dest
        job = self._submit(self.FUEL_SAFE_URL, form)
        if supercharge:
            return _normalize_fuel_safe(self._poll(job), source, profile="FAST", risk="HIGH")
        return _normalize_fuel_safe(self._poll(job), source)


class EDSMClient:
    """EDSM sphere-systems (DIRECT-TO candidates) + system validation."""

    SPHERE_URL = "https://www.edsm.net/api-v1/sphere-systems"
    SYSTEM_URL = "https://www.edsm.net/api-v1/system"

    def __init__(self, session=None):
        self.session = session or _default_session()

    def sphere_systems(self, system: str, radius: float) -> list:
        params = {"systemName": system, "radius": radius,
                  "showPrimaryStar": 1, "showCoordinates": 1}
        try:
            resp = self.session.get(self.SPHERE_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:  # noqa: BLE001
            raise PlotError(f"EDSM sphere-systems request failed: {e}")
        return data or []

    def system(self, name: str) -> dict | None:
        params = {"systemName": name, "showCoordinates": 1, "showPrimaryStar": 1}
        try:
            resp = self.session.get(self.SYSTEM_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:  # noqa: BLE001
            raise PlotError(f"EDSM system request failed: {e}")
        if not data:  # [] or {} => system does not exist
            return None
        return data


# --------------------------------------------------------------------------- #
# Route planner (in-memory state; blocking calls driven from run_in_executor)
# --------------------------------------------------------------------------- #

class RoutePlanner:
    """Owns the secondary (SEC F-PLN) route and the DIR candidate.

    State lives in process memory only (v1: no disk persistence). A single
    busy flag serialises the blocking plot/nearest calls; snapshot() returns a
    JSON-safe copy for broadcasting.
    """

    def __init__(self, ed_ap: "EDAutopilot", spansh: SpanshClient | None = None,
                 edsm: EDSMClient | None = None):
        self.ap = ed_ap
        self._lock = threading.Lock()
        self._busy = False
        self._secondary = None
        self._dir = None
        self._error = None
        self._spansh = spansh or SpanshClient()
        self._edsm = edsm or EDSMClient()

    # --- state helpers ---------------------------------------------------- #

    def _current_location(self) -> str:
        state = self.ap.jn.ship_state()
        location = state.get("location") if isinstance(state, dict) else None
        if not location:
            raise PlotError("current location unknown — cannot plot a route")
        return location

    def _default_dest(self) -> str | None:
        """dest fallback: current secondary destination, else active F-PLN dest."""
        if self._secondary and self._secondary.get("destination"):
            return self._secondary["destination"]
        try:
            data = self.ap.nav_route.get_nav_route_data()
        except Exception:  # noqa: BLE001 — nav route is best-effort here
            data = None
        route = (data or {}).get("Route") if isinstance(data, dict) else None
        if route:
            return route[-1].get("StarSystem")
        return None

    def _fast_range(self) -> float:
        state = self.ap.jn.ship_state()
        max_range = state.get("max_jump_range") if isinstance(state, dict) else None
        if max_range:
            return float(max_range)
        loadout = state.get("loadout_raw") if isinstance(state, dict) else None
        if loadout:
            return max_range_from_loadout(loadout)
        raise PlotError("cannot determine jump range for the fast route")

    def _loadout(self) -> dict:
        state = self.ap.jn.ship_state()
        loadout = state.get("loadout_raw") if isinstance(state, dict) else None
        if not loadout:
            raise PlotError("no ship loadout available for a fuel-safe route")
        return loadout

    def _live_cargo(self) -> float:
        """Current cargo tonnage from Status.json (0.0 when unavailable) —
        mass matters: a loaded ship must not be plotted as empty."""
        try:
            data = self.ap.status.get_cleaned_data()
            return float(data.get("Cargo") or 0.0)
        except Exception:  # noqa: BLE001 — no status on a bare fake core
            return 0.0

    # --- blocking operations ---------------------------------------------- #

    def plot_secondary(self, dest: str | None = None, profile: str = "fuel_safe",
                       source: str | None = None) -> None:
        """Plot the secondary route into self._secondary (blocking).

        `source` overrides the journal location (the SEC F-PLN FROM field) so
        a route can be planned from anywhere before flying there. Busy
        re-entry raises PlotError; plotting failures are captured in
        self._error so the broadcast snapshot carries them.
        """
        with self._lock:
            if self._busy:
                raise PlotError("PLOT IN PROGRESS")
            self._busy = True
            self._error = None
        try:
            route = self._do_plot(dest, profile, source)
            with self._lock:
                self._secondary = route
        except PlotError as e:
            with self._lock:
                self._error = str(e)
        finally:
            with self._lock:
                self._busy = False

    def _resolve_source(self, source: str | None) -> str:
        """Manual FROM override (EDSM-validated to its canonical name), else
        the journal location."""
        source = (source or "").strip()
        if not source:
            return self._current_location()
        info = self._edsm.system(source)
        if not info:
            raise PlotError(f"unknown FROM system: {source}")
        return info.get("name") or source

    def _do_plot(self, dest: str | None, profile: str, source: str | None = None) -> dict:
        source = self._resolve_source(source)
        if not dest:
            dest = self._default_dest()
        if not dest:
            raise PlotError("no destination for the secondary route")

        key = (profile or "").lower().replace("-", "_")
        if key == "fast":
            # FAST = exact plotter with neutron/WD supercharge: the full ship
            # config (guardian booster, SCO MkII x6, engineering) is respected
            # AND fuel is modelled, so the route is executable segment-wise.
            loadout = self._loadout()
            route = self._spansh.plot_fuel_safe(
                source, dest, ship_plot_params(loadout, self._live_cargo()),
                supercharge=True)
            route["ship"] = ship_summary(loadout)
            return route
        if key in ("fuel_safe", "fuelsafe"):
            loadout = self._loadout()
            route = self._spansh.plot_fuel_safe(
                source, dest, ship_plot_params(loadout, self._live_cargo()))
            route["ship"] = ship_summary(loadout)
            return route
        if key == "ultra":
            # range-only neutron plotter: no fuel model, but handles the very
            # long hauls (Colonia-class) much faster than the exact plotter.
            return self._spansh.plot_fast(source, dest, self._fast_range())
        raise PlotError(f"unknown route profile: {profile!r}")

    def nearest(self, scoopable: bool) -> None:
        """Find the nearest (scoopable) system via EDSM sphere cascade (blocking)."""
        with self._lock:
            if self._busy:
                raise PlotError("PLOT IN PROGRESS")
            self._busy = True
            self._error = None
        try:
            source = self._current_location()
            candidate = None
            for radius in (15, 30, 50):
                candidate = self._pick_nearest(self._edsm.sphere_systems(source, radius), scoopable)
                if candidate:
                    break
            with self._lock:
                self._dir = candidate  # may be None if nothing matched at 50 LY
        except PlotError as e:
            with self._lock:
                self._error = str(e)
        finally:
            with self._lock:
                self._busy = False

    @staticmethod
    def _pick_nearest(systems: list, scoopable: bool) -> dict | None:
        best = None
        for s in systems or []:
            dist = s.get("distance")
            if dist is None or dist == 0:  # exclude the origin system itself
                continue
            star = s.get("primaryStar") or {}
            if scoopable and not star.get("isScoopable"):
                continue
            if best is None or dist < best["dist_ly"]:
                best = {
                    "system": s.get("name", ""),
                    "star_class": star.get("type", ""),
                    "dist_ly": dist,
                    "scoopable": bool(star.get("isScoopable")),
                }
        return best

    def direct_to(self, name: str) -> bool:
        """Set the DIR candidate to an explicit system. Returns False (INVALID)
        when EDSM does not know the system."""
        with self._lock:
            self._error = None
        data = self._edsm.system(name)
        if not data:
            return False

        dist = None
        source = self._current_location()
        if source != data.get("name", name):
            src = self._edsm.system(source)
            src_coords = (src or {}).get("coords") if isinstance(src, dict) else None
            dst_coords = data.get("coords")
            if src_coords and dst_coords:
                dist = round(sum((dst_coords[a] - src_coords[a]) ** 2
                                 for a in ("x", "y", "z")) ** 0.5, 2)

        star = data.get("primaryStar") or {}
        with self._lock:
            self._dir = {
                "system": data.get("name", name),
                "star_class": star.get("type", ""),
                "dist_ly": dist,
                "scoopable": bool(star.get("isScoopable")),
            }
        return True

    def snapshot(self) -> dict:
        """JSON-safe copy of the planner state (for broadcast)."""
        with self._lock:
            return {
                "secondary": copy.deepcopy(self._secondary),
                "dir": copy.deepcopy(self._dir),
                "busy": self._busy,
                "error": self._error,
            }
