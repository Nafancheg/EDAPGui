"""Segment-wise executor for an activated planner route (Phase 8.1).

Takes a Route dict plotted by RoutePlanner (FUEL-SAFE or FAST — the exact
plotter profiles, where every leg and its fuel state are known) and walks it
against the live journal location:

  * the route is split into SEGMENTS ending at each must_refuel stop (and at
    the final destination) — the chosen in-game entry strategy is
    per-segment: the galaxy map gets the segment endpoint and the game plots
    the jumps in between;
  * every location change advances the position; reaching a segment endpoint
    requests the next segment from the GalaxyMapDriver;
  * a location that is not on the route flips the state to OFF_ROUTE (and
    back to ACTIVE the moment the ship rejoins the plan);
  * reaching the destination flips to COMPLETE.

GalaxyMapDriver is the game-side abstraction: on this laptop it is a stub
that only records what would be typed into the galaxy map; the real
keyboard/OCR driver (game part of Phase 8.1) replaces it with the same
interface. Location updates come from the webserver's 1 Hz status tick
(`tick()`), so this module needs no thread of its own.

Like RoutePlanner, this module never imports the ED_AP core at runtime.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # avoid importing the core at runtime
    from ED_AP import EDAutopilot

logger = logging.getLogger(__name__)

# executor states
INACTIVE = "INACTIVE"
ACTIVE = "ACTIVE"
OFF_ROUTE = "OFF ROUTE"
COMPLETE = "COMPLETE"


class ExecuteError(Exception):
    """Human-readable activation failure — surfaced to the client as an error."""


class GalaxyMapDriver:
    """Interface + laptop stub: records the system that would be entered into
    the in-game galaxy map. The real driver (game part of 8.1) overrides
    plot_to() with actual key/OCR input and returns False on failure."""

    def __init__(self):
        self.last_target: str | None = None
        self.requests: list[str] = []

    def plot_to(self, system: str) -> bool:
        self.last_target = system
        self.requests.append(system)
        logger.info("GalaxyMapDriver(stub): would plot galaxy map to %r", system)
        return True


class RouteExecutor:
    """Owns the ACTIVE (executed) route. State changes only via activate() /
    deactivate() / tick(); snapshot() returns a JSON-safe copy."""

    def __init__(self, ed_ap: "EDAutopilot", map_driver: GalaxyMapDriver | None = None):
        self.ap = ed_ap
        self.map_driver = map_driver or GalaxyMapDriver()
        self._lock = threading.Lock()
        self._route: dict | None = None
        self._idx = 0                    # index into route["systems"] we are AT
        self._status = INACTIVE
        self._off_route_at: str | None = None
        self._last_fuel: float | None = None

    # --- helpers ------------------------------------------------------------ #

    def _systems(self) -> list:
        return (self._route or {}).get("systems") or []

    def _find(self, location: str, start: int = 0) -> int | None:
        """Index of `location` in the route systems (case-insensitive), or None."""
        loc = (location or "").lower()
        for i in range(start, len(self._systems())):
            if (self._systems()[i].get("system") or "").lower() == loc:
                return i
        return None

    def _segment_target(self, idx: int) -> str | None:
        """Endpoint of the current segment: the next must_refuel stop after
        `idx`, else the destination."""
        systems = self._systems()
        for s in systems[idx + 1:]:
            if s.get("must_refuel"):
                return s.get("system")
        return systems[-1].get("system") if systems else None

    def _journal_location(self) -> str | None:
        try:
            state = self.ap.jn.ship_state()
        except Exception:  # noqa: BLE001 — no journal is a valid laptop state
            return None
        return state.get("location") if isinstance(state, dict) else None

    # --- commands ------------------------------------------------------------ #

    def activate(self, route: dict | None) -> None:
        """Adopt a plotted route as the active one and request the first
        segment from the galaxy-map driver. Raises ExecuteError when the
        route is missing or not executable per-leg."""
        if not route or not route.get("systems"):
            raise ExecuteError("NO SEC ROUTE — PLOT FIRST")
        if (route.get("profile") or "").upper() == "ULTRA":
            # waypoint list without fuel model — no per-leg segments to walk
            raise ExecuteError("ULTRA ROUTE IS NOT EXECUTABLE PER-LEG")
        systems = route["systems"]
        if len(systems) < 2:
            raise ExecuteError("ROUTE HAS NO LEGS")

        with self._lock:
            self._route = route
            location = self._journal_location()
            idx = self._find(location, 0) if location else None
            self._idx = idx if idx is not None else 0
            self._status = ACTIVE
            self._off_route_at = None
        target = self._segment_target(self._idx)
        if target:
            self.map_driver.plot_to(target)
        logger.info("route activated: %s -> %s (%d legs), first segment target %r",
                    route.get("source"), route.get("destination"),
                    len(systems) - 1, target)

    def deactivate(self) -> None:
        with self._lock:
            self._route = None
            self._idx = 0
            self._status = INACTIVE
            self._off_route_at = None

    # --- 1 Hz tick ------------------------------------------------------------ #

    def tick(self, location: str | None, fuel_level: float | None = None) -> bool:
        """Advance against the latest journal location. Returns True when the
        public snapshot changed (caller broadcasts it)."""
        with self._lock:
            if self._status not in (ACTIVE, OFF_ROUTE) or not location:
                return False
            self._last_fuel = fuel_level

            cur = self._systems()[self._idx].get("system") or ""
            if location.lower() == cur.lower():
                # still where we were; only a rejoin after OFF_ROUTE counts
                if self._status == OFF_ROUTE:
                    self._status = ACTIVE
                    self._off_route_at = None
                    return True
                return False

            found = self._find(location, self._idx + 1)
            if found is None:
                # allow matching BEHIND the current index too (a re-log or a
                # manual back-jump keeps us on the plan, just further back)
                found = self._find(location, 0)
            if found is None:
                changed = self._status != OFF_ROUTE or self._off_route_at != location
                self._status = OFF_ROUTE
                self._off_route_at = location
                return changed

            was_target = self._segment_target(self._idx)
            self._idx = found
            self._off_route_at = None
            if found == len(self._systems()) - 1:
                self._status = COMPLETE
                logger.info("route complete at %r", location)
                return True
            self._status = ACTIVE
            arrived_segment_end = was_target and location.lower() == was_target.lower()

        # segment endpoint reached -> hand the next segment to the map driver
        # (outside the lock: the real driver will do slow key/OCR work)
        if arrived_segment_end:
            nxt = self._segment_target(self._idx)
            if nxt:
                self.map_driver.plot_to(nxt)
        return True

    # --- snapshot ------------------------------------------------------------ #

    def snapshot(self) -> dict:
        with self._lock:
            if self._route is None:
                return {"active": False, "status": self._status}
            systems = self._systems()
            idx = self._idx
            remaining = systems[idx + 1:]
            here = systems[idx]
            return {
                "active": self._status in (ACTIVE, OFF_ROUTE),
                "status": self._status,
                "profile": self._route.get("profile"),
                "destination": self._route.get("destination"),
                "idx": idx,
                "jumps_total": len(systems) - 1,
                "jumps_done": idx,
                "next_system": remaining[0].get("system") if remaining else None,
                "segment_target": self._segment_target(idx),
                "map_target": self.map_driver.last_target,
                "remaining_jumps": len(remaining),
                "remaining_dist_ly": round(sum(s.get("dist_ly") or 0.0 for s in remaining), 2),
                "next_refuel_in": next(
                    (n + 1 for n, s in enumerate(remaining) if s.get("must_refuel")), None),
                "fuel_plan": here.get("fuel_tank"),
                "fuel_actual": self._last_fuel,
                "off_route_at": self._off_route_at,
            }
