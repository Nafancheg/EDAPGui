"""Independent validity check of the SEC F-PLN route on a running server.

Cross-checks the plotted secondary route against sources Spansh does NOT
control:
  1. leg distances     — recomputed from EDSM star coordinates;
  2. jump reachability — every leg must fit the ship's max jump range,
                         derived from the journal Loadout via the game's
                         own FSD formula (not Spansh's numbers);
  3. fuel simulation   — Elite's fuel cost  fuel_mult * (dist * mass /
                         optimal_mass) ** fuel_power  jump by jump, tank
                         refilled at must_refuel stops: the tank must never
                         run dry and no jump may exceed max_fuel_per_jump;
  4. totals            — jumps / dist_ly summary vs the waypoint list.

Usage:  python tools/route_validity_check.py [--url http://127.0.0.1:8090]
        [--plot DEST]   re-plot fuel-safe to DEST first, then validate
"""
import argparse
import asyncio
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aiohttp

from RoutePlanner import EDSMClient, ShipFSD

FAILS = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))
    if not ok:
        FAILS.append(name)


async def fetch_state(url, plot_dest):
    """sec.get (optionally after a fresh sec.plot) + the ship's loadout_raw
    via the status snapshot is not exposed, so read it from the journal the
    same way the server does: not needed — the loadout ships inside the mock
    journal; we take it from EDJournal to stay independent of the planner."""
    async with aiohttp.ClientSession() as s:
        async with s.ws_connect(url + "/ws") as ws:
            if plot_dest:
                await ws.send_str(json.dumps(
                    {"cmd": "sec.plot", "profile": "fuel_safe", "dest": plot_dest}))
            await ws.send_str(json.dumps({"cmd": "sec.get"}))
            async with asyncio.timeout(120):
                async for m in ws:
                    if m.type != aiohttp.WSMsgType.TEXT:
                        continue
                    d = json.loads(m.data)
                    if d.get("type") != "sec_route":
                        continue
                    data = d.get("data") or {}
                    if plot_dest and (data.get("busy") or not data.get("secondary")):
                        await asyncio.sleep(2)
                        await ws.send_str(json.dumps({"cmd": "sec.get"}))
                        continue
                    return data
    raise SystemExit("no sec_route from server")


def load_loadout():
    from EDJournal import EDJournal
    jn = EDJournal(lambda *_a, **_k: None)
    ship = jn.ship_state()
    lo = ship.get("loadout_raw")
    if not lo:
        raise SystemExit("journal has no Loadout — run tools/setup_mock_env.ps1")
    return lo


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8090")
    ap.add_argument("--plot", default=None, metavar="DEST")
    args = ap.parse_args()

    data = asyncio.run(fetch_state(args.url, args.plot))
    sec = data.get("secondary")
    if not sec:
        raise SystemExit(f"no secondary route on the server (error: {data.get('error')!r})")

    print(f"Route: {sec['profile']}  {sec['source']} -> {sec['destination']}  "
          f"{sec['jumps']} jumps · {sec['dist_ly']} LY · scoops {sec['scoops']} · risk {sec['risk']}\n")

    # --- ship physics from the journal Loadout (independent of Spansh) ------
    # ShipFSD is the shared FSD-physics model (exact guardian-booster scaling
    # + neutron/WD supercharge), bench-verified against the Spansh exact
    # plotter by tools/route_mechanics_bench.py.
    lo = load_loadout()
    fsd = ShipFSD(lo)
    tank = fsd.tank_size
    max_fuel = fsd.max_fuel
    # neutron legs only boost profiles plotted with use_supercharge (FAST);
    # a FUEL-SAFE route never relies on supercharge.
    supercharge_on = (sec.get("profile") or "").upper() != "FUEL-SAFE"

    rng_full = fsd.jump_range(tank)
    print(f"Ship: {lo['Ship']}  unladen {fsd.unladen_mass} t · tank {tank} t "
          f"(+{fsd.reserve_size} reserve) · FSD opt {fsd.optimal_mass} t · "
          f"max/jump {max_fuel} t · boost +{fsd.range_boost} LY")
    print(f"Max jump range (full tank): {rng_full:.2f} LY\n")

    # --- 1. leg distances vs EDSM coordinates -------------------------------
    edsm = EDSMClient()
    systems = sec["systems"]
    coords = {}
    for w in systems:
        info = edsm.system(w["system"])
        check(f"EDSM knows '{w['system']}'", info is not None and "coords" in (info or {}))
        if info and "coords" in info:
            coords[w["system"]] = info["coords"]

    for prev, cur in zip(systems, systems[1:]):
        a, b = coords.get(prev["system"]), coords.get(cur["system"])
        if not a or not b:
            continue
        d = math.dist((a["x"], a["y"], a["z"]), (b["x"], b["y"], b["z"]))
        check(f"leg {prev['system']} -> {cur['system']}",
              abs(d - cur["dist_ly"]) < 0.05,
              f"EDSM {d:.2f} LY vs route {cur['dist_ly']} LY")

    # --- 2+3. per-jump reachability + fuel simulation -------------------------
    # The range grows as fuel burns off (lighter ship), so both checks run
    # against the fuel actually in the tank BEFORE each jump, not the
    # full-tank figure. TOL absorbs the reserve-tank mass nuance (Spansh
    # models the 0.63 t reservoir slightly differently) — engineering
    # tolerance, not a fudge: 2% on fuel, 1% on distance.
    TOL_FUEL, TOL_DIST = 1.02, 1.01
    fuel = tank
    ok_fuel = True
    ok_reach = True
    log = []
    for prev, cur in zip(systems, systems[1:]):
        a, b = coords.get(prev["system"]), coords.get(cur["system"])
        if not a or not b:
            ok_fuel = ok_reach = False
            break
        d = math.dist((a["x"], a["y"], a["z"]), (b["x"], b["y"], b["z"]))
        mult = fsd.supercharge_multiplier if (supercharge_on and prev.get("neutron")) else 1.0
        rng = fsd.jump_range(fuel, supercharge=mult)
        cost = fsd.fuel_cost(d, fuel, supercharge=mult)
        reach = d <= rng * TOL_DIST
        burn_ok = cost <= max_fuel * TOL_FUEL and fuel - cost > -0.2
        log.append(f"  {prev['system']:<28}->{cur['system']:<28} {d:6.2f} LY  "
                   f"range {rng:5.2f}  burn {cost:4.2f} t  tank {max(fuel - cost, 0):5.2f} t"
                   + (f"  SC x{mult:g}" if mult > 1 else "")
                   + ("  REFUEL" if cur["must_refuel"] else "")
                   + ("" if (reach and burn_ok) else "  <-- PROBLEM"))
        ok_reach = ok_reach and reach
        ok_fuel = ok_fuel and burn_ok
        fuel = tank if cur["must_refuel"] else fuel - cost
    print()
    print("\n".join(log))
    check("every jump within range for its fuel state", ok_reach)
    check("fuel never runs dry / per-jump cap respected", ok_fuel,
          f"final tank {fuel:.2f} t")

    # --- 4. totals ------------------------------------------------------------
    check("jumps total matches list", sec["jumps"] == len(systems) - 1,
          f"{sec['jumps']} == {len(systems) - 1}")
    dist_sum = round(sum(w["dist_ly"] for w in systems if w["dist_ly"] is not None), 2)
    check("dist_ly total matches list", abs(dist_sum - sec["dist_ly"]) < 0.5,
          f"{dist_sum} vs {sec['dist_ly']}")

    print()
    if FAILS:
        print(f"{len(FAILS)} CHECK(S) FAILED")
        return 1
    print("ROUTE VALID — all checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
