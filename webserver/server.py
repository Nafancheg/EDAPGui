"""
Headless web server for ED_Autopilot (Phase 7 vertical slice).

Thin aiohttp layer over the already-headless EDAutopilot core:
  * publishes core -> UI state (the ap_ckb callback + a 1s status snapshot)
    over a WebSocket to every connected client, and
  * routes UI -> core commands from the same WebSocket into the same core
    methods the tkinter GUI used to call.

No tkinter anywhere in this module. Core construction lives in the launcher
(edap_headless.py) so this module stays importable/testable on its own.
"""

import asyncio
import json
import logging
import os

from aiohttp import web, WSMsgType

log = logging.getLogger("edap.webserver")

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

SCOOPABLE_CLASSES = {"K", "G", "B", "F", "O", "A", "M"}


def map_nav_route(data):
    """Map raw NavRoute.json data to the web 'route' event payload.
    Returns {"active": bool, "destination": str|None, "systems": [
        {"system": str, "star_class": str, "scoopable": bool, "dist_ly": float|None}, ...]}
    The first entry is the starting system (dist_ly None)."""
    if not data or data.get("event") == "NavRouteClear" or not data.get("Route"):
        return {"active": False, "destination": None, "systems": []}
    systems = []
    prev_pos = None
    for hop in data["Route"]:
        pos = hop.get("StarPos")
        dist = None
        if prev_pos is not None and pos is not None:
            dist = round(sum((a - b) ** 2 for a, b in zip(pos, prev_pos)) ** 0.5, 2)
        star_class = hop.get("StarClass") or ""
        systems.append({
            "system": hop.get("StarSystem", ""),
            "star_class": star_class,
            "scoopable": star_class in SCOOPABLE_CLASSES,
            "dist_ly": dist,
        })
        if pos is not None:
            prev_pos = pos
    return {"active": True, "destination": systems[-1]["system"], "systems": systems}


def map_ap_ckb(msg, body=None):
    """Translate an ap_ckb (tag, body) into a JSON-friendly event dict, or
    None if the tag should be dropped (GUI-internal signals with no meaning
    for a web client). See docs/web_api_contract.md section 5/6."""
    if msg in ("log", "log+vce"):
        return {"type": "log", "text": body, "voice": msg == "log+vce"}
    if msg == "statusline":
        return {"type": "statusline", "text": body}
    if msg == "jumpcount":
        return {"type": "jumpcount", "text": body}
    if msg == "fsd_start":
        return {"type": "assist", "mode": "fsd", "running": True}
    if msg == "fsd_stop":
        return {"type": "assist", "mode": "fsd", "running": False}
    if msg == "sc_start":
        return {"type": "assist", "mode": "sc", "running": True}
    if msg == "sc_stop":
        return {"type": "assist", "mode": "sc", "running": False}
    if msg == "update_ship_cfg":
        return {"type": "ship_changed"}
    # GUI-internal re-dispatch / dead nudge tags: drop them.
    if msg in ("stop_all_assists", "up", "down", "left", "right"):
        return None
    # Anything unrecognised passes through generically so nothing is lost.
    return {"type": "event", "tag": msg, "body": body}


class Broadcaster:
    """The ap_ckb callback (core -> UI seam) AND the WS client registry.

    __call__ runs on the engine worker THREAD, so it must not touch asyncio
    state directly; it hands (msg, body) to the loop thread-safely. A drain
    task (started in the loop thread) maps and fans each item out to all
    connected WebSocket clients.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop
        self._queue: asyncio.Queue = asyncio.Queue()
        self._clients: set[web.WebSocketResponse] = set()
        self._drain_task: asyncio.Task | None = None

    # --- called from the engine worker thread ---
    def __call__(self, msg, body=None):
        # Tolerate being invoked before the loop is running: call_soon_threadsafe
        # only requires the loop object to exist, which it does (launcher creates
        # the loop before the core).
        try:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, (msg, body))
        except RuntimeError:
            # Loop already closed during shutdown; drop the message.
            pass

    # --- asyncio side ---
    def register(self, ws: web.WebSocketResponse):
        self._clients.add(ws)

    def unregister(self, ws: web.WebSocketResponse):
        self._clients.discard(ws)

    async def broadcast(self, event: dict):
        if not self._clients:
            return
        data = json.dumps(event)
        dead = []
        for ws in list(self._clients):
            try:
                await ws.send_str(data)
            except Exception as e:
                log.debug("dropping dead ws client: %s", e)
                dead.append(ws)
        for ws in dead:
            self._clients.discard(ws)

    def start(self):
        if self._drain_task is None:
            self._drain_task = self._loop.create_task(self._drain_loop())

    async def _drain_loop(self):
        while True:
            msg, body = await self._queue.get()
            try:
                event = map_ap_ckb(msg, body)
                if event is not None:
                    await self.broadcast(event)
            except Exception:
                log.exception("error broadcasting ap_ckb event %r", msg)

    async def stop(self):
        if self._drain_task is not None:
            self._drain_task.cancel()
            try:
                await self._drain_task
            except asyncio.CancelledError:
                pass
            self._drain_task = None


async def _status_snapshot_loop(ed_ap, broadcaster: Broadcaster, interval: float = 1.0):
    """Every `interval` seconds pull structured telemetry and broadcast it."""
    while True:
        try:
            data = ed_ap.get_status_dict()
            await broadcaster.broadcast({"type": "status_snapshot", "data": data})
        except Exception:
            log.exception("error building/broadcasting status_snapshot")
        await asyncio.sleep(interval)


def _normalize_curve(data):
    """Validate and normalize a curve dict coming from the web UI.
    Returns a {str: float} dict sorted ascending by angle, or None if invalid.
    Sorting here is mandatory: JS objects serialize integer-like keys ("30")
    before fractional ones ("0.5"), and the core's rate interpolation
    (EDShipControl) iterates the dict in insertion order assuming ascending
    angles. Keys are re-rendered via str(float) to match the core's
    convert_curve_to_str format ("45.0", not "45")."""
    if not isinstance(data, dict) or not data:
        return None
    entries = []
    for k, v in data.items():
        try:
            angle = float(k)
            rate = float(v)
        except (TypeError, ValueError):
            return None
        if angle <= 0 or rate < 0:
            return None
        entries.append((angle, rate))
    entries.sort()
    return {str(angle): round(rate, 2) for angle, rate in entries}


def _apply_config_side_effects(ed_ap, key: str):
    """Fire the live side-effect for a config key when writing it isn't enough.

    process_config_settings() (called just before this) already applies most
    settings from config: ActivateEliteEachKey, the key-emulation timings, the
    debug flags and cv_view. The overlay reads OverlayTextEnable from config on
    every update_overlay() cycle. What it does NOT do is start/stop the TTS
    worker or repaint the overlay right away, so a web toggle for those would
    otherwise only take effect on the next relevant event. Fire their setters
    here. New keys with their own side-effects get added to this map.
    """
    if key == "VoiceEnable":
        ed_ap.set_voice(bool(ed_ap.config.get("VoiceEnable")))
    elif key == "OverlayTextEnable":
        ed_ap.set_overlay(bool(ed_ap.config.get("OverlayTextEnable")))
    elif key == "Language":
        # core log/voice locale (OCR strings come from OCRLanguage separately)
        ed_ap.locale.change_language(str(ed_ap.config.get("Language") or "en"))
    elif key in ("LogDEBUG", "LogINFO"):
        # re-derive the logger level from the flag pair (DEBUG wins over INFO,
        # neither = ERROR) — the ED_AP setters also normalise the flags
        if ed_ap.config.get("LogDEBUG"):
            ed_ap.set_log_debug(True)
        elif ed_ap.config.get("LogINFO"):
            ed_ap.set_log_info(True)
        else:
            ed_ap.set_log_error(True)


async def _dispatch_command(ed_ap, broadcaster, ws: web.WebSocketResponse, cmd: dict):
    """Handle a single UI -> core command. Runs on the asyncio thread, which
    is safe: set_*_assist is thread-safe and the throttle setters are quick."""
    name = cmd.get("cmd")
    if name == "assist.start":
        mode = cmd.get("mode")
        if mode == "fsd":
            ed_ap.set_fsd_assist(True)
        elif mode == "sc":
            ed_ap.set_sc_assist(True)
        else:
            await ws.send_str(json.dumps({"type": "error", "text": f"unknown assist mode: {mode!r}"}))
    elif name == "assist.stop":
        mode = cmd.get("mode")
        if mode == "fsd":
            ed_ap.set_fsd_assist(False)
        elif mode == "sc":
            ed_ap.set_sc_assist(False)
        else:
            await ws.send_str(json.dumps({"type": "error", "text": f"unknown assist mode: {mode!r}"}))
    elif name == "assist.stop_all":
        ed_ap.set_fsd_assist(False)
        ed_ap.set_sc_assist(False)
    elif name == "action.request":
        action = cmd.get("action")
        if isinstance(action, str) and ed_ap.request_action(action):
            await ws.send_str(json.dumps({"type": "action_queued", "action": action}))
        else:
            await ws.send_str(json.dumps({"type": "error", "text": f"unknown action: {action!r}"}))
    elif name == "throttle.set":
        level = cmd.get("level")
        if level == 0:
            ed_ap.set_throttle_0()
        elif level == 50:
            ed_ap.set_throttle_50()
        elif level == 100:
            ed_ap.set_throttle_100()
        else:
            await ws.send_str(json.dumps({"type": "error", "text": f"invalid throttle level: {level!r}"}))
    elif name == "config.get":
        await ws.send_str(json.dumps({"type": "config", "data": dict(ed_ap.config)}))
    elif name == "config.set":
        key = cmd.get("key")
        if not isinstance(key, str) or key not in ed_ap.config:
            await ws.send_str(json.dumps({"type": "error", "text": f"unknown config key: {key!r}"}))
        else:
            ed_ap.config[key] = cmd.get("value")
            ed_ap.process_config_settings()
            _apply_config_side_effects(ed_ap, key)
            # keep every connected client's view of the config in sync
            await broadcaster.broadcast({"type": "config", "data": dict(ed_ap.config)})
    elif name == "config.save_ship":
        if ed_ap.update_ship_configs():
            await ws.send_str(json.dumps({"type": "ship_saved", "ok": True}))
        else:
            await ws.send_str(json.dumps({
                "type": "ship_saved", "ok": False,
                "text": f"not saved: no ship detected (current type: {ed_ap.current_ship_type!r})"}))
    elif name == "config.save":
        # SETTINGS/SAVE ALL: persist the in-memory config to configs/AP.json.
        # config.set only mutates ed_ap.config in memory; this is what writes
        # the web-side toggle changes to disk so they survive a restart.
        ed_ap.update_config()
        await ws.send_str(json.dumps({"type": "config_saved", "ok": True}))
    elif name == "config.load":
        # SETTINGS/LOAD ALL: re-read configs/AP.json AND ship_configs.json from
        # disk (the old GUI "Load All" reloaded ship configs too), apply to the
        # subclasses, and push the refreshed config to every client.
        ed_ap.load_config()
        ed_ap.load_ship_configs()
        ed_ap.process_config_settings()
        await broadcaster.broadcast({"type": "config", "data": dict(ed_ap.config)})
        await ws.send_str(json.dumps({"type": "config_loaded", "ok": True}))
    elif name == "route.get":
        data = ed_ap.nav_route.get_nav_route_data()
        await ws.send_str(json.dumps({"type": "route", "data": map_nav_route(data)}))
    elif name == "curve.get":
        axis = cmd.get("axis")
        if axis not in ("RollRate", "PitchRate", "YawRate"):
            await ws.send_str(json.dumps({"type": "error", "text": f"invalid curve axis: {axis!r}"}))
        elif ed_ap.current_ship_cfg is None:
            await ws.send_str(json.dumps({"type": "error", "text": "no ship config loaded — ship not detected yet"}))
        else:
            spd_key = ed_ap.speed_demand or 'SCSpeed50'
            spd = ed_ap.current_ship_cfg.get(spd_key)
            curve = spd.get(axis, {}) if isinstance(spd, dict) else {}
            await ws.send_str(json.dumps({"type": "curve", "axis": axis, "data": curve, "speed": spd_key}))
    elif name == "curve.set":
        axis = cmd.get("axis")
        curve = _normalize_curve(cmd.get("data"))
        if axis not in ("RollRate", "PitchRate", "YawRate"):
            await ws.send_str(json.dumps({"type": "error", "text": f"invalid curve axis: {axis!r}"}))
        elif curve is None:
            await ws.send_str(json.dumps({"type": "error", "text": "curve data must be a non-empty dict of positive angle -> rate numbers"}))
        elif ed_ap.current_ship_cfg is None:
            await ws.send_str(json.dumps({"type": "error", "text": "no ship config loaded — ship not detected yet"}))
        else:
            spd_key = ed_ap.speed_demand or 'SCSpeed50'
            ed_ap.current_ship_cfg.setdefault(spd_key, {})[axis] = curve
            ed_ap.ap_ckb('log', f'RPY curve updated: {spd_key}/{axis}')
            await ws.send_str(json.dumps({"type": "curve_saved", "axis": axis}))
    else:
        await ws.send_str(json.dumps({"type": "error", "text": f"unknown command: {name!r}"}))


def create_app(ed_ap, loop: asyncio.AbstractEventLoop):
    """App factory. Returns (aiohttp.web.Application, Broadcaster).

    The caller is responsible for having created `broadcaster` earlier (it is
    the ap_ckb passed to the core); here we build a fresh one bound to the same
    loop so the app owns its lifecycle. To keep the seam consistent the launcher
    passes the SAME broadcaster it gave the core -- so we accept an existing one
    on the app if present. For simplicity of the slice we take it from ed_ap's
    ap_ckb if it is a Broadcaster."""
    broadcaster = ed_ap.ap_ckb if isinstance(ed_ap.ap_ckb, Broadcaster) else Broadcaster(loop)
    broadcaster.start()

    @web.middleware
    async def no_cache_mw(request, handler):
        # The UI is served to a handful of LAN clients and changes with every
        # iteration; stale cached css/js breaks the page silently. Force
        # revalidation on every load (WS route untouched).
        resp = await handler(request)
        if request.path == "/" or request.path.startswith("/static/"):
            resp.headers["Cache-Control"] = "no-cache"
        return resp

    app = web.Application(middlewares=[no_cache_mw])
    app["ed_ap"] = ed_ap
    app["broadcaster"] = broadcaster

    async def handle_index(request):
        return web.FileResponse(os.path.join(STATIC_DIR, "index.html"))

    async def handle_ws(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        broadcaster.register(ws)
        try:
            await ws.send_str(json.dumps({"type": "hello"}))
            # immediate snapshot on connect
            try:
                await ws.send_str(json.dumps(
                    {"type": "status_snapshot", "data": ed_ap.get_status_dict()}))
            except Exception:
                log.exception("error sending initial snapshot")

            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        cmd = json.loads(msg.data)
                    except (ValueError, TypeError):
                        await ws.send_str(json.dumps({"type": "error", "text": "invalid JSON"}))
                        continue
                    try:
                        await _dispatch_command(ed_ap, broadcaster, ws, cmd)
                    except Exception as e:
                        log.exception("error dispatching command")
                        await ws.send_str(json.dumps({"type": "error", "text": str(e)}))
                elif msg.type == WSMsgType.ERROR:
                    log.debug("ws connection error: %s", ws.exception())
        finally:
            broadcaster.unregister(ws)
        return ws

    app.router.add_get("/", handle_index)
    app.router.add_get("/ws", handle_ws)
    app.router.add_static("/static/", STATIC_DIR, name="static")
    return app, broadcaster
