"""
JetConeService — fully automated neutron star / white dwarf FSD supercharge.

Sequence (with YOLO model):
  1. Arrive at neutron star → STOP (throttle 0)
  2. Screen capture → YOLO detects cone positions and angles
  3. Roll until star is horizontal (cones left/right: >o<)
  4. Roll +90° right → right cone points UP
  5. Pitch/yaw → align parallel to cone, slightly angled toward far end
  6. Throttle 50% → gentle entry → OCR: "WARNING! FSD OPERATING BEYOND SAFETY LIMITS"
  7. Stay in turbulence → OCR: "FRAME SHIFT DRIVE SUPERCHARGED"
  8. Throttle 100% → exit cone (angle-dependent, turbulent)
  9. Course away from star

Fallback (no YOLO): blind pitch toward one pole, OCR-driven entry.
Self-training: every successful OCR entry saves a pre-labelled frame.
"""

from __future__ import annotations

import math
import time
from time import sleep
from typing import TYPE_CHECKING

import cv2

from EDAP_data import *
from EDlogger import logger

if TYPE_CHECKING:
    from ED_AP import EDAutopilot, JetConeDetection


class JetConeService:
    """Neutron star / white dwarf jet cone FSD supercharge."""

    # Star classes that have jet cones
    NEUTRON_CLASSES = ('N', 'D')       # N=neutron, D=white dwarf
    NEUTRON_CLASSES_BOOST = ('N',)     # only neutron gives ×4; white dwarf only ×1.5, skip

    def __init__(self, ed_ap):
        self.ap = ed_ap

    # ── detection ────────────────────────────────────────────────────────

    def is_neutron_star(self, boost_only: bool = True) -> bool:
        """Check if the current star has jet cones.
        If boost_only=True, only returns True for neutron stars (×4 boost)."""
        sc = self.ap.jn.ship_state().get('star_class')
        classes = self.NEUTRON_CLASSES_BOOST if boost_only else self.NEUTRON_CLASSES
        return sc in classes

    def is_supercharged(self) -> bool:
        """FSD already supercharged?"""
        return self.ap.jn.is_supercharged()

    # ── full boost sequence ──────────────────────────────────────────────

    def boost(self, scr_reg) -> bool:
        """Run the full jet-cone boost sequence. Returns True if supercharged."""
        if self.is_supercharged():
            self.ap.ap_ckb('log', 'FSD already supercharged — skipping cone entry')
            return True

        if not self.is_neutron_star(boost_only=True):
            return False

        self.ap.update_ap_status("Jet cone boost")
        self.ap.vce.say("Neutron star — jet cone boost")
        self.ap.ap_ckb('log+vce', 'Neutron star detected — entering jet cone')

        # 1. STOP immediately after jump — do NOT fly toward the star
        self.ap.set_throttle_0()
        sleep(0.5)

        # 2. Enter the cone (YOLO-guided if available, else blind)
        if not self._enter_cone(scr_reg):
            self.ap.ap_ckb('log', 'Jet cone entry failed — continuing normal jump')
            return False

        # 3. Stay in cone until supercharged
        if not self._wait_supercharged(scr_reg):
            self.ap.ap_ckb('log', 'Supercharge failed — exiting cone')
            self._exit_cone()
            return False

        # 4. Exit cone
        self._exit_cone()

        self.ap.ap_ckb('log+vce', 'FSD supercharged! Jump range ×4')
        return True

    # ── cone entry ───────────────────────────────────────────────────────

    def _enter_cone(self, scr_reg) -> bool:
        """YOLO-guided if model available, else blind pitch toward pole."""
        self.ap.ap_ckb('log', 'Searching for jet cone...')
        if self._try_yolo_entry(scr_reg):
            return True
        self.ap.ap_ckb('log', 'YOLO not available — blind cone search')
        return self._blind_entry(scr_reg)

    # ── YOLO-guided entry ────────────────────────────────────────────

    # Thresholds
    DETECT_CONFIDENCE = 0.5
    ALIGN_TIMEOUT = 30.0
    APPROACH_THROTTLE = 50
    ROLL_TOL_DEG = 3.0          # roll alignment tolerance

    def _try_yolo_entry(self, scr_reg) -> bool:
        """Full YOLO-guided algorithm:

        Capture → Detect → Validate → Roll horizontal → Roll +90° right →
        Re-detect + fine-tune roll → Select working jet → Approach control
        loop (align + fly + OCR)"""
        # ── detect & validate ──
        detection = self.ap.jet_cone_ml_detect(scr_reg)
        if not self._validate_yolo_detection(detection):
            return False

        self.ap.ap_ckb('log',
            f'Jet cone detected (conf={detection.confidence:.2f}, '
            f'axis={detection.jet_axis_angle:.1f}°)')

        # ── roll to horizontal: jets at 3 and 9 o'clock ──
        if not self._roll_to_horizontal(scr_reg, detection):
            return False

        # ── roll +90° right (closed-loop): right jet → points UP ──
        if not self._roll_to_angle(scr_reg, detection, target_angle=90.0):
            return False

        self.ap.ap_ckb('log',
            f'Right jet up (axis={detection.jet_axis_angle:.1f}°)')

        # ── compute approach target (picks the jet that is actually UP) ──
        target = self._compute_entry_target(detection)
        if target is None:
            self.ap.ap_ckb('log', 'Entry target out of bounds — re-detecting...')
            detection = self.ap.jet_cone_ml_detect(scr_reg)
            if not self._validate_yolo_detection(detection):
                return False
            target = self._compute_entry_target(detection)
            if target is None:
                self.ap.ap_ckb('log', 'Entry target still invalid — blind fallback')
                return False
        self.ap.ap_ckb('log',
            f'Target entry: ({target[0]:.3f}, {target[1]:.3f})')

        # ── single approach control loop: align + fly + OCR ──
        self.ap.set_throttle_50()
        self.ap.ap_ckb('log', f'Approaching cone at {self.APPROACH_THROTTLE}% throttle')

        if not self._approach_control_loop(scr_reg, target):
            return False

        self._save_yolo_training_frame(scr_reg, detection)
        return True

    # ── validation ──────────────────────────────────────────────────

    def _quad_center(self, q) -> tuple[float, float]:
        """Center point of a Quad in pixel coordinates."""
        return ((q.left + q.right) / 2, (q.top + q.bottom) / 2)

    def _validate_yolo_detection(self, detection: JetConeDetection | None) -> bool:
        """Check that YOLO found all required components with good geometry."""
        if detection is None:
            return False
        if detection.confidence < self.DETECT_CONFIDENCE:
            logger.debug(f"JetCone validate: confidence too low ({detection.confidence})")
            return False
        if detection.core is None:
            logger.debug("JetCone validate: missing core")
            return False
        if detection.left_jet is None or detection.right_jet is None:
            logger.debug("JetCone validate: missing jets")
            return False
        # Geometry: left and right jets on opposite sides of core
        core_cx, _ = self._quad_center(detection.core)
        lj_cx, _ = self._quad_center(detection.left_jet)
        rj_cx, _ = self._quad_center(detection.right_jet)
        if not (lj_cx < core_cx < rj_cx or rj_cx < core_cx < lj_cx):
            logger.debug("JetCone validate: jets not on opposite sides of core")
            return False
        return True

    # ── roll control ────────────────────────────────────────────────

    def _roll_to_horizontal(self, scr_reg, detection: JetConeDetection) -> bool:
        """Roll until jet axis is horizontal (±3° from 0° or 180°).

        jet_axis_angle is the screen-space angle of the LeftJet→RightJet
        vector — it MUST change after every roll so the loop converges."""
        return self._roll_to_angle(scr_reg, detection, target_angle=0.0, tol_deg=3.0)

    def _roll_to_angle(self, scr_reg, detection: JetConeDetection,
                       target_angle: float, tol_deg: float = 3.0) -> bool:
        """Closed-loop: roll until jet_axis_angle ≈ target_angle.

        Does NOT use a single blind roll — instead:
          detect → compute error → small roll correction → detect → repeat
        until the error is within tolerance.

        @param target_angle: desired jet_axis_angle (0=horizontal, 90=vertical)
        @param tol_deg: stop when |jet_axis_angle - target_angle| < tol_deg
        """
        target = target_angle % 180
        step_max = 20  # max degrees per correction step

        start = time.time()
        while time.time() - start < self.ALIGN_TIMEOUT:
            angle = detection.jet_axis_angle % 180

            error = target - angle
            # Normalise to ±90° (shortest rotation)
            if error > 90:
                error -= 180
            elif error < -90:
                error += 180

            if abs(error) < tol_deg:
                self.ap.ap_ckb('log',
                    f'Roll complete: axis={angle:.1f}° (target={target_angle}°)')
                return True

            # Small correction step
            corr = max(min(error, step_max), -step_max)
            self.ap.ship_control.roll_clockwise_anticlockwise(corr)
            sleep(0.3)

            # Re-detect
            detection = self.ap.jet_cone_ml_detect(scr_reg)
            if not self._validate_yolo_detection(detection):
                sleep(0.3)
                continue

        self.ap.ap_ckb('log', f'Roll-to-angle {target_angle}° timed out')
        return False

    # ── geometric target computation ─────────────────────────────────

    def _compute_entry_target(self, detection: JetConeDetection
                              ) -> tuple[float, float] | None:
        """Compute approach point from Core→WorkingJet vector.

        AFTER roll normalization, one jet is physically ABOVE the core
        (smaller screen Y).  We pick that jet, compute the Core→Jet vector,
        and target a point ~70% along it with a proportional lateral offset
        for grazing entry.

        Returns (x_pct, y_pct) in 0..1 full-screen coordinates,
        or None if the entry point falls outside the visible screen
        (caller should re-detect/re-orient)."""
        w = self.ap.scr.screen_width
        h = self.ap.scr.screen_height

        core_cx, core_cy = self._quad_center(detection.core)
        lj_cx, lj_cy = self._quad_center(detection.left_jet)
        rj_cx, rj_cy = self._quad_center(detection.right_jet)

        # Determine which jet is ABOVE the core (smaller Y on screen)
        if lj_cy < rj_cy:
            jet_cx, jet_cy = lj_cx, lj_cy
        else:
            jet_cx, jet_cy = rj_cx, rj_cy

        # Normalise to 0..1
        core_x, core_y = core_cx / w, core_cy / h
        jet_x, jet_y = jet_cx / w, jet_y / h

        # Core→Jet vector
        dx = jet_x - core_x
        dy = jet_y - core_y
        length = math.hypot(dx, dy)
        if length < 0.001:
            return None

        # Target at ~70% along the cone, with lateral offset proportional
        # to the vector length (so scaling is resolution-independent)
        along = 0.70
        lateral = 0.10 * length

        # Perpendicular vector (rotate 90° CCW)
        perp_x = -dy / length
        perp_y = dx / length

        entry_x = core_x + dx * along + perp_x * lateral
        entry_y = core_y + dy * along + perp_y * lateral

        # Check bounds: if entry is off-screen, the geometry is likely wrong —
        # caller should re-detect rather than clamp silently
        if not (0.0 <= entry_x <= 1.0 and 0.0 <= entry_y <= 1.0):
            logger.debug(
                f"JetCone entry target out of screen: ({entry_x:.2f}, {entry_y:.2f})")
            return None

        return (entry_x, entry_y)

    # ── approach control loop (merged align + fly + OCR) ─────────────

    def _approach_control_loop(self, scr_reg,
                                target: tuple[float, float]) -> bool:
        """Single control loop: align to target while flying forward.
        No nested inner loop — each iteration does one detect→correct step
        and one OCR check.

        Errors are computed in full-screen coordinates (scr.screen_width/
        screen_height), not relative to object bounding boxes.

        @param target: (x_pct, y_pct) 0..1 in full-screen coordinates
        """
        timeout = 45.0
        start = time.time()
        tol_pct = 0.05  # 5% of screen

        w = self.ap.scr.screen_width
        h = self.ap.scr.screen_height

        while time.time() - start < timeout:
            # ── OCR check for entry warning ──
            if self.ap.jet_cone_entry_ocr(scr_reg):
                self.ap.ap_ckb('log+vce', 'Entered jet cone — FSD charging')
                return True

            # ── overheating ──
            if self.ap.status.get_flag(FlagsOverHeating):
                self.ap.nav_service.overheat_escape(scr_reg)
                self.ap.set_throttle_50()
                continue

            # ── detect right jet position ──
            detection = self.ap.jet_cone_ml_detect(scr_reg)
            if not self._validate_yolo_detection(detection):
                sleep(0.3)
                continue

            jet_cx, jet_cy = self._quad_center(detection.right_jet)

            # Current position as fraction of FULL screen
            cur_x = jet_cx / w
            cur_y = jet_cy / h

            error_x = target[0] - cur_x
            error_y = target[1] - cur_y

            # Within tolerance → do nothing, just keep flying
            if abs(error_x) < tol_pct and abs(error_y) < tol_pct:
                sleep(0.5)
                continue

            # Convert screen error → pitch/yaw correction (proportional,
            # capped at ±10° per iteration)
            gain = 40  # ° per screen fraction
            yaw_corr = max(min(error_x * gain, 10), -10)
            pit_corr = max(min(-error_y * gain, 10), -10)

            if abs(pit_corr) > 0.5:
                self.ap.ship_control.pitch_up_down(pit_corr)
            if abs(yaw_corr) > 0.5:
                self.ap.ship_control.yaw_right_left(yaw_corr)

            sleep(0.25)

        self.ap.ap_ckb('log', 'Approach control loop timed out')
        return False

    # ── blind entry (no YOLO) ────────────────────────────────────────

    def _blind_entry(self, scr_reg) -> bool:
        """Pitch toward one pole until OCR fires the entry warning.

        After jump we face the star.  Cone extends from a pole.
        Pitch up in steps; if not found in ~15s, roll 180° and
        try the opposite pole."""
        self.ap.set_throttle_50()
        sleep(1)

        timeout = 90.0
        start = time.time()
        pole = 'up'

        while time.time() - start < timeout:
            if self.ap.status.get_flag(FlagsOverHeating):
                self.ap.nav_service.overheat_escape(scr_reg)
                self.ap.set_throttle_50()
                pole = 'down' if pole == 'up' else 'up'
                continue

            # Retry YOLO — model may have loaded
            detection = self.ap.jet_cone_ml_detect(scr_reg)
            if self._validate_yolo_detection(detection):
                return self._try_yolo_entry(scr_reg)

            deg = 8 if pole == 'up' else -8
            self.ap.ship_control.pitch_up_down(deg)
            sleep(0.4)

            if self.ap.jet_cone_entry_ocr(scr_reg):
                self.ap.ap_ckb('log+vce', 'Entered jet cone — FSD charging')
                return True

            if time.time() - start > 15 and pole == 'up':
                self.ap.ship_control.roll_clockwise_anticlockwise(180)
                sleep(1.5)
                pole = 'down'
                self.ap.set_throttle_50()
                self.ap.ap_ckb('log', 'Switching to opposite pole...')

        return False

    # ── wait for supercharge ─────────────────────────────────────────────

    def _wait_supercharged(self, scr_reg) -> bool:
        """Stay in cone until supercharged. Turbulence compensation.

        Uses ship_control for micro-corrections (no raw keys.send).
        Checks journal (fast) and OCR."""
        self.ap.update_ap_status("Charging FSD")

        timeout = 45.0
        start = time.time()

        while time.time() - start < timeout:
            if self.is_supercharged():
                return True

            if self.ap.status.get_flag(FlagsOverHeating):
                self.ap.ship_control.pitch_up_down(8)
                sleep(0.5)

            if self.ap.jet_cone_supercharged_ocr(scr_reg):
                self.ap.ap_ckb('log+vce', 'FSD supercharged!')
                self._save_yolo_training_frame(scr_reg, None)  # save on success
                return True

            # Micro-pitch to fight turbulence (ship_control, not keys.send)
            self.ap.ship_control.pitch_up_down(2)
            sleep(0.5)

        return self.is_supercharged()

    # ── exit cone ────────────────────────────────────────────────────────

    def _exit_cone(self):
        """Exit the jet cone after supercharge.

        Per requirements: first turn the ship AWAY from the cone,
        THEN apply full throttle.  Uses ship_control, not raw keys."""
        self.ap.ap_ckb('log', 'Exiting jet cone')

        # 1. Turn away first — pitch up to point away from the cone stream
        self.ap.ship_control.pitch_up_down(30)
        sleep(1.5)

        # 2. Full throttle to clear the cone trail
        self.ap.set_throttle_100()
        sleep(4)

        # 3. Level out and set course away
        self.ap.ship_control.pitch_up_down(-15)
        sleep(1)
        self.ap.set_throttle_50()
        self.ap.update_ap_status("Boost complete")

    # ── self-training ────────────────────────────────────────────────

    def _save_yolo_training_frame(self, scr_reg,
                                   detection: JetConeDetection | None) -> None:
        """Save current frame with YOLO-format labels for future fine-tuning.

        If detection is provided (YOLO-guided entry), uses the model's own
        bounding boxes as ground truth.  Otherwise falls back to HSV mask.

        Saved to Yolo26/jetcone-model/auto_labels/."""
        import os as _os
        from datetime import datetime as _dt

        auto_dir = _os.path.join("Yolo26", "jetcone-model", "auto_labels")
        _os.makedirs(auto_dir, exist_ok=True)

        full = scr_reg.capture_region_percent(self.ap.scr, 'full_panel')
        if full is None:
            return

        ts = _dt.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        img_name = f"auto_{ts}.jpg"
        img_path = _os.path.join(auto_dir, img_name)
        cv2.imwrite(img_path, full, [cv2.IMWRITE_JPEG_QUALITY, 90])

        h, w = full.shape[:2]
        label_path = img_path.replace('.jpg', '.txt')

        if detection and detection.core and detection.left_jet and detection.right_jet:
            # Use YOLO's own detection as ground-truth labels
            with open(label_path, 'w') as f:
                for cls_id, quad in [(0, detection.core),
                                      (1, detection.left_jet),
                                      (1, detection.right_jet)]:
                    cx = (quad.left + quad.right) / 2 / w
                    cy = (quad.top + quad.bottom) / 2 / h
                    nw = (quad.right - quad.left) / w
                    nh = (quad.bottom - quad.top) / h
                    f.write(f"{cls_id} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}\n")
        else:
            # Fallback: HSV-based pre-label (1 class: jetcone)
            hsv = cv2.cvtColor(full, cv2.COLOR_BGR2HSV)
            mask = cv2.inRange(hsv, (90, 20, 180), (140, 255, 255))
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if contours:
                largest = max(contours, key=cv2.contourArea)
                x, y, bw, bh = cv2.boundingRect(largest)
                if bw > 40 and bh > 40 and bw < w * 0.9:
                    cx = (x + bw / 2) / w
                    cy = (y + bh / 2) / h
                    nw = bw / w
                    nh = bh / h
                    with open(label_path, 'w') as f:
                        f.write(f"1 {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}\n")

        self.ap.ap_ckb('log', f'Training frame saved: {img_name}')
