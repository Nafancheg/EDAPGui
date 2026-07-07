---
name: web-ui-direction
description: Strategic decision — replace tkinter GUI with a headless server + web MCDU interface (tablet)
metadata: 
  node_type: memory
  type: project
  originSessionId: 00b1c7fa-9b0a-48ea-b5f2-0789fbd3f484
---

**Decision (2026-07-06):** The tkinter GUI (`EDAPGui.py`) will be **fully replaced** by a headless autopilot service + a **web interface** the user opens on a tablet/browser next to the keyboard — a real MCDU-style cockpit terminal, matching the "avionics" theme (compute unit separate from display terminal). User designed the current UI as an aircraft MCDU (dual screen, LSK side keys, scratchpad) but finds it cluttered; the web rebuild is the real fix, not re-skinning tkinter.

**Sequencing:** cleanup (Phase 1) + decomposition (Phase 2) FIRST — they produce the headless core that a web server needs. Web server + MCDU frontend is a NEW later phase. This ordering was user's explicit choice.

**Consequences that change earlier phases:**
- **Do NOT delete `EDMesg`** (EDAP_EDMesg_Server/Client/Interface, EDMesg/ dir) in Phase 1 as the old plan said. It's an existing external-control IPC layer (ZeroMQ) — a candidate foundation/reference for the web server. Re-mark it "keep / re-evaluate", not "remove". The `ap_ckb` callback bridge is the existing seam between core and UI — formalize it, don't rebuild from scratch.
- **Do NOT redesign or lovingly decompose `EDAPGui.py`.** It gets deleted with the web replacement. Phase 1 GUI cleanup (TODO 1.4) = bare minimum so the GUI doesn't crash on removed features; no polish.

**Revised assessment (2026-07-06, after user pushback):** metaphor-as-choice 9/10 (carries an interaction *model*, not just a look); current static execution 5/10 (LSK not yet wired, pages static); ceiling is very high. My initial "5/10" undervalued the *potential* — I judged the photo, user showed the film.

**FULL MCDU workflow is the chosen design (not decorative).** Real-MCDU interaction model, exactly as user wants:
- **Hard keys = modes/pages** (like Airbus FPLN/DATA/PROG/PERF): `ROUTE`, `FUEL`, `SHIP`, `PROG`, `NAV`. They select WHICH data page is shown, they are not actions.
- **LSK (6 per side) = context actions on the data row facing them.** Meaning changes per page. NOT 36 fixed buttons — 6+6 contextual slots re-purposed each page.
- **Scratchpad = buffer:** type a value, "throw" it into a row via LSK. Rare here (mostly selection) but needed e.g. "find scoopable star within X ly" — type X, drop into field.

**Worked example (user's own, the north star):** ROUTE page lists systems along the route, each flagged scoopable/not. LSK on a non-scoopable system → submenu (RSS scan / body info / find fuel within radius). An LSK "SCOOP SEARCH" → type radius in scratchpad → page rebuilds into nearby scoopable stars, each with an LSK "route via this". `FUEL` hard key → instant FuelState (tank, N-jump forecast, next scoop).

**CRITICAL cross-phase consequence:** this makes the MCDU frontend the natural display surface for the avionics core. So Phases 2-4 services must expose **structured data for pages**, not scalar values for toggles: route = list of systems WITH scoopable flags; FuelState = a forecast struct; `navigation_service`/`NavRouteParser` feed ROUTE page. Design each service with its future "MCDU contract" in mind. The UI justifies the core and vice-versa — this may be the best UI of any ED autopilot because nobody builds a *real* MCDU workflow, only forms-with-buttons.

Also: one screen with page-flip (not two panels), compact scratchpad, no duplicated SHIP/status info.

See [[edap-cleanup-project]] and [[dev-env-setup]].
