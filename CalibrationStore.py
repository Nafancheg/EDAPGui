"""Headless store for the OCR calibration data (configs/ocr_calibration.json).

Extracted from the tkinter Calibration tab (EDAPCalibration.py) so the web
MCDU can edit/save/preview calibration rects without the GUI. The runtime
consumers (Screen_Regions.load_calibrated_regions*) read the json from disk
themselves, so this store only manages the editing copy + persistence; the
core picks changes up on restart (same behaviour the GUI tab had).
"""

from __future__ import annotations

import json
import os

from Screen_Regions import Quad, load_default_calib_data, MyRegion

CALIBRATION_FILE = 'configs/ocr_calibration.json'


class CalibrationStore:
    def __init__(self):
        # load_default_calib_data() merges the defaults with an existing json
        # (and creates the file when missing) — same source the GUI tab used.
        self.data: dict[str, MyRegion] = load_default_calib_data()

    def snapshot(self) -> dict:
        """JSON-safe view for the web client: key -> rect/text/readonly."""
        out = {}
        for key, val in self.data.items():
            if not isinstance(val, dict) or 'rect' not in val:
                continue
            out[key] = {
                'rect': list(val['rect']),
                'text': val.get('text', ''),
                'readonly': bool(val.get('readonly', False)),
            }
        return out

    def set_rect(self, key, rect) -> str | None:
        """Update one region's rect. Returns an error string or None on success."""
        if not isinstance(key, str) or key not in self.data:
            return f"unknown calibration key: {key!r}"
        entry = self.data[key]
        if not isinstance(entry, dict) or 'rect' not in entry:
            return f"not an editable region: {key!r}"
        if entry.get('readonly'):
            return f"region is read-only (derived automatically): {key}"
        if not isinstance(rect, (list, tuple)) or len(rect) != 4:
            return "rect must be a list of 4 numbers [x0, y0, x1, y1]"
        try:
            vals = [float(v) for v in rect]
        except (TypeError, ValueError):
            return "rect must be a list of 4 numbers [x0, y0, x1, y1]"
        if not all(0.0 <= v <= 1.0 for v in vals):
            return "rect values must be fractions in 0.0..1.0"
        if vals[0] >= vals[2] or vals[1] >= vals[3]:
            return "rect must satisfy x0 < x1 and y0 < y1"
        entry['rect'] = [round(v, 4) for v in vals]
        return None

    def save(self, ap_ckb=None):
        """Persist to disk, deriving the dependent panels first.

        The derive block is a straight port of the GUI's
        save_ocr_calibration_data(): the Codex full-panel rect drives the
        commodities market / system map / galaxy map / FSS panels (readonly
        entries). Guarded per key so a trimmed json cannot KeyError.
        """
        src = self.data.get('EDCodex.full_panel')
        if isinstance(src, dict) and 'rect' in src:
            derived = (
                ('EDStationServicesInShip.commodities_market', 1.025, 1.0),
                ('EDSystemMap.full_panel', 1.05, 1.08),
                ('EDGalaxyMap.full_panel', 1.05, 1.08),
                ('EDFSS.full_panel', 1.0, 1.0),
            )
            for dst_key, fx, fy in derived:
                dst = self.data.get(dst_key)
                if isinstance(dst, dict) and 'rect' in dst:
                    q = Quad.from_rect(src['rect'])
                    q.scale(fx=fx, fy=fy)
                    dst['rect'] = q.to_rect_list(round_dp=4)

        with open(CALIBRATION_FILE, 'w') as f:
            json.dump(self.data, f, indent=4)
        if ap_ckb:
            ap_ckb('log', 'OCR calibration data saved.')

    def reset(self, ap_ckb=None):
        """Delete the json and reload the defaults (GUI 'Reset All')."""
        if os.path.exists(CALIBRATION_FILE):
            os.remove(CALIBRATION_FILE)
            if ap_ckb:
                ap_ckb('log', 'Removed existing ocr_calibration.json.')
        # recreates the file with defaults
        self.data = load_default_calib_data()

    def preview(self, ed_ap, key) -> str | None:
        """Draw the region on the game overlay (visible on the game monitor).

        Port of the GUI's on_region_select/on_subregion_select preview: a
        subregion is cropped out of its parent region before drawing.
        Returns an error string or None on success.
        """
        if not isinstance(key, str) or key not in self.data:
            return f"unknown calibration key: {key!r}"
        overlay = getattr(ed_ap, 'overlay', None)
        if overlay is None:
            return "overlay not available on this core"
        entry = self.data[key]
        try:
            if '.subregion.' in key:
                parent_key = key.split('.subregion.')[0]
                parent = self.data.get(parent_key)
                if not (isinstance(parent, dict) and 'rect' in parent):
                    return f"parent region missing for {key!r}"
                quad = Quad.from_rect(parent['rect'])
                quad.crop(Quad.from_rect(entry['rect']))
                overlay.overlay_quad_pct('subregion select', quad, (0, 255, 0), 2, 15)
            else:
                quad = Quad.from_rect(entry['rect'])
                overlay.overlay_quad_pct('region select', quad, (0, 255, 0), 2, 15)
            overlay.overlay_paint()
        except Exception as e:  # noqa: BLE001 — surface overlay errors to the client
            return f"overlay preview failed: {e}"
        return None
