"""Mechanics bench: cross-check OUR FSD physics against the Spansh exact
plotter and EDSM, leg by leg, across several ship configurations.

What is verified (per ship fixture, per profile):
  1. geometry     — every leg's `distance` matches the star coordinates in the
                    Spansh response, and a sample of systems is re-checked
                    against EDSM coordinates (independent source);
  2. fuel ledger  — Spansh's own per-jump fuel bookkeeping is self-consistent:
                    fuel_in_tank[i] == (tank if refueled else previous - used);
  3. our physics  — ShipFSD.fuel_cost() reproduces Spansh's fuel_used for every
                    jump (incl. guardian-booster scaling and neutron/WD
                    supercharge), and ShipFSD.jump_range() admits every leg;
  4. plot params  — ship_plot_params() resolves boosters / engineering / the
                    SCO MkII x6 multiplier the way we expect.

Fixtures cover the parameter space Spansh cannot infer on its own (the user
point: "spansh does not know our ship"): plain engineered SCO, guardian
booster, small ship, and the size8 SCO MkII drive with supercharge x6.
The `journal` fixture validates the REAL current ship when a journal with a
Loadout event is available (mock on the laptop, live on the game PC).

Usage:
  python tools/route_mechanics_bench.py                     # all fixtures
  python tools/route_mechanics_bench.py --fixture krait_guardian
  python tools/route_mechanics_bench.py --source Devataru --dest Maia
Exit code 0 = all checks passed. Live Spansh/EDSM calls: needs network.
"""
import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from RoutePlanner import EDSMClient, ShipFSD, SpanshClient, ship_plot_params

# tolerances: relative on fuel (Spansh rounds masses slightly differently),
# absolute LY on geometry, relative on range admission.
TOL_FUEL_REL = 0.02
TOL_FUEL_ABS = 0.01
TOL_GEOM_LY = 0.02
TOL_RANGE_REL = 1.005

FAILS = []


def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))
    if not ok:
        FAILS.append(name)


# --------------------------------------------------------------------------- #
# Ship fixtures (synthetic but physically consistent loadouts)
# --------------------------------------------------------------------------- #

def _loadout(ship, unladen, tank, reserve, fsd_item, optimal_mass=None, booster=None):
    fsd = {"Item": fsd_item}
    if optimal_mass is not None:
        fsd["Engineering"] = {"Modifiers": [
            {"Label": "FSDOptimalMass", "Value": optimal_mass}]}
    modules = [fsd]
    if booster:
        modules.append({"Item": booster})
    return {"Ship": ship, "UnladenMass": unladen,
            "FuelCapacity": {"Main": tank, "Reserve": reserve},
            "Modules": modules}


def _journal_loadout():
    from EDJournal import EDJournal
    jn = EDJournal(lambda *_a, **_k: None)
    state = jn.ship_state()
    return (state or {}).get("loadout_raw")


FIXTURES = {
    # standard 5A drive, G5 increased-range engineering, guardian booster 5H
    "krait_guardian": _loadout(
        "krait_mkii", 320.4, 32.0, 0.63, "int_hyperdrive_size5_class5",
        optimal_mass=1698.9, booster="int_guardianfsdbooster_size5"),
    # small long-range ship: 4A drive engineered + size4 booster
    "dbx_longrange": _loadout(
        "diamondbackxl", 170.0, 16.0, 0.52, "int_hyperdrive_size4_class5",
        optimal_mass=849.2, booster="int_guardianfsdbooster_size4"),
    # size8 SCO MkII drive: supercharge x6 + guardian booster combined
    "panther_mkii": _loadout(
        "panthermkii", 1250.0, 128.0, 1.13,
        "int_hyperdrive_overcharge_size8_class5_overchargebooster_mkii",
        booster="int_guardianfsdbooster_size5"),
}


# --------------------------------------------------------------------------- #
# Per-route validation
# --------------------------------------------------------------------------- #

def leg_distance(a, b):
    return math.dist((a["x"], a["y"], a["z"]), (b["x"], b["y"], b["z"]))


def validate_route(fsd: ShipFSD, jumps: list, supercharge_on: bool, edsm_coords: dict):
    """Run geometry + fuel-ledger + our-physics checks over one raw route."""
    tank = fsd.tank_size

    # 1. geometry: Spansh distance field vs Spansh coordinates
    geom_ok, worst_geom = True, 0.0
    for prev, cur in zip(jumps, jumps[1:]):
        d = leg_distance(prev, cur)
        err = abs(d - cur["distance"])
        worst_geom = max(worst_geom, err)
        geom_ok = geom_ok and err < TOL_GEOM_LY
    check("legs match Spansh coordinates", geom_ok, f"worst {worst_geom:.4f} LY")

    # geometry vs EDSM (independent coordinates, sampled)
    edsm_ok, edsm_n = True, 0
    for j in jumps:
        c = edsm_coords.get(j["name"])
        if not c:
            continue
        edsm_n += 1
        err = math.dist((c["x"], c["y"], c["z"]), (j["x"], j["y"], j["z"]))
        edsm_ok = edsm_ok and err < TOL_GEOM_LY
    check(f"EDSM coordinates agree ({edsm_n} sampled)", edsm_ok and edsm_n > 0)

    # 2+3. fuel ledger + our physics, jump by jump
    ledger_ok = True
    physics_ok = True
    range_ok = True
    worst_rel = 0.0
    fuel_before = tank
    check("start fuel == full tank", abs(jumps[0]["fuel_in_tank"] - tank) < 0.01,
          f"{jumps[0]['fuel_in_tank']} vs {tank}")
    for prev, cur in zip(jumps, jumps[1:]):
        dist = cur["distance"]
        # supercharged when we DEPART a neutron/WD system on a supercharge plot
        mult = fsd.supercharge_multiplier if (supercharge_on and prev["has_neutron"]) else 1.0

        # Spansh ledger self-consistency: fuel_in_tank is the level after
        # arriving at `cur` and after refuelling there when must_refuel is set.
        expect_after = tank if cur["must_refuel"] else fuel_before - cur["fuel_used"]
        if abs(cur["fuel_in_tank"] - expect_after) > 0.05:
            ledger_ok = False

        # our fuel equation vs Spansh's number for the same jump
        ours = fsd.fuel_cost(dist, fuel_before, supercharge=mult)
        err = abs(ours - cur["fuel_used"])
        rel = err / max(cur["fuel_used"], TOL_FUEL_ABS)
        worst_rel = max(worst_rel, rel)
        if err > TOL_FUEL_ABS and rel > TOL_FUEL_REL:
            physics_ok = False
            print(f"        fuel mismatch {prev['name']} -> {cur['name']}: "
                  f"ours {ours:.3f} t vs spansh {cur['fuel_used']:.3f} t "
                  f"(dist {dist:.2f} LY, before {fuel_before:.2f} t, x{mult:g})")

        # our range equation must admit the leg
        rng = fsd.jump_range(fuel_before, supercharge=mult)
        if dist > rng * TOL_RANGE_REL:
            range_ok = False
            print(f"        leg beyond our range {prev['name']} -> {cur['name']}: "
                  f"{dist:.2f} LY > {rng:.2f} LY (x{mult:g})")

        fuel_before = cur["fuel_in_tank"]

    check("Spansh fuel ledger self-consistent", ledger_ok)
    check("our fuel_cost matches Spansh fuel_used",
          physics_ok, f"worst rel err {worst_rel * 100:.2f}%")
    check("our jump_range admits every leg", range_ok)


def run_fixture(name, loadout, spansh, edsm, source, dest, edsm_cache):
    print(f"\n=== {name} ===")
    try:
        params = ship_plot_params(loadout)
    except Exception as e:  # noqa: BLE001
        check(f"{name}: ship_plot_params resolves", False, str(e))
        return
    fsd = ShipFSD(loadout)
    print(f"  drive x{fsd.supercharge_multiplier} sc-mult · boost +{fsd.range_boost} LY · "
          f"opt {fsd.optimal_mass} t · max/jump {fsd.max_fuel} t · "
          f"full-tank range {fsd.jump_range(fsd.tank_size):.2f} LY")
    check("params carry the guardian boost", params["range_boost"] == fsd.range_boost)
    check("params carry the supercharge multiplier",
          params["supercharge_multiplier"] == fsd.supercharge_multiplier)

    for supercharge_on in (False, True):
        label = "supercharge" if supercharge_on else "plain"
        form = dict(params)
        form["use_supercharge"] = 1 if supercharge_on else 0
        form["source"] = source
        form["destination"] = dest
        try:
            job = spansh._submit(SpanshClient.FUEL_SAFE_URL, form)
            jumps = (spansh._poll(job) or {}).get("jumps") or []
        except Exception as e:  # noqa: BLE001
            check(f"{label}: Spansh plot succeeds", False, str(e))
            continue
        n_neutron = sum(1 for j in jumps if j.get("has_neutron"))
        n_refuel = sum(1 for j in jumps if j.get("must_refuel"))
        print(f"  -- {label}: {len(jumps) - 1} jumps · {n_neutron} neutron · "
              f"{n_refuel} refuels")
        check(f"{label}: route returned", len(jumps) >= 2)
        if len(jumps) < 2:
            continue
        if supercharge_on:
            check("supercharge plot uses at least one neutron/WD leg", n_neutron > 0)

        # EDSM sample: first 3 intermediate systems + destination (cached)
        sample = [j["name"] for j in jumps[1:4]] + [jumps[-1]["name"]]
        for sysname in sample:
            if sysname not in edsm_cache:
                try:
                    info = edsm.system(sysname)
                except Exception:  # noqa: BLE001
                    info = None
                edsm_cache[sysname] = (info or {}).get("coords") if info else None
        coords = {k: v for k, v in edsm_cache.items() if v}
        validate_route(fsd, jumps, supercharge_on, coords)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="Devataru")
    ap.add_argument("--dest", default="Maia")
    ap.add_argument("--fixture", default=None,
                    help="run one fixture (or 'journal') instead of all")
    args = ap.parse_args()

    fixtures = dict(FIXTURES)
    journal_lo = None
    try:
        journal_lo = _journal_loadout()
    except Exception:  # noqa: BLE001 — no journal on this machine is fine
        pass
    if journal_lo:
        fixtures["journal"] = journal_lo

    if args.fixture:
        if args.fixture not in fixtures:
            raise SystemExit(f"unknown fixture {args.fixture!r} "
                             f"(have: {', '.join(fixtures)})")
        fixtures = {args.fixture: fixtures[args.fixture]}

    spansh = SpanshClient()
    edsm = EDSMClient()
    edsm_cache = {}
    print(f"Route pair: {args.source} -> {args.dest}")
    for name, lo in fixtures.items():
        run_fixture(name, lo, spansh, edsm, args.source, args.dest, edsm_cache)

    print()
    if FAILS:
        print(f"{len(FAILS)} CHECK(S) FAILED")
        return 1
    print("MECHANICS OK — all checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
