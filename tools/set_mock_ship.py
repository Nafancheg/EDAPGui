"""Mock-ship loader / ship-profile inspector.

Without arguments: print the CURRENT ship profile as the core sees it (the
"am I 100% sure what the plan will assume" pre-flight check) — name,
fingerprint, drive, ranges.

With a file argument: load a ship into the mock environment by APPENDING a
LoadGame+Loadout pair to the mock journal — exactly what the game writes on
a ship swap, so the running headless server picks it up live (no restart)
and the executor's ship-change watch fires if a route is active. Accepts:
  * an SLEF export (EDSY/Coriolis "journal" format: [{header, data}, ...]);
  * a raw journal Loadout event (single JSON object).

Usage:
    python tools/set_mock_ship.py                 # inspect current profile
    python tools/set_mock_ship.py mybuild.slef    # load a build
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from RoutePlanner import PlotError, ShipFSD, ship_fingerprint, ship_summary  # noqa: E402


def journal_path() -> str:
    from EDJournal import EDJournal
    return EDJournal(lambda *_a, **_k: None).current_log


def append_journal(path: str, event: dict) -> None:
    event.setdefault("timestamp",
                     datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
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


def extract_loadout(payload) -> dict:
    """SLEF array / {header,data} wrapper / bare Loadout event -> Loadout."""
    if isinstance(payload, list):
        payload = payload[0]
    if isinstance(payload, dict) and "data" in payload:
        payload = payload["data"]
    if not (isinstance(payload, dict) and payload.get("event") == "Loadout"):
        raise SystemExit("input is not an SLEF export or journal Loadout event")
    return payload


def show(loadout: dict, title: str) -> None:
    s = ship_summary(loadout)
    fsd = ShipFSD(loadout)
    print(f"{title}")
    print(f"  ship         : {s['name']}")
    print(f"  fingerprint  : {s['fingerprint']}")
    print(f"  max range    : {s['max_range']} LY"
          f"  (journal MaxJumpRange: {loadout.get('MaxJumpRange')})")
    print(f"  full-tank    : {fsd.jump_range(fsd.tank_size):.2f} LY laden")
    print(f"  supercharged : x{s['supercharge_multiplier']} -> "
          f"{fsd.jump_range(fsd.tank_size, supercharge=s['supercharge_multiplier']):.2f} LY")
    print(f"  guardian     : +{s['range_boost']} LY")
    print(f"  tank         : {s['tank']} t (+{fsd.reserve_size} reserve)"
          f"  · unladen {fsd.unladen_mass} t · cargo cap {loadout.get('CargoCapacity')}")


def main() -> int:
    if len(sys.argv) < 2:
        from EDJournal import EDJournal
        state = EDJournal(lambda *_a, **_k: None).ship_state()
        loadout = (state or {}).get("loadout_raw")
        if not loadout:
            raise SystemExit("journal has no Loadout — run tools/setup_mock_env.ps1")
        show(loadout, "CURRENT ship profile (as the core sees it):")
        return 0

    with open(sys.argv[1], encoding="utf-8") as f:
        loadout = extract_loadout(json.load(f))
    try:
        show(loadout, "Loading ship profile:")
    except PlotError as e:
        raise SystemExit(f"REJECTED — loadout fails physics validation: {e}")

    path = journal_path()
    ship = loadout.get("Ship") or "ship"
    append_journal(path, {"event": "LoadGame", "Commander": "TestCmdr",
                          "Ship": ship, "ShipID": 1, "GameMode": "Solo",
                          "FuelLevel": (loadout.get("FuelCapacity") or {}).get("Main", 0),
                          "FuelCapacity": (loadout.get("FuelCapacity") or {}).get("Main", 0)})
    append_journal(path, dict(loadout))
    print(f"\nappended LoadGame+Loadout to {path}")
    print("A running headless server picks this up within a second.")
    print(f"new fingerprint: {ship_fingerprint(loadout)} — any previously "
          f"plotted route now fails activation with SHIP CHANGED; replot.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
