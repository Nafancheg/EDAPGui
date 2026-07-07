---
name: dev-env-setup
description: "How the ED_Autopilot dev environment is set up on this laptop (Python, venv, mock ED files)"
metadata: 
  node_type: memory
  type: project
  originSessionId: 00b1c7fa-9b0a-48ea-b5f2-0789fbd3f484
---

Dev machine for ED_Autopilot (laptop, `nafancheg@live.com`). Elite Dangerous is NOT installed here and the laptop can't run it — all game verification happens on a different machine.

**Repo location:** git root is `C:\Users\nafan\Documents\ED_Autopilot\` (moved up from the old nested `EDAPGui/` on 2026-07-06). Working branch for the cleanup/decomposition project: `cleanup-decompose-avionics` (off `81071e7`). `.claude/` is gitignored.

**Python/venv:** Machine had only Python 3.13; project needs 3.11 (pinned `torch==2.12.0`/`paddlepaddle==3.2.2` have cp311 wheels). Installed Python 3.11.9 via `winget install Python.Python.3.11` (sits beside 3.13; use `py -3.11`). venv at `venv\` created with `py -3.11 -m venv venv`, all `requirements.txt` installed (123 pkgs). Launch: `.\venv\Scripts\python.exe EDAPGui.py`.

**Mock ED files (to launch GUI without the game):** EDAP startup hard-`raise`s if ED settings/journal/binds/live-JSON are missing. Run `.\tools\setup_mock_env.ps1` (committed `cfc522c`) to write minimal valid mocks into `%LOCALAPPDATA%\Frontier Developments\...` and `%USERPROFILE%\Saved Games\Frontier Developments\Elite Dangerous\`. After that GUI starts clean (exit 0). Two harmless ERRORs remain in the log ("Could not find window 'Elite - Dangerous (CLIENT)'" / "could not be located on any monitor") — the game window isn't running; these do NOT stop startup. Only `EDGraphicsSettings`, `EDPlayerSettings`, `EDJournal`, `EDKeys`, and the parsers (`CargoParser` etc.) raise hard on missing files; `Screen` degrades gracefully.

**Verification split:** here we can run `import EDAPGui`, launch the GUI, and check tabs/checkboxes visually. Real autopilot runs (FSD Route Assist, refuel, watchdog) need the machine with ED installed. See [[edap-cleanup-project]].
