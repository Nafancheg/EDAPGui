"""Mock flight: fly an activated route by writing real journal events.

Drives the FULL stack end-to-end on a game-less machine: the headless server
(edap_headless.py) runs the real core + real EDJournal over the mock journal;
this tool plots a SEC route, activates it, then "flies" it by appending
FSDJump / FuelScoop lines to the mock journal file — exactly what the game
would write. The server's 1 Hz status tick picks the jumps up, the
RouteExecutor advances leg by leg, hands each segment to the (stub)
GalaxyMapDriver and broadcasts exec_state, which this tool prints and
verifies. Optionally simulates a wrong jump (--deviate) to exercise the
OFF ROUTE -> rejoin path.

Usage (headless server must be running):
    python tools/mock_flight.py [--url http://127.0.0.1:8090]
        [--dest Maia] [--profile fuel_safe|fast] [--interval 1.5] [--deviate]

Exit code 0 = the route reached COMPLETE with every leg confirmed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import aiohttp  # noqa: E402


def journal_path() -> str:
    """The journal file the server is reading — resolved the same way the
    core does (EDJournal.get_latest_log)."""
    from EDJournal import EDJournal
    jn = EDJournal(lambda *_a, **_k: None)
    return jn.current_log


def append_journal(path: str, event: dict) -> None:
    event.setdefault("timestamp",
                     datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    # the mock journal may lack a trailing newline — never glue two events
    needs_nl = False
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        if f.tell() > 0:
            f.seek(-1, os.SEEK_END)
            needs_nl = f.read(1) != b"\n"
    with open(path, "a", encoding="utf-8") as f:
        if needs_nl:
            f.write("\n")
        f.write(json.dumps(event) + "\n")


def jump_event(system: str, dist, fuel_used, fuel_level) -> dict:
    return {"event": "FSDJump", "StarSystem": system, "SystemAddress": 0,
            "StarPos": [0.0, 0.0, 0.0], "JumpDist": float(dist or 0.0),
            "FuelUsed": float(fuel_used or 0.0),
            "FuelLevel": float(fuel_level if fuel_level is not None else 0.0)}


async def recv_type(ws, wanted: tuple, timeout: float = 30.0) -> dict:
    async with asyncio.timeout(timeout):
        while True:
            m = json.loads((await ws.receive()).data)
            if m.get("type") in wanted:
                return m


async def fly(args) -> int:
    jpath = journal_path()
    print(f"journal: {jpath}")

    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(args.url + "/ws") as ws:
            # --- route: reuse a matching plotted SEC or plot a fresh one ----- #
            await ws.send_str(json.dumps({"cmd": "sec.get"}))
            data = (await recv_type(ws, ("sec_route",)))["data"] or {}
            sec = data.get("secondary")
            if not sec or (args.dest and sec.get("destination", "").lower() != args.dest.lower()):
                print(f"plotting {args.profile} route to {args.dest} …")
                await ws.send_str(json.dumps(
                    {"cmd": "sec.plot", "profile": args.profile, "dest": args.dest}))
                while True:
                    data = (await recv_type(ws, ("sec_route",), timeout=300))["data"] or {}
                    if data.get("busy"):
                        continue
                    sec = data.get("secondary")
                    if not sec or data.get("error"):
                        print(f"PLOT FAILED: {data.get('error')!r}")
                        return 1
                    break
            systems = sec["systems"]
            print(f"route: {sec['profile']}  {sec['source']} -> {sec['destination']}  "
                  f"{sec['jumps']} jumps · {sec['dist_ly']} LY · scoops {sec['scoops']}")

            # --- activate ------------------------------------------------------ #
            await ws.send_str(json.dumps({"cmd": "sec.activate"}))
            d = (await recv_type(ws, ("exec_state",)))["data"] or {}
            if not d.get("active"):
                print(f"ACTIVATE FAILED: {d!r}")
                return 1
            print(f"activated: status {d['status']}, map driver got {d['map_target']!r}\n")

            # --- fly it ---------------------------------------------------------- #
            failures = 0
            start_idx = d["idx"]
            tank = None
            deviate_at = (start_idx + 1 + len(systems)) // 2 if args.deviate else None
            fuel = systems[start_idx].get("fuel_tank")
            for i in range(start_idx + 1, len(systems)):
                if deviate_at == i:
                    print("-- deviation: jumping OFF the plan …")
                    append_journal(jpath, jump_event("QA Wrong Turn", 12.0, 1.0, fuel or 10.0))
                    d = (await recv_type(ws, ("exec_state",)))["data"] or {}
                    ok = d.get("status") == "OFF ROUTE" and d.get("off_route_at") == "QA Wrong Turn"
                    print(f"   exec: {d.get('status')} at {d.get('off_route_at')!r}  "
                          f"{'ok' if ok else 'UNEXPECTED'}")
                    failures += 0 if ok else 1
                    await asyncio.sleep(args.interval)

                s = systems[i]
                arrived_fuel = None
                if fuel is not None and s.get("fuel_used") is not None:
                    arrived_fuel = max(fuel - s["fuel_used"], 0.0)
                append_journal(jpath, jump_event(
                    s["system"], s.get("dist_ly"), s.get("fuel_used"), arrived_fuel))
                if s.get("must_refuel") and s.get("fuel_tank") is not None:
                    append_journal(jpath, {"event": "FuelScoop", "Scooped": 5.0,
                                           "Total": s["fuel_tank"]})
                fuel = s.get("fuel_tank") if s.get("fuel_tank") is not None else arrived_fuel

                d = (await recv_type(ws, ("exec_state",)))["data"] or {}
                expect_last = i == len(systems) - 1
                ok = (d.get("idx") == i
                      and d.get("status") == ("COMPLETE" if expect_last else "ACTIVE"))
                failures += 0 if ok else 1
                plan = s.get("fuel_tank")
                actual = d.get("fuel_actual")
                print(f"   {i:>2}/{len(systems) - 1}  {s['system']:<28} {d.get('status'):<9} "
                      f"next {str(d.get('next_system')):<24} map->{str(d.get('map_target')):<24} "
                      f"fuel plan {plan} / jrnl {actual}"
                      + ("" if ok else "   <-- UNEXPECTED " + str(d)))
                tank = actual
                await asyncio.sleep(args.interval)

            print(f"\nfinal: {d.get('status')}  jumps {d.get('jumps_done')}/{d.get('jumps_total')}  "
                  f"fuel {tank}")
            if failures or d.get("status") != "COMPLETE":
                print(f"{failures} step(s) FAILED")
                return 1
            print("MOCK FLIGHT COMPLETE — executor tracked every leg.")
            return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8090")
    ap.add_argument("--dest", default="Maia")
    ap.add_argument("--profile", default="fuel_safe")
    ap.add_argument("--interval", type=float, default=1.5)
    ap.add_argument("--deviate", action="store_true",
                    help="inject one off-plan jump mid-route (OFF ROUTE -> rejoin)")
    args = ap.parse_args()
    return asyncio.run(fly(args))


if __name__ == "__main__":
    sys.exit(main())
