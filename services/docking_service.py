from __future__ import annotations

from time import sleep
from typing import TYPE_CHECKING

import cv2

from EDAP_data import *
from EDJournal import StationType
from EDlogger import logger

if TYPE_CHECKING:
    from ED_AP import ScTargetAlignReturn


class DockingService:
    """ Docking / undocking / supercruise engage-disengage logic extracted from ED_AP. """

    def __init__(self, ed_ap):
        self.ap = ed_ap

    def sc_disengage(self, scr_reg) -> bool:
        """ DEPRECATED - Replaced with 'sc_disengage_label_up' and 'sc_disengage_active' using OCR.
        look for the "PRESS [J] TO DISENGAGE" image, if in this region then return true
        """
        dis_image, (minVal, maxVal, minLoc, maxLoc), match = scr_reg.match_template_in_region('disengage', 'disengage')

        pt = maxLoc

        width = scr_reg.templates.template['disengage']['width']
        height = scr_reg.templates.template['disengage']['height']

        # Draw box around region
        if self.ap.debug_overlay:
            abs_rect = scr_reg.reg['disengage']['rect']
            self.ap.overlay.overlay_rect1('sc_disengage', abs_rect, (0, 255, 0), 2)
            self.ap.overlay.overlay_floating_text('sc_disengage', f'Dis: {maxVal:5.4f} > {scr_reg.disengage_thresh}', abs_rect[0], abs_rect[1] - 25, (0, 255, 0))
            self.ap.overlay.overlay_paint()

        if self.ap.cv_view:
            self.ap.draw_match_rect(dis_image, pt, (pt[0] + width, pt[1] + height), (0, 255, 0), 2)
            dis_image = cv2.rectangle(dis_image, (0, 0), (1000, 25), (0, 0, 0), -1)
            cv2.putText(dis_image, f'{maxVal:5.4f} > {scr_reg.disengage_thresh}', (1, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1, cv2.LINE_AA)
            cv2.imshow('disengage', dis_image)
            cv2.moveWindow('disengage', self.ap.cv_view_x-460, self.ap.cv_view_y+575)
            cv2.waitKey(1)

        if maxVal > scr_reg.disengage_thresh:
            # logger.info("'PRESS [] TO DISENGAGE' detected. Disengaging Supercruise")
            # self.ap_ckb('log+vce', "Disengaging Supercruise")
            return True
        else:
            return False

    def undock(self):
        """ Performs menu action to undock from Station """
        # Go to cockpit view
        self.ap.ship_control.goto_cockpit_view()

        # Now we are on initial menu, we go up to top (which is Refuel)
        self.ap.keys.send('UI_Up', repeat=3)

        # down to Auto Undock and Select it...
        self.ap.keys.send('UI_Down')
        self.ap.keys.send('UI_Down')
        self.ap.keys.send('UI_Select')
        self.ap.set_throttle_0(repeat=2)

        # Performs left menu ops to request docking

    def request_docking(self):
        """ Request docking from Nav Panel. """
        self.ap.nav_panel.request_docking()

    def dock(self):
        """ Docking sequence.  Assumes in normal space, will get closer to the Station
        then zero the velocity and execute menu commands to request docking, when granted
        will wait a configurable time for dock.  Perform Refueling and Repair.
        """
        # if not in normal space, give a few more sections as at times it will take a little bit
        if self.ap.jn.ship_state()['status'] != "in_space":
            sleep(3)  # sleep a little longer

        if self.ap.jn.ship_state()['status'] != "in_space":
            logger.error('In dock(), after wait, but still not in_space')

        sleep(5)  # wait 5 seconds to get to 7.5km to request docking
        self.ap.set_throttle_50()

        if self.ap.jn.ship_state()['status'] != "in_space":
            self.ap.set_throttle_0()
            logger.error('In dock(), after long wait, but still not in_space')
            raise Exception('Docking failed (not in space)')

        sleep(float(self.ap.config['Wait_DockApproach']))
        # At this point (of sleep()) we should be < 7.5km from the station.  Go 0 speed
        # if we get docking granted ED's docking computer will take over
        self.ap.set_throttle_0(repeat=2)
        sleep(float(self.ap.config['Wait_ShipStop']))  # Wait for ship to come to stop
        self.ap.ap_ckb('log+vce', "Initiating Docking Procedure")
        # Request docking through Nav panel.
        self.request_docking()
        sleep(1)

        tries = self.ap.config['DockingRetries']
        granted = False
        if self.ap.jn.ship_state()['status'] == "dockinggranted":
            granted = True
        else:
            for i in range(tries):
                if self.ap.jn.ship_state()['no_dock_reason'] == "Distance":
                    self.ap.set_throttle_50()
                    sleep(5)
                    self.ap.set_throttle_0(repeat=2)
                sleep(float(self.ap.config['Wait_ShipStop']))  # Wait for ship to come to stop
                # Request docking through Nav panel.
                self.request_docking()
                self.ap.set_throttle_0(repeat=2)

                sleep(1.5)
                if self.ap.jn.ship_state()['status'] == "dockinggranted":
                    granted = True
                    # Go back to navigation tab
                    # self.request_docking_cleanup()
                    break
                if self.ap.jn.ship_state()['status'] == "dockingdenied":
                    pass

        if not granted:
            self.ap.ap_ckb('log', 'Docking denied: '+str(self.ap.jn.ship_state()['no_dock_reason']))
            logger.warning('Did not get docking authorization, reason:'+str(self.ap.jn.ship_state()['no_dock_reason']))
            raise Exception('Docking failed (Did not get docking authorization)')
        else:
            self.ap.ap_ckb('log+vce', "Docking request granted")
            # allow auto dock to take over
            for i in range(self.ap.config['WaitForAutoDockTimer']):
                sleep(1)
                if self.ap.jn.ship_state()['status'] == "in_station":
                    # go to top item, select (which should be refuel)
                    self.ap.keys.send('UI_Up', hold=3)
                    self.ap.keys.send('UI_Select')  # Refuel
                    sleep(0.5)
                    self.ap.keys.send('UI_Right')  # Repair
                    self.ap.keys.send('UI_Select')
                    sleep(0.5)
                    self.ap.keys.send('UI_Right')  # Ammo
                    self.ap.keys.send('UI_Select')
                    sleep(0.5)
                    self.ap.keys.send("UI_Left", repeat=2)  # back to fuel
                    return

            self.ap.ap_ckb('log', 'Auto dock timer timed out.')
            logger.warning('Auto dock timer timed out. Aborting Docking.')
            raise Exception('Docking failed (Auto dock timer timed out)')

    def undock_seq(self):
        self.ap.update_ap_status("Executing Undocking/Launch")

        # Store current location (on planet or in space)
        on_planet = self.ap.status.get_flag(FlagsHasLatLong)
        on_orbital_construction_site = self.ap.jn.ship_state()['exp_station_type'] == StationType.SpaceConstructionDepot
        fleet_carrier = self.ap.jn.ship_state()['exp_station_type'] == StationType.FleetCarrier
        squadron_fleet_carrier = self.ap.jn.ship_state()['exp_station_type'] == StationType.SquadronCarrier
        starport_outpost = not on_planet and not on_orbital_construction_site and not fleet_carrier and not squadron_fleet_carrier

        # Leave starport or planetary port
        if not on_planet:
            # Check that we are docked
            if self.ap.status.get_flag(FlagsDocked):
                # Check if we have an advanced docking computer
                if not self.ap.jn.ship_state()['has_adv_dock_comp']:
                    self.ap.ap_ckb('log', "Unable to undock. Advanced Docking Computer not fitted.")
                    logger.warning('Unable to undock. Advanced Docking Computer not fitted.')
                    raise Exception('Unable to undock. Advanced Docking Computer not fitted.')

                # Undock from station
                self.undock()

                # need to wait until undock complete, that is when we are back in_space
                # TODO - This maybe an FDEV error. On leaving a FC, no music was played so the journal never logged that we went into space.
                while self.ap.jn.ship_state()['status'] != 'in_space':
                    sleep(1)

                # If we are on a Fleet Carrier/Squadron Carrier we will pitch up 90 deg and fly away to avoid planet
                if fleet_carrier or squadron_fleet_carrier:
                    self.ap.ap_ckb('log+vce', 'Maneuvering')
                    # The pitch rates are defined in SC, not normal flights, so bump this up a bit
                    self.ap.ship_control.pitch_up_down(self.ap.config['FCDepartureAngle'])

                    self.ap.update_ap_status("Undock Complete, accelerating")

                    # Engage Supercruise
                    self.sc_engage(True)

                    # Wait the configured time before continuing
                    self.ap.ap_ckb('log', 'Flying for configured FC departure time.')
                    sleep(self.ap.config['FCDepartureTime'])

                # If we are on an Orbital Construction Site we will need to pitch up 90 deg to avoid crashes
                if on_orbital_construction_site:
                    self.ap.ap_ckb('log+vce', 'Maneuvering')
                    # The pitch rates are defined in SC, not normal flights, so bump this up a bit
                    self.ap.ship_control.pitch_up_down(self.ap.config['OCDepartureAngle'])

                if starport_outpost or on_orbital_construction_site:
                    # In space (launched from starport or outpost etc.) OR construction site
                    self.ap.update_ap_status("Undock Complete, accelerating")

                    # Engage Supercruise
                    self.sc_engage(True)

        elif on_planet:
            # Check if we are on a landing pad (docked), or landed on the planet surface
            if self.ap.status.get_flag(FlagsDocked):
                # We are on a landing pad (docked)
                # Check if we have an advanced docking computer
                if not self.ap.jn.ship_state()['has_adv_dock_comp']:
                    self.ap.ap_ckb('log', "Unable to undock. Advanced Docking Computer not fitted.")
                    logger.warning('Unable to undock. Advanced Docking Computer not fitted.')
                    raise Exception('Unable to undock. Advanced Docking Computer not fitted.')

                # Undock from port
                self.undock()

                # need to wait until undock complete, that is when we are back in_space
                while self.ap.jn.ship_state()['status'] != 'in_space':
                    sleep(1)
                self.ap.update_ap_status("Undock Complete, accelerating")

            elif self.ap.status.get_flag(FlagsLanded):
                # We are on planet surface (not docked at planet landing pad)
                # Hold UP for takeoff
                self.ap.keys.send('UpThrustButton', hold=6)
                self.ap.keys.send('LandingGearToggle')
                self.ap.update_ap_status("Takeoff Complete, accelerating")

            # Undocked or off the surface, so leave planet
            self.ap.set_throttle_50()
            # Wait for throttle to take effect.
            sleep(2.0)

            # The pitch rates are defined in SC, not normal flights, so bump this up a bit
            self.ap.ship_control.pitch_up_down(90)

            # Engage Supercruise
            self.sc_engage(True)

            # Enable SCO. If SCO not fitted, this will do nothing.
            self.ap.keys.send('UseBoostJuice')

            # Wait until out of orbit.
            res = self.ap.status.wait_for_flag_off(FlagsHasLatLong, timeout=60)  # This takes too long to update
            # TODO - wait_for_flag_off(FlagsHasLatLong) takes too long when SCO is active and sends us far from the
            #  planet which is not useful when we are doing exobiology stuff and want to go back to the planet.
            #  The below tries to help do this, but is not very effective. Maybe another flag would be useful?
            # dly = self.config['PlanetDepartureSCOTime']
            # if dly > 0.0:
            #     sleep(dly)

            # TODO - do we need to check if we never leave orbit?

            # Disable SCO. If SCO not fitted, this will do nothing.
            self.ap.keys.send('UseBoostJuice')

    def sc_engage(self, boost: bool) -> bool:
        """ Engages supercruise, then returns us to 50% speed, unless we are in SC already.
        """
        # Check if we are already in SC
        if self.ap.status.get_flag(FlagsSupercruise):
            # Start SCO monitoring
            self.ap.start_sco_monitoring()
            return True

        self.ap.set_throttle_100()

        # While Mass Locked, keep boosting.
        while self.ap.status.get_flag(FlagsFsdMassLocked):
            if boost:
                self.ap.keys.send('UseBoostJuice')
            sleep(1)

        # Engage Supercruise
        self.ap.keys.send('Supercruise')

        # Start SCO monitoring
        self.ap.start_sco_monitoring()

        # Wait for jump to supercruise, keep boosting.
        while not self.ap.status.get_flag(FlagsFsdJump):
            if boost:
                self.ap.keys.send('UseBoostJuice')
            sleep(1)

        # Wait for supercruise
        self.ap.status.wait_for_flag_on(FlagsSupercruise, timeout=30)

        # Revert to 50%
        self.ap.set_throttle_50()

        return True

    def supercruise_to_station(self, scr_reg, station_name: str) -> bool:
        """ Supercruise to the specified target, which may be a station, FC, body, signal source, etc.
        Returns True if we travel successfully travel there, else False. """
        self.ap.update_ap_status(f"Targeting Station: {station_name}")
        # res = self.ap.nav_panel.lock_destination(station_name)
        # if not res:
        #    return False

        # if we are starting docked at a station, we need to undock first
        if self.ap.status.get_flag(FlagsDocked) or self.ap.status.get_flag(FlagsLanded):
            self.undock_seq()

        # Ensure we are in supercruise
        self.sc_engage(False)

        # Successful targeting of Station, lets go to it
        sleep(3)  # Wait for compass to stop flashing blue!
        if self.ap.have_destination(scr_reg):
            self.ap.ap_ckb('log', " - Station: " + station_name)
            self.ap.update_ap_status(f"SC to Station: {station_name}")
            self.sc_assist(scr_reg)
        else:
            self.ap.ap_ckb('log', f" - Could not target station: {station_name}")
            return False

        return True

    def sc_assist(self, scr_reg, do_docking=True):
        """ Supercruise Assist loop to travel to target in system and perform autodock.
        """
        from ED_AP import ScTargetAlignReturn

        logger.debug("Entered sc_assist")

        # Goto cockpit view
        self.ap.ship_control.goto_cockpit_view()

        align_failed = False
        # see if we have a compass up, if so then we have a target
        if not self.ap.have_destination(scr_reg):
            self.ap.ap_ckb('log', "Quiting SC Assist - Compass not found. Rotate ship and try again.")
            logger.debug("Quiting sc_assist - compass not found")
            return
        # else:
        #     # Quick calibrate the compass
        #     self.ap.quick_calibrate_compass()

        # if we are starting docked at a station or landed, we need to undock/takeoff first
        if self.ap.status.get_flag(FlagsDocked) or self.ap.status.get_flag(FlagsLanded):
            self.ap.update_overlay()
            self.undock_seq()

        # Ensure we are in supercruise
        self.sc_engage(False)
        self.ap.jn.ship_state()['interdicted'] = False

        # Ensure we are 50%, don't want the loop of shame
        # Align Nav to target
        self.ap.set_throttle_50()
        res = self.ap.nav_service.compass_align(scr_reg)  # Compass Align

        self.ap.ap_ckb('log+vce', 'Target Align')
        self.ap.set_throttle_50()
        align_res = self.ap.nav_service.sc_target_align(scr_reg)

        # Loop forever keeping tight align to target, until we get SC Disengage popup
        while True:
            sleep(0.05)
            if (self.ap.jn.ship_state()['status'] == 'in_supercruise' or self.ap.status.get_flag(FlagsSupercruise) or
                    self.ap._sc_disengage_active):
                # Align and stay on target. If false is returned, we have lost the target behind us.
                # self.ap.set_speed_50()
                align_res = self.ap.nav_service.sc_target_align(scr_reg)
                if align_res == ScTargetAlignReturn.Lost:
                    # Continue ahead before aligning to prevent us circling the target
                    # self.ap.set_speed_100()
                    sleep(10)
                    self.ap.set_throttle_50()
                    self.ap.nav_service.compass_align(scr_reg)  # Compass Align

                elif align_res == ScTargetAlignReturn.Found:
                    pass

                elif align_res == ScTargetAlignReturn.Overheat:
                    # Too close to the star - escape and cool down before trying again
                    self.ap.nav_service.overheat_escape(scr_reg)
                    self.ap.set_throttle_50()
                    self.ap.nav_service.compass_align(scr_reg)  # Compass Align

                elif align_res == ScTargetAlignReturn.Disengage:
                    break

            elif self.ap.status.get_flag2(Flags2GlideMode):
                # Gliding - wait to complete
                logger.debug("Gliding")
                self.ap.status.wait_for_flag2_off(Flags2GlideMode, 30)
                break
            else:
                # if we dropped from SC, then we rammed into planet
                logger.debug("No longer in supercruise")
                align_failed = True
                break

            # check if we are being interdicted
            interdicted = self.ap.nav_service.interdiction_check()
            if interdicted:
                # Continue journey after interdiction
                self.ap.set_throttle_50()
                self.ap.nav_service.compass_align(scr_reg)  # realign with station

            # check for SC Disengage
            # if self.ap.sc_disengage_label_up(scr_reg):
            #     if self.ap.sc_disengage_ocr(scr_reg):
            if self.ap._sc_disengage_active:
                # self.ap.ap_ckb('log+vce', 'Disengage Supercruise')
                # self.ap.keys.send('HyperSuperCombination')
                self.ap.stop_sco_monitoring()
                break

        # if no error, we must have gotten disengage
        if not align_failed and do_docking:
            sleep(4)  # wait for the journal to catch up

            # Check if this is a target we cannot dock at
            skip_docking = False
            if not self.ap.jn.ship_state()['has_adv_dock_comp'] and not self.ap.jn.ship_state()['has_std_dock_comp']:
                self.ap.ap_ckb('log', "Skipping docking. No Docking Computer fitted.")
                skip_docking = True

            if not self.ap.jn.ship_state()['SupercruiseDestinationDrop_type'] is None:
                if (self.ap.jn.ship_state()['SupercruiseDestinationDrop_type'].startswith("$USS_Type")
                        # Bulk Cruisers
                        or "-class Cropper" in self.ap.jn.ship_state()['SupercruiseDestinationDrop_type']
                        or "-class Hauler" in self.ap.jn.ship_state()['SupercruiseDestinationDrop_type']
                        or "-class Reformatory" in self.ap.jn.ship_state()['SupercruiseDestinationDrop_type']
                        or "-class Researcher" in self.ap.jn.ship_state()['SupercruiseDestinationDrop_type']
                        or "-class Surveyor" in self.ap.jn.ship_state()['SupercruiseDestinationDrop_type']
                        or "-class Traveller" in self.ap.jn.ship_state()['SupercruiseDestinationDrop_type']
                        or "-class Tanker" in self.ap.jn.ship_state()['SupercruiseDestinationDrop_type']):
                    self.ap.ap_ckb('log', "Skipping docking. No docking privilege at MegaShips.")
                    skip_docking = True

            if not skip_docking:
                # go into docking sequence
                self.dock()
                self.ap.ap_ckb('log+vce', "Docking complete, refueled, repaired and re-armed")
                self.ap.update_ap_status("Docking Complete")
            else:
                self.ap.set_throttle_0()
        else:
            self.ap.vce.say("Exiting Supercruise, setting throttle to zero")
            self.ap.set_throttle_0()  # make sure we don't continue to land
            self.ap.ap_ckb('log', "Supercruise dropped, terminating SC Assist")

        self.ap.ap_ckb('log+vce', "Supercruise Assist complete")
