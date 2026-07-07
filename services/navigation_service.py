from __future__ import annotations

import math
import time
from copy import copy
from math import atan, degrees, tan, radians
from time import sleep
from typing import TYPE_CHECKING

import cv2

from EDAP_data import *
from EDShipControl import CompassTargetOffset
from EDlogger import logger
from MachineLearning import ModelType
from Screen_Regions import Quad

if TYPE_CHECKING:
    from ED_AP import ScTargetAlignReturn, TargetOffset, CompassOffset


class NavigationService:
    """ Navigation / alignment logic extracted from ED_AP. """

    def __init__(self, ed_ap):
        self.ap = ed_ap

    def interdiction_check(self) -> bool:
        """ Checks if we are being interdicted. This can occur in SC and maybe in system jump by Thargoids
        (needs to be verified). Returns False if not interdicted, True after interdiction is detected and we
        get away. Use return result to determine the next action (continue, or do something else).
        """
        # Return if we are not being interdicted.
        if not self.ap.status.get_flag(FlagsBeingInterdicted):
            return False

        # Interdiction detected.
        self.ap.vce.say("Danger. Interdiction detected.")
        self.ap.ap_ckb('log', 'Interdiction detected.')

        # Keep setting speed to zero to submit while in supercruise or system jump.
        while self.ap.status.get_flag(FlagsSupercruise) or self.ap.status.get_flag2(Flags2FsdHyperdriveCharging):
            self.ap.set_throttle_0()  # Submit.
            sleep(0.5)

        # Set speed to 100%.
        self.ap.set_throttle_100()

        # Wait for cooldown to start.
        self.ap.status.wait_for_flag_on(FlagsFsdCooldown)

        # Boost while waiting for cooldown to complete.
        while not self.ap.status.wait_for_flag_off(FlagsFsdCooldown, timeout=1):
            self.ap.keys.send('UseBoostJuice')

        # Ensure we are in supercruise
        self.ap.sc_engage(True)

        # Update journal flag.
        self.ap.jn.ship_state()['interdicted'] = False  # reset flag
        return True

    def get_nav_offset(self, scr_reg) -> CompassOffset | None:
        """ Determine the x,y offset from center of the compass of the nav point.
        @return: Returns the x,y,z value as x,y in degrees (-90 to 90) and z as 1 or -1.
        {'x': x.xx, 'y': y.yy, 'z': -1.0|0.0|+1.0,'roll': r.rr, 'pit': p.pp, 'yaw': y.yy} | None
        Where 'roll' is:
           -180deg (6 o'clock anticlockwise) to
            0deg (12 o'clock) to
            180deg (6 o'clock clockwise)
        """
        from ED_AP import get_timestamped_filename

        full_compass_image = None
        # full_compass_image = scr_reg.capture_region(self.ap.scr, 'compass', inv_col=False)
        full_compass_image = scr_reg.capture_region_percent(self.ap.scr, 'compass')

        # ML test
        max_val = 0.0
        compass_quad = Quad()
        # pt = [0.0, 0.0]
        n_max_val = 0.0
        n_compass_quad = Quad()
        # n_pt = [0.0, 0.0]
        b_max_val = 0.0
        b_compass_quad = Quad()
        # b_pt = [0.0, 0.0]
        full_compass_image2 = cv2.cvtColor(full_compass_image, cv2.COLOR_BGRA2BGR)
        ml_res = self.ap.mach_learn.model_predict(ModelType.Compass, full_compass_image2, '')
        if ml_res and len(ml_res) > 0:
            for ml in ml_res:
                if ml.class_name == 'compass':
                    max_val = ml.match_pct
                    compass_quad = ml.bounding_quad
                    # pt = [compass_quad.left, compass_quad.top]
                if ml.class_name == 'navpoint':
                    n_max_val = ml.match_pct
                    n_compass_quad = ml.bounding_quad
                    # n_pt = [n_compass_quad.left, n_compass_quad.top]
                if ml.class_name == 'navpoint-behind':
                    b_max_val = ml.match_pct
                    b_compass_quad = ml.bounding_quad
                    # b_pt = [b_compass_quad.left, b_compass_quad.top]

        # Check compass
        if max_val == 0.0:
            # Log screenshot for diagnostics/training
            if self.ap.debug_images:
                f = get_timestamped_filename('[get_nav_offset] no_compass_match', '', 'png')
                cv2.imwrite(f'{self.ap.debug_image_folder}/{f}', full_compass_image2)
            return None
        # Check navpoint
        if n_max_val == 0.0 and b_max_val == 0.0:
            # Log screenshot for diagnostics/training
            if self.ap.debug_images:
                f = get_timestamped_filename('[get_nav_offset] no_navpoint_match', '', 'png')
                cv2.imwrite(f'{self.ap.debug_image_folder}/{f}', full_compass_image2)
            return None

        # Check if the Nav Point is visible. If not, the Nav Point Behind may be visible
        if n_max_val > b_max_val:
            final_z_pct = 1.0  # Ahead
            n_compass_quad = n_compass_quad
        else:
            final_z_pct = -1.0  # Behind
            n_compass_quad = b_compass_quad

        # get wid/hgt of templates
        # c_left = scr_reg.reg['compass']['rect'][0]
        # c_top = scr_reg.reg['compass']['rect'][1]
        compass_region = Quad.from_rect(scr_reg.reg['compass']['rect'])
        # wid = scr_reg.templates.template['navpoint']['width']
        # hgt = scr_reg.templates.template['navpoint']['height']

        # cut out the compass from the region
        # pad = 5
        # compass_image = Screen.crop_image_pix(full_compass_image, compass_quad)

        # find the nav point within the compass box
        # navpt_image, (n_minVal, n_maxVal, n_minLoc, n_maxLoc), match = scr_reg.match_template_in_image_x3(compass_image, 'navpoint')
        # navpt_image_beh, (n_minVal, n_maxVal_beh, n_minLoc, n_maxLoc_beh), match_beh = scr_reg.match_template_in_image_x3(compass_image, 'navpoint-behind')

        # n_pt = n_maxLoc
        # n_pt_beh = n_maxLoc_beh

        # compass_x_min = 0
        # compass_x_max = compass_quad.get_width() - n_compass_quad.get_width()
        # compass_y_min = 0
        # compass_y_max = compass_quad.get_height() - n_compass_quad.get_height()

        # Check if the Nav Point is visible. If not, the Nav Point Behind may be visible
        # if n_maxVal > scr_reg.navpoint_match_thresh:
        #     final_z_pct = 1.0  # Ahead
        #     n_pt = n_maxLoc
        # else:
        #     final_z_pct = -1.0  # Behind
        #     n_pt = n_maxLoc_beh

        # Continue calc
        final_x_pct = 2*(((n_compass_quad.left-compass_quad.left) / (compass_quad.width - n_compass_quad.width)) - 0.5)  # X as percent (-1.0 to 1.0, 0.0 in the center)
        # final_x_pct = final_x_pct - self._nav_cor_x
        final_x_pct = max(min(final_x_pct, 1.0), -1.0)

        final_y_pct = -2*(((n_compass_quad.top-compass_quad.top) / (compass_quad.height - n_compass_quad.height)) - 0.5)  # Y as percent (-1.0 to 1.0, 0.0 in the center)
        # final_y_pct = final_y_pct - self._nav_cor_y
        final_y_pct = max(min(final_y_pct, 1.0), -1.0)

        # Calc angle in degrees starting at 0 deg at 12 o'clock and increasing clockwise
        # so 3 o'clock is +90° and 9 o'clock is -90°.
        final_roll_deg = 0.0
        if final_x_pct > 0.0:
            final_roll_deg = 90 - degrees(atan(final_y_pct/final_x_pct))
        elif final_x_pct < 0.0:
            final_roll_deg = -90 - degrees(atan(final_y_pct/final_x_pct))
        elif final_y_pct < 0.0:
            final_roll_deg = 180.0

        # 'longitudinal' radius of compass at given 'latitude'
        lng_rad_at_lat = math.cos(math.asin(final_y_pct))
        lng_rad_at_lat = max(lng_rad_at_lat, 0.001)  # Prevent div by zero

        # 'Latitudinal' radius of compass at given 'longitude'
        lat_rad_at_lng = math.sin(math.acos(final_x_pct))
        lat_rad_at_lng = max(lat_rad_at_lng, 0.001)  # Prevent div by zero

        # Pitch and yaw as a % of the max as defined by the compass circle
        pit_pct = max(min(final_y_pct/lat_rad_at_lng, 1.0), -1.0)
        yaw_pct = max(min(final_x_pct/lng_rad_at_lat, 1.0), -1.0)

        if final_z_pct > 0:
            final_pit_deg = (-1 * degrees(math.acos(pit_pct))) + 90  # Y in deg (-90.0 to 90.0, 0.0 in the center)
            final_yaw_deg = (-1 * degrees(math.acos(yaw_pct))) + 90  # X in deg (-90.0 to 90.0, 0.0 in the center)
        else:
            if final_y_pct > 0:
                final_pit_deg = degrees(math.acos(pit_pct)) + 90  # Y in deg (-90.0 to 90.0, 0.0 in the center)
            else:
                final_pit_deg = degrees(math.acos(pit_pct)) - 270  # Y in deg (-90.0 to 90.0, 0.0 in the center)

            if final_x_pct > 0:
                final_yaw_deg = degrees(math.acos(yaw_pct)) + 90  # X in deg (-90.0 to 90.0, 0.0 in the center)
            else:
                final_yaw_deg = degrees(math.acos(yaw_pct)) - 270  # X in deg (-90.0 to 90.0, 0.0 in the center)

        result = {'x': round(final_x_pct, 4), 'y': round(final_y_pct, 4), 'z': round(final_z_pct, 2),
                  'roll': round(final_roll_deg, 2), 'pit': round(final_pit_deg, 2), 'yaw': round(final_yaw_deg, 2)}

        # Draw box around region
        if self.ap.debug_overlay:
            border = 10  # border to prevent the box from interfering with future matches
            # left = c_left + compass_quad.left
            # top = c_top + compass_quad.top
            # Copy compass quad and offset to screen co-ords
            compass_to_screen = copy(compass_quad)
            compass_to_screen.offset(compass_region.left, compass_region.top)
            compass_with_border = copy(compass_to_screen)
            compass_with_border.inflate(border, border)
            nav_to_screen = copy(n_compass_quad)
            nav_to_screen.offset(compass_region.left, compass_region.top)

            self.ap.overlay.overlay_rect('compass', (compass_with_border.left, compass_with_border.top), (compass_with_border.right, compass_with_border.bottom), (0, 255, 0), 2)
            self.ap.overlay.overlay_rect('nav', (nav_to_screen.left, nav_to_screen.top), (nav_to_screen.right, nav_to_screen.bottom), (0, 255, 0), 2)
            self.ap.overlay.overlay_floating_text('compass', f'Com: {max_val:5.2f} > {scr_reg.compass_match_thresh}', compass_with_border.left, compass_with_border.top - 85, (0, 255, 0))
            self.ap.overlay.overlay_floating_text('nav', f'Nav: {n_max_val:5.2f} > {scr_reg.navpoint_match_thresh}', compass_with_border.left, compass_with_border.top - 65, (0, 255, 0))
            self.ap.overlay.overlay_floating_text('nav_beh', f'NavB: {b_max_val:5.2f}', compass_with_border.left, compass_with_border.top - 45, (0, 255, 0))
            self.ap.overlay.overlay_floating_text('compass_rpy', f'r: {round(final_roll_deg, 2)} p: {round(final_pit_deg, 2)} y: {round(final_yaw_deg, 2)}', compass_with_border.left, compass_with_border.bottom, (0, 255, 0))
            self.ap.overlay.overlay_paint()

        if self.ap.cv_view:
            # icompass_image_d = cv2.cvtColor(compass_image_gray, cv2.COLOR_GRAY2RGB)
            icompass_image_d = full_compass_image
            self.ap.draw_match_rect(icompass_image_d, (compass_quad.left, compass_quad.top), (compass_quad.right, compass_quad.bottom), (0, 0, 255), 2)
            # cv2.rectangle(icompass_image_display, pt, (pt[0]+c_wid, pt[1]+c_hgt), (0, 0, 255), 2)
            # self.draw_match_rect(compass_image, n_pt, (n_pt[0] + wid, n_pt[1] + hgt), (255,255,255), 2)
            self.ap.draw_match_rect(icompass_image_d, (n_compass_quad.left, n_compass_quad.top), (n_compass_quad.right, n_compass_quad.bottom), (0, 255, 0), 1)
            # cv2.rectangle(icompass_image_display, (pt[0]+n_pt[0]-pad, pt[1]+n_pt[1]-pad), (pt[0]+n_pt[0] + wid-pad, pt[1]+n_pt[1] + hgt-pad), (0, 0, 255), 2)

            #   dim = (int(destination_width/3), int(destination_height/3))

            #   img = cv2.resize(dst_image, dim, interpolation =cv2.INTER_AREA)
            icompass_image_d = cv2.rectangle(icompass_image_d, (0, 0), (1000, 60), (0, 0, 0), -1)
            cv2.putText(icompass_image_d, f'Compass: {max_val:5.4f} > {scr_reg.compass_match_thresh:5.2f}', (1, 10), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1, cv2.LINE_AA)
            cv2.putText(icompass_image_d, f'Nav Point: {n_max_val:5.4f} > {scr_reg.navpoint_match_thresh:5.2f}', (1, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1, cv2.LINE_AA)
            # cv2.putText(icompass_image_d, f'Result: {result}', (1, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1, cv2.LINE_AA)
            cv2.putText(icompass_image_d, f'x: {final_x_pct:5.2f} y: {final_y_pct:5.2f} z: {final_z_pct:5.2f}', (1, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1, cv2.LINE_AA)
            cv2.putText(icompass_image_d, f'r: {final_roll_deg:5.2f}deg p: {final_pit_deg:5.2f}deg y: {final_yaw_deg:5.2f}deg', (1, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1, cv2.LINE_AA)
            cv2.imshow('compass', icompass_image_d)
            cv2.moveWindow('compass', self.ap.cv_view_x - 400, self.ap.cv_view_y + 600)
            cv2.waitKey(30)

        return result

    def get_target_offset(self, scr_reg, disable_auto_cal: bool = False) -> TargetOffset | None:
        """ Determine how far off we are from the target being in the middle of the screen
        (in this case the specified region).
        @return: {'roll': r.rr, 'pit': p.pp, 'yaw': y.yy, 'occ': True|False}, where all are in degrees
            Where 'roll' is:
            -180deg (6 o'clock anticlockwise) to
             0deg (12 o'clock) to
             180deg (6 o'clock clockwise)
            'occ' is True if the target is occluded, else False
        """
        from ED_AP import get_timestamped_filename

        # Clear the overlays before grabbing image
        # if self.debug_overlay:
        #     self.overlay.overlay_remove_rect('target')
        #     self.overlay.overlay_remove_floating_text('target')
        #     self.overlay.overlay_remove_floating_text('target_rpy')
        #     self.overlay.overlay_paint()

        # dst_image_unfiltered = scr_reg.capture_region(self.scr, 'target', inv_col=False)
        dst_image_unfiltered = scr_reg.capture_region_percent(self.ap.scr, 'target')

        # ML test
        max_val = 0.0
        maxVal_occ = 0.0
        target_quad = Quad()
        sel_pt = [0.0, 0.0]
        pt = [0.0, 0.0]
        pt_occ = [0.0, 0.0]
        target_occ_quad = Quad()
        target_image2 = cv2.cvtColor(dst_image_unfiltered, cv2.COLOR_BGRA2BGR)
        ml_res = self.ap.mach_learn.model_predict(ModelType.Target, target_image2, '')
        if ml_res and len(ml_res) > 0:
            for ml in ml_res:
                if ml.class_name == 'target':
                    max_val = ml.match_pct
                    target_quad = ml.bounding_quad
                    pt = [target_quad.left, target_quad.top]
                if ml.class_name == 'target-occluded':
                    maxVal_occ = ml.match_pct
                    target_occ_quad = ml.bounding_quad
                    pt_occ = [target_occ_quad.left, target_occ_quad.top]

        dst_image = target_image2

        # Check if target is occluded
        tar_quad = Quad()
        occluded = False
        if max_val > 0.0 or maxVal_occ > 0.0:
            if max_val >= maxVal_occ:
                sel_pt = pt
                sel_loc = pt
                tar_quad = target_quad
                occluded = False
            elif maxVal_occ > max_val:
                sel_pt = pt_occ
                sel_loc = pt_occ
                tar_quad = target_occ_quad
                occluded = True
        else:
            if self.ap.debug_images:
                f = get_timestamped_filename('[get_target_offset] no_target_match', '', 'png')
                cv2.imwrite(f'{self.ap.debug_image_folder}/{f}', dst_image_unfiltered)
            return None

        target_region = Quad.from_rect(scr_reg.reg['target']['rect'])
        # destination_left = scr_reg.reg['target']['rect'][0]
        # destination_top = scr_reg.reg['target']['rect'][1]
        # destination_width = scr_reg.reg['target']['width']
        # destination_height = scr_reg.reg['target']['height']

        # width = scr_reg.templates.template['target']['width']
        # height = scr_reg.templates.template['target']['height']

        target_x_max = self.ap.scr.screen_width - tar_quad.width
        target_y_max = self.ap.scr.screen_height - tar_quad.height

        # X as percent (-1.0 to 1.0, 0.0 in the center)
        final_x_pct = 2.0*(((tar_quad.left+target_region.left) / target_x_max) - 0.5)
        final_x_pct = 100 * max(min(final_x_pct, 1.0), -1.0)

        # Y as percent (-1.0 to 1.0, 0.0 in the center)
        final_y_pct = -2.0*(((tar_quad.top+target_region.top) / target_y_max) - 0.5)
        final_y_pct = 100 * max(min(final_y_pct, 1.0), -1.0)

        final_yaw_deg = final_x_pct / 100 * (self.ap.hor_fov / 2)  # X in deg (-90.0 to 90.0, 0.0 in the center)
        final_pit_deg = final_y_pct / 100 * (self.ap.ver_fov / 2)  # Y in deg (-90.0 to 90.0, 0.0 in the center)

        # Calc angle in degrees starting at 0 deg at 12 o'clock and increasing clockwise
        # so 3 o'clock is +90° and 9 o'clock is -90°.
        final_roll_deg = 0.0
        if final_x_pct > 0.0:
            final_roll_deg = 90 - degrees(atan(radians(final_pit_deg)/radians(final_yaw_deg)))
        elif final_x_pct < 0.0:
            final_roll_deg = -90 - degrees(atan(radians(final_pit_deg)/radians(final_yaw_deg)))
        elif final_y_pct < 0.0:
            final_roll_deg = 180.0

        # Draw box around region
        if self.ap.debug_overlay:
            border = 10  # border to prevent the box from interfering with future matches
            # Copy compass quad and offset to screen co-ords
            target_to_screen = copy(tar_quad)
            target_to_screen.offset(target_region.left, target_region.top)
            target_with_border = copy(target_to_screen)
            target_with_border.inflate(border, border)

            self.ap.overlay.overlay_rect('target', (target_with_border.left, target_with_border.top), (target_with_border.right, target_with_border.bottom), (0, 255, 0), 2)
            self.ap.overlay.overlay_floating_text('target', f'Tar: {max_val:5.2f} > {scr_reg.target_thresh}', target_with_border.left, target_with_border.top - 45, (0, 255, 0))
            self.ap.overlay.overlay_floating_text('target_occ', f'TarOcc: {maxVal_occ:5.2f} > {scr_reg.target_occluded_thresh}', target_with_border.left, target_with_border.top - 25, (0, 255, 0))
            self.ap.overlay.overlay_floating_text('target_rpy', f'r: {round(final_roll_deg, 2)} p: {round(final_pit_deg, 2)} y: {round(final_yaw_deg, 2)}', target_with_border.left, target_with_border.top , (0, 255, 0))
            self.ap.overlay.overlay_paint()

        if self.ap.cv_view:
            try:
                self.ap.draw_match_rect(dst_image, sel_pt, (sel_pt[0]+tar_quad.width, sel_pt[1]+tar_quad.height), (0, 0, 255), 2)
                dim = (int(target_region.width/2), int(target_region.height/2))

                img = cv2.resize(dst_image, dim, interpolation=cv2.INTER_AREA)
                img = cv2.rectangle(img, (0, 0), (1000, 25), (0, 0, 0), -1)
                cv2.putText(img, f'{max_val:5.4f} > {scr_reg.target_thresh:5.2f}', (1, 10), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1, cv2.LINE_AA)
                cv2.putText(img, f'p: {round(final_pit_deg, 4)} y: {round(final_yaw_deg, 4)}',
                            (1, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1, cv2.LINE_AA)
                cv2.imshow('target', img)
                #cv2.moveWindow('target', self.cv_view_x, self.cv_view_y+425)
            except Exception as e:
                print("exception in getdest: "+str(e))
            cv2.waitKey(30)

        # must be > x to have solid hit, otherwise we are facing wrong way (empty circle)
        # Added max_val ==0 as ML gives any match > 0
        # if max_val == 0 and max_val < scr_reg.target_thresh and maxVal_occ < scr_reg.target_occluded_thresh:
        if max_val > 0.0 or maxVal_occ > 0.0:
            result = {'roll': round(final_roll_deg, 2), 'pit': round(final_pit_deg, 2), 'yaw': round(final_yaw_deg, 2), 'occ': occluded}
        else:
            if self.ap.debug_images:
                f = get_timestamped_filename('[get_target_offset] no_target_match', '', 'png')
                cv2.imwrite(f'{self.ap.debug_image_folder}/{f}', dst_image_unfiltered)
            result = None

        return result

    def get_compass_target_offset(self) -> CompassTargetOffset | None:
        """
        Gets the Navigation and Target offsets and determines the best match between the two.
        @return: A TypedDict representing the compass and/or target information.
        """
        # Check Target and Compass
        nav_off1 = self.get_nav_offset(self.ap.scrReg)
        tar_off1 = self.get_target_offset(self.ap.scrReg)
        if nav_off1 and not tar_off1:
            # Compass detected and not target
            # Try to use the compass data if the target is not visible.
            # self.ap_ckb('log', 'Found Compass only for destination offset.')

            behind = nav_off1['z'] < 0
            result = {'roll': nav_off1['roll'], 'pit': nav_off1['pit'], 'yaw': nav_off1['yaw'],
                      'tar_occ': False, 'tar_behind': behind, 'used_nav': True, 'used_tar': False}
            return result

        elif tar_off1 and not nav_off1:
            # Target detected and not compass
            # self.ap_ckb('log', 'Found Target only for destination offset.')

            occ: bool = tar_off1['occ']
            behind = False
            result = {'roll': tar_off1['roll'], 'pit': tar_off1['pit'], 'yaw': tar_off1['yaw'],
                      'tar_occ': occ, 'tar_behind': behind, 'used_nav': False, 'used_tar': True}
            return result

        elif tar_off1 and nav_off1:
            # Target and Compass detected
            # self.ap_ckb('log', 'Found Compass and Target for destination offset.')

            # See what the error is between compass and target
            roll_err = abs(nav_off1['roll'] - tar_off1['roll'])
            pit_err = abs(nav_off1['pit'] - tar_off1['pit'])
            yaw_err = abs(nav_off1['yaw'] - tar_off1['yaw'])

            # Roll is not useful as a comparison because it goes wild when at p=0, y=0.
            if pit_err > 2.0 or yaw_err > 2.0:
                self.ap.ap_ckb('log', f'Compass-Target error p: {round(pit_err, 2)}deg y: {round(yaw_err, 2)}deg')

            # Prefer target (will be more accurate). Maybe add some additional logic to this later.
            use_target = True
            if use_target:
                occ: bool = tar_off1['occ']
                behind = nav_off1['z'] < 0
                result = {'roll': tar_off1['roll'], 'pit': tar_off1['pit'], 'yaw': tar_off1['yaw'],
                          'tar_occ': occ, 'tar_behind': behind, 'used_nav': False, 'used_tar': True}
                return result
            else:
                result = {'roll': nav_off1['roll'], 'pit': nav_off1['pit'], 'yaw': nav_off1['yaw'],
                          'tar_occ': False, 'tar_behind': False, 'used_nav': True, 'used_tar': False}
                return result

        else:
            # Neither Target nor Compass detected
            self.ap.ap_ckb('log', 'Found neither Compass nor Target for destination offset.')
            return None

    def is_sun_dead_ahead(self, scr_reg):
        return scr_reg.sun_percent(scr_reg.screen) > 5

    def sun_avoid(self, scr_reg, scooping: bool):
        """ Use to orient the ship to not be pointing right at the Sun
        Checks brightness in the region in front of us, if brightness exceeds a threshold
        then will pitch up until below threshold.
        @param scooping: Are we scooping this star?
        @param scr_reg:
        @return:
        """
        logger.debug('align= avoid sun')

        sleep(0.5)

        # close to core the 'sky' is very bright with close stars, if we are pitch due to a non-scoopable star
        #  which is dull red, the star field is 'brighter' than the sun, so our sun avoidance could pitch up
        #  endlessly. So we will have a fail_safe_timeout to kick us out of pitch up if we've pitch past 110 degrees,
        #  but we'll add 3 more second for pad in case the user has a higher pitch rate than the vehicle can do
        fail_safe_timeout = (120/self.ap.pitchrate)+3
        starttime = time.time()

        # if sun in front of us, then keep pitching up until it is below us
        while self.is_sun_dead_ahead(scr_reg):
            self.ap.keys.send('PitchUpButton', state=1)

            # check if we are being interdicted
            interdicted = self.interdiction_check()
            if interdicted:
                # Continue journey after interdiction
                self.ap.set_throttle_0()

            # if we are pitching more than N seconds break, may be in high density area star area (close to core)
            if (time.time()-starttime) > fail_safe_timeout:
                logger.debug('sun avoid failsafe timeout')
                print("sun avoid failsafe timeout")
                break

        sleep(0.35)                 # up slightly so not to overheat when scooping
        # Some ships heat up too much and need pitch up a little further
        if self.ap.sunpitchuptime > 0.0:
            sleep(self.ap.sunpitchuptime)
        self.ap.keys.send('PitchUpButton', state=0)

        # Some ships run cool so need to pitch down a little if we are scooping.
        # Never pitch back towards the star if we are already overheating.
        if scooping and self.ap.sunpitchuptime < 0.0 and not self.ap.status.get_flag(FlagsOverHeating):
            self.ap.keys.send('PitchDownButton', state=1)
            sleep(-1.0 * self.ap.sunpitchuptime)
            self.ap.keys.send('PitchDownButton', state=0)

    def overheat_escape(self, scr_reg):
        """ Emergency escape when overheating near a star. Pitch away from the star and
        fly at full throttle until the ship cools down. """
        self.ap.ap_ckb('log+vce', self.ap.locale_safe('OVERHEAT_AVOID_STAR', 'Overheating, avoiding star'))
        self.ap.set_throttle_100()
        self.sun_avoid(scr_reg, scooping=False)
        # Fly away from the star until the heat drops
        cooled = self.ap.status.wait_for_flag_off(FlagsOverHeating, 60)
        if not cooled:
            logger.warning('overheat_escape: still overheating after timeout')
        sleep(float(self.ap.config['Wait_HeatDissipate']))
        self.ap.set_throttle_50()

    def compass_align(self, scr_reg) -> bool:
        """ Use the compass to find the nav point position when in SC or in space.  Will then perform rotation and
        pitching to put the nav point in the middle of the compass, i.e. target right in front of us.
        @return: True if aligned, else False.
        """
        if not self.ap._is_in_supercruise_or_space():
            logger.error('align=err1, nav_align not in super or space')
            raise Exception('nav_align not in super or space')

        self.ap.ap_ckb('log+vce', 'Compass Align')

        # try multiple times to get aligned.  If the sun is shining on console, this it will be hard to match
        # the vehicle should be positioned with the sun below us via the sun_avoid() routine after a jump
        for ii in range(self.ap.config['NavAlignTries']):
            # Check for overheating - we may be pointing at the star
            if self.ap.status.get_flag(FlagsOverHeating):
                self.ap.ap_ckb('log+vce', self.ap.locale_safe('OVERHEAT_ABORT_ALIGN', 'Overheating - aborting compass align'))
                return False

            off = self.get_compass_target_offset()
            if off is None:
                self.ap.ap_ckb('log', 'Unable to detect compass. Rolling to new position.')
                # Try rolling if star glare is obscuring the compass
                self.ap.ship_control.roll_clockwise_anticlockwise(90)
                continue

            logger.debug(f"Compass position: yaw: {str(off['yaw'])} pit: {str(off['pit'])}")

            # Reduce the closeness as we are using the target instead of compass
            close = 3.0  # in degrees

            # Check if we are close enough already
            if abs(off['yaw']) < close and abs(off['pit']) < close:
                self.ap.ap_ckb('log', 'Compass Align complete')
                return True

            # Increase the closeness as we are using the compass only
            close = 30.0  # in degrees

            # Roll if the nav point is not directly behind us, or in front of us.
            if ((((-180 + close) < off['yaw'] < (0 - close)) or
                 ((0 + close) < off['yaw'] < (180 - close))) and
                    (((-180 + close) < off['pit'] < (0 - close)) or
                     ((0 + close) < off['pit'] < (180 - close)))):

                # Increase the closeness as we are using the compass only
                close = 8.0  # in degrees

                for i in range(20):
                    # Calc roll time based on nav point location
                    if off is None:
                        self.ap.ap_ckb('log', 'Unable to detect compass.')
                        break
                    if abs(off['roll']) > close and (180 - abs(off['roll']) > close):
                        # Clear the overlays before moving
                        if self.ap.debug_overlay:
                            self.ap.overlay.overlay_remove_rect('compass')
                            self.ap.overlay.overlay_remove_floating_text('compass')
                            self.ap.overlay.overlay_remove_floating_text('nav')
                            self.ap.overlay.overlay_remove_floating_text('nav_beh')
                            self.ap.overlay.overlay_remove_floating_text('compass_rpy')
                            self.ap.overlay.overlay_paint()

                        off = self.ap.ship_control.roll_clockwise_anticlockwise(off['roll'], auto_tune=self.ap.auto_tune_rpy, cur_deg=off['roll'])
                    else:
                        break

            # Reduce the closeness as we are using the target instead of compass
            close = 3.0  # in degrees

            for i in range(20):
                # Calc pitch time based on nav point location
                if off is None:
                    self.ap.ap_ckb('log', 'Unable to detect compass.')
                    break
                if abs(off['pit']) > close:
                    # Clear the overlays before moving
                    if self.ap.debug_overlay:
                        self.ap.overlay.overlay_remove_rect('compass')
                        self.ap.overlay.overlay_remove_floating_text('compass')
                        self.ap.overlay.overlay_remove_floating_text('nav')
                        self.ap.overlay.overlay_remove_floating_text('nav_beh')
                        self.ap.overlay.overlay_remove_floating_text('compass_rpy')
                        self.ap.overlay.overlay_paint()

                    off = self.ap.ship_control.pitch_up_down(off['pit'], auto_tune=self.ap.auto_tune_rpy, cur_deg=off['pit'])
                else:
                    break

            for i in range(20):
                # Calc yaw time based on nav point location
                if off is None:
                    self.ap.ap_ckb('log', 'Unable to detect compass.')
                    break
                if abs(off['yaw']) > close:
                    # Clear the overlays before moving
                    if self.ap.debug_overlay:
                        self.ap.overlay.overlay_remove_rect('compass')
                        self.ap.overlay.overlay_remove_floating_text('compass')
                        self.ap.overlay.overlay_remove_floating_text('nav')
                        self.ap.overlay.overlay_remove_floating_text('nav_beh')
                        self.ap.overlay.overlay_remove_floating_text('compass_rpy')
                        self.ap.overlay.overlay_paint()

                    off = self.ap.ship_control.yaw_right_left(off['yaw'], auto_tune=self.ap.auto_tune_rpy, cur_deg=off['yaw'])
                else:
                    break

            sleep(.1)
            if off is not None:
                logger.debug(f"Compass position: yaw: {str(off['yaw'])} pit: {str(off['pit'])}")

        # Not aligned
        self.ap.ap_ckb('log+vce', 'Compass Align failed - exhausted all retries')
        return False

    def mnvr_to_target(self, scr_reg):
        """ Maneuver to Target using compass then target before performing a jump."""
        from ED_AP import ScTargetAlignReturn

        logger.debug('mnvr_to_target entered')

        if not self.ap._is_in_supercruise_or_space():
            for _ in range(10):
                sleep(0.5)
                if self.ap._is_in_supercruise_or_space():
                    break
            else:
                logger.error('align() not in sc or space')
                raise Exception('align() not in sc or space')

        self.sun_avoid(scr_reg, scooping=False)

        self.ap.set_throttle_50()
        res = self.compass_align(scr_reg)
        # Quick calibrate the compass
        # if res:
        #     self.quick_calibrate_compass()

        self.ap.ap_ckb('log+vce', 'Target Align')
        for i in range(5):
            self.ap.set_throttle_50()
            # Use the wider jump limits - the FSD self-corrects within its cone, so
            # sub-degree alignment is not needed and only causes oscillation.
            align_res = self.sc_target_align(scr_reg, outer_lim=self.ap.config['jump_align_outer_lim'],
                                             inner_lim=self.ap.config['jump_align_inner_lim'])
            if align_res == ScTargetAlignReturn.Lost:
                self.ap.set_throttle_50()
                self.compass_align(scr_reg)  # Compass Align

            elif align_res == ScTargetAlignReturn.Found:
                # Check the star is not in front of us after aligning. The FSD charges for
                # ~15s at 100% throttle, so jumping with the star ahead flies us into it.
                if self.is_sun_dead_ahead(scr_reg):
                    self.ap.ap_ckb('log+vce', self.ap.locale_safe('ALIGN_STAR_AHEAD', 'Star in front of target, flying past it first'))
                    self.sun_avoid(scr_reg, scooping=False)
                    self.ap.set_throttle_100()
                    sleep(float(self.ap.config['Wait_PastSun']))
                    self.ap.set_throttle_50()
                    self.compass_align(scr_reg)
                    continue
                self.ap.set_throttle_100()
                return

            elif align_res == ScTargetAlignReturn.Overheat:
                # Too close to the star - escape and cool down before trying again
                self.overheat_escape(scr_reg)
                self.ap.set_throttle_50()
                self.compass_align(scr_reg)  # Compass Align

            elif align_res == ScTargetAlignReturn.Disengage:
                break

        logger.error('mnvr_to_target failed 5 times')
        raise Exception('mnvr_to_target failed 5 times')

    def sc_target_align(self, scr_reg, outer_lim: float | None = None,
                        inner_lim: float | None = None) -> ScTargetAlignReturn:
        """ Align to the target, monitoring for disengage and obscured.
        @param scr_reg: The screen region class.
        @param outer_lim: Alignment tolerance in deg that triggers alignment. None uses the configured default.
        @param inner_lim: Alignment tolerance in deg to stop aligning at. None uses the configured default.
        @return: A string detailing the reason for the method return. Current return options:
            'lost': Lost target
            'found': Target found
            'disengage': Disengage text found
        """
        from ED_AP import ScTargetAlignReturn

        target_align_compass_mult = 3  # Multiplier to close and target_align_inner_lim when using compass for align.
        target_align_pit_off = 0.25  # In deg. To keep the target above the center line (prevent it going down out of view).
        max_occlusion_repositions = 2  # Limit repositions per align call to prevent an endless reposition loop.
        occlusion_repositions = 0
        align_timeout = 60.0  # In seconds. Failsafe to prevent an endless alignment loop.
        compass_lims_applied = False  # Compass limit multiplier applied only once per align call.

        target_pit = target_align_pit_off
        target_yaw = 0.0

        # Copy locally as we will change the values
        target_align_outer_lim = outer_lim if outer_lim is not None else self.ap.target_align_outer_lim
        target_align_inner_lim = inner_lim if inner_lim is not None else self.ap.target_align_inner_lim

        off = None
        tar_off1: CompassTargetOffset | None = None
        nav_off1 = None
        tar_off2: CompassTargetOffset | None = None
        nav_off2 = None

        # Try to get the target 5 times before quiting
        for i in range(5):
            # Check for overheating - we may be pointing at the star
            if self.ap.status.get_flag(FlagsOverHeating):
                self.ap.ap_ckb('log+vce', self.ap.locale_safe('OVERHEAT_ABORT_ALIGN', 'Overheating - aborting target align'))
                return ScTargetAlignReturn.Overheat

            # Check Target and Compass
            # nav_off1 = self.get_nav_offset(scr_reg)
            tar_off1 = self.get_compass_target_offset()
            if tar_off1:
                # Target detected
                off = tar_off1
                # logger.debug(f"sc_target_align x: {str(off['x'])} y:{str(off['y'])}")
                # Apply offset to keep target above center
                off['pit'] = off['pit'] - target_align_pit_off
                # elif nav_off1:
                #     # Try to use the compass data if the target is not visible.
                #     off = nav_off1
                #     self.ap_ckb('log', 'Using Compass for Target Align')

                # We are using compass align, increase the values as compass is much less accurate
                if off['used_nav'] and not compass_lims_applied:
                    compass_lims_applied = True
                    target_align_outer_lim = target_align_outer_lim * target_align_compass_mult
                    target_align_inner_lim = target_align_inner_lim * target_align_compass_mult
                    target_align_pit_off = target_align_pit_off * target_align_compass_mult

                # Check if Target is now behind us
                if off['tar_behind']:
                    self.ap.ap_ckb('log', 'Target is behind us')
                    return ScTargetAlignReturn.Lost

                # Check if target occluded
                if tar_off1['tar_occ']:
                    if occlusion_repositions < max_occlusion_repositions:
                        occlusion_repositions += 1
                        self.ap.occluded_reposition(scr_reg)
                        self.ap.ap_ckb('log+vce', 'Target Align')
                    else:
                        self.ap.ap_ckb('log', self.ap.locale_safe('ALIGN_STILL_OCCLUDED', 'Target still occluded, continuing align without reposition.'))

            # if self.is_destination_occluded(scr_reg):
            #     self.occluded_reposition(scr_reg)
            #     self.ap_ckb('log+vce', 'Target Align')

            # check for SC Disengage
            # if self.sc_disengage_label_up(scr_reg):
            #     if self.sc_disengage_ocr(scr_reg):
            if self.ap._sc_disengage_active:
                # self.ap_ckb('log+vce', 'Disengage Supercruise')
                # self.keys.send('HyperSuperCombination')
                self.ap.stop_sco_monitoring()
                return ScTargetAlignReturn.Disengage

            # Quit loop if we found Target or Compass
            if off:
                break

        # Target could not be found, return
        if tar_off1 is None:
            logger.debug("sc_target_align not finding target")
            self.ap.ap_ckb('log', 'Target Align failed - target not found')
            return ScTargetAlignReturn.Lost

        # We have Target or Compass. Are we close to Target?
        align_start = time.time()
        while ((abs(off['yaw']) > target_align_outer_lim) or
               (abs(off['pit']) > target_align_outer_lim)):

            # Failsafe timeout to prevent an endless alignment loop.
            if (time.time() - align_start) > align_timeout:
                logger.debug("sc_target_align timed out")
                self.ap.ap_ckb('log', self.ap.locale_safe('ALIGN_TIMEOUT', 'Target Align failed - timed out.'))
                return ScTargetAlignReturn.Lost

            # Check for overheating - we may be pointing at the star
            if self.ap.status.get_flag(FlagsOverHeating):
                self.ap.ap_ckb('log+vce', self.ap.locale_safe('OVERHEAT_ABORT_ALIGN', 'Overheating - aborting target align'))
                return ScTargetAlignReturn.Overheat

            target_align_outer_lim = target_align_inner_lim  # Keep aligning until we are within this lower range.

            # Clear the overlays before moving
            if self.ap.debug_overlay:
                self.ap.overlay.overlay_remove_rect('compass')
                self.ap.overlay.overlay_remove_floating_text('compass')
                self.ap.overlay.overlay_remove_floating_text('nav')
                self.ap.overlay.overlay_remove_floating_text('nav_beh')
                self.ap.overlay.overlay_remove_floating_text('compass_rpy')

                self.ap.overlay.overlay_remove_rect('target')
                self.ap.overlay.overlay_remove_floating_text('target')
                self.ap.overlay.overlay_remove_floating_text('target_occ')
                self.ap.overlay.overlay_remove_floating_text('target_rpy')
                self.ap.overlay.overlay_paint()

            # Calc pitch time based on nav point location
            logger.debug(f"sc_target_align before: pit: {off['pit']} yaw: {off['yaw']} ")

            # p_deg = 0.0
            if abs(off['pit']) > target_align_outer_lim:
                # p_deg = off['pit']
                # self.ship_control.pitch_up_down(p_deg)
                self.ap.ship_control.pitch_up_down(off['pit'], auto_tune=self.ap.auto_tune_rpy, cur_deg=off['pit'])

            # Calc yaw time based on nav point location
            # y_deg = 0.0
            if abs(off['yaw']) > target_align_outer_lim:
                # y_deg = off['yaw']
                # self.ship_control.yaw_right_left(y_deg)
                self.ap.ship_control.yaw_right_left(off['yaw'], auto_tune=self.ap.auto_tune_rpy, cur_deg=off['yaw'])

            # Check Target and Compass
            tar_off2 = self.get_compass_target_offset()
            if tar_off2:
                off = tar_off2
                logger.debug(f"sc_target_align after: pit:{off['pit']} yaw: {off['yaw']} ")
                # Apply offset to keep target above center
                off['pit'] = off['pit'] - target_align_pit_off
            # elif nav_off2:
            #     # Try to use the compass data if the target is not visible.
            #     off = nav_off2
            #     self.ap_ckb('log', 'Using Compass for Target Align')
                # Check if Target is now behind us
                if tar_off2['tar_behind']:
                    self.ap.ap_ckb('log', 'Target is behind us')
                    return ScTargetAlignReturn.Lost

                # We are using compass align, increase the values as compass is much less accurate
                if off['used_nav'] and not compass_lims_applied:
                    compass_lims_applied = True
                    target_align_outer_lim = target_align_outer_lim * target_align_compass_mult
                    target_align_inner_lim = target_align_inner_lim * target_align_compass_mult
                    target_align_pit_off = target_align_pit_off * target_align_compass_mult

            if tar_off1 and tar_off2:
                # Check diff from before and after movement
                # TODO - At some point check/increase the RPY if we overshoot?
                pit_delta = tar_off2['pit'] - tar_off1['pit']
                yaw_delta = tar_off2['yaw'] - tar_off1['yaw']

            if tar_off2:
                # Store current offsets
                tar_off1 = tar_off2.copy()

            # Check if target occluded
            if tar_off2 and tar_off2['tar_occ']:
                if occlusion_repositions < max_occlusion_repositions:
                    occlusion_repositions += 1
                    self.ap.occluded_reposition(scr_reg)
                    self.ap.ap_ckb('log+vce', 'Target Align')
                else:
                    self.ap.ap_ckb('log', self.ap.locale_safe('ALIGN_STILL_OCCLUDED', 'Target still occluded, continuing align without reposition.'))

            # if self.is_destination_occluded(scr_reg):
            #     self.occluded_reposition(scr_reg)
            #     self.ap_ckb('log+vce', 'Target Align')

            # check for SC Disengage
            # if self.sc_disengage_label_up(scr_reg):
            #     if self.sc_disengage_ocr(scr_reg):
            if self.ap._sc_disengage_active:
                # self.ap_ckb('log+vce', 'Disengage Supercruise')
                # self.keys.send('HyperSuperCombination')
                self.ap.stop_sco_monitoring()
                return ScTargetAlignReturn.Disengage

            # Check if target is outside the target region (behind us) and break loop
            if tar_off2 is None:
                logger.debug("sc_target_align lost target")
                self.ap.ap_ckb('log', 'Target Align failed - lost target.')
                return ScTargetAlignReturn.Lost

        # # We are aligned, so define the navigation correction as the current offset. This won't be 100% accurate, but
        # # will be within a few degrees.
        # if tar_off1 and nav_off1:
        #     self._nav_cor_x = self._nav_cor_x + nav_off1['x']
        #     self._nav_cor_y = self._nav_cor_y + nav_off1['y']
        # elif tar_off2 and nav_off2:
        #     self._nav_cor_x = self._nav_cor_x + nav_off2['x']
        #     self._nav_cor_y = self._nav_cor_y + nav_off2['y']

        # self.ap_ckb('log', 'Target Align complete.')
        return ScTargetAlignReturn.Found
