"""Offline QA for RoutePlanner.py (Phase 8.1, iteration 1).

Self-contained checker (no pytest): prints PASS/FAIL per check and exits 0
only when everything passes. All network access is faked through a canned
session object whose responses match the shapes in
design/route-planner-backend.md 2. An optional `--live` flag runs a tiny
smoke test against the real APIs (NOT part of the mandatory gate).

Run from the repo root:
    .\\venv\\Scripts\\python.exe tools\\qa_route_planner.py
"""

from __future__ import annotations

import os
import subprocess
import sys

# Allow running from the repo root (import RoutePlanner from ..).
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import RoutePlanner as rp  # noqa: E402
from RoutePlanner import (  # noqa: E402
    EDSMClient,
    PlotError,
    RoutePlanner,
    SpanshClient,
    ship_plot_params,
)

_results: list[tuple[bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((ok, name))
    status = "PASS" if ok else "FAIL"
    line = f"[{status}] {name}"
    if detail and not ok:
        line += f"  -- {detail}"
    print(line)


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #

class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSpanshSession:
    """Fakes POST /api/route|generic/route (job) + GET /api/results/<job>.

    `poll_payloads` is a queue of GET responses drained one per poll; when
    exhausted the last one repeats (so a permanently-queued state simulates a
    timeout)."""

    def __init__(self, job="job-1", poll_payloads=None):
        self.job = job
        self.poll_payloads = list(poll_payloads or [])
        self.posts = []
        self.gets = 0

    def post(self, url, data=None, **kwargs):
        self.posts.append((url, data))
        return FakeResponse({"job": self.job, "status": "queued"})

    def get(self, url, params=None, **kwargs):
        self.gets += 1
        if self.poll_payloads:
            payload = self.poll_payloads.pop(0) if len(self.poll_payloads) > 1 else self.poll_payloads[0]
        else:
            payload = {"status": "queued", "state": "started"}
        return FakeResponse(payload)


class FakeEDSMSession:
    """Fakes GET sphere-systems and GET system by URL routing."""

    def __init__(self, sphere_by_radius=None, systems=None):
        # sphere_by_radius: {radius(int) -> list[...]}, systems: {name -> dict|None}
        self.sphere_by_radius = sphere_by_radius or {}
        self.systems = systems or {}
        self.sphere_calls = []
        self.system_calls = []

    def get(self, url, params=None, **kwargs):
        params = params or {}
        if "sphere-systems" in url:
            radius = int(params.get("radius"))
            self.sphere_calls.append(radius)
            return FakeResponse(self.sphere_by_radius.get(radius, []))
        # /api-v1/system
        name = params.get("systemName")
        self.system_calls.append(name)
        return FakeResponse(self.systems.get(name, []))


class FakeNavRoute:
    def __init__(self, data):
        self._data = data

    def get_nav_route_data(self):
        return self._data


class FakeJournal:
    def __init__(self, state):
        self._state = state

    def ship_state(self):
        return self._state


class FakeAP:
    def __init__(self, state, nav_data=None):
        self.jn = FakeJournal(state)
        self.nav_route = FakeNavRoute(nav_data)


# --------------------------------------------------------------------------- #
# Sample data
# --------------------------------------------------------------------------- #

def loadout_plain(with_engineering=False):
    fsd = {"Slot": "FrameShiftDrive", "Item": "int_hyperdrive_size5_class5"}
    if with_engineering:
        fsd["Engineering"] = {"Modifiers": [
            {"Label": "FSDOptimalMass", "Value": 1587.75},
            {"Label": "MaxFuelPerJump", "Value": 5.0},
        ]}
    return {
        "Ship": "python",
        "UnladenMass": 350.0,
        "FuelCapacity": {"Main": 32.0, "Reserve": 0.83},
        "MaxJumpRange": 34.5,
        "Modules": [
            fsd,
            {"Slot": "Slot01_Size6", "Item": "int_guardianfsdbooster_size5"},
        ],
    }


def loadout_no_fsd():
    return {
        "Ship": "sidewinder",
        "UnladenMass": 40.0,
        "FuelCapacity": {"Main": 2.0, "Reserve": 0.3},
        "Modules": [{"Slot": "PowerPlant", "Item": "int_powerplant_size2_class1"}],
    }


FAST_RESULT = {"result": {
    "source_system": "Sol", "destination_system": "Colonia", "distance": 22000.0,
    "system_jumps": [
        {"system": "Sol", "distance_jumped": 0.0, "jumps": 0, "neutron_star": False},
        {"system": "Waypoint A", "distance_jumped": 300.0, "jumps": 8, "neutron_star": True},
        {"system": "Colonia", "distance_jumped": 250.0, "jumps": 6, "neutron_star": False},
    ],
}}

FUEL_SAFE_RESULT = {"result": {"jumps": [
    {"name": "Sol", "distance": 0.0, "is_scoopable": True, "must_refuel": False, "has_neutron": False,
     "fuel_used": 0.0, "fuel_in_tank": 32.0},
    {"name": "Alpha", "distance": 30.0, "is_scoopable": True, "must_refuel": True, "has_neutron": False,
     "fuel_used": 4.1, "fuel_in_tank": 32.0},
    {"name": "Beta", "distance": 28.0, "is_scoopable": False, "must_refuel": False, "has_neutron": True,
     "fuel_used": 3.7, "fuel_in_tank": 28.3},
    {"name": "Gamma", "distance": 31.0, "is_scoopable": True, "must_refuel": True, "has_neutron": False,
     "fuel_used": 4.4, "fuel_in_tank": 32.0},
]}}


# --------------------------------------------------------------------------- #
# Checks
# --------------------------------------------------------------------------- #

def check_ship_plot_params():
    # (a) plain loadout: constants come from the FSD tables.
    p = ship_plot_params(loadout_plain())
    ok = (
        p["fuel_power"] == rp.FSD_SIZE_CONST[5]
        and abs(p["fuel_multiplier"] - rp.FSD_CLASS_CONST[5] / 1000.0) < 1e-9
        and p["optimal_mass"] == 1050.0
        and p["max_fuel_per_jump"] == 5.00
        and p["range_boost"] == 10.5
        and p["tank_size"] == 32.0
        and p["internal_tank_size"] == 0.83
        and abs(p["base_mass"] - (350.0 + 0.83)) < 1e-9
        and p["cargo"] == 0 and p["exclude_secondary"] == 1
        and p["is_supercharged"] == 0 and p["use_supercharge"] == 0
        and p["use_injections"] == 0
        and p["supercharge_multiplier"] == rp.DEFAULT_SUPERCHARGE_MULTIPLIER
    )
    check("ship_plot_params: plain loadout uses FSD tables", ok, detail=str(p))

    # (a) engineered loadout: optimal_mass / max_fuel overridden.
    pe = ship_plot_params(loadout_plain(with_engineering=True))
    oke = pe["optimal_mass"] == 1587.75 and pe["max_fuel_per_jump"] == 5.0
    check("ship_plot_params: engineering overrides optimal_mass/max_fuel", oke, detail=str(pe))


def check_plot_error_no_fsd():
    # (b)
    try:
        ship_plot_params(loadout_no_fsd())
        check("ship_plot_params: PlotError when no FSD", False, "no exception raised")
    except PlotError:
        check("ship_plot_params: PlotError when no FSD", True)
    except Exception as e:  # noqa: BLE001
        check("ship_plot_params: PlotError when no FSD", False, f"wrong exception {e!r}")


def check_plot_fast():
    # (c) submit -> poll (queued then result) -> normalise.
    sess = FakeSpanshSession(poll_payloads=[
        {"status": "queued", "state": "started"},
        FAST_RESULT,
    ])
    client = SpanshClient(session=sess, poll_interval=0.0, timeout=5.0)
    route = client.plot_fast("Sol", "Colonia", 34.5)
    ok = (
        route["profile"] == "ULTRA"
        and route["risk"] == "HIGH"
        and route["scoops"] is None
        and route["jumps"] == 14                # 0 + 8 + 6
        and route["source"] == "Sol"
        and route["destination"] == "Colonia"
        and route["systems"][0]["dist_ly"] is None
        and route["systems"][1]["neutron"] is True
        and all(s["scoopable"] is None for s in route["systems"])
        and sess.posts and "api/route" in sess.posts[0][0]
    )
    check("plot_fast: submit/poll/normalise (ULTRA, jumps=sum, scoops None)", ok, detail=str(route))


def check_plot_fuel_safe():
    # (d)
    sess = FakeSpanshSession(poll_payloads=[
        {"status": "queued"},
        FUEL_SAFE_RESULT,
    ])
    client = SpanshClient(session=sess, poll_interval=0.0, timeout=5.0)
    route = client.plot_fuel_safe("Sol", "Gamma", ship_plot_params(loadout_plain()))
    ok = (
        route["profile"] == "FUEL-SAFE"
        and route["risk"] == "LOW"
        and route["jumps"] == 3                 # len(systems) - 1
        and route["scoops"] == 2                # must_refuel on Alpha + Gamma
        and route["destination"] == "Gamma"
        and route["systems"][0]["dist_ly"] is None
        and abs(route["dist_ly"] - (30.0 + 28.0 + 31.0)) < 1e-6
        and "generic/route" in sess.posts[0][0]
        and sess.posts[0][1].get("use_supercharge") == 0
        and route["systems"][1]["fuel_used"] == 4.1     # Spansh fuel model kept
        and route["systems"][2]["fuel_tank"] == 28.3
        and route["systems"][0]["fuel_used"] is None    # start system burns nothing
    )
    check("plot_fuel_safe: normalise (jumps=len-1, scoops=sum must_refuel, LOW)", ok, detail=str(route))

    # FAST = same exact plotter with use_supercharge=1, labelled FAST/HIGH.
    sess2 = FakeSpanshSession(poll_payloads=[
        {"status": "queued"},
        FUEL_SAFE_RESULT,
    ])
    client2 = SpanshClient(session=sess2, poll_interval=0.0, timeout=5.0)
    route2 = client2.plot_fuel_safe("Sol", "Gamma", ship_plot_params(loadout_plain()),
                                    supercharge=True)
    ok2 = (
        route2["profile"] == "FAST"
        and route2["risk"] == "HIGH"
        and route2["scoops"] == 2               # fuel model intact on FAST
        and route2["systems"][2]["neutron"] is True
        and "generic/route" in sess2.posts[0][0]
        and sess2.posts[0][1].get("use_supercharge") == 1
    )
    check("plot_fuel_safe(supercharge): FAST/HIGH via exact plotter, use_supercharge=1",
          ok2, detail=str(route2))


def check_poll_timeout():
    # (e) always queued -> timeout -> PlotError.
    sess = FakeSpanshSession(poll_payloads=[{"status": "queued", "state": "started"}])
    client = SpanshClient(session=sess, poll_interval=0.0, timeout=0.05)
    try:
        client.plot_fast("Sol", "Colonia", 34.5)
        check("poll timeout -> PlotError", False, "no exception raised")
    except PlotError:
        check("poll timeout -> PlotError", True)
    except Exception as e:  # noqa: BLE001
        check("poll timeout -> PlotError", False, f"wrong exception {e!r}")


def check_nearest_cascade():
    # (f) empty at 15, found at 30; scoopable filter; distance==0 excluded.
    sphere = {
        15: [],
        30: [
            {"name": "Origin", "distance": 0.0, "primaryStar": {"type": "M", "isScoopable": True}},
            {"name": "NonScoop", "distance": 12.0, "primaryStar": {"type": "T Tauri", "isScoopable": False}},
            {"name": "ScoopFar", "distance": 25.0, "primaryStar": {"type": "K", "isScoopable": True}},
            {"name": "ScoopNear", "distance": 18.0, "primaryStar": {"type": "G", "isScoopable": True}},
        ],
    }
    edsm = EDSMClient(session=FakeEDSMSession(sphere_by_radius=sphere))
    ap = FakeAP({"location": "Origin"})
    planner = RoutePlanner(ap, edsm=edsm)

    planner.nearest(scoopable=True)
    snap = planner.snapshot()
    d = snap["dir"]
    ok_scoop = (
        d is not None and d["system"] == "ScoopNear"  # nearest scoopable, origin excluded
        and d["dist_ly"] == 18.0 and snap["error"] is None
    )
    check("nearest: radius cascade 15->30, scoopable filter, exclude distance==0", ok_scoop, detail=str(snap))

    # scoopable=False picks the truly nearest (the non-scoopable one at 12).
    planner.nearest(scoopable=False)
    d2 = planner.snapshot()["dir"]
    ok_any = d2 is not None and d2["system"] == "NonScoop" and d2["dist_ly"] == 12.0
    check("nearest: scoopable=False allows non-scoopable nearest", ok_any, detail=str(d2))


def check_direct_to():
    # (g) unknown system -> False; known -> True with distance.
    edsm_sess = FakeEDSMSession(systems={
        "Sol": {"name": "Sol", "coords": {"x": 0.0, "y": 0.0, "z": 0.0},
                "primaryStar": {"type": "G", "isScoopable": True}},
        "Colonia": {"name": "Colonia", "coords": {"x": 0.0, "y": 0.0, "z": 100.0},
                    "primaryStar": {"type": "K", "isScoopable": True}},
        "Nowhere": [],
    })
    planner = RoutePlanner(FakeAP({"location": "Sol"}), edsm=EDSMClient(session=edsm_sess))

    ok_invalid = planner.direct_to("Nowhere") is False
    check("direct_to: nonexistent system -> False", ok_invalid)

    ok_valid = planner.direct_to("Colonia") is True
    d = planner.snapshot()["dir"]
    ok_valid = ok_valid and d["system"] == "Colonia" and d["dist_ly"] == 100.0
    check("direct_to: valid system -> True with distance from current", ok_valid, detail=str(d))


def check_busy_guard():
    # (h) plot while busy -> PlotError.
    planner = RoutePlanner(FakeAP({"location": "Sol"}))
    planner._busy = True
    try:
        planner.plot_secondary(dest="Colonia", profile="fast")
        check("busy guard: plot while busy -> PlotError", False, "no exception raised")
    except PlotError as e:
        check("busy guard: plot while busy -> PlotError", "PROGRESS" in str(e).upper())
    except Exception as e:  # noqa: BLE001
        check("busy guard: plot while busy -> PlotError", False, f"wrong exception {e!r}")


def check_planner_plot_end_to_end():
    # Bonus: exercise RoutePlanner.plot_secondary through a fake Spansh client
    # (source from ship_state location, dest default from nav route). The FAST
    # profile now goes through the exact plotter with use_supercharge=1.
    sess = FakeSpanshSession(poll_payloads=[{"status": "queued"}, FUEL_SAFE_RESULT])
    spansh = SpanshClient(session=sess, poll_interval=0.0, timeout=5.0)
    nav = {"event": "NavRoute", "Route": [
        {"StarSystem": "Sol"}, {"StarSystem": "Gamma"}]}
    ap = FakeAP({"location": "Sol", "loadout_raw": loadout_plain()}, nav_data=nav)
    planner = RoutePlanner(ap, spansh=spansh)
    planner.plot_secondary(dest=None, profile="fast")  # dest defaults to nav route end
    snap = planner.snapshot()
    ok = (
        snap["error"] is None and snap["busy"] is False
        and snap["secondary"] is not None
        and snap["secondary"]["profile"] == "FAST"
        and snap["secondary"]["destination"] == "Gamma"
        and snap["secondary"]["jumps"] == 3
        and "generic/route" in sess.posts[0][0]
        and sess.posts[0][1].get("use_supercharge") == 1
        and sess.posts[0][1].get("range_boost") == 10.5    # ship config reaches Spansh
    )
    check("plot_secondary: FAST end-to-end via exact plotter + snapshot", ok, detail=str(snap))


def check_max_range_fallback():
    # ULTRA (neutron plotter) range fallback: no max_jump_range in the state ->
    # the submitted range is computed from the loadout via ShipFSD.
    sess = FakeSpanshSession(poll_payloads=[FAST_RESULT])
    spansh = SpanshClient(session=sess, poll_interval=0.0, timeout=5.0)
    state = {"location": "Sol", "loadout_raw": loadout_plain()}  # no max_jump_range key
    planner = RoutePlanner(FakeAP(state), spansh=spansh)
    planner.plot_secondary(dest="Colonia", profile="ultra")
    snap = planner.snapshot()
    # The submitted 'range' must be a positive number derived from the loadout.
    submitted_range = sess.posts[0][1].get("range")
    ok = snap["error"] is None and isinstance(submitted_range, float) and submitted_range > 0
    check("ultra range fallback: computed from loadout when MaxJumpRange missing", ok,
          detail=f"range={submitted_range} err={snap['error']}")


def check_imports_clean():
    # (i) import RoutePlanner clean + EDAPGui import not broken.
    check("import RoutePlanner clean", True)  # reaching here means it imported
    try:
        out = subprocess.run(
            [sys.executable, "-c", "import EDAPGui"],
            cwd=ROOT, capture_output=True, text=True, timeout=120,
        )
        ok = out.returncode == 0
        check("import EDAPGui not broken", ok, detail=(out.stderr or out.stdout).strip()[-400:])
    except Exception as e:  # noqa: BLE001
        check("import EDAPGui not broken", False, str(e))


# --------------------------------------------------------------------------- #
# Live smoke (optional; not part of the gate)
# --------------------------------------------------------------------------- #

def run_live():
    print("\n--- LIVE smoke (real APIs) ---")
    edsm = EDSMClient()
    sysdata = edsm.system("Sol")
    print("EDSM Sol:", "ok" if sysdata else "MISSING")
    spansh = SpanshClient(poll_interval=3.0, timeout=120.0)
    route = spansh.plot_fast("Sol", "Sagittarius A*", 34.5)
    print("Spansh FAST Sol->Sgr A*:", route["jumps"], "jumps,", route["dist_ly"], "ly")


def main():
    if "--live" in sys.argv:
        run_live()
        return 0

    check_ship_plot_params()
    check_plot_error_no_fsd()
    check_plot_fast()
    check_plot_fuel_safe()
    check_poll_timeout()
    check_nearest_cascade()
    check_direct_to()
    check_busy_guard()
    check_planner_plot_end_to_end()
    check_max_range_fallback()
    check_imports_clean()

    total = len(_results)
    passed = sum(1 for ok, _ in _results if ok)
    print(f"\n{passed}/{total} checks passed.")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
