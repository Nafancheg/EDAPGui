"""
Headless entry point for ED_Autopilot (Phase 7 vertical slice).

Starts the EDAutopilot core (no tkinter GUI) and serves a minimal web MCDU
over HTTP + WebSocket. The core->UI seam is a Broadcaster used as the ap_ckb
callback; UI->core commands are routed back into the same core methods the
GUI used to call.

Usage:
    python edap_headless.py [--host 127.0.0.1] [--port 8090] [--duration N]
                            [--log-level debug|info|warning]

--duration N shuts the process down automatically after N seconds (for
non-interactive / CI testing). Omit for a normal long-running server.
"""

import argparse
import asyncio
import logging
import signal

from aiohttp import web

from ED_AP import EDAutopilot
from webserver.server import Broadcaster, create_app, _status_snapshot_loop

log = logging.getLogger("edap.headless")


async def _run(host: str, port: int, duration: float | None,
               log_level: str | None):
    loop = asyncio.get_running_loop()

    # A web client dropping abruptly (tablet browser going to sleep, wifi
    # blip) surfaces on the Windows proactor loop as an unhandled
    # ConnectionResetError [WinError 10054] in _call_connection_lost.
    # It's harmless — keep it out of the log, pass everything else through.
    def _quiet_conn_reset(loop_, context):
        if isinstance(context.get("exception"), ConnectionResetError):
            log.debug("client connection reset: %s", context.get("exception"))
            return
        loop_.default_exception_handler(context)

    loop.set_exception_handler(_quiet_conn_reset)

    # 1) Broadcaster must exist (bound to the loop) BEFORE the core, because
    #    constructing the core starts the engine thread which may call ap_ckb.
    broadcaster = Broadcaster(loop)

    # 2) Construct the core headless. This starts the single long-lived engine
    #    worker thread. Core construction is slow (OCR model load).
    print("Constructing EDAutopilot core (this can take a few seconds)...")
    ed_ap = EDAutopilot(cb=broadcaster, do_thread=True)

    # --log-level beats the LogDEBUG/LogINFO flags from the user's AP.json:
    # the core has just applied those in its constructor, so override after.
    if log_level is not None:
        from EDlogger import logger as ed_logger
        ed_logger.setLevel(getattr(logging, log_level.upper()))
        print(f"  (file log level forced to {log_level.upper()})")

    # 3) Build the aiohttp app (reuses the same broadcaster via ed_ap.ap_ckb).
    app, broadcaster = create_app(ed_ap, loop)

    # 4) Periodic structured telemetry snapshot.
    status_task = loop.create_task(_status_snapshot_loop(ed_ap, broadcaster, 1.0))

    # 5) Start the web server.
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()

    print("=" * 60)
    print(f"  ED Autopilot headless server listening on {host}:{port}")
    print(f"  Open http://{host}:{port}")
    print("=" * 60)

    stop_event = asyncio.Event()

    # Ctrl-C / SIGINT -> clean shutdown. add_signal_handler is not available on
    # Windows proactor loops for SIGINT, so fall back to signal.signal.
    def _request_stop(*_a):
        loop.call_soon_threadsafe(stop_event.set)

    try:
        loop.add_signal_handler(signal.SIGINT, stop_event.set)
    except (NotImplementedError, RuntimeError):
        signal.signal(signal.SIGINT, _request_stop)

    if duration is not None:
        loop.call_later(duration, stop_event.set)
        print(f"  (auto-shutdown scheduled after {duration}s)")

    await stop_event.wait()

    # --- clean shutdown ---
    print("Shutting down...")
    status_task.cancel()
    try:
        await status_task
    except asyncio.CancelledError:
        pass
    await broadcaster.stop()
    await runner.cleanup()
    try:
        ed_ap.quit()
    except Exception:
        log.exception("error during ed_ap.quit()")
    print("Shutdown complete.")


def main():
    parser = argparse.ArgumentParser(description="ED Autopilot headless web server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--duration", type=float, default=None,
                        help="auto-shutdown after N seconds (for testing)")
    parser.add_argument("--log-level", choices=("debug", "info", "warning"),
                        default=None,
                        help="force autopilot.log verbosity, overriding the "
                             "LogDEBUG/LogINFO flags in the AP config")
    args = parser.parse_args()

    # NOTE: no logging.basicConfig here — EDlogger already configured the
    # root logger (file handler on logs/autopilot.log) when ED_AP was imported.
    try:
        asyncio.run(_run(args.host, args.port, args.duration, args.log_level))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
