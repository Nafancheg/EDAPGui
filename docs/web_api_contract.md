# EDAPGui <-> Core Contract Inventory

Purpose: precise inventory of everything the tkinter GUI (`EDAPGui.py`) reads from,
writes to, or invokes on the core (`ED_AP.py` / `services/*`), so the future
headless-server + web-MCDU (Phase 7) can reproduce the same contract over
HTTP/WebSocket. This is a factual inventory, not a redesign (except section 6).

Files read in full: `EDAPGui.py` (1517 lines), `EDAPCalibration.py` (394 lines),
`MousePt.py` (86 lines). Files read for call sites: `ED_AP.py` (constructor,
`update_config`/`load_config`, `get_status_lines`, `update_overlay`,
`process_config_settings`, `set_*`, `quit`, `engine_loop`, `ap_ckb(...)` call
sites), `services/*.py` (`ap_ckb` call sites), `EDKeys.py` (signatures only),
`EDAP_EDMesg_Server.py` (skimmed — separate protocol, see note at the end).

All line numbers below are `file:line`.

---

## 1. Toggles / checkboxes

All checkbox state lives in `self.checkboxvar[<label>]` (a `tk.IntVar`/`BooleanVar`),
created in `makeform()` (`EDAPGui.py:932`) for grouped fields, or ad hoc per
checkbox. Load-from-config happens once in `__init__` (`EDAPGui.py:229-243`);
write-back happens either immediately on click via `check_cb()`
(`EDAPGui.py:836-930`), or (for the numeric/entry fields) on **Save All
Settings** via `entry_update()` (`EDAPGui.py:787-834`) + `ed_ap.update_config()`.

| GUI label | config key | default | controls | read-on-load | write-back |
|---|---|---|---|---|---|
| FSD Route Assist (Main/MODE) | *(no config key — runtime only)* | n/a | starts/stops FSD Route Assist | not persisted | `check_cb` (`:842`) calls `start_fsd`/`stop_fsd`, driven by `ap_ckb('fsd_start'/'fsd_stop')` too |
| Supercruise Assist (Main/MODE) | *(no config key — runtime only)* | n/a | starts/stops SC Assist | not persisted | `check_cb` (`:851`), also driven by `ap_ckb('sc_start'/'sc_stop')` |
| Fast Travel Mode (Main/MODE) | `FastTravelMode` | `False` | skip honk/FSS scans, minimal waits | `:239` `.get('FastTravelMode', False)` | `check_cb` field `'Fast Travel'` (`:929-930`) writes `config['FastTravelMode']` immediately (no Save needed) |
| Enable Auto-tune RPY (Main/SHIP) | `AutoTuneRPYRates` | `False` | enables live RPY-rate auto-tune | `:1257` `bool(config['AutoTuneRPYRates'])` | `check_cb` (`:926-927`) writes immediately; also re-set in `entry_update` (`:819`) on Save |
| Enable Randomness (Settings/AUTOPILOT) | `EnableRandomness` | `False` | adds random sleeps to evade AP detection | `:229` | `check_cb` (`:860-863`) → `ed_ap.set_randomness(bool)` (writes `config['EnableRandomness']`, not persisted to disk until Save) |
| Automatic logout (Settings/AUTOPILOT) | `AutomaticLogout` | `False` | auto-logout when mission done | `:231` | `check_cb` (`:872-875`) → `ed_ap.set_automatic_logout(bool)` |
| Enable Hotkeys (Settings/BUTTONS) | `HotkeysEnable` | `False` | global hotkeys active | `:235` | `check_cb` field `'Enable Hotkeys'` (`:916-918`) sets `config['HotkeysEnable']` **and** calls `setup_hotkeys()` immediately |
| D-Scanner (Honk) Button (Settings/BUTTONS) — radio | `DSSButton` | `"Primary"` | Primary/Secondary fire button used for DSS/honk | `:241` | `check_cb` (`:901`) always re-writes `config['DSSButton']` from the radio var on every checkbox event |
| Enable Overlay (Settings/OVERLAY) | `OverlayTextEnable` | `False` | in-game overlay text on/off | `:232` | `check_cb` (`:877-880`) → `ed_ap.set_overlay(bool)` (also calls `overlay.overlay_clear()`/`overlay_paint()`) |
| Activate Elite for each key (Settings/KEYS) | `ActivateEliteEachKey` | `False` | refocus ED window before each keypress | `:230` | `check_cb` (`:865-870`) → `ed_ap.set_activate_elite_eachkey(bool)` + directly sets `ed_ap.keys.activate_window` |
| Enable Voice (Settings/VOICE) | `VoiceEnable` | `False` | TTS voice announcements | `:233` | `check_cb` (`:882-885`) → `ed_ap.set_voice(bool)` (calls `vce.set_on()`/`set_off()`) |
| ELW Scanner Enable (Settings/ELW SCANNER) | `ElwScannerEnable` | `False` | FSS scan for Earth/Water/Ammonia worlds during FSD travel | `:234` | `check_cb` (`:887-890`) → `ed_ap.set_fss_scan(bool)` |
| Language combobox (Settings/AUTOPILOT) | `Language` | `'en'` | UI/log locale (OCR strings need matching game language) | `:242` `language_var.set(...)` | `on_language_select` (`:535-540`) sets `config['Language']` + calls `locale.change_language()` directly (not via `check_cb`); labels need app restart |
| Debug mode radio: Debug/Info/Error (Debug/Test) | `LogDEBUG`, `LogINFO` (derived) | `LogDEBUG=True, LogINFO=True` (both true by default → most verbose) | log verbosity | `:306-311` derives radio value from the two bools | `check_cb` (`:903-908`) → `set_log_error/debug/info(True)`, which set both config bools and `logger.setLevel` |
| Debug Overlay (Debug/Test) | `DebugOverlay` | `False` | overlay debug data | `:236` | `check_cb` field `'Debug Overlay'` (`:910-914`) sets `ed_ap.debug_overlay` directly (config key also re-set in `entry_update` `:812`) |
| Debug OCR (Debug/Test) | `DebugOCR` | `False` | write OCR debug output to `ocr_output/` | `:237` | `check_cb` (`:920-921`) sets `ed_ap.debug_ocr` directly |
| Debug Images (Debug/Test) | `DebugImages` | `False` | write debug images to `debug_output/` | `:238` | `check_cb` (`:923-924`) sets `ed_ap.debug_images` directly |
| Enable CV View (Debug/Test) | `Enable_CV_View` | `0` | opens an OpenCV debug window positioned next to the GUI | `:1395` `int(config['Enable_CV_View'])` | `check_cb` (`:892-899`) → `ed_ap.set_cv_view(bool, x, y)` (x/y computed from the tk root window position — **tkinter-window-position-specific**, no meaning for a web client) |

### Numeric/text entry fields (Settings tab), written only via `entry_update()` on **Save All Settings**

All loaded in `__init__` (`EDAPGui.py:244-304`) via `.delete(0, END)` + `.insert(0, value)`; all
written back in `entry_update()` (`EDAPGui.py:787-834`) plus a final call to
`ed_ap.process_config_settings()` (`:832`) so subordinate classes (`keys`, debug flags,
align-limits) pick up the change immediately.

| GUI label | config key | default | notes |
|---|---|---|---|
| SunPitchUp+Time (SHIP) | *(not a config key — `ed_ap.sunpitchuptime`, per-ship)* | `0.0` | per-ship value, loaded via `update_ship_cfg` |
| Sun Bright Threshold (AUTOPILOT) | `SunBrightThreshold` | `125` | |
| Nav Align Tries (AUTOPILOT) | `NavAlignTries` | `3` | |
| Jump Tries (AUTOPILOT) | `JumpTries` | `3` | |
| Docking Retries (AUTOPILOT) | `DockingRetries` | `30` | |
| Wait For Autodock (AUTOPILOT) | `WaitForAutoDockTimer` | `240` | seconds |
| Refuel Threshold (FUEL) | `RefuelThreshold` | `65` | percent |
| Scoop Timeout (FUEL) | `FuelScoopTimeOut` | `35` | seconds |
| Fuel Threshold Abort (FUEL) | `FuelThreasholdAbortAP` | `10` | percent |
| X Offset (OVERLAY) | `OverlayTextXOffset` | `50` | pixels |
| Y Offset (OVERLAY) | `OverlayTextYOffset` | `400` | pixels |
| Font Size (OVERLAY) | `OverlayTextFontSize` | `14` | |
| Start FSD (BUTTONS, hotkey string) | `HotKey_StartFSD` | `"home"` | `keyboard` package key name |
| Start SC (BUTTONS, hotkey string) | `HotKey_StartSC` | `"ins"` | |
| Stop All (BUTTONS, hotkey string) | `HotKey_StopAllAssists` | `"end"` | |
| Modifier Key Delay (KEYS) | `Key_ModDelay` | `0.01` | seconds |
| Default Hold Time (KEYS) | `Key_DefHoldTime` | `0.2` | seconds |
| Repeat Key Delay (KEYS) | `Key_RepeatDelay` | `0.1` | seconds |
| FSS Detect Wait (Game tab) | `Wait_FSSDetect` | `2.5` | sec |
| Dock Approach Time (Game tab) | `Wait_DockApproach` | `12.0` | sec |
| Ship Stop Wait (Game tab) | `Wait_ShipStop` | `3.0` | sec |
| Occluded Reposition Time (Game tab) | `Wait_OccludedReposition` | `15.0` | sec |
| DSS Scan Time (Game tab) | `Wait_DSSScan` | `7.0` | sec |
| Past Sun Time (Game tab) | `Wait_PastSun` | `12.0` | sec |
| Heat Dissipate Time (Game tab) | `Wait_HeatDissipate` | `5.0` | sec |
| After Jump Wait (Game tab) | `Wait_AfterJump` | `1.0` | sec |
| Planet Departure SCO Time (Game tab) | `PlanetDepartureSCOTime` | `5.0` | sec |
| FC Departure Time (Game tab) | `FCDepartureTime` | `5.0` | sec |

Full config default table (~65 keys) is defined in `ED_AP.py:309-378`
(`load_config`); not every key has a GUI field (e.g. `TargetScale`,
`ScreenScale`, `DiscordWebhook*`, `EDSMCheckEnable`, `jump_align_*`,
`OCDepartureAngle`, `FCDepartureAngle`, `EnableEDMesg`/`EDMesgActionsPort`/
`EDMesgEventsPort`, `Debug_ShowCompassOverlay`, `Debug_ShowTargetOverlay`,
`DisengageUseMatch`, `OCRLanguage`, `OCRMobile`). These are config-file-only
knobs today with no UI surface — a web settings API should probably expose
all of `ed_ap.config` generically (get/set by key) rather than hand-porting
only the fields the tkinter GUI happens to expose.

---

## 2. Commands / buttons / actions

| GUI control | core call | args | effect |
|---|---|---|---|
| FSD Route Assist checkbox ON | `ed_ap.set_fsd_assist(True)` via `start_fsd()` (`EDAPGui.py:442-447`) | — | sets `fsd_assist_enabled=True`; disables the SC checkbox in the GUI; `engine_loop` picks it up next iteration |
| FSD Route Assist checkbox OFF | `ed_ap.set_fsd_assist(False)` via `stop_fsd()` (`:449-455`) | — | interrupts the AP thread (`ctype_async_raise`, see §3) |
| Supercruise Assist checkbox ON/OFF | `ed_ap.set_sc_assist(bool)` via `start_sc()`/`stop_sc()` (`:457-470`) | — | same pattern as FSD |
| Stop All (hotkey / mini-panel STOP button) | `stop_all_assists()` → `self.callback('stop_all_assists')` (`:438-440`), which is the *GUI's own* dispatcher, not a core call — it unchecks both mode checkboxes, which in turn calls `stop_fsd`/`stop_sc` | — | stops both assists |
| 0% Throttle (SHIP) | `ed_ap.set_throttle_0()` (`EDAPGui.py:691-692` → `ED_AP.py:1343`) | — | sends `Speed0`/`SCSpeed0` key, logs via `ap_ckb('log', ...)` |
| 50% Throttle | `ed_ap.set_throttle_50()` (`:694-695` → `ED_AP.py:1353`) | — | |
| 100% Throttle | `ed_ap.set_throttle_100()` (`:697-698` → `ED_AP.py:1363`) | — | |
| Align to Target (SHIP) | `ed_ap.nav_service.compass_align(ed_ap.scrReg)` (`EDAPGui.py:751-756`) | screen regions | one-shot alignment maneuver for RPY tuning; runs synchronously on the GUI's calling thread (main tk thread) |
| Throttle dropdown + Edit Roll/Pitch/Yaw Curve buttons | reads/writes `ed_ap.current_ship_cfg[selected_throttle]['RollRate'/'PitchRate'/'YawRate']` directly (`:700-749`) via `RPYLineEditor.line_editor()` (opens its own tk dialog) | — | in-memory edit only; persisted by **Save All Settings** → `ed_ap.update_ship_configs()` |
| Load All Settings | `ed_ap.load_ship_configs()` (`:765-766`) | — | reloads ship configs from disk |
| Save All Settings | `entry_update(None)` then `ed_ap.update_config()`, `ed_ap.update_ship_configs()`, `calibration.save_ocr_calibration_data()` (`:758-763`) | — | writes `configs/AP.json`, ship configs, and OCR calibration JSON to disk |
| Reload bindings from game (Game tab) | `ed_ap.keys.reload_bindings()` (`:1057-1064`) | — | re-reads the game's `.binds` file; then `populate_bindings_tree()` re-renders the table by reading `ed_ap.keys.keys_to_obtain`, `get_latest_keybinds()`, `get_binding_display_name()` |
| Auto-assign missing keys (Game tab) | `ed_ap.keys.assign_missing_keyboard_binds()` (`:1078`) | — | returns `{'assigned': {...}, 'skipped': [...], 'backup': path}`; writes into the game's `.binds` file directly (after a `messagebox.askyesno` confirm) |
| Refresh game settings (Game tab) | constructs fresh `EDGraphicsSettings()` and `EDPlayerSettings(callback, locale)` (`:1111-1159`), reads `ed_ap.jn.get_game_language()` | — | re-reads on-disk game config files (graphics.xml-equivalent, player prefs, journal Fileheader), no core AP method involved beyond attaching results to `ed_ap.gfx_settings`/`ed_ap.player_settings` |
| Calibrate Target (Calibration tab) | `ed_ap.calibrate_target()` via `calibrate_callback()` (`EDAPGui.py:422-423`, `EDAPCalibration.py:377-378`) | — | scale-sweep template match against the live game screen; draws match rectangles onto the **game's overlay** (not a tkinter widget) via `ED_AP.py:768+` |
| Region/Subregion select + Left/Top/Right/Bottom spinboxes (Calibration tab) | mutates `Calibration.ocr_calibration_data[key]['rect']` in memory (`EDAPCalibration.py:247-371`), drives `ed_ap.overlay.overlay_quad_pct(...)` to preview the rect on the **game window** | — | no ED_AP method call; direct dict mutation, persisted only by Save All Calibrations |
| Save All Calibrations | `Calibration.save_ocr_calibration_data()` (`EDAPCalibration.py:179-211`) | — | writes `configs/ocr_calibration.json`; also called automatically by "Save All Settings" |
| Reset All to Default (Calibration) | reloads `load_default_calib_data()`, deletes `configs/ocr_calibration.json` (`:213-245`) | — | |
| Restart (Debug/Test) | `restart_program()` (`EDAPGui.py:1462-1477`): `stop_fsd()`, `stop_sc()`, `ed_ap.quit()`, then `os.execv` | — | full process restart |
| Exit (Debug/Test) | `close_window()` (`:429-435`): `stop_fsd()`, `stop_sc()`, `ed_ap.quit()`, `root.destroy()` | — | |
| Check for Updates / View Changelog / Join Discord / About / Online HELP | `webbrowser.open_new(...)` or a `git fetch`+`rev-parse` subprocess check (`:475-529`) | — | no core involvement |
| Mini Panel toggle + its FSD/SC/STOP/FAST buttons/FSS test | reuses the same `checkboxvar`s and `check_cb`/`stop_all_assists` (`:582-674`); FSS test spawns `threading.Thread(target=ed_ap.elw_advisor.test_fss_scan)` (`:676-678`) | — | duplicate control surface over the same state, refreshed every 1s via `ed_ap.get_status_lines()` (`:658-674`) |

---

## 3. Assist lifecycle

- **The engine thread is not started/stopped by the GUI.** `ED_AP.__init__` (called once,
  when `APGui.__init__` constructs `self.ed_ap = EDAutopilot(cb=self.callback)`,
  `EDAPGui.py:167`) starts a single long-lived `kthread.KThread` running
  `engine_loop` (`ED_AP.py:259-261`) for the whole app lifetime. `engine_loop`
  (`ED_AP.py:1203-1341`) polls once per second (`sleep(1)` at the bottom) and,
  each iteration, checks `self.fsd_assist_enabled` / `self.sc_assist_enabled` flags.
- **Mode fields**: `modes_check_fields = ('FSD Route Assist', 'Supercruise Assist')`
  (`EDAPGui.py:1163`), rendered as plain checkboxes in the MODE block
  (`makeform(blk_modes, FORM_TYPE_CHECKBOX, modes_check_fields)`, `:1224`).
  They have **no config key** — they are pure runtime state, not persisted.
- **Turning a mode on**: `check_cb('FSD Route Assist')` (`EDAPGui.py:842-849`)
  checks `checkboxvar['FSD Route Assist'].get() == 1 and not FSD_A_running`,
  disables the other mode's checkbox widget (`lab_ck['Supercruise Assist'].config(state='disabled')`,
  mutual exclusion is GUI-side only — the core does not enforce it), then calls
  `start_fsd()` → `ed_ap.set_fsd_assist(True)` (`ED_AP.py:1127-1131`), which just
  sets `self.fsd_assist_enabled = True`. The next `engine_loop` tick
  (up to ~1s later) sees the flag and calls `jump_service.fsd_assist(scrReg)`
  in a `try/except EDAP_Interrupt` block (`ED_AP.py:1229-1252`).
- **Turning a mode off**: `set_fsd_assist(False)`/`set_sc_assist(False)`
  (`ED_AP.py:1127-1137`) — if the assist is currently running, it raises an
  **asynchronous exception (`EDAP_Interrupt`) into the running AP thread**
  via `ctype_async_raise` (a ctypes trick to unwind whatever blocking OCR/sleep
  call the assist logic is stuck in). This is how "Stop" is able to interrupt
  mid-maneuver rather than waiting for the next polling point.
- **When an assist finishes naturally** (destination reached, error, or
  interrupted), `engine_loop` sets the flag back to `False` itself and fires
  `ap_ckb('fsd_stop')` or `ap_ckb('sc_stop')` (`ED_AP.py:1251`, `:1283`) so the
  GUI checkbox un-ticks itself (see §5). A `Partial` FSD-assist return additionally
  fires `ap_ckb('sc_start')` to auto-chain into Supercruise Assist for the final
  system leg (`ED_AP.py:1258-1259`).
- **Threading model summary**: exactly one core worker thread (`ap_thread`,
  `engine_loop`) for the whole app; the tkinter main thread only ever *sets
  flags* and *reads state* (`ed_ap.<flag>`, `ed_ap.config[...]`, `get_status_lines()`),
  it never runs AP logic itself. `keyboard` hotkeys (`setup_hotkeys`,
  `EDAPGui.py:326-345`) run their own background listener thread supplied by the
  `keyboard` package and call back into `APGui.callback` (not directly into
  `ed_ap`) for `fsd_start`/`sc_start`/`stop_all_assists`. The mini-panel's
  `_mini_panel_tick` (`:658-674`) is a `root.after(1000, ...)` tk-scheduled
  poll — see §4.

---

## 4. State displayed to the user

### LOG panel
`self.msgList` (`tk.Listbox`, `EDAPGui.py:1308-1311`), appended to only via
`log_msg()` (`:551-570`), which is called by the `ap_ckb` handler on `'log'`
and `'log+vce'` (see §5). Before `gui_loaded` is set, messages queue in
`self.log_buffer` (a `queue.Queue`) and get flushed on the first post-load
`log_msg` call (`:556-566`).

### Status line / AP status
`self.status` ttk Label (`EDAPGui.py:1455`), updated only via
`update_statusline(txt)` (`:578-580`), which prefixes it with a locale string
and *also* appends the same text to the log (`log_msg`). Driven by the
`'statusline'` `ap_ckb` tag, itself only ever sent from `ED_AP.update_ap_status()`
(`ED_AP.py:650-653`), which is the single choke point core code uses to change
`self.ap_state` (e.g. `docking_service` sets `"SC to Target"` via
`engine_loop:1270`).

### Jump count field
`self.jumpcount` ttk Label (`EDAPGui.py:1456`), updated only via
`update_jumpcount(txt)` (`:575-576`), driven by the `'jumpcount'` `ap_ckb` tag
sent from `services/jump_service.py:240` — a pre-formatted string
(`"Dist: {:,.1f}ly ..."`), i.e. the core sends **display-ready text**, not
structured data.

### Overlay (drawn on the ED game window, not in the tkinter window)
`ED_AP.update_overlay()` (`ED_AP.py:638-648`) is called after every state
change of interest (assist start/stop, each `engine_loop` tick, jump events,
etc.) and only actually draws if `config['OverlayTextEnable']`. It calls
`get_status_lines()` (`ED_AP.py:576-636`) to build a `list[(text, highlight)]`
each time — this is a **pure derived view**, not cached state — sourced from:
  - `fsd_assist_enabled` / `sc_assist_enabled` → "AP MODE"
  - `self.ap_state` → "AP STATUS"
  - `jn.ship_state()['status']`, `['fuel_percent']` → "SHIP"/"FUEL"
  - `jn.ship_state()['location']`, `['star_class']` (+ scoopable-class check) → "CURRENT SYSTEM"
  - `jn.ship_state()['target']`, `['jumps_remains']` → "TARGET"
  - `self.jump_cnt`, `self.total_jumps`, `self.total_dist_jumped` → "JUMPS"
  - `self._str_eta` → "ETA (to System)"
  - `self.fss_detected` (only if `config['ElwScannerEnable']`) → "ELW SCANNER"
  - `self.edsm_info` / `self.edsm_undiscovered` (highlight flag) → EDSM discovery line
  - `jn.ship_state()['fss_honk_done'/'scanned_bodies'/'fss_body_count'/'fss_all_found']`,
    `self._fss_valuables[-4:]` → "FSS SCAN" progress + up to 4 valuable-body lines (highlighted)
  Font/position/size come from `config['OverlayTextFont'/'OverlayTextXOffset'/'OverlayTextYOffset'/'OverlayTextFontSize']`,
  applied once at `Overlay` construction (`ED_AP.py:238-240`) — changing X/Y/Font
  Size in the GUI does **not** live-update the overlay (`set_overlay`,
  `ED_AP.py:1159-1165`, has a `# TODO: apply the change without restarting the program`).

### Mini panel (`EDAPGui.py:582-674`)
An always-on-top borderless duplicate of the FSD/SC/Fast/FSS/Stop controls
plus a text block. Its info block is **polled**, not pushed: `_mini_panel_tick`
calls `ed_ap.get_status_lines()` directly every 1000ms via `root.after` and
re-renders two labels (normal lines vs. highlighted lines). This is the one
place in the GUI that treats `get_status_lines()` as a pull-based state API
rather than the push-based overlay/log/statusline mechanism.

### Game tab settings display
`refresh_game_settings()` (`EDAPGui.py:1111-1159`) is **pull-only**, invoked on
tab creation and by its own "Refresh" button — resolution/screen mode/monitor/FOV
from a freshly constructed `EDGraphicsSettings()`, brightness/nav-icon-visibility
from a freshly constructed `EDPlayerSettings(...)`, and game language from
`ed_ap.jn.get_game_language()`. Nothing here is pushed via `ap_ckb`.

### Bindings tree (Game tab)
`populate_bindings_tree()` (`EDAPGui.py:1036-1055`) is also pull-only, re-read
on tab load and after Reload/Auto-assign actions; iterates
`ed_ap.keys.keys_to_obtain` and calls `get_latest_keybinds()` /
`get_binding_display_name()` per binding.

### Summary: push vs poll
- **Push (via `ap_ckb`)**: log lines, status line, jump count, fsd/sc
  start/stop (which reopen/close the checkbox), ship-config-changed signal.
- **Poll (GUI-initiated, no `ap_ckb` involved)**: mini-panel info block (1s
  timer calling `get_status_lines()`), Game tab settings/bindings (manual
  refresh button or tab open), throttle/ship-curve editor (reads
  `current_ship_cfg` directly on demand).
- The main overlay is technically "push" in the sense that core code decides
  when to call `update_overlay()`, but the content is *recomputed from scratch*
  from `get_status_lines()` every time — there is no incremental diffing.

---

## 5. The `ap_ckb` bridge

Signature: `ap_ckb(msg: str, body=None)` — set as `self.ap_ckb = cb` in
`ED_AP.__init__` (`ED_AP.py:202`), where `cb` is `APGui.callback`
(`EDAPGui.py:167`, `def callback(self, msg, body=None)` at `:348`). It is also
handed down to every constructed subsystem (`Screen`, `EDPlayerSettings`,
`EDJournal`, `EDKeys`, `EDShipControl`, `EDNavigationPanel`, `EDMesgServer`,
and, via `self.ap`, to every `services/*.py` class and `EDAPCalibration.Calibration`)
so **any** core/service code can push a message straight to the GUI without
routing through `ED_AP`.

Full set of tags observed (grepped across `ED_AP.py`, `services/*.py`,
`EDAPCalibration.py`, and the GUI's own re-dispatch in `EDAPGui.py:348-407`):

| Tag | Payload (`body`) | Emitted from | GUI handling |
|---|---|---|---|
| `'log'` | plain string | very widely — `ED_AP.py`, all of `services/*.py`, `EDAPCalibration.py` | `log_msg(body)` (`EDAPGui.py:349-350`) — timestamps and appends to the Listbox |
| `'log+vce'` | plain string | widely, for messages that should also be spoken — `ED_AP.py`, `services/*.py` | `log_msg(body)` **and** `ed_ap.vce.say(body)` (`:351-353`) |
| `'statusline'` | plain string | only `ED_AP.update_ap_status()` (`ED_AP.py:653`) | `update_statusline(body)` (`:354-355`) |
| `'fsd_stop'` | none | `engine_loop` when FSD assist finishes/errors (`ED_AP.py:1251`) | unchecks `'FSD Route Assist'` and calls `check_cb` (`:356-359`) — re-enables the SC checkbox as a side effect |
| `'fsd_start'` | none | not emitted by core; only used as the **hotkey** callback arg (`setup_hotkeys`, `EDAPGui.py:338`) — GUI calls its own `callback('fsd_start', None)` directly | checks `'FSD Route Assist'` + `check_cb` (`:360-362`) |
| `'sc_stop'` | none | `engine_loop` when SC assist finishes/errors (`ED_AP.py:1283`) | unchecks `'Supercruise Assist'` + `check_cb` (`:363-366`) |
| `'sc_start'` | none | `engine_loop` auto-chain after a `Partial` FSD-assist return (`ED_AP.py:1259`); also the SC hotkey (`EDAPGui.py:339`) | checks `'Supercruise Assist'` + `check_cb` (`:367-369`) |
| `'stop_all_assists'` | none | only the GUI's own `stop_all_assists()` (`EDAPGui.py:440`) — not emitted by core | unchecks both mode checkboxes (`:371-378`) |
| `'jumpcount'` | pre-formatted string | `services/jump_service.py:240` | `update_jumpcount(body)` (`:380-381`) |
| `'update_ship_cfg'` | none | `engine_loop` on ship-type change (`ED_AP.py:1326`) | `root.after(0, self.update_ship_cfg)` (`:382-383`) — repopulates SunPitchUp+Time entry and the throttle-curve combobox from `ed_ap.current_ship_cfg` |
| `'up'` / `'down'` / `'left'` / `'right'` | none | **not emitted anywhere** currently — dead/TODO code path (commented-out hotkey registration at `EDAPGui.py:341-345`); handlers exist (`:384-407`) but are unreachable | would nudge power distribution pips via `ed_ap.keys.send(...)` if ever wired up |

Notes:
- There is no tag carrying structured numeric telemetry (fuel %, position,
  ETA, jump counts as numbers) — everything pushed through `ap_ckb` is either
  a free-text log line or a control-flow signal (start/stop/ship-changed).
  The one place that gets structured data is `get_status_lines()`, and it is
  **pull-only** (§4).
- `'fsd_start'`/`'stop_all_assists'` are GUI-internal re-dispatch tags, not
  really part of the core→GUI contract — worth NOT reproducing as server→client
  events; they belong to a UI-side command layer instead.

---

## 6. Summary for the web API

### (a) State pushed core → UI (candidate WebSocket "event" stream)
- `log` / `log+vce` lines — a single `log` event type is enough; voice-TTS
  can be a client-side (or server-side, headless-friendly) concern keyed off
  the same event rather than a separate tag.
- `statusline` (AP status text) — trivial 1:1 mapping to an event.
- `jumpcount` — should be **restructured** as a small numeric/structured
  payload (`total_dist_jumped`, `jump_cnt`, `total_jumps`) instead of a
  pre-formatted string, so the web client can lay it out however it wants
  (the current string-only tag is a tkinter-era shortcut).
- `fsd_stop`/`sc_stop`/`sc_start` (engine-driven only, not the GUI-internal
  hotkey ones) — map to an `assist_state` event `{mode: 'fsd'|'sc', running: bool}`.
- `update_ship_cfg` — map to a `ship_changed` event whose payload is (or
  references) `ed_ap.current_ship_cfg` / `ed_ap.sunpitchuptime`, instead of
  the current "GUI, please re-pull from `ed_ap`" signal.
- The overlay's `get_status_lines()` content — this is the richest state and
  currently has **no push equivalent** (only polled by the mini panel every
  1s and drawn to the local game window by `update_overlay()`). For the web
  MCDU this should become the main telemetry event, e.g. `status_snapshot`
  pushed every ~1s (or on change) from inside `engine_loop`, carrying the
  same fields listed in §4 as structured JSON rather than pre-joined strings.

### (b) Commands UI → core (WebSocket or HTTP)
- `assist.start` / `assist.stop` with `{mode: 'fsd'|'sc'}` → `set_fsd_assist`/`set_sc_assist`.
- `assist.stop_all` → both stops.
- `throttle.set` with `{level: 0|50|100}` → `set_throttle_0/50/100`.
- `ship.align_to_target` → `nav_service.compass_align(scrReg)` — fine as a
  fire-and-forget command since it's already synchronous and quick; consider
  running it off the request thread so a slow HTTP client doesn't block AP polling.
- `ship.throttle_curve.get/set` (roll/pitch/yaw) → replace the tkinter
  `line_editor` dialog with a data endpoint that GETs/PUTs the curve point
  list for `current_ship_cfg[throttle]['RollRate'/'PitchRate'/'YawRate']`.
- `keys.reload_bindings`, `keys.assign_missing`, `keys.get_bindings` →
  straightforward RPCs wrapping `EDKeys` methods already returning plain dicts.
- `game_settings.refresh` → wraps constructing `EDGraphicsSettings()`/`EDPlayerSettings()`.
- `settings.load` / `settings.save` → `load_ship_configs()` / (`update_config`
  + `update_ship_configs` + `save_ocr_calibration_data`).
- `app.restart` / `app.exit` → needs rethinking for a headless server (there
  is no "close the GUI window" concept; likely becomes a server-restart
  admin action, decoupled from any one web client's session).
- `calibration.get_target_estimate` → wraps `calibrate_target()`; since it
  draws directly to the game overlay (not to the requesting client), see (c) below.

### (c) Config get/set
Rather than hand-porting each of the ~30 GUI-exposed keys individually, expose
`ed_ap.config` generically: `GET /config` returns the whole dict (or a
filtered view), `PATCH /config` accepts a partial dict of key/value pairs and
internally does what `entry_update()` + `check_cb()` currently do — i.e. set
`ed_ap.config[key]`, then call `ed_ap.process_config_settings()` afterwards
(§1) so subordinate objects immediately pick up delay/threshold changes
without needing an app restart, and a final `update_config()` to persist to
`configs/AP.json`. This also naturally covers config-only keys the tkinter
GUI never exposed a widget for (`EDSMCheckEnable`, `jump_align_*`, `OCRLanguage`,
etc.) for free.

### Tkinter-specific things with no clean web equivalent (need rethinking)
1. **Calibration region preview** (`EDAPCalibration.py:247-371`): live-previews
   the selected OCR rect by drawing a quad **onto the actual Elite Dangerous
   game window overlay** (`ed_ap.overlay.overlay_quad_pct(...)`), not onto any
   tkinter widget. This actually degrades gracefully for a *local* headless
   server (the overlay still draws on the monitor the game runs on), but it
   gives a tablet/remote client **no visual feedback at all** unless the web
   server also streams a screenshot with the rect burned in, or the tablet
   is expected to be used while looking at the same monitor.
2. **`calibrate_target()`** (`ED_AP.py:768+`): a synchronous scale-sweep
   template-match against a live screen grab, also drawing match rectangles
   onto the game overlay. Same remote-feedback gap as above; also currently
   blocks whatever thread calls it (main tk thread today) — needs to run off
   the request-handling thread in a server.
3. **`Enable CV View`** (`EDAPGui.py:892-899`): opens a native OpenCV debug
   window positioned relative to the *tkinter root window's screen
   coordinates* (`x = root.winfo_x() + root.winfo_width() + 4`). This concept
   (a debug image viewer next to the control window) doesn't map to a browser
   client at all; would need to become a debug image stream/snapshot endpoint
   if kept.
4. **Roll/Pitch/Yaw curve editor** (`edit_roll_curve`/`edit_pit_curve`/`edit_yaw_curve`,
   `EDAPGui.py:700-749`): opens `RPYLineEditor.line_editor()`, a separate
   tkinter modal with its own interactive plot for editing a curve's points,
   plus a `messagebox.askyesno` confirm. Needs a proper data endpoint (get/set
   curve points) and a web-side chart/editor widget to replace the interactive
   plot.
5. **Mini Panel** (`EDAPGui.py:582-674`): an always-on-top, draggable,
   semi-transparent, borderless `Toplevel` overlay meant to sit on top of the
   game window while playing. This is inherently a desktop-window-manager
   feature; a tablet web client's "mini view" would need to be a genuinely
   separate lightweight page/layout rather than a port of this widget.
6. **`self.mouse = MousePoint()`** (`EDAPGui.py:206`): constructed but never
   used anywhere else in `EDAPGui.py` — dead code, not part of the real
   contract, safe to drop rather than "port."
7. **Restart / Exit** (`restart_program`, `close_window`): tied to the GUI
   process's own lifecycle (`os.execv`, `root.destroy()`). A headless server
   has no per-client "close the window"; these become server-lifecycle admin
   actions (if kept at all), independent of any browser tab closing.
8. **Language combobox restart note** (`EDAPGui.py:539-540`): changing
   `Language` takes effect for new log lines immediately but explicitly tells
   the user labels need an app restart — a web UI could instead re-fetch
   fresh label strings without a full process restart, so this is a
   "shouldn't need to carry the limitation forward" item, not a "can't be done"
   item.

### Adjacent existing protocol (not the GUI, but overlapping intent)
`ED_AP.py:190` constructs `self.mesg_server = EDMesgServer(self, cb)`
(`EDAP_EDMesg_Server.py`), a separate always-on TCP/EDMesg action/event
protocol used for third-party integration (e.g. EDCoPilot): actions like
`StartWaypointAssistAction`, `StopAllAssistsAction`, `GetEDAPLocationAction`,
events like `EDAPLocationEvent`, `LaunchCompleteEvent`. It is independent of
`EDAPGui.py` and already headless-friendly. Per existing project direction
(keep EDMesg, don't polish EDAPGui — see `web-ui-direction` memory), this
should stay a separate channel; the new web server's WebSocket/HTTP contract
does not need to subsume it, though the two overlap conceptually (both are
"external control of the core") and could eventually share the same
underlying command dispatch if convenient.

---

## 7. Route planner commands (Phase 8.1, iteration 2)

New WebSocket commands backing the SEC F-PLN (secondary route) and DIR
(direct-to) MCDU pages, added on top of the existing `_dispatch_command`
elif-chain in `webserver/server.py`. Design reference:
`design/route-planner-backend.md` (§4 `RoutePlanner.py`, §5 this table).
The planner instance is a lazy module-level singleton
(`_get_route_planner(ed_ap)`, same pattern as `_get_calib_store()`), so
`import webserver.server` never touches the network.

**Scope note:** everything here runs on the laptop against the public Spansh
+ EDSM APIs, without the game. `sec.activate` (actually entering the plotted
route into the game via the galaxy map) is gated on the in-game part of
Phase 8.1 and is a stub for now — see §1 of the design doc.

| Command | Params | Response / broadcast |
|---|---|---|
| `sec.plot` | `profile: "fuel_safe"\|"fast"\|"ultra"`, `dest?: str`, `source?: str` | ack `{"type":"sec_plot_started"}` on the requesting socket, then (after the blocking Spansh round-trip runs in an executor) broadcast `{"type":"sec_route","data":<sec_route data>}` to all clients. Ordinary plotting failures (no destination, no loadout, unknown profile, HTTP/timeout errors) are captured inside `data.error`, not raised — the broadcast still fires. Only the busy-guard (`plot_secondary` called while a plot is already running) surfaces as `{"type":"error","text":"PLOT IN PROGRESS"}` instead of a broadcast. `source` (SEC FROM [E]) overrides the journal location as the plot origin; it is EDSM-validated, an unknown name lands in `data.error` as `unknown FROM system: ...`. |
| `sec.get` | — | direct reply (not broadcast) `{"type":"sec_route","data":<sec_route data>}` — same payload shape as the `sec.plot` broadcast, for a client that just (re)connected. |
| `sec.activate` | — | adopts the plotted SEC route as the ACTIVE (executed) one: the RouteExecutor walks it against the journal location (fed by the 1 Hz status tick) and hands each segment endpoint (next `must_refuel` stop, then the destination) to the GalaxyMapDriver — a stub that only records the target until the in-game galaxy-map driving (game part of 8.1) replaces it. Success broadcasts `{"type":"exec_state","data":<exec_state>}`; failures (no plotted route, ULTRA profile) reply `{"type":"error","text":"..."}`. |
| `exec.get` | — | direct reply `{"type":"exec_state","data":<exec_state>}` — current executor state for a (re)connecting client. |
| `exec.stop` | — | deactivates the executor; broadcasts `exec_state` (status `INACTIVE`). |
| `dir.nearest` | `scoopable: bool` | ack `{"type":"dir_started"}`, then broadcast `{"type":"dir_state","data":<planner snapshot>}` once the EDSM sphere-cascade lookup (executor) finishes. A failure (e.g. unknown current location) broadcasts `{"type":"error","text":"..."}` instead. |
| `dir.set` | `system: str` | no ack — runs `direct_to(system)` in an executor (blocking EDSM call), then broadcasts `{"type":"dir_state","data":<planner snapshot>}` on success. An unresolvable system name broadcasts `{"type":"error","text":"INVALID"}`; a hard failure (e.g. unknown current location) broadcasts `{"type":"error","text":"..."}`. |

### `sec_route` payload (`data`)

The planner `snapshot()` (see below) plus one extra key:

```json
{"secondary": <Route|null>, "dir": <DirCandidate|null>, "busy": bool, "error": str|null,
 "compare": {"primary": {"jumps": int|null, "dist_ly": float|null, "scoops": int|null}}}
```

`compare.primary` is built server-side from the active F-PLN
(`map_nav_route(ed_ap.nav_route.get_nav_route_data())`, §1 above): `jumps` =
`len(systems) - 1`, `dist_ly` = Σ per-hop `dist_ly`, `scoops` = count of
scoopable-class hops; all three are `null` when there is no active primary
route. Secondary-side comparison numbers (jumps/dist_ly/scoops/risk) are not
duplicated into `compare` — the client reads them straight from
`data.secondary`.

### `dir_state` payload (`data`)

The planner `snapshot()` as-is (no `compare` key — DIR has nothing to compare
against):

```json
{"secondary": <Route|null>, "dir": <DirCandidate|null>, "busy": bool, "error": str|null}
```

### `Route` dict (`secondary`, when present)

```json
{"profile": "FUEL-SAFE"|"FAST"|"ULTRA", "source": "...", "destination": "...",
 "jumps": int, "dist_ly": float, "scoops": int|null, "risk": "LOW"|"HIGH",
 "plotted_at": "<iso>",
 "systems": [{"system": "...", "dist_ly": float|null, "scoopable": bool|null,
              "neutron": bool, "must_refuel": bool,
              "fuel_used": float|null, "fuel_tank": float|null}, ...]}
```

`systems[0]` is the starting system (`dist_ly`/`fuel_used` null). FUEL-SAFE
and FAST both come from the Spansh exact plotter with the full ship config
and per-jump fuel model (`fuel_used` = tonnes burned by the jump into this
system, `fuel_tank` = level after arriving and refuelling when `must_refuel`
is set; `scoops` = count of `must_refuel` hops). FAST adds
`use_supercharge=1` — neutron/WD boosted legs (incl. the SCO MkII x6 drive),
`risk` "HIGH". ULTRA is the range-only neutron-plotter waypoint list for
very long hauls (fuel not modelled: `scoops` null, `fuel_*` null); it is not
exposed in the MCDU. See `design/route-planner-backend.md` §4 for the full
per-profile breakdown.

### `DirCandidate` dict (`dir`, when present)

```json
{"system": "...", "star_class": "...", "dist_ly": float|null, "scoopable": bool}
```

### `exec_state` payload (`data`)

`RouteExecutor.snapshot()`. When nothing was ever activated (or after
`exec.stop`) it is just `{"active": false, "status": "INACTIVE"}`; otherwise:

```json
{"active": bool, "status": "ACTIVE"|"OFF ROUTE"|"COMPLETE",
 "profile": "FUEL-SAFE"|"FAST", "destination": "...",
 "idx": int, "jumps_total": int, "jumps_done": int,
 "next_system": str|null, "segment_target": str|null, "map_target": str|null,
 "remaining_jumps": int, "remaining_dist_ly": float, "next_refuel_in": int|null,
 "fuel_plan": float|null, "fuel_actual": float|null, "off_route_at": str|null}
```

`idx` is the position (index into the activated route's `systems[]`);
`segment_target` is the endpoint of the current segment (next `must_refuel`
stop, else the destination) and `map_target` is what the GalaxyMapDriver was
last asked to plot. `fuel_plan` is the route's expected `fuel_tank` at the
current system, `fuel_actual` the journal's fuel level — the pair is the
live plan-vs-reality fuel cross-check. `active` is true for
`ACTIVE`/`OFF ROUTE` only. The server broadcasts `exec_state` on every
change detected by the 1 Hz status tick (jump, off-route, rejoin,
completion) plus on `sec.activate`/`exec.stop`; `tools/mock_flight.py`
exercises the full cycle on the mock journal without the game.
