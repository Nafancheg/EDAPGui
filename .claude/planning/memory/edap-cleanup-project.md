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
- `fss-glowing-island-TODO.md` — the HOW/WHO: phased checklist with per-task model tags (🐤 Haiku mechanical / 🔵 Sonnet code edits / 🟣 Opus architecture). Route ALL tasks through subagents with the model I set per those tags; never ask the user about model or to switch `/model` (see [[feedback-delegate-model-via-subagent]]). After each coding subagent, a read-only QA subagent gates the commit ([[feedback-qa-subagent-before-commit]]).

**Phases:** 0 prep (DONE), 1 remove peripherals (DONE), 2 decompose ED_AP.py into services/ (DONE 2026-07-07 — fuel/navigation/jump/docking/elw_advisor + JsonConfigIO; ED_AP.py 4574→1527 lines; every method-move parity-verified IDENTICAL), 3 fuel sensor-fusion (FuelState.py), 4 Watchdog+state-machine, 5 ship-profile timings, 6 focus-loss pause, 7 web MCDU + headless server (see [[web-ui-direction]]).

**ORDER REVISED (2026-07-07, user decision): Phase 7 goes NEXT, before 3–4.** Rationale: Phases 3–4 (FuelState sensor-fusion, Watchdog/state-machine) can't be built blind — they must be designed/tuned against the REAL game (live Fuel fields, source disagreements, overheat, alignment failures); static mocks on this game-less laptop can't calibrate the thresholds/voting, and unvalidated reliability code is worse than none. Phase 7 (web MCDU + headless) is ~80–90% developable here WITHOUT the game and doubles as the observability instrument for 3–4. Added an early Phase 7.0 "capture harness" sub-step: record raw Status.json/journal/NavRoute during real play into replay logs so 3–4 can later be developed on realistic data, not stubs. Phases 3–6 are now flagged gated-on-game.

**Key discovery for Phase 1:** `ED_AP.py` directly imports+instantiates the peripherals in `__init__` (lines 24-46, 192-208), and some are used elsewhere (galaxy_map:733/3992, afk_combat:3956-3967, mesg_server:205-208). So removal is Sonnet-inline (untangle imports+instances+uses), not blind file deletion.

**Verification:** no test harness exists; after each step run `import EDAPGui` + launch GUI here; real in-game runs done on the ED-installed machine. See [[dev-env-setup]].

Work is done within ONE Claude Code session to keep context warm (user watches usage limits — don't start a heavy iteration near a limit). Session resumes rely on these memories + the plan/TODO files + `[x]` checkboxes in the TODO.
