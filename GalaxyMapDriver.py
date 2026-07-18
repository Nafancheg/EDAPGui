"""
Game-side galaxy-map driver for the route executor (game part of Phase 8.1).

Implements the GalaxyMapDriver interface from RouteExecutor.py with real key
input: open the galaxy map, type the system name into the search field, and
long-press select to plot the (always single-jump) leg — which target-locks
the system for the next manual/assisted jump. Per the owner's decision
(mcdu-button-map Замечание 21) the in-game plotter is only ever given the
NEXT system of OUR plan, never the final destination, so its inability to
plan supercharged legs does not matter: every leg is ShipFSD-validated to be
within the current jump range.

The key sequence is a port of the proven pre-fork EDGalaxyMap.py
(set_gal_map_destination_text_odyssey, removed in Phase 1 — recovered from
git f2ae525~1). Notable beats that are NOT obvious: after picking a search
match the focus must be returned to the MAP with CamZoomIn before the
long-press plot, and the search box sometimes needs a UI_Down/UI_Up nudge
after Enter to behave.

Key work is slow (map load + typing + confirmation ≈ 10-20 s) and
set_target() is called from the webserver's asyncio thread
(RouteExecutor.tick), so the actual driving runs on a single background
worker thread; set_target() just queues the request (latest wins) and
returns. The worker also waits out the hyperspace exit (Status.json flags)
plus ExecMapTargetDelay seconds so the map is not slammed open the instant
the jump lands. Success/failure is reported through ap_ckb('log') and
confirmed against the journal (FSDTarget / NavRoute).
"""

import os
import threading
from time import sleep

from EDAP_data import (FlagsFsdCharging, FlagsFsdJump, GuiFocusGalaxyMap,
                       GuiFocusNoFocus)
from EDlogger import logger
from MousePt import MousePoint
from Screen import set_focus_elite_window
from directinput import SCANCODE, PressKey, ReleaseKey


# characters the galaxy-map search accepts from a bare (unshifted) keyboard;
# anything else (e.g. the '*' in "Sagittarius A*") is dropped — the search
# matches on prefix, so a trimmed name still finds the right system
_CHAR_KEYS = {
    ' ': 'Key_Space', '-': 'Key_Minus', "'": 'Key_Apostrophe', '.': 'Key_Period',
}
for _c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
    _CHAR_KEYS[_c] = 'Key_' + _c
for _d in '0123456789':
    _CHAR_KEYS[_d] = 'Key_' + _d

# UI bindings the drive sequence needs (checked before touching the game)
_REQUIRED_BINDS = ('GalaxyMapOpen', 'UI_Up', 'UI_Down', 'UI_Left', 'UI_Right',
                   'UI_Select', 'UI_Back', 'CamZoomIn')

_SEARCH_ATTEMPTS = 3          # search matches to try before giving up
_CONFIRM_TIMEOUT = 8.0        # s to wait for the journal to confirm one pick


class GameGalaxyMapDriver:
    """Real target-lock driver. Same public surface as the RouteExecutor stub
    (set_target/last_target/requests) so either can be plugged in."""

    def __init__(self, ed_ap):
        self.ap = ed_ap
        self.last_target: str | None = None
        self.requests: list[str] = []
        self._pending: str | None = None
        self._cv = threading.Condition()
        self._worker: threading.Thread | None = None
        self._mouse = MousePoint()

    # --- executor-facing interface ------------------------------------------ #

    def set_target(self, system: str) -> bool:
        """Queue `system` for target lock and return immediately (the caller
        runs on the asyncio thread). Latest request wins if several arrive
        before the worker gets to them (e.g. two quick jumps)."""
        self.last_target = system
        self.requests.append(system)
        if not self.ap.config.get('ExecMapTargetLock', True):
            logger.info("map driver: ExecMapTargetLock off — recording %r only", system)
            return True
        with self._cv:
            self._pending = system
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(
                    target=self._worker_loop, name="galmap-driver", daemon=True)
                self._worker.start()
            self._cv.notify()
        return True

    # --- worker -------------------------------------------------------------- #

    def _worker_loop(self):
        while True:
            with self._cv:
                if self._pending is None:
                    if not self._cv.wait(timeout=3600):
                        continue
                system, self._pending = self._pending, None
            if not system:
                continue
            try:
                ok = self._drive(system)
                self.ap.ap_ckb('log', f"MAP TARGET {'OK' if ok else 'FAILED'}: {system}")
            except Exception as e:  # noqa: BLE001 — never kill the worker
                logger.exception("map driver: set_target(%r) failed", system)
                try:
                    self.ap.ap_ckb('log', f"MAP TARGET ERROR: {system} ({e})")
                except Exception:
                    pass

    # --- the drive sequence (port of EDGalaxyMap odyssey flow) ---------------- #

    def _drive(self, system: str) -> bool:
        keys = self.ap.keys
        missing = [b for b in _REQUIRED_BINDS if keys.keys.get(b) is None]
        if missing:
            logger.warning("map driver: missing binds %s — cannot target-lock", missing)
            return False
        # no Status.json = game not running; get_gui_focus() would retry the
        # missing file forever and wedge this worker
        if not os.path.isfile(self.ap.status.file_path):
            logger.warning("map driver: no Status.json — game not running?")
            return False

        # let the arrival settle: wait out witchspace/FSD charge, then give
        # the pilot a configurable breath before grabbing the keyboard
        if not self._wait_settled(30.0):
            logger.warning("map driver: FSD still busy after 30s — skipping")
            return False
        sleep(self._settle_delay())

        # someone (the game, the pilot, a previous pass) may already have it
        if self._target_confirmed(system):
            logger.info("map driver: %r already targeted", system)
            return True

        set_focus_elite_window()
        sleep(0.25)

        if not self._goto_map(keys):
            logger.warning("map driver: galaxy map did not open")
            return False

        ok = False
        try:
            # _goto_map left the highlight on the search bar
            keys.send('UI_Select')          # enter the search box
            sleep(0.3)
            self._type_text(system)
            sleep(0.3)
            self._tap('Key_Enter')          # run the search
            sleep(2.0)                      # map centres the hit, info panel opens

            # primary path (owner request 2026-07-17): the system-info panel
            # has a STATIC «Задать цель» button — a mouse click on it sets a
            # clean target lock (метка), no route plotted, nothing overwritten
            if self._click_set_target():
                ok = self._wait_confirmed(system, _CONFIRM_TIMEOUT)

            if not ok:
                # fallback: the proven plot-route dance (a 1-jump route to an
                # in-range system is functionally the same метка)
                keys.send('UI_Down')        # ENTER does not always reselect the
                sleep(0.1)                  # text box (old-code quirk) — nudge
                keys.send('UI_Up')
                sleep(0.1)
                keys.send('UI_Right')       # to the >| next-match button
                sleep(0.1)

                for attempt in range(_SEARCH_ATTEMPTS):
                    keys.send('UI_Select')  # pick first (or next) search match
                    sleep(0.5)
                    keys.send('CamZoomIn')  # put the focus back on the MAP
                    sleep(0.5)
                    # long-press select on the map = plot route to the selection
                    keys.send('UI_Select', hold=0.85)
                    if self._wait_confirmed(system, _CONFIRM_TIMEOUT):
                        ok = True
                        break
                    logger.debug("map driver: attempt %d did not confirm %r",
                                 attempt + 1, system)
                    keys.send('UI_Up')      # back toward the search controls
                    sleep(0.3)
        finally:
            if self.ap.status.get_gui_focus() == GuiFocusGalaxyMap:
                keys.send('GalaxyMapOpen')
                self._wait_gui(GuiFocusNoFocus, 4.0)
        return ok

    def _goto_map(self, keys) -> bool:
        """Open the galaxy map (from any panel) and leave the highlight on the
        search bar — the two branches of the old goto_galaxy_map()."""
        if self.ap.status.get_gui_focus() != GuiFocusGalaxyMap:
            # drop whatever panel is open first, then open the map fresh
            try:
                ship_control = getattr(self.ap, 'ship_control', None)
                if ship_control is not None:
                    ship_control.goto_cockpit_view()
            except Exception:  # noqa: BLE001 — cockpit view is best-effort
                logger.debug("map driver: goto_cockpit_view failed", exc_info=True)
            keys.send('GalaxyMapOpen')
            if not self._wait_gui(GuiFocusGalaxyMap, 15.0):
                return False
            sleep(2.0)                      # map load/зум-анимация
            keys.send('UI_Up')              # up to the search bar
        else:
            # already open (pilot left it up): normalise onto the search bar
            keys.send('UI_Left', repeat=2)
            keys.send('UI_Up', hold=2)
        sleep(0.3)
        return True

    def _click_set_target(self) -> bool:
        """Hover-and-click the static «Задать цель» button of the system-info
        panel. Position comes from config ExecMapTargetBtnPct as fractions of
        the game screen (default measured on the owner's 2530x1408 screenshot,
        2026-07-17). Returns False when disabled or misconfigured — caller
        falls back to the plot-route sequence."""
        if not self.ap.config.get('ExecMapTargetUseMouse', True):
            return False
        pct = self.ap.config.get('ExecMapTargetBtnPct') or [0.952, 0.613]
        try:
            fx, fy = float(pct[0]), float(pct[1])
        except (TypeError, ValueError, IndexError):
            logger.warning("map driver: bad ExecMapTargetBtnPct %r", pct)
            return False
        scr = getattr(self.ap, 'scr', None)
        width = getattr(scr, 'screen_width', 0) or 0
        height = getattr(scr, 'screen_height', 0) or 0
        if not width or not height:
            logger.warning("map driver: unknown screen size — mouse path off")
            return False
        x, y = int(width * fx), int(height * fy)
        logger.info("map driver: clicking «Задать цель» at %d,%d", x, y)
        self._mouse.ms.position = (x, y)
        sleep(0.4)                          # hover first so the button arms
        self._mouse.do_click(x, y, 0.15)
        return True

    # --- helpers -------------------------------------------------------------- #

    def _settle_delay(self) -> float:
        try:
            return max(0.0, float(self.ap.config.get('ExecMapTargetDelay', 3.0)))
        except (TypeError, ValueError):
            return 3.0

    def _wait_settled(self, timeout: float) -> bool:
        """True once the ship is neither in witchspace nor charging the FSD."""
        waited = 0.0
        while waited < timeout:
            try:
                busy = (self.ap.status.get_flag(FlagsFsdJump)
                        or self.ap.status.get_flag(FlagsFsdCharging))
            except Exception:  # noqa: BLE001
                busy = False
            if not busy:
                return True
            sleep(0.5)
            waited += 0.5
        return False

    def _tap(self, key_name: str, delay: float = 0.06):
        code = SCANCODE[key_name]
        PressKey(code)
        sleep(delay)
        ReleaseKey(code)
        sleep(delay)

    def _type_text(self, text: str):
        for ch in str(text).upper():
            key = _CHAR_KEYS.get(ch)
            if key is None:
                continue        # '*' and friends — search matches on prefix anyway
            self._tap(key, 0.08)

    def _wait_gui(self, focus: int, timeout: float) -> bool:
        waited = 0.0
        while waited < timeout:
            if self.ap.status.get_gui_focus() == focus:
                return True
            sleep(0.25)
            waited += 0.25
        return False

    def _target_confirmed(self, system: str) -> bool:
        """The journal agrees the target/route now points at `system`:
        FSDTarget (target lock) or NavRoute.json final system (plotted)."""
        want = str(system).lower()
        try:
            target = (self.ap.jn.ship_state() or {}).get('target')
            if target and str(target).lower() == want:
                return True
        except Exception:  # noqa: BLE001
            pass
        try:
            last = self.ap.nav_route.get_last_system()
            if last and str(last).lower() == want:
                return True
        except Exception:  # noqa: BLE001
            pass
        return False

    def _wait_confirmed(self, system: str, timeout: float) -> bool:
        waited = 0.0
        while waited < timeout:
            if self._target_confirmed(system):
                return True
            sleep(0.5)
            waited += 0.5
        return False
