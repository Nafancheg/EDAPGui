from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime
from time import sleep

import cv2

from EDAP_data import *
from EDFSS import EDFSS
from EDlogger import logger
from Screen import set_focus_elite_window


class ElwAdvisor:
    """ Earth-like/Water/Ammonia world scan advisor: FSS spectral detection + journal-driven
    per-body verdicts + EDSM online lookup. Extracted from ED_AP. """

    def __init__(self, ed_ap):
        self.ap = ed_ap
        self._fss_screen = None

    @property
    def fss_screen(self) -> EDFSS:
        """ Load FSS class when needed. """
        if not self._fss_screen:
            self._fss_screen = EDFSS(self.ap, self.ap.ap_ckb)
        return self._fss_screen

    @staticmethod
    def _body_is_valuable(e) -> bool:
        """ Whether a scanned body is worth the player's attention (text advisory). """
        return (e.get('PlanetClass') in ('Earthlike body', 'Water world', 'Ammonia world')
                or e.get('TerraformState') == 'Terraformable'
                or e.get('bio_signals', 0) > 0 or e.get('geo_signals', 0) > 0)

    def _announce_body(self, e, system: str):
        """ Log a text verdict for a body that just resolved in the FSS. No voice. """
        short = e['BodyName'].removeprefix(system).strip() or e['BodyName']
        cls_map = {'Earthlike body': self.ap.locale_safe('ELW_TYPE_EARTH', 'Earth-like world'),
                   'Water world': self.ap.locale_safe('ELW_TYPE_WATER', 'Water world'),
                   'Ammonia world': self.ap.locale_safe('ELW_TYPE_AMMONIA', 'Ammonia world')}
        cls = cls_map.get(e['PlanetClass'], e['PlanetClass'] or 'body')

        if not self._body_is_valuable(e):
            return

        parts = [cls]
        if e.get('TerraformState') == 'Terraformable':
            parts.append(self.ap.locale_safe('FSS_TERRAFORMABLE', 'terraformable'))
        if e.get('bio_signals', 0):
            parts.append(self.ap.locale_safe('FSS_BIO', '{count} bio').format(count=e['bio_signals']))
        if e.get('geo_signals', 0):
            parts.append(self.ap.locale_safe('FSS_GEO', '{count} geo').format(count=e['geo_signals']))

        if not e.get('WasDiscovered', True):
            status = self.ap.locale_safe('FSS_FIRST_DISCOVERY', 'First discovery!')
            marker = '[1st!]'
        elif not e.get('WasMapped', True):
            status = self.ap.locale_safe('FSS_MAPPING_BONUS', 'Discovered, not mapped - mapping bonus.')
            marker = '[map$]'
        else:
            status = self.ap.locale_safe('FSS_KNOWN_BODY', 'Already discovered and mapped - skip.')
            marker = '[known]'

        self.ap.ap_ckb('log', f"{short}: {', '.join(parts)}. {status}")
        self.ap._fss_valuables.append((short, f"{', '.join(parts)} {marker}"))
        self.ap.update_overlay()

    def poll_body_scans(self):
        """ FSS scan advisor: watch the journal for bodies resolved in the FSS and report
        (text only) whether they are valuable and already discovered/mapped. Called ~1x/sec
        from the engine loop; inert unless Scan/FSS events appear in the journal. """
        ship = self.ap.jn.ship_state()
        bodies = ship.get('scanned_bodies') or {}
        system = ship.get('cur_star_system') or ''

        # First poll after startup: the whole journal file was replayed - seed silently
        if self.ap._fss_announced is None:
            self.ap._fss_announced = set(bodies.keys())
            self.ap._fss_honk_announced = ship.get('fss_honk_done', False)
            self.ap._fss_allfound_announced = ship.get('fss_all_found', False)
            self.ap._fss_last_system = system
            return

        if system != self.ap._fss_last_system:
            # Safety net in addition to the journal FSDJump reset
            self.ap._fss_last_system = system
            self.ap._fss_announced.clear()
            self.ap._fss_pending.clear()
            self.ap._fss_valuables = []
            self.ap._fss_honk_announced = False
            self.ap._fss_allfound_announced = False

        if ship.get('fss_honk_done') and not self.ap._fss_honk_announced:
            self.ap._fss_honk_announced = True
            if ship.get('fss_progress', 0.0) >= 1.0:
                self.ap.ap_ckb('log', self.ap.locale_safe(
                    'FSS_HONK_NOTHING', 'Discovery scan: nothing left to find here.'))
            else:
                self.ap.ap_ckb('log', self.ap.locale_safe(
                    'FSS_HONK_BODIES', 'Discovery scan: {count} bodies in system.').format(
                    count=ship.get('fss_body_count', 0)))

        # Per-body verdicts with a 1-poll delay so a lagging FSSBodySignals event
        # can merge with its Scan before the verdict is printed
        for name, e in bodies.items():
            if name in self.ap._fss_announced or not e.get('has_scan'):
                continue
            if e.get('is_star'):
                self.ap._fss_announced.add(name)  # stars count for progress, no report
                continue
            if name not in self.ap._fss_pending:
                self.ap._fss_pending.add(name)
                continue
            self.ap._fss_pending.discard(name)
            self.ap._fss_announced.add(name)
            self._announce_body(e, system)

        if ship.get('fss_all_found') and not self.ap._fss_allfound_announced:
            self.ap._fss_allfound_announced = True
            n_val = sum(1 for e in bodies.values()
                        if e.get('has_scan') and self._body_is_valuable(e))
            self.ap.ap_ckb('log', self.ap.locale_safe(
                'FSS_ALL_FOUND', 'System scan complete. {valuable} valuable bodies.').format(
                valuable=n_val))

    def edsm_check_system(self, system_name: str):
        """ Query EDSM online to see if the system is already discovered and what notable
        bodies it contains. Intended to run in a background thread after each jump;
        the result is stored in self.edsm_info and shown in the overlay. """
        if not system_name:
            return
        try:
            url = 'https://www.edsm.net/api-system-v1/bodies?systemName=' + urllib.parse.quote(system_name)
            req = urllib.request.Request(url, headers={'User-Agent': 'EDAPGui'})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            logger.warning(f'EDSM query failed for {system_name}: {e}')
            self.ap.edsm_info = self.ap.locale_safe('EDSM_QUERY_FAILED', 'EDSM: query failed')
            return

        # EDSM returns an empty response for systems it does not know about
        if not data or not data.get('bodies'):
            self.ap.edsm_undiscovered = True
            self.ap.edsm_info = self.ap.locale_safe('EDSM_NOT_IN_DB', 'EDSM: NOT IN DATABASE - possibly undiscovered!')
            self.ap.ap_ckb('log+vce', self.ap.locale_safe(
                'EDSM_NOT_IN_DB_VOICE', '{system} is not in EDSM. Possibly undiscovered system!').format(system=system_name))
            self.ap.update_overlay()
            return

        bodies = data['bodies']
        body_count = data.get('bodyCount')

        # Who discovered the main star and when
        disc = ''
        for b in bodies:
            if b.get('isMainStar'):
                d = b.get('discovery')
                if d:
                    disc = f", {self.ap.locale_safe('EDSM_DISC_BY', 'disc.by')} {d.get('commander', '?')}"
                break

        # Count the notable bodies
        elw = sum(1 for b in bodies if b.get('subType') == 'Earth-like world')
        ww = sum(1 for b in bodies if b.get('subType') == 'Water world')
        aw = sum(1 for b in bodies if b.get('subType') == 'Ammonia world')
        terra = sum(1 for b in bodies if b.get('terraformingState') == 'Candidate for terraforming')

        notable = ''
        if elw:
            notable += f' ELW:{elw}'
        if ww:
            notable += f' WW:{ww}'
        if aw:
            notable += f' AW:{aw}'
        if terra:
            notable += f' Terra:{terra}'

        # Per-body details for valuable bodies: who discovered them and when
        for b in bodies:
            sub = b.get('subType')
            b_terra = b.get('terraformingState') == 'Candidate for terraforming'
            if sub in ('Earth-like world', 'Water world', 'Ammonia world') or b_terra:
                d = b.get('discovery') or {}
                when = (d.get('date') or '')[:10]
                terra_mark = ' (terra)' if b_terra else ''
                self.ap.ap_ckb('log', f"  {b.get('name')}: {sub}{terra_mark}"
                                   f" - {d.get('commander', '?')} {when}")

        # Check if the system is only partially explored
        partial = ''
        if body_count is not None:
            if body_count <= len(bodies):
                partial = f' ({self.ap.locale_safe("EDSM_FULLY_KNOWN", "fully known")})'
            else:
                unknown_cnt = body_count - len(bodies)
                partial = f' ({unknown_cnt} {self.ap.locale_safe("EDSM_UNKNOWN", "unknown")})'
                self.ap.ap_ckb('log', self.ap.locale_safe(
                    'EDSM_UNKNOWN_BODIES', '{count} bodies unknown to EDSM.').format(count=unknown_cnt))

        self.ap.edsm_undiscovered = False
        bodies_word = self.ap.locale_safe('EDSM_BODIES', 'bodies')
        self.ap.edsm_info = f'EDSM: {len(bodies)} {bodies_word}{partial}{disc}{notable}'
        if elw or ww or aw:
            self.ap.ap_ckb('log+vce', self.ap.locale_safe(
                'EDSM_NOTABLE_VOICE', '{system} has notable bodies:').format(system=system_name) + notable)
        else:
            self.ap.ap_ckb('log', f'EDSM {system_name}: {len(bodies)} {bodies_word}{partial}{disc}')
        self.ap.update_overlay()

    def fss_detect_elw(self, scr_reg, restore_throttle: bool = True) -> bool:
        """ Go into FSS, check to see if we have a signal waveform in the Earth, Water or Ammonia zone
        if so, announce finding and log the type of world found.
        @param restore_throttle: Set throttle back to 100% when done. Pass False when the ship
            must stay stopped (e.g. scanning during the fuel scooping stop).
        @return: True if the scan was performed, False if the FSS did not open. """
        from ED_AP import get_timestamped_filename

        # open fss
        self.ap.ap_ckb('log+vce', self.ap.locale_safe('ELW_SCANNING', 'Scanning FSS spectrum'))
        self.ap.set_throttle_0()
        sleep(0.1)
        self.ap.keys.send('ExplorationFSSEnter')
        sleep(float(self.ap.config['Wait_FSSDetect']))

        # Verify the FSS actually opened, otherwise we would be template matching on the cockpit view
        # which produces false detections.
        if self.ap.status.get_gui_focus() != GuiFocusFSS:
            logger.warning('fss_detect_elw: FSS did not open, skipping ELW detection')
            self.ap.fss_detected = self.ap.locale_safe('ELW_FSS_NOT_OPEN', 'FSS did not open')
            if restore_throttle:
                self.ap.set_throttle_100()
            return False

        # Capture the calibrated Water/Earth-like/Ammonia segment of the spectral bar
        # (EDFSS -> subregion 'elw_zones', calibratable in the Calibration tab).
        region = self.fss_screen.reg['elw_zones']
        img = self.ap.ocr.capture_region_pct(region)
        if img.shape[2] == 4:
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

        # Log screenshot of the actual detection segment for diagnostics/calibration
        f = get_timestamped_filename(f'[fss_detect_elw] {self.ap.jn.ship_state()["cur_star_system"]}', '', 'png')
        cv2.imwrite(f'{self.ap.debug_image_folder}/{f}', img)

        # Look for the signal waveform in this segment
        elw_image = scr_reg.equalize(img)
        elw_sig_image, (minVal1, maxVal1, minLoc1, maxLoc1), match = scr_reg.match_template_in_image(elw_image, 'elw_sig')

        # Classify by the match center. The segment covers exactly the three zones,
        # in bar order (left to right): Earth-like, Ammonia, Water
        # (per the community FSS spectral analysis diagram: ...Rocky Ice | ELW | AW | WW | Gas Giants).
        strip_height, strip_width = elw_image.shape[:2]
        sig_w = scr_reg.templates.template['elw_sig']['width']
        match_x = maxLoc1[0] + sig_w / 2
        wid_div3 = strip_width / 3

        # Exit out of FSS, we got the images we need to process
        self.ap.keys.send('ExplorationFSSQuit')

        # Uncomment this to show on the ED Window where the region is define.  Must run this file as an App, so uncomment out
        # the main at the bottom of file
        # self.ap.overlay.overlay_rect('fss', (scr_reg.reg['fss']['rect'][0], scr_reg.reg['fss']['rect'][1]),
        #                (scr_reg.reg['fss']['rect'][2],  scr_reg.reg['fss']['rect'][3]), (120, 255, 0),2)
        # self.ap.overlay.overlay_paint()

        if self.ap.cv_view:
            elw_image_d = elw_image.copy()
            elw_image_d = cv2.cvtColor(elw_image_d, cv2.COLOR_GRAY2RGB)
            # self.ap.draw_match_rect(elw_image_d, maxLoc, (maxLoc[0]+15,maxLoc[1]+15), (255,255,255), 1)
            self.ap.draw_match_rect(elw_image_d, maxLoc1, (maxLoc1[0]+15, maxLoc1[1]+25), (0, 0, 255), 1)
            cv2.putText(elw_image_d, f'{maxVal1:5.2f}> .70', (1, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.30, (255, 255, 255), 1, cv2.LINE_AA)
            cv2.imshow('fss', elw_image_d)
            cv2.moveWindow('fss', self.ap.cv_view_x, self.ap.cv_view_y+100)
            cv2.waitKey(30)

        logger.info("elw sig:{0:6.2f} at x:{1} of {2}".format(maxVal1, int(match_x), strip_width))

        # Check the signal meets the probability number and sits in the waveform area
        # (upper half of the segment, above the ruler), then classify by zone third.
        if maxVal1 > 0.70 and maxLoc1[1] < strip_height * 0.5:
            if match_x < wid_div3:
                sstr = "Earth"
            elif match_x > (wid_div3*2):
                sstr = "Water"
            else:
                sstr = "Ammonia"
            # log the entry into the elw.txt file
            f = open("elw.txt", 'a')
            f.write(self.ap.jn.ship_state()["location"]+", Type: "+sstr +
                    ", Probabilty: {0:3.0f}% ".format((maxVal1*100)) +
                    ", MatchX: "+str(int(match_x))+"/"+str(strip_width) +
                    ", Date: "+str(datetime.now())+str("\n"))
            f.close()
            type_names = {'Earth': self.ap.locale_safe('ELW_TYPE_EARTH', 'Earth-like world'),
                          'Water': self.ap.locale_safe('ELW_TYPE_WATER', 'Water world'),
                          'Ammonia': self.ap.locale_safe('ELW_TYPE_AMMONIA', 'Ammonia world')}
            detected_msg = self.ap.locale_safe('ELW_DETECTED_MSG', '{type} detected').format(type=type_names[sstr])
            self.ap.vce.say(detected_msg)
            self.ap.fss_detected = detected_msg
            logger.info(sstr+" world at: "+str(self.ap.jn.ship_state()["location"]))
        else:
            self.ap.fss_detected = self.ap.locale_safe('ELW_NOTHING_FOUND', 'nothing found')

        if restore_throttle:
            self.ap.set_throttle_100()

        return True

    def test_fss_scan(self):
        """ Manual FSS/ELW scan test (mini panel button): stop the ship, open the FSS,
        run the detection and report the verdict. Leaves the ship stopped. """
        set_focus_elite_window()
        sleep(0.25)
        res = self.fss_detect_elw(self.ap.scrReg, restore_throttle=False)
        if not res:
            self.ap.ap_ckb('log+vce', self.ap.locale_safe('ELW_FSS_NOT_OPEN', 'FSS did not open'))
        else:
            verdict = self.ap.fss_detected
            self.ap.ap_ckb('log', f"FSS test: {verdict}")
            # A successful detection has already been announced by the scan itself
            if verdict == self.ap.locale_safe('ELW_NOTHING_FOUND', 'nothing found'):
                self.ap.vce.say(verdict)
        self.ap.update_overlay()
