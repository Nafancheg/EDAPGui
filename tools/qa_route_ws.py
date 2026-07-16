"""Offline QA for the route-planner WS commands (Phase 8.1, iteration 2).

Self-contained checker (no pytest): prints PASS/FAIL per check and exits 0
only when everything passes. Drives the REAL aiohttp app built by
webserver.server.create_app() through aiohttp.test_utils (TestServer +
TestClient) against a fake ed_ap core -- no game, no tkinter. The
RoutePlanner itself is replaced by monkeypatching the module-level lazy
singleton (webserver.server._route_planner) with a FakeRoutePlanner per
check, so no network call ever happens.

Run from the repo root:
    .\\venv\\Scripts\\python.exe tools\\qa_route_ws.py
"""

from __future__ import annotations

import asyncio
import os
import sys

# Allow running from the repo root (import webserver/RoutePlanner from ..).
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

import webserver.server as server  # noqa: E402
from RoutePlanner import PlotError  # noqa: E402

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

class FakeNavRoute:
    def __init__(self, data):
        self._data = data

    def get_nav_route_data(self):
        return self._data


class FakeAP:
    """Minimal ed_ap stand-in: only what create_app()/handle_ws()/
    route_primary_stats() touch. The route planner itself is faked
    separately (module singleton), so ed_ap.jn is never needed.
    `status` is mutable so a check can move the ship: the 1 Hz snapshot loop
    feeds it to the route executor's tick()."""

    def __init__(self, nav_data=None):
        self.ap_ckb = None  # not a Broadcaster -> create_app makes a fresh one
        self.nav_route = FakeNavRoute(nav_data)
        self.status = {}

    def get_status_dict(self):
        return dict(self.status)


class FakeRoutePlanner:
    """Stands in for RoutePlanner: same public surface, no network, and each
    call's outcome is configured up front by the check that installs it."""

    def __init__(self, secondary=None, dir_=None, busy=False, error=None,
                 plot_result=None, plot_raises=None,
                 nearest_result=None, nearest_raises=None,
                 direct_result=True, direct_raises=None):
        self._secondary = secondary
        self._dir = dir_
        self._busy = busy
        self._error = error
        self._plot_result = plot_result
        self._plot_raises = plot_raises
        self._nearest_result = nearest_result
        self._nearest_raises = nearest_raises
        self._direct_result = direct_result
        self._direct_raises = direct_raises

    def plot_secondary(self, dest=None, profile="fuel_safe", source=None):
        if self._plot_raises is not None:
            raise self._plot_raises
        if self._plot_result is not None:
            self._secondary = self._plot_result
            self._error = None

    def nearest(self, scoopable):
        if self._nearest_raises is not None:
            raise self._nearest_raises
        if self._nearest_result is not None:
            self._dir = self._nearest_result

    def direct_to(self, name):
        if self._direct_raises is not None:
            raise self._direct_raises
        if self._direct_result:
            self._dir = {"system": name, "star_class": "K", "dist_ly": 12.3, "scoopable": True}
        return self._direct_result

    def snapshot(self):
        return {"secondary": self._secondary, "dir": self._dir,
                 "busy": self._busy, "error": self._error}


def set_planner(**kwargs) -> FakeRoutePlanner:
    """Install a fresh FakeRoutePlanner as the module-level singleton that
    _get_route_planner() returns, bypassing the real RoutePlanner entirely."""
    planner = FakeRoutePlanner(**kwargs)
    server._route_planner = planner
    return planner


# --------------------------------------------------------------------------- #
# Sample data
# --------------------------------------------------------------------------- #

# 4-system primary F-PLN: Sol(G) -> Alpha(M) -> Beta(N, not scoopable) -> Colonia(K).
# Expected compare.primary: jumps=3, dist_ly=10+5+5=20.0, scoops=3 (G/M/K, not N).
NAV_DATA = {
    "event": "NavRoute",
    "Route": [
        {"StarSystem": "Sol", "StarClass": "G", "StarPos": [0.0, 0.0, 0.0]},
        {"StarSystem": "Alpha", "StarClass": "M", "StarPos": [10.0, 0.0, 0.0]},
        {"StarSystem": "Beta", "StarClass": "N", "StarPos": [10.0, 0.0, 5.0]},
        {"StarSystem": "Colonia", "StarClass": "K", "StarPos": [15.0, 0.0, 5.0]},
    ],
}

FAKE_SECONDARY = {
    "profile": "FUEL-SAFE", "source": "Sol", "destination": "Colonia",
    "jumps": 5, "dist_ly": 42.0, "scoops": 2, "risk": "LOW",
    "plotted_at": "2026-07-13T00:00:00+00:00",
    "systems": [{"system": "Sol", "dist_ly": None, "scoopable": True,
                 "neutron": False, "must_refuel": False}],
}

# Executable secondary for the sec.activate / executor checks:
# Sol -> Alpha (refuel stop = first segment endpoint) -> Colonia.
EXEC_ROUTE = {
    "profile": "FUEL-SAFE", "source": "Sol", "destination": "Colonia",
    "jumps": 2, "dist_ly": 60.0, "scoops": 1, "risk": "LOW",
    "plotted_at": "2026-07-16T00:00:00+00:00",
    "systems": [
        {"system": "Sol", "dist_ly": None, "scoopable": True, "neutron": False,
         "must_refuel": False, "fuel_used": None, "fuel_tank": 32.0},
        {"system": "Alpha", "dist_ly": 30.0, "scoopable": True, "neutron": False,
         "must_refuel": True, "fuel_used": 4.0, "fuel_tank": 32.0},
        {"system": "Colonia", "dist_ly": 30.0, "scoopable": True, "neutron": False,
         "must_refuel": False, "fuel_used": 4.0, "fuel_tank": 28.0},
    ],
}


# --------------------------------------------------------------------------- #
# WS helpers
# --------------------------------------------------------------------------- #

async def collect(ws, n: int, timeout: float = 5.0) -> list[dict]:
    """Read exactly n JSON messages (order not assumed -- see by_type),
    skipping the periodic status_snapshot broadcasts: the QA status loop
    ticks fast and would otherwise interleave them into every check."""
    msgs = []
    async with asyncio.timeout(timeout):
        while len(msgs) < n:
            m = await ws.receive_json()
            if m.get("type") == "status_snapshot":
                continue
            msgs.append(m)
    return msgs


def by_type(msgs: list[dict]) -> dict[str, dict]:
    return {m.get("type"): m for m in msgs}


async def recv_type(ws, wanted: tuple, timeout: float = 6.0) -> dict:
    """Next message whose type is in `wanted`, skipping the periodic
    status_snapshot broadcasts from the 1 Hz loop."""
    async with asyncio.timeout(timeout):
        while True:
            m = await ws.receive_json()
            if m.get("type") in wanted:
                return m


# --------------------------------------------------------------------------- #
# Checks
# --------------------------------------------------------------------------- #

async def check_sec_get(ws):
    set_planner(secondary=None, dir_=None, busy=False, error=None)
    await ws.send_json({"cmd": "sec.get"})
    m = (await collect(ws, 1))[0]
    data = m.get("data") or {}
    primary = (data.get("compare") or {}).get("primary") or {}
    ok = (
        m.get("type") == "sec_route"
        and primary.get("jumps") == 3
        and abs((primary.get("dist_ly") or -1) - 20.0) < 1e-6
        and primary.get("scoops") == 3
    )
    check("sec.get: sec_route with compare.primary from fake nav_route", ok, detail=str(m))


async def check_sec_plot_success(ws):
    set_planner(plot_result=dict(FAKE_SECONDARY))
    await ws.send_json({"cmd": "sec.plot", "profile": "fuel_safe", "dest": "Colonia"})
    msgs = await collect(ws, 2)
    types = by_type(msgs)
    ok = "sec_plot_started" in types and "sec_route" in types
    if ok:
        data = types["sec_route"].get("data") or {}
        ok = (
            (data.get("secondary") or {}).get("destination") == "Colonia"
            and "compare" in data
        )
    check("sec.plot: ack sec_plot_started then broadcast sec_route", ok, detail=str(msgs))


async def check_sec_plot_busy(ws):
    set_planner(plot_raises=PlotError("PLOT IN PROGRESS"))
    await ws.send_json({"cmd": "sec.plot", "profile": "fast"})
    msgs = await collect(ws, 2)
    types = by_type(msgs)
    ok = (
        "sec_plot_started" in types
        and types.get("error", {}).get("text") == "PLOT IN PROGRESS"
    )
    check("sec.plot: busy-guard PlotError -> error PLOT IN PROGRESS", ok, detail=str(msgs))


async def check_sec_activate(ws, fake_ap):
    # (a) no plotted secondary -> clean error, executor stays inactive
    set_planner(secondary=None)
    server._route_executor = None
    await ws.send_json({"cmd": "sec.activate"})
    m = await recv_type(ws, ("error",))
    check("sec.activate: no SEC route -> error", "NO SEC ROUTE" in (m.get("text") or ""), str(m))

    # (b) executable secondary -> real activation, exec_state broadcast
    set_planner(secondary=dict(EXEC_ROUTE))
    await ws.send_json({"cmd": "sec.activate"})
    m = await recv_type(ws, ("exec_state",))
    d = m.get("data") or {}
    ok = (
        d.get("active") is True and d.get("status") == "ACTIVE"
        and d.get("idx") == 0 and d.get("jumps_total") == 2
        and d.get("segment_target") == "Alpha"     # first refuel stop
        and d.get("map_target") == "Alpha"         # stub driver got the segment
        and d.get("next_refuel_in") == 1
    )
    check("sec.activate: executable route -> exec_state ACTIVE, segment to map driver", ok, str(d))

    # (c) the 1 Hz status tick advances the executor on a location change
    fake_ap.status["location"] = "Alpha"
    m = await recv_type(ws, ("exec_state",))
    d = m.get("data") or {}
    ok = (
        d.get("idx") == 1 and d.get("status") == "ACTIVE"
        and d.get("map_target") == "Colonia"       # refuel stop -> next segment plotted
        and d.get("next_system") == "Colonia" and d.get("remaining_jumps") == 1
    )
    check("status tick: FSD jump advances executor + hands next segment", ok, str(d))

    # (d) off route and back
    fake_ap.status["location"] = "Wrong Turn"
    m = await recv_type(ws, ("exec_state",))
    d = m.get("data") or {}
    check("status tick: unknown system -> OFF ROUTE",
          d.get("status") == "OFF ROUTE" and d.get("off_route_at") == "Wrong Turn", str(d))

    # (e) destination -> COMPLETE
    fake_ap.status["location"] = "Colonia"
    m = await recv_type(ws, ("exec_state",))
    d = m.get("data") or {}
    check("status tick: destination -> COMPLETE",
          d.get("status") == "COMPLETE" and d.get("active") is False, str(d))

    # (f) exec.get / exec.stop round-trip
    await ws.send_json({"cmd": "exec.get"})
    m = await recv_type(ws, ("exec_state",))
    check("exec.get: returns current executor state",
          (m.get("data") or {}).get("status") == "COMPLETE", str(m))
    await ws.send_json({"cmd": "exec.stop"})
    m = await recv_type(ws, ("exec_state",))
    check("exec.stop: deactivates the executor",
          (m.get("data") or {}).get("status") == "INACTIVE", str(m))


async def check_dir_nearest(ws):
    candidate = {"system": "Alpha Centauri", "star_class": "K", "dist_ly": 4.2, "scoopable": True}
    set_planner(nearest_result=candidate)
    await ws.send_json({"cmd": "dir.nearest", "scoopable": True})
    msgs = await collect(ws, 2)
    types = by_type(msgs)
    ok = "dir_started" in types and "dir_state" in types
    if ok:
        d = (types["dir_state"].get("data") or {}).get("dir") or {}
        ok = d.get("system") == "Alpha Centauri"
    check("dir.nearest: ack dir_started then broadcast dir_state", ok, detail=str(msgs))


async def check_dir_set_invalid(ws):
    set_planner(direct_result=False)
    await ws.send_json({"cmd": "dir.set", "system": "Nowhere"})
    m = (await collect(ws, 1))[0]
    ok = m.get("type") == "error" and m.get("text") == "INVALID"
    check("dir.set: unresolvable system -> error INVALID", ok, detail=str(m))


async def check_dir_set_valid(ws):
    set_planner(direct_result=True)
    await ws.send_json({"cmd": "dir.set", "system": "Colonia"})
    m = (await collect(ws, 1))[0]
    ok = m.get("type") == "dir_state"
    if ok:
        d = (m.get("data") or {}).get("dir") or {}
        ok = d.get("system") == "Colonia"
    check("dir.set: valid system -> broadcast dir_state with candidate", ok, detail=str(m))


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #

async def run_all() -> None:
    fake_ap = FakeAP(nav_data=NAV_DATA)
    loop = asyncio.get_running_loop()
    app, _broadcaster = server.create_app(fake_ap, loop)

    test_server = TestServer(app)
    client = TestClient(test_server)
    await client.start_server()
    # The status/executor tick normally runs in the launcher (edap_headless /
    # demo server) -- start the real loop here so the executor checks can
    # drive it, with a fast interval to keep the QA quick.
    status_task = asyncio.create_task(
        server._status_snapshot_loop(fake_ap, _broadcaster, 0.1))
    try:
        ws = await client.ws_connect("/ws")
        try:
            # connect-time hello (snapshots are skipped by collect) + prove
            # the status stream itself is flowing.
            initial = await collect(ws, 1)
            ok = initial[0].get("type") == "hello"
            snap = await recv_type(ws, ("status_snapshot",))
            ok = ok and snap.get("type") == "status_snapshot"
            check("ws connect: initial hello + status_snapshot", ok, detail=str(initial))

            await check_sec_get(ws)
            await check_sec_plot_success(ws)
            await check_sec_plot_busy(ws)
            await check_sec_activate(ws, fake_ap)
            await check_dir_nearest(ws)
            await check_dir_set_invalid(ws)
            await check_dir_set_valid(ws)
        finally:
            await ws.close()
    finally:
        status_task.cancel()
        try:
            await status_task
        except asyncio.CancelledError:
            pass
        await client.close()


def main() -> int:
    asyncio.run(run_all())

    total = len(_results)
    passed = sum(1 for ok, _ in _results if ok)
    print(f"\n{passed}/{total} checks passed.")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
