---
name: edap-cleanup-project
description: "The ED_Autopilot cleanup/decomposition/avionics-reliability project — plan, TODO, current phase"
metadata: 
  node_type: memory
  type: project
  originSessionId: 00b1c7fa-9b0a-48ea-b5f2-0789fbd3f484
---

Multi-stage project on ED_Autopilot, branch `cleanup-decompose-avionics`. Goal: the autopilot once ran a ship dry of fuel with no warning; instead of patching, rework toward an "avionics" approach (redundant data sources, cross-checks, safe-state, observable pauses).

**Two planning docs** (in `C:\Users\nafan\.claude\plans\`):
- `fss-glowing-island.md` — the WHY/WHAT (rationale, boundaries). Verified against real code; 6 discrepancies fixed (EDFSS.py is an ELW-advisor dependency that stays; `ship_configs` is a dict in `EDAP_data.py:213+` NOT a json file; NavRouteParser already wired; etc.).
- `fss-glowing-island-TODO.md` — the HOW/WHO: phased checklist with per-task model tags (🐤 Haiku mechanical / 🔵 Sonnet code edits / 🟣 Opus architecture). Delegate to a subagent ONLY when self-contained (subagents cold-start and re-read context); otherwise do it inline switching `/model`.

**Phases:** 0 prep (done: branch + gitignore + venv + mock env), 1 remove peripherals (Robigo/AFK/TCE/Waypoint/DSS/EDMesg/GalaxyMap/SystemMap/Auto-FSS), 2 decompose ED_AP.py into services/, 3 fuel sensor-fusion (FuelState.py), 4 Watchdog+state-machine, 5 ship-profile timings, 6 focus-loss pause + click-through overlay.

**Key discovery for Phase 1:** `ED_AP.py` directly imports+instantiates the peripherals in `__init__` (lines 24-46, 192-208), and some are used elsewhere (galaxy_map:733/3992, afk_combat:3956-3967, mesg_server:205-208). So removal is Sonnet-inline (untangle imports+instances+uses), not blind file deletion.

**Verification:** no test harness exists; after each step run `import EDAPGui` + launch GUI here; real in-game runs done on the ED-installed machine. See [[dev-env-setup]].

Work is done within ONE Claude Code session to keep context warm (user watches usage limits — don't start a heavy iteration near a limit). Session resumes rely on these memories + the plan/TODO files + `[x]` checkboxes in the TODO.
