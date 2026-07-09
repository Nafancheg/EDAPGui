"""Fake-core server for developing/QA-ing the MCDU web frontend (Phase 7.3).
Uses the REAL webserver/server.py app + a synthetic EDAutopilot stand-in that
emits believable telemetry. No OCR, no game, no tkinter.

Run:  python tools/demo_mcdu_server.py   then open http://127.0.0.1:8765
"""
import asyncio
import itertools
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiohttp import web

from webserver.server import Broadcaster, create_app, _status_snapshot_loop

ROUTE = {
    "timestamp": "t", "event": "NavRoute", "Route": [
        {"StarSystem": "Leesti", "StarPos": [72.75, 48.75, 68.25], "StarClass": "K"},
        {"StarSystem": "Crucis Sector NY-R b4-3", "StarPos": [46.84, 31.59, 76.21], "StarClass": "M"},
        {"StarSystem": "Devataru", "StarPos": [24.28, 19.34, 90.93], "StarClass": "M"},
        {"StarSystem": "Scorpii Sector ZU-Y b4", "StarPos": [-0.5, -0.65, 86.65], "StarClass": "T"},
        {"StarSystem": "HR 6836", "StarPos": [-7.53, -11.03, 98.53], "StarClass": "F"},
        {"StarSystem": "Wolf 1453", "StarPos": [-17.0, -15.0, 105.0], "StarClass": "L"},
        {"StarSystem": "LHS 3447", "StarPos": [-30.0, -20.0, 110.0], "StarClass": "G"},
        {"StarSystem": "Eravate", "StarPos": [-42.0, -25.0, 118.0], "StarClass": "K"},
        {"StarSystem": "Kremainn", "StarPos": [-55.0, -28.0, 121.0], "StarClass": "A"},
        {"StarSystem": "Sharur", "StarPos": [-63.0, -33.0, 130.0], "StarClass": "Y"},
        {"StarSystem": "Nanomam", "StarPos": [-72.0, -40.0, 139.0], "StarClass": "G"},
        {"StarSystem": "Diaguandri", "StarPos": [-80.0, -46.0, 148.0], "StarClass": "M"},
        {"StarSystem": "Deciat", "StarPos": [-92.0, -52.0, 155.0], "StarClass": "G"},
        {"StarSystem": "Maia", "StarPos": [-81.78, -149.44, -343.37], "StarClass": "B"},
    ]}


class FakeNavRoute:
    def get_nav_route_data(self):
        return ROUTE


class FakeAP:
    def __init__(self):
        self.ap_ckb = None
        self.config = {"FastTravelMode": False, "RefuelThreshold": 65,
                       "ElwScannerEnable": False}
        self.nav_route = FakeNavRoute()
        self.fsd = False
        self.sc = False
        self.fuel = itertools.cycle([72.4, 71.9, 71.3, 44.0, 23.5, 8.2, 91.0])
        self._fuel = 72.4

    def get_status_dict(self):
        self._fuel = next(self.fuel)
        if self.fsd:
            mode = "fsd"
        elif self.sc:
            mode = "sc"
        else:
            mode = "offline"
        return {
            "ap_mode": mode,
            "ap_state": "Waiting" if mode == "offline" else "Aligning",
            "ship_status": "in_space",
            "fuel_percent": self._fuel,
            "location": "Devataru",
            "star_class": "M",
            "scoopable": False,
            "target": "Maia",
            "jumps_remaining": 9,
            "jump_cnt": 5,
            "total_jumps": 14,
            "total_dist_jumped": 182.4,
            "eta": "00:41",
            "elw_scanner": None,
            "edsm_info": None,
        }

    def process_config_settings(self):
        self.ap_ckb("log", "config applied")

    def set_fsd_assist(self, v):
        self.fsd = v
        self.ap_ckb("log", f"FSD assist -> {v}")

    def set_sc_assist(self, v):
        self.sc = v
        self.ap_ckb("log", f"SC assist -> {v}")

    def set_throttle_0(self):
        self.ap_ckb("log", "Throttle set to 0%")

    def set_throttle_50(self):
        self.ap_ckb("log", "Throttle set to 50%")

    def set_throttle_100(self):
        self.ap_ckb("log", "Throttle set to 100%")


async def chatter(ap):
    n = 0
    msgs = ["Aligning to target", "WARNING: heat rising", "Jump complete",
            "Refuel complete", "ERROR: alignment lost"]
    while True:
        await asyncio.sleep(4)
        ap.ap_ckb("log" if n % 3 else "log+vce", msgs[n % len(msgs)])
        n += 1


async def main():
    loop = asyncio.get_running_loop()
    broadcaster = Broadcaster(loop)
    ap = FakeAP()
    ap.ap_ckb = broadcaster
    app, broadcaster = create_app(ap, loop)
    loop.create_task(_status_snapshot_loop(ap, broadcaster, 1.0))
    loop.create_task(chatter(ap))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 8765)
    await site.start()
    print("fake MCDU server on http://127.0.0.1:8765")
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
