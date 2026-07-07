import time
from time import sleep

from EDlogger import logger
from EDAP_data import *


class FuelService:
    """ Fuel scooping / refuel logic extracted from ED_AP. """

    def __init__(self, ed_ap):
        self.ap = ed_ap

    def refuel_new(self, scr_reg):
        """ Check if refueling needed, ensure correct start type. """
        # Check if we have a fuel scoop
        has_fuel_scoop = self.ap.jn.ship_state()['has_fuel_scoop']

        logger.debug('refuel')
        scoopable_stars = ['F', 'O', 'G', 'K', 'B', 'A', 'M']

        if self.ap.jn.ship_state()['status'] != 'in_supercruise':
            logger.error('refuel=err1')
            return False

        is_star_scoopable = self.ap.jn.ship_state()['star_class'] in scoopable_stars

        # if the sun is not scoopable, then set a low low threshold so we can pick up the dull red
        # sun types.  Since we won't scoop it doesn't matter how much we pitch up
        # if scoopable we know white/yellow stars are bright, so set higher threshold, this will allow us to
        #  mast out the galaxy edge (which is bright) and not pitch up too much and avoid scooping
        if is_star_scoopable == False or not has_fuel_scoop:
            scr_reg.set_sun_threshold(25)
        else:
            scr_reg.set_sun_threshold(self.ap.config['SunBrightThreshold'])

        # Conditions to avoid refueling
        avoid_star = False
        if not is_star_scoopable:
            self.ap.ap_ckb('log', 'Skip refuel - not a fuel star')
            avoid_star = True

        elif (self.ap.jn.ship_state()['fuel_percent'] == 100 or
                self.ap.jn.ship_state()['fuel_percent'] >= self.ap.config['RefuelThreshold']):
            self.ap.ap_ckb('log', 'Skip refuel - fuel level okay')
            avoid_star = True

        elif not has_fuel_scoop:
            self.ap.ap_ckb('log', 'Skip refuel - no fuel scoop fitted')
            avoid_star = True

        # Check if we are avoiding this star
        if avoid_star:
            # Let's avoid the star, shall we
            self.ap.update_ap_status("Avoiding star")
            self.ap.ap_ckb('log+vce', 'Avoiding star')

            # Avoid star
            self.ap.sun_avoid(scr_reg, scooping=False)
            # Move and additional 20 deg up to avoid scooping
            self.ap.ship_control.pitch_up_down(20)
            return False

        # Continue refueling operation
        self.ap.ap_ckb('log+vce', 'Preparing for refuel')
        self.ap.update_ap_status("Preparing for refuel")
        # Avoid star
        self.ap.sun_avoid(scr_reg, scooping=True)

        # mnvr into position
        self.ap.set_throttle_100()
        endtime = time.time() + 5
        while time.time() < endtime:
            sleep(0.25)
            # Abort the approach if we start overheating - we are too close to the star
            if self.ap.status.get_flag(FlagsOverHeating):
                self.ap.vce.say(self.ap.locale_safe('REFUEL_ABORT_OVERHEAT', 'Refueling abort, overheating'))
                self.ap.overheat_escape(scr_reg)
                return False
        self.ap.set_throttle_50()
        sleep(1.7)
        self.ap.set_throttle_0(repeat=3)

        self.ap.refuel_cnt += 1

        # The log will not reflect a FuelScoop until first 5 tons filled, then every 5 tons until complete. If we
        # don't scoop first 5 tons with 40 sec break, since not scooping or not fast enough or not at all, then abort.
        startime = time.time()
        while not self.ap.status.get_flag(FlagsScoopingFuel):
            # check if we are being interdicted
            interdicted = self.ap.interdiction_check()
            if interdicted:
                # Continue journey after interdiction
                self.ap.set_throttle_0()

            # Abort scooping if we are overheating
            if self.ap.status.get_flag(FlagsOverHeating):
                self.ap.vce.say(self.ap.locale_safe('REFUEL_ABORT_OVERHEAT', 'Refueling abort, overheating'))
                self.ap.overheat_escape(scr_reg)
                return False

            if (time.time() - startime) > int(self.ap.config['FuelScoopTimeOut']):
                self.ap.ap_ckb('log+vce', self.ap.locale_safe('REFUEL_ABORT_SCOOP', 'Refueling abort, insufficient scooping'))
                return False

        logger.debug('refuel=refueling')
        self.ap.ap_ckb('log+vce', 'Refueling')
        self.ap.update_ap_status("Refueling")

        # The ship is stopped while scooping - the perfect moment to run the FSS/ELW scan
        # instead of stopping again later in position() (saves an accelerate-brake cycle).
        if self.ap.config["ElwScannerEnable"] and not self.ap.config.get('FastTravelMode', False):
            if self.ap.fss_detect_elw(scr_reg, restore_throttle=False):
                self.ap._elw_scanned_this_system = True

        # We started fueling, so lets give it another timeout period to fuel up
        startime = time.time()
        while not self.ap.jn.ship_state()['fuel_percent'] == 100:
            # check if we are being interdicted
            interdicted = self.ap.interdiction_check()
            if interdicted:
                # Continue journey after interdiction
                self.ap.set_throttle_0()

            # Stop scooping if we are overheating - keep whatever fuel we got
            if self.ap.status.get_flag(FlagsOverHeating):
                self.ap.ap_ckb('log+vce', self.ap.locale_safe('OVERHEAT_STOP_REFUEL', 'Overheating - stopping refuel'))
                self.ap.overheat_escape(scr_reg)
                return True

            if (time.time() - startime) > int(self.ap.config['FuelScoopTimeOut']):
                self.ap.ap_ckb('log+vce', self.ap.locale_safe('REFUEL_ABORT_SCOOP', 'Refueling abort, insufficient scooping'))
                self.ap.ship_control.pitch_up_down(20)
                return True

            if not self.ap.status.get_flag(FlagsScoopingFuel):
                self.ap.ap_ckb('log', 'Fuel scooping Ended')
                self.ap.ship_control.pitch_up_down(20)
                return True
            sleep(1)

        self.ap.ap_ckb('log', 'Refueling complete')
        self.ap.ship_control.pitch_up_down(20)
        return True
