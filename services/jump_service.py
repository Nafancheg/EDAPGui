from __future__ import annotations

import random
import threading
import time
from time import sleep
from typing import TYPE_CHECKING

from EDAP_data import *
from EDlogger import logger

if TYPE_CHECKING:
    from ED_AP import FSDAssistReturn


class JumpService:
    """ Discovery scan / positioning / FSD jump logic extracted from ED_AP. """

    def __init__(self, ed_ap):
        self.ap = ed_ap

    def honk(self):
        # Do the Discovery Scan (Honk)

        if self.ap.status.get_flag(FlagsAnalysisMode):
            if self.ap.config['DSSButton'] == 'Primary':
                logger.debug('position=scanning')
                self.ap.keys.send('PrimaryFire', state=1)
            else:
                logger.debug('position=scanning')
                self.ap.keys.send('SecondaryFire', state=1)

            sleep(float(self.ap.config['Wait_DSSScan']))  # roughly 6 seconds for DSS

            # stop pressing the Scanner button
            if self.ap.config['DSSButton'] == 'Primary':
                logger.debug('position=scanning complete')
                self.ap.keys.send('PrimaryFire', state=0)
            else:
                logger.debug('position=scanning complete')
                self.ap.keys.send('SecondaryFire', state=0)
        else:
            self.ap.ap_ckb('log', 'Not in analysis mode. Skipping discovery scan (honk).')

    def position(self, scr_reg, did_refuel=True):
        """ Position() happens after a refuel and performs
            - accelerate past sun
            - perform Discovery scan
            - perform fss (if enabled)
        @param scr_reg:
        @param did_refuel:
        @return:
        """
        logger.debug('position')
        add_time = float(self.ap.config['Wait_PastSun'])

        self.ap.set_throttle_100()

        self.ap.vce.say("Passing star")

        # Need time to move past Sun, account for slowed ship if refueled
        pause_time = add_time
        if self.ap.config["EnableRandomness"]:
            pause_time = pause_time+random.randint(0, 3)
        # need time to get away from the Sun so heat will dissipate before we use FSD
        pitched_away = False
        endtime = time.time() + pause_time
        while time.time() < endtime:
            sleep(0.5)
            # If we are heating up we are too close to the star - pitch further away from it
            if not pitched_away and self.ap.status.get_flag(FlagsOverHeating):
                self.ap.ap_ckb('log+vce', self.ap.locale_safe('OVERHEAT_PITCH_AWAY', 'Overheating, pitching away from star'))
                self.ap.nav_service.sun_avoid(scr_reg, scooping=False)
                self.ap.ship_control.pitch_up_down(20)
                pitched_away = True

        fast_travel = self.ap.config.get('FastTravelMode', False)
        if fast_travel:
            # Fast Travel - no scanning, but the ship still needs the full escape time at
            # 100% throttle. Without it we turn back towards the target (often near the
            # star) far too close to it and fly into the star.
            sleep(float(self.ap.config['Wait_HeatDissipate']))
        elif self.ap.config["ElwScannerEnable"] and not self.ap._elw_scanned_this_system:
            # Not scanned during the refuel stop - stop and scan here
            self.ap.fss_detect_elw(scr_reg)
            if self.ap.config["EnableRandomness"]:
                sleep(random.randint(0, 3))
            sleep(3)
        else:
            sleep(float(self.ap.config['Wait_HeatDissipate']))  # since not doing FSS, need to give a little more time to get away from Sun, for heat

        self.ap.vce.say("Maneuvering")

        logger.debug('position=complete')
        return True

    def jump(self, scr_reg):
        """ jump() happens after we are aligned to Target
        TODO: nees to check for Thargoid interdiction and their wave that would shut us down,
        if thargoid, then we wait until reboot and continue on.. go back into FSD and align
        @param scr_reg:
        @return:
        """
        logger.debug('jump')

        self.ap.vce.say("Frameshift Jump")

        # Stop SCO monitoring
        self.ap.stop_sco_monitoring()

        jump_tries = self.ap.config['JumpTries']
        for i in range(jump_tries):

            logger.debug('jump= try:'+str(i))
            if not self.ap._is_in_supercruise_or_space():
                logger.error('Not ready to FSD jump. jump=err1')
                raise Exception('not ready to jump')
            sleep(0.5)
            logger.debug('jump= start fsd')

            # Initiate FSD Jump
            self.ap.keys.send('HyperSuperCombination')

            res = self.ap.status.wait_for_flag_on(FlagsFsdCharging, 5)
            if not res:
                logger.error('FSD failed to charge.')
                # Charging is blocked while fuel scooping or overheating near the star.
                # Get away from the star and realign before retrying, otherwise we keep
                # flying towards the star at 100% throttle with the FSD refusing to charge.
                if (self.ap.status.get_flag(FlagsScoopingFuel) or self.ap.status.get_flag(FlagsOverHeating)
                        or self.ap.nav_service.is_sun_dead_ahead(scr_reg)):
                    self.ap.ap_ckb('log+vce', self.ap.locale_safe('JUMP_BLOCKED_STAR', 'FSD blocked by the star, escaping'))
                    self.ap.nav_service.sun_avoid(scr_reg, scooping=False)
                    self.ap.set_throttle_100()
                    sleep(float(self.ap.config['Wait_PastSun']))
                    self.ap.nav_service.mnvr_to_target(scr_reg)
                continue

            res = self.ap.status.wait_for_flag_on(FlagsFsdJump, 30)
            if not res:
                logger.warning('FSD failure to start jump timeout.')
                self.ap.nav_service.mnvr_to_target(scr_reg)  # attempt realign to target
                continue

            logger.debug('jump= in jump')
            # Wait for jump to complete. Should never err
            res = self.ap.status.wait_for_flag_off(FlagsFsdJump, 360)
            if not res:
                logger.error('FSD failure to complete jump timeout.')
                continue

            logger.debug('jump= speed 0')
            self.ap.jump_cnt = self.ap.jump_cnt+1
            self.ap.set_throttle_0(repeat=3)  # Let's be triply sure that we set speed to 0% :)
            sleep(float(self.ap.config['Wait_AfterJump']))  # wait after jump to allow graphics to stablize and accept inputs
            logger.debug('jump=complete')

            # Check EDSM online for the discovery status of this system in the background
            if self.ap.config.get('EDSMCheckEnable', True):
                self.ap.edsm_undiscovered = False
                self.ap.edsm_info = self.ap.locale_safe('EDSM_CHECKING', 'EDSM: checking...')
                threading.Thread(target=self.ap.edsm_check_system,
                                 args=(self.ap.jn.ship_state()['location'],), daemon=True).start()

            # New system - the ELW scan has not run here yet
            self.ap._elw_scanned_this_system = False

            # Start SCO monitoring ready when we drop back to SC.
            self.ap.start_sco_monitoring()

            # We completed the jump
            return True

        logger.error(f'FSD Jump failed {jump_tries} times. jump=err2')
        raise Exception("FSD Jump failure")

        # a set of convience routes to pitch, rotate by specified degress

    def fsd_assist(self, scr_reg) -> FSDAssistReturn:
        """ FSD Route Assist. Jumps repeatedly to the destination system then returns.
        @return: True when arrived in system and no in-system target exists. False when
        arrived in system and an in-system target does exist."""
        from ED_AP import FSDAssistReturn, strfdelta

        # TODO - can we enable this? Seems like a better way
        # nav_route_parser = NavRouteParser()
        logger.debug('self.jn.ship_state='+str(self.ap.jn.ship_state()))

        starttime = time.time()
        starttime -= 20  # to account for first instance not doing positioning

        # TODO - can we enable this? Seems like a better way
        # if nav_route_parser.get_last_system() is not None:
        if self.ap.jn.ship_state()['target']:
            # if we are starting docked at a station, we need to undock first
            if self.ap.status.get_flag(FlagsDocked) or self.ap.status.get_flag(FlagsLanded):
                self.ap.update_overlay()
                self.ap.docking_service.undock_seq()

        # If we are already in supercruise (e.g. manual restart), check if the sun is ahead
        # and perform the same post-jump sequence: refuel (which includes sun_avoid with
        # correct brightness threshold), then position to fly past the star
        # TODO - Add this to SC Assist?
        if self.ap._is_in_supercruise_or_space() and self.ap.nav_service.is_sun_dead_ahead(scr_reg):
            refueled = self.ap.fuel_service.refuel_new(scr_reg)
            self.ap.update_ap_status("Maneuvering")
            self.position(scr_reg, refueled)

        # Keep jumping as long as there is a system to jump to.
        # TODO - can we enable this? Seems like a better way
        # while nav_route_parser.get_last_system() is not None:
        while self.ap.jn.ship_state()['target']:
            self.ap.update_overlay()

            if self.ap.jn.ship_state()['status'] == 'in_space' or self.ap.jn.ship_state()['status'] == 'in_supercruise':
                self.ap.update_ap_status("Align")

                self.ap.nav_service.mnvr_to_target(scr_reg)

                self.ap.update_ap_status("Jump")

                self.jump(scr_reg)

                # update jump counters
                self.ap.total_dist_jumped += self.ap.jn.ship_state()['dist_jumped']
                self.ap.total_jumps = self.ap.jump_cnt + self.ap.jn.ship_state()['jumps_remains']

                # reset, upon next Jump the Journal will be updated again, unless last jump,
                # so we need to clear this out

                self.ap.jn.ship_state()['jumps_remains'] = 0

                avg_time_jump = (time.time()-starttime) / self.ap.jump_cnt

                self.ap._eta = (self.ap.total_jumps - self.ap.jump_cnt) * avg_time_jump
                self.ap._str_eta = strfdelta(tdelta=self.ap._eta, inputtype='seconds')

                self.ap.update_overlay()

                self.ap.ap_ckb('jumpcount', "Dist: {:,.1f}".format(self.ap.total_dist_jumped)+"ly" +
                            "  Jumps: {}of{}".format(self.ap.jump_cnt, self.ap.total_jumps)+"  @{}s/j".format(int(avg_time_jump)) +
                            "  Fu#: "+str(self.ap.refuel_cnt) + " ETA: "+self.ap._str_eta)
                self.ap.ap_ckb('log', 'ETA (to System): '+self.ap._str_eta)

                # Do the Discovery Scan (Honk). Skipped in Fast Travel mode.
                if not self.ap.config.get('FastTravelMode', False):
                    self.ap.honk_thread = threading.Thread(target=self.honk, daemon=True)
                    self.ap.honk_thread.start()

                # Rotate destination to roughly the top if we have a destination
                # Should make it easier to get to the destination the other side of the star
                off = self.ap.nav_service.get_compass_target_offset()
                if off:
                    self.ap.ship_control.roll_clockwise_anticlockwise(off['roll'], auto_tune=self.ap.auto_tune_rpy, cur_deg=off['roll'])

                # Refuel
                refueled = self.ap.fuel_service.refuel_new(scr_reg)

                self.ap.update_ap_status("Maneuvering")

                self.position(scr_reg, refueled)

                if self.ap.jn.ship_state()['fuel_percent'] < self.ap.config['FuelThreasholdAbortAP']:
                    self.ap.ap_ckb('log', "AP Aborting, low fuel")
                    self.ap.vce.say("AP Aborting, low fuel")
                    return FSDAssistReturn.Failed

        sleep(2)  # wait until screen stabilizes from possible last positioning

        # if there is no destination defined, we are done
        if not self.ap.have_destination(scr_reg):
            self.ap.set_throttle_0()
            self.ap.ap_ckb('log+vce', f"Destination reached, distance jumped:"+str(int(self.ap.total_dist_jumped))+" lightyears")
            if self.ap.config["AutomaticLogout"]:
                sleep(5)
                self.ap.logout()
            return FSDAssistReturn.Complete
        # else there is a destination in System, so let jump over to SC Assist
        else:
            self.ap.set_throttle_100()
            self.ap.ap_ckb('log+vce', f"System reached, preparing for supercruise")
            sleep(1)
            return FSDAssistReturn.Partial
