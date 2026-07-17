"""Offline QA for RouteExecutor.py (Phase 8.1, segment-wise execution).

Self-contained checker (no pytest, no network): drives the real RouteExecutor
against a fake ed_ap whose journal location is set by hand, and asserts the
whole lifecycle: activate (with/without route), per-leg advance, segment
hand-off to the GalaxyMapDriver stub, off-route detection and rejoin,
completion, deactivate.

Run from the repo root:
    .\\venv\\Scripts\\python.exe tools\\qa_route_executor.py
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from RouteExecutor import ExecuteError, GalaxyMapDriver, RouteExecutor  # noqa: E402

_results: list[tuple[bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((ok, name))
    line = f"[{'PASS' if ok else 'FAIL'}] {name}"
    if detail and not ok:
        line += f"  -- {detail}"
    print(line)


class FakeJournal:
    def __init__(self, location, loadout=None):
        self.location = location
        self.loadout = loadout

    def ship_state(self):
        return {"location": self.location, "loadout_raw": self.loadout}


class FakeAP:
    def __init__(self, location="Sol", loadout=None):
        self.jn = FakeJournal(location, loadout)


def loadout(ship="krait_mkii", unladen=320.4):
    return {"event": "Loadout", "Ship": ship, "UnladenMass": unladen,
            "FuelCapacity": {"Main": 32.0, "Reserve": 0.63},
            "Modules": [{"Item": "int_hyperdrive_size5_class5"}]}


def sysentry(name, dist=30.0, refuel=False, neutron=False, fuel_tank=None):
    return {"system": name, "dist_ly": dist, "scoopable": True,
            "neutron": neutron, "must_refuel": refuel, "fuel_used": 3.0,
            "fuel_tank": fuel_tank}


# Sol -> Alpha(RFL) -> Beta -> Gamma(RFL, NTR) -> Colonia
ROUTE = {
    "profile": "FAST", "source": "Sol", "destination": "Colonia",
    "jumps": 4, "dist_ly": 120.0, "scoops": 2, "risk": "HIGH",
    "systems": [
        {**sysentry("Sol", dist=None), "fuel_tank": 32.0},
        sysentry("Alpha", refuel=True, fuel_tank=32.0),
        sysentry("Beta", fuel_tank=27.0),
        sysentry("Gamma", refuel=True, neutron=True, fuel_tank=32.0),
        sysentry("Colonia", fuel_tank=28.5),
    ],
}


def main() -> int:
    # --- activation guards -------------------------------------------------- #
    ex = RouteExecutor(FakeAP())
    for bad, label in [
        (None, "no route"),
        ({"profile": "FAST", "systems": []}, "empty systems"),
        ({"profile": "ULTRA", "systems": ROUTE["systems"]}, "ULTRA profile"),
        ({"profile": "FAST", "systems": ROUTE["systems"][:1]}, "single system"),
    ]:
        try:
            ex.activate(bad)
            check(f"activate rejects {label}", False, "no exception")
        except ExecuteError:
            check(f"activate rejects {label}", True)
    check("guarded activate stays INACTIVE", ex.snapshot() == {"active": False, "status": "INACTIVE"})

    # --- activation + first target lock ---------------------------------------- #
    drv = GalaxyMapDriver()
    ex = RouteExecutor(FakeAP("Sol"), map_driver=drv)
    ex.activate(dict(ROUTE))
    s = ex.snapshot()
    check("activate: ACTIVE at journal location", s["status"] == "ACTIVE" and s["idx"] == 0, str(s))
    check("activate: driver locks the NEXT waypoint (not a segment plot)",
          drv.last_target == "Alpha" and drv.requests == ["Alpha"], str(drv.requests))
    check("activate: snapshot fields", s["next_system"] == "Alpha" and s["segment_target"] == "Alpha"
          and s["remaining_jumps"] == 4 and s["jumps_total"] == 4
          and s["next_refuel_in"] == 1 and s["fuel_plan"] == 32.0, str(s))

    # journal location mid-route -> executor picks it up as the start
    ex2 = RouteExecutor(FakeAP("Beta"), map_driver=GalaxyMapDriver())
    ex2.activate(dict(ROUTE))
    check("activate: journal mid-route location adopted", ex2.snapshot()["idx"] == 2)
    # unknown journal location -> starts from index 0 (route origin)
    ex3 = RouteExecutor(FakeAP("Elsewhere"), map_driver=GalaxyMapDriver())
    ex3.activate(dict(ROUTE))
    check("activate: unknown journal location starts at origin", ex3.snapshot()["idx"] == 0)

    # --- tick: same location is a no-op --------------------------------------- #
    check("tick: same location -> no change", ex.tick("Sol", 32.0) is False)
    check("tick: empty location -> no change", ex.tick(None) is False)

    # --- advance leg by leg: EVERY arrival locks the next waypoint -------------- #
    changed = ex.tick("Alpha", 32.0)
    s = ex.snapshot()
    check("tick: jump to Alpha advances", changed and s["idx"] == 1 and s["status"] == "ACTIVE", str(s))
    check("tick: arrival locks the next waypoint", drv.last_target == "Beta", str(drv.requests))
    check("tick: fuel readback", s["fuel_actual"] == 32.0 and s["fuel_plan"] == 32.0, str(s))
    check("tick: segment_target stays a display hint (next refuel)",
          s["segment_target"] == "Gamma", str(s))

    ex.tick("Beta", 27.1)
    check("tick: every jump retargets (per-waypoint, no game plotting)",
          drv.last_target == "Gamma" and drv.requests == ["Alpha", "Beta", "Gamma"],
          str(drv.requests))
    check("tick: case-insensitive match", ex.tick("gAMMA", 31.9) and ex.snapshot()["idx"] == 3)
    check("tick: penultimate arrival locks the destination",
          drv.last_target == "Colonia", str(drv.requests))

    # --- off-route and rejoin ---------------------------------------------------- #
    changed = ex.tick("Wrong Turn", 30.0)
    s = ex.snapshot()
    check("tick: unknown system -> OFF ROUTE (position kept)",
          changed and s["status"] == "OFF ROUTE" and s["off_route_at"] == "Wrong Turn"
          and s["idx"] == 3 and s["active"] is True, str(s))
    check("tick: OFF ROUTE does not retarget", drv.last_target == "Colonia"
          and len(drv.requests) == 4, str(drv.requests))
    check("tick: staying off route is not a new change", ex.tick("Wrong Turn", 30.0) is False)
    changed = ex.tick("Gamma", 31.0)
    s = ex.snapshot()
    check("tick: rejoin at current position -> ACTIVE again",
          changed and s["status"] == "ACTIVE" and s["off_route_at"] is None, str(s))
    check("tick: rejoin re-issues the target lock",
          drv.requests == ["Alpha", "Beta", "Gamma", "Colonia", "Colonia"], str(drv.requests))

    # jump BACK along the plan is still on-route (not OFF ROUTE) and retargets
    ex.tick("Beta", 28.0)
    s = ex.snapshot()
    check("tick: back-jump matches earlier waypoint", s["idx"] == 2 and s["status"] == "ACTIVE", str(s))
    check("tick: back-jump retargets its next waypoint", drv.last_target == "Gamma", str(drv.requests))
    ex.tick("Gamma", 32.0)

    # --- completion ---------------------------------------------------------------- #
    changed = ex.tick("Colonia", 28.4)
    s = ex.snapshot()
    check("tick: destination -> COMPLETE",
          changed and s["status"] == "COMPLETE" and s["active"] is False
          and s["remaining_jumps"] == 0 and s["next_system"] is None, str(s))
    check("tick: after COMPLETE ticks are inert", ex.tick("Somewhere") is False)

    # --- deactivate ------------------------------------------------------------------ #
    ex.deactivate()
    check("deactivate -> INACTIVE snapshot", ex.snapshot() == {"active": False, "status": "INACTIVE"})

    # --- ship-profile guard (fingerprint) --------------------------------------------- #
    from RoutePlanner import ship_fingerprint, ship_summary
    lo_a = loadout()
    lo_b = loadout(unladen=999.0)      # outfitting change -> different physics
    check("fingerprint: stable for identical loadouts",
          ship_fingerprint(loadout()) == ship_fingerprint(lo_a))
    check("fingerprint: differs when mass changes",
          ship_fingerprint(lo_a) != ship_fingerprint(lo_b))

    route_a = dict(ROUTE)
    route_a["ship"] = ship_summary(lo_a)
    # (a) activation refused when the current ship differs from the plan's
    ex2 = RouteExecutor(FakeAP("Sol", loadout=lo_b), map_driver=GalaxyMapDriver())
    try:
        ex2.activate(dict(route_a))
        check("activate: refuses a plan for another ship", False, "no exception")
    except ExecuteError as e:
        check("activate: refuses a plan for another ship", "SHIP CHANGED" in str(e), str(e))

    # (b) activation ok on the matching ship; a mid-flight loadout change is
    # flagged by the tick and cleared when the loadout reverts
    ap = FakeAP("Sol", loadout=lo_a)
    ex3 = RouteExecutor(ap, map_driver=GalaxyMapDriver())
    ex3.activate(dict(route_a))
    check("activate: matching ship accepted", ex3.snapshot()["status"] == "ACTIVE"
          and ex3.snapshot()["ship_mismatch"] is False
          and ex3.snapshot()["ship"]["name"] == "krait_mkii")
    ap.jn.loadout = lo_b
    changed = ex3.tick("Alpha", 30.0)
    s = ex3.snapshot()
    check("tick: mid-flight loadout change -> ship_mismatch flagged",
          changed and s["ship_mismatch"] is True, str(s))
    ap.jn.loadout = lo_a
    ex3.tick("Beta", 28.0)
    check("tick: loadout reverted -> mismatch cleared",
          ex3.snapshot()["ship_mismatch"] is False)
    # legacy routes without a ship passport still activate (no fp to compare)
    ex4 = RouteExecutor(FakeAP("Sol", loadout=lo_b), map_driver=GalaxyMapDriver())
    ex4.activate(dict(ROUTE))
    check("activate: passport-less route still flies", ex4.snapshot()["status"] == "ACTIVE")

    total = len(_results)
    passed = sum(1 for ok, _ in _results if ok)
    print(f"\n{passed}/{total} checks passed.")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
