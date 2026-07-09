from __future__ import annotations

import json
import math
import threading
import traceback
import urllib.parse
import urllib.request
from math import atan, degrees, tan, radians
import random
from string import Formatter
from tkinter import messagebox
from typing import TypedDict

import cv2
import numpy as np

from EDAP_data import *
from JsonConfigIO import read_json_file, write_json_file
from EDPlayerSettings import EDPlayerSettings
from MachineLearning import MachLearn, ModelType
from simple_localization import LocalizationManager

from EDGraphicsSettings import EDGraphicsSettings
from EDShipControl import EDShipControl, CompassTargetOffset
from EDlogger import logging
from services.docking_service import DockingService
from services.elw_advisor import ElwAdvisor
from services.fuel_service import FuelService
from services.jump_service import JumpService
from services.navigation_service import NavigationService
import Image_Templates
import Screen
import Screen_Regions
from EDJournal import *
from EDKeys import *
from NavRouteParser import NavRouteParser
from OCR import OCR
from EDNavigationPanel import EDNavigationPanel
from Overlay import *
from StatusParser import StatusParser
from Voice import *

"""
File:EDAP.py    EDAutopilot

Description:

Note:
Ideas taken from: https://github.com/skai2/EDAutopilot

Author: sumzer0@yahoo.com
"""


# Exception class used to unroll the call tree to to stop execution
class EDAP_Interrupt(Exception):
    pass


class ScTargetAlignReturn(Enum):
    Lost = 1
    Found = 2
    Disengage = 3
    Overheat = 4


class FSDAssistReturn(Enum):
    Failed = 0  # Failed to reach system
    Partial = 1  # Reached final system, but there is a local destination
    Complete = 2  # Reached final system and there is no local destination


class TargetOffset(TypedDict):
    """
    Dictionary containing target information.
    """
    roll: float
    pit: float
    yaw: float
    occ: bool


class CompassOffset(TypedDict):
    """
    Dictionary containing navigation (compass) information.
    """
    x: float
    y: float
    z: float
    roll: float
    pit: float
    yaw: float


class EDAutopilot:

    def __init__(self, cb, do_thread=True):
        self.config = {}
        self.ship_configs = {
            "Ship_Configs": {},  # Dictionary of ship types with additional settings
        }
        self._sc_sco_active_loop_thread = None
        self._sc_sco_active_loop_enable = False
        self.sc_sco_is_active = 0
        self._sc_sco_active_on_ls = 0
        self._prev_star_system = None
        self.honk_thread = None
        self.speed_demand = None  # 'Speed0', 'Speed50', 'Speed100', 'SCSpeed0', 'SCSpeed50' or 'SCSpeed100'
        self._ocr = None
        self._mach_learn = None
        self._sc_disengage_active = False  # Is SC Disengage active
        self.ship_tst_roll_enabled = False
        self.ship_tst_pitch_enabled = False
        self.ship_tst_yaw_enabled = False

        # Load AP.json config
        self.load_config()

        # Load selected language. The locales/*.json phrases mirror what the
        # GAME renders on screen in that language, so Language doubles as the
        # source of OCR reference phrases — keep OCRLanguage (the PaddleOCR
        # recognition model) consistent with it or screen text won't match.
        self.locale = LocalizationManager('locales', self.config['Language'])
        if self.config['Language'] != self.config['OCRLanguage']:
            logger.warning(f"Language={self.config['Language']!r} but "
                           f"OCRLanguage={self.config['OCRLanguage']!r}: the OCR model may not "
                           "read the game's script, breaking disengage/nav-panel detection.")

        # config the voice interface
        self.vce = Voice()
        self.vce.v_enabled = self.config['VoiceEnable']
        self.vce.set_voice_id(self.config['VoiceID'])
        self.vce.say("Welcome to Autopilot")

        # set log level based on config input, defaulting to warning
        logger.setLevel(logging.WARNING)
        if self.config['LogINFO']:
            logger.setLevel(logging.INFO)
        if self.config['LogDEBUG']:
            logger.setLevel(logging.DEBUG)

        # initialize all to false
        self.fsd_assist_enabled = False
        self.sc_assist_enabled = False

        # Create instance of each of the needed Classes
        self.scr = Screen.Screen(cb)
        self.scr.scaleX = self.config['ScreenScale']
        self.scr.scaleY = self.config['ScreenScale']

        self.gfx_settings = EDGraphicsSettings()
        # Aspect ratio greater than 1920/1080 (1.7777) seems to be the magic cutoff. At > 1920/1080 (1.7777), the FOV
        # appears to be the top of the screen. Looks like FDev made the FOV for 1920x1080 resolution height.
        if self.scr.aspect_ratio >= 1.7777:
            self.ver_fov = round(float(self.gfx_settings.fov), 4)
            logger.debug(f'Vertical FOV: {self.ver_fov} deg (-{self.ver_fov / 2} to {self.ver_fov / 2} deg).')
            self.hor_fov = round(self.ver_fov * self.scr.aspect_ratio, 4)
            logger.debug(f'Horizontal FOV: {self.hor_fov} deg (-{self.hor_fov / 2} to {self.hor_fov / 2} deg).')
        else:
            self.ver_fov = round(float(self.gfx_settings.fov) * (1.7777 / self.scr.aspect_ratio), 4)
            logger.debug(f'Vertical FOV: {self.ver_fov} deg (-{self.ver_fov / 2} to {self.ver_fov / 2}).')
            self.hor_fov = round(self.ver_fov * self.scr.aspect_ratio, 4)
            logger.debug(f'Horizontal FOV: {self.hor_fov} deg (-{self.hor_fov / 2} to {self.hor_fov / 2}).')

        self.player_settings = EDPlayerSettings(cb, locale=self.locale)

        self.templ = Image_Templates.Image_Templates(self.scr.scaleX, self.scr.scaleY)
        self.scrReg = Screen_Regions.Screen_Regions(self.scr, self.templ)
        self.jn = EDJournal(cb)

        # Check the actual game session language (journal Fileheader) against the language
        # the active locale's OCR strings are written for.
        game_language = self.jn.get_game_language().split('/')[0]  # 'Russian/RU' -> 'Russian'
        expected_language = self.locale_safe('OCR_GAME_LANGUAGE', 'English')
        if game_language and game_language != expected_language:
            msg = self.locale_safe(
                'LOG_ED_LANGUAGE_MISMATCH',
                "ED interface language is '{game}', but the selected EDAP locale expects '{expected}' for"
                " screen text recognition (OCR). Set the game language to '{expected}' or switch the EDAP"
                " language.").format(game=game_language, expected=expected_language)
            cb('log', f"WARNING: {msg}")
            logger.warning(f"WARNING: {msg}")

        self.keys = EDKeys(cb, locale=self.locale)
        self.status = StatusParser()
        self.nav_route = NavRouteParser()
        self.ship_control = EDShipControl(self, self.scr, self.keys, cb)
        self.fuel_service = FuelService(self)
        self.nav_service = NavigationService(self)
        self.jump_service = JumpService(self)
        self.docking_service = DockingService(self)
        self.elw_advisor = ElwAdvisor(self)
        self.nav_panel = EDNavigationPanel(self, self.scr, self.keys, cb)

        # Set defaults for data read from ships config
        self.yawrate = 8.0
        self.rollrate = 80.0
        self.pitchrate = 33.0
        self.sunpitchuptime = 0.0

        self.ap_ckb = cb

        self.load_ship_configs()

        self.jump_cnt = 0
        self._eta = 0
        self._str_eta = ''
        self.total_dist_jumped = 0
        self.total_jumps = 0
        self.refuel_cnt = 0
        self.current_ship_type = None
        self.current_ship_cfg = None
        self.gui_loaded = False
        # self._nav_cor_x = 0.0  # Nav Point correction to pitch
        # self._nav_cor_y = 0.0  # Nav Point correction to yaw
        self.target_align_outer_lim = 1.0  # In deg. Anything outside of this range will cause alignment.
        self.target_align_inner_lim = 0.5  # In deg. Will stop alignment when in this range.
        self.debug_show_compass_overlay = False
        self.debug_show_target_overlay = False

        # Overlay vars
        self.ap_state = "Idle"
        self.fss_detected = self.locale_safe('ELW_NOTHING_FOUND', 'nothing found')
        self.edsm_info = ""
        self.edsm_undiscovered = False
        self._elw_scanned_this_system = False

        # FSS scan advisor state (journal-driven, see poll_body_scans)
        self._fss_announced = None       # None => first poll seeds silently (journal replay guard)
        self._fss_pending = set()        # bodies seen once, announced on the NEXT poll
        self._fss_honk_announced = False
        self._fss_allfound_announced = False
        self._fss_last_system = ''
        self._fss_valuables = []         # list[(short_name, marker_str)] for the status lines

        # Initialize the Overlay class
        self.overlay = Overlay("", elite=1)
        self.overlay.overlay_setfont(self.config['OverlayTextFont'], self.config['OverlayTextFontSize'])
        self.overlay.overlay_set_pos(self.config['OverlayTextXOffset'], self.config['OverlayTextYOffset'])
        # must be called after we initialized the objects above
        self.update_overlay()

        self.debug_overlay = False
        self.debug_ocr = False
        self.debug_images = False
        self.auto_tune_rpy = False
        self.debug_image_folder = './debug-output/images'
        if not os.path.exists(self.debug_image_folder):
            os.makedirs(self.debug_image_folder)

        # debug window
        self.cv_view = False
        self.cv_view_x = 10
        self.cv_view_y = 10

        # start the engine thread
        self.terminate = False  # terminate used by the thread to exit its loop
        if do_thread:
            self.ap_thread = kthread.KThread(target=self.engine_loop, name="EDAutopilot")
            self.ap_thread.start()

        # Start thread to delete old log files.
        del_log_files_thread = threading.Thread(target=delete_old_log_files, daemon=True)
        del_log_files_thread.start()

        # Process config[] settings to update classes as necessary
        self.process_config_settings()

    @property
    def mach_learn(self) -> MachLearn:
        """ Load Machine Learning class when needed. """
        if not self._mach_learn:
            self._mach_learn = MachLearn(self, self.ap_ckb)
        return self._mach_learn

    @property
    def ocr(self) -> OCR:
        """ Load OCR class when needed. """
        if not self._ocr:
            self._ocr = OCR(self, self.scr)
        return self._ocr

    def locale_safe(self, key: str, default: str) -> str:
        """ Safely looks up a locale string, falling back to default if unavailable. """
        try:
            return self.locale[key]
        except Exception:
            return default

    def update_config(self):
        # Get values from classes
        if self.keys:
            self.config['ActivateEliteEachKey'] = self.keys.activate_window
            self.config['Key_ModDelay'] = self.keys.key_mod_delay
            self.config['Key_DefHoldTime'] = self.keys.key_def_hold_time
            self.config['Key_RepeatDelay'] = self.keys.key_repeat_delay

        # Delete old settings
        self.config.pop('target_align_inertia_pitch_factor', None)
        self.config.pop('target_align_inertia_yaw_factor', None)

        write_json_file(self.config, filepath='./configs/AP.json')

    def load_config(self):
        """ Load AP.Json Config File. """
        # NOTE!!! When adding a new config value below, add the same after read_config() to set
        # a default value or an error will occur reading the new value!
        self.config = {
            "DSSButton": "Primary",  # if anything other than "Primary", it will use the Secondary Fire button for DSS
            "JumpTries": 3,  #
            "NavAlignTries": 3,  #
            "RefuelThreshold": 65,  # if fuel level get below this level, it will attempt refuel
            "FuelThreasholdAbortAP": 10,  # level at which AP will terminate, because we are not scooping well
            "WaitForAutoDockTimer": 240,  # After docking granted, wait this amount of time for us to get docked with autodocking
            "SunBrightThreshold": 125,  # The low level for brightness detection, range 0-255, want to mask out darker items
            "FuelScoopTimeOut": 35,  # number of second to wait for full tank, might mean we are not scooping well or got a small scooper
            "DockingRetries": 30,  # number of time to attempt docking
            "HotKey_StartFSD": "home",  # if going to use other keys, need to look at the python keyboard package
            "HotKey_StartSC": "ins",  # to determine other keynames, make sure these keys are not used in ED bindings
            "HotKey_StopAllAssists": "end",
            "EnableRandomness": False,  # add some additional random sleep times to avoid AP detection (0-3sec at specific locations)
            "ActivateEliteEachKey": False,  # Activate Elite window before each key or group of keys
            "OverlayTextEnable": False,  # Experimental at this stage
            "OverlayTextYOffset": 400,  # offset down the screen to start place overlay text
            "OverlayTextXOffset": 50,  # offset left the screen to start place overlay text
            "OverlayTextFont": "Eurostyle",
            "OverlayTextFontSize": 14,
            "OverlayGraphicEnable": False,  # not implemented yet
            "DiscordWebhook": False,  # discord not implemented yet
            "DiscordWebhookURL": "",
            "DiscordUserID": "",
            "VoiceEnable": False,
            "VoiceID": 1,  # my Windows only have 3 defined (0-2)
            "ElwScannerEnable": False,
            "LogDEBUG": False,  # enable for debug messages (per-frame key sends, compass reads — very noisy)
            "LogINFO": True,
            "Enable_CV_View": 0,  # Should CV View be enabled by default
            "ShipConfigFile": None,  # Ship config to load on start - deprecated
            "TargetScale": 1.0,  # Scaling of the target when a system is selected
            "ScreenScale": 1.0,  # Scaling of the target when a system is selected
            "AutomaticLogout": False,  # Logout when we are done with the mission
            "FCDepartureTime": 5.0,  # Extra time to fly away from a Fleet Carrier
            "FCDepartureAngle": 90.0,  # Angle to pitch up when leaving a Fleet Carrier
            "OCDepartureAngle": 90.0,  # Angle to pitch up when leaving an Orbital Construction Site
            "Language": 'en',  # Language (matching ./locales/xx.json file)
            "OCRLanguage": 'en',  # Language for OCR detection (see OCR language doc in \docs)
            "OCRMobile": False,  # Use the mobile (light) version which is smaller and faster, but less accurate.
            "DebugOverlay": False,
            "HotkeysEnable": False,  # Enable hotkeys
            "DebugOCR": False,  # For debug, write all OCR data to output folder
            "DebugImages": False,  # For debug, write debug images to output folder
            "Key_ModDelay": 0.01,  # Delay for key modifiers to ensure modifier is detected before/after the key
            "Key_DefHoldTime": 0.2,  # Default hold time for a key press
            "Key_RepeatDelay": 0.1,  # Delay between key press repeats
            "DisengageUseMatch": False,  # For 'Disengage' use old image match instead of OCR
            "target_align_outer_lim": 1.0,  # For test
            "target_align_inner_lim": 0.5,  # For test
            "jump_align_outer_lim": 3.0,  # In deg. Alignment tolerance before an FSD jump (FSD self-corrects within its cone)
            "jump_align_inner_lim": 2.0,  # In deg. Stop aligning for an FSD jump when within this range
            "EDSMCheckEnable": True,  # Query EDSM after each jump for system discovery status (shown in overlay)
            "FastTravelMode": False,  # Skip honk/FSS scans and extra waits to travel as fast as possible
            "Debug_ShowCompassOverlay": False,  # For test
            "Debug_ShowTargetOverlay": False,  # For test
            "PlanetDepartureSCOTime": 5.0,  # SCO boost time when leaving planet in secs
            "AutoTuneRPYRates": False,  # Enable auto-tune for RPY rates.
            "Wait_FSSDetect": 2.5,  # Wait after entering FSS before capturing the screen for ELW detection
            "Wait_DockApproach": 12.0,  # Time at 50% throttle to get within 7.5km of the station before requesting docking
            "Wait_ShipStop": 3.0,  # Wait for the ship to come to a stop after setting throttle to 0
            "Wait_OccludedReposition": 15.0,  # Time at 100% throttle to fly clear when target is occluded
            "Wait_DSSScan": 7.0,  # Time to hold the DSS (honk) button, scan takes roughly 6 seconds
            "Wait_PastSun": 12.0,  # Time at 100% throttle to get away from the sun after a jump
            "Wait_HeatDissipate": 5.0,  # Extra time to let heat dissipate before using FSD (when FSS is disabled)
            "Wait_AfterJump": 1.0,  # Wait after a jump completes to allow graphics to stabilize and accept inputs
        }
        # NOTE!!! When adding a new config value above, add the same after read_config() to set
        # a default value or an error will occur reading the new value!

        cnf = read_json_file(filepath='./configs/AP.json')
        # if we read it then point to it, otherwise use the default table above
        if cnf is not None:
            # NOTE!!! Add default values for new entries below!
            if 'SunBrightThreshold' not in cnf:
                cnf['SunBrightThreshold'] = 125
            if 'ScreenScale' not in cnf:
                cnf['ScreenScale'] = 1.0
            if 'AutomaticLogout' not in cnf:
                cnf['AutomaticLogout'] = False
            if 'FCDepartureTime' not in cnf:
                cnf['FCDepartureTime'] = 5.0
            if 'Language' not in cnf:
                cnf['Language'] = 'en'
            if 'OCRLanguage' not in cnf:
                cnf['OCRLanguage'] = 'en'
            if 'OCRMobile' not in cnf:
                cnf['OCRMobile'] = False
            if 'DebugOverlay' not in cnf:
                cnf['DebugOverlay'] = False
            if 'HotkeysEnable' not in cnf:
                cnf['HotkeysEnable'] = False
            if 'DebugOCR' not in cnf:
                cnf['DebugOCR'] = False
            if 'DebugImages' not in cnf:
                cnf['DebugImages'] = False
            if 'Key_ModDelay' not in cnf:
                cnf['Key_ModDelay'] = 0.01
            if 'Key_DefHoldTime' not in cnf:
                cnf['Key_DefHoldTime'] = 0.2
            if 'Key_RepeatDelay' not in cnf:
                cnf['Key_RepeatDelay'] = 0.1
            if 'DisengageUseMatch' not in cnf:
                cnf['DisengageUseMatch'] = False
            if 'target_align_outer_lim' not in cnf:
                cnf['target_align_outer_lim'] = 1.0  # For test
            if 'target_align_inner_lim' not in cnf:
                cnf['target_align_inner_lim'] = 0.5  # For test
            if 'jump_align_outer_lim' not in cnf:
                cnf['jump_align_outer_lim'] = 3.0
            if 'jump_align_inner_lim' not in cnf:
                cnf['jump_align_inner_lim'] = 2.0
            if 'EDSMCheckEnable' not in cnf:
                cnf['EDSMCheckEnable'] = True
            if 'FastTravelMode' not in cnf:
                cnf['FastTravelMode'] = False
            if 'Debug_ShowCompassOverlay' not in cnf:
                cnf['Debug_ShowCompassOverlay'] = False  # For test
            if 'Debug_ShowTargetOverlay' not in cnf:
                cnf['Debug_ShowTargetOverlay'] = False  # For test
            if 'FCDepartureAngle' not in cnf:
                cnf['FCDepartureAngle'] = 90.0
            if 'OCDepartureAngle' not in cnf:
                cnf['OCDepartureAngle'] = 90.0
            if 'PlanetDepartureSCOTime' not in cnf:
                cnf['PlanetDepartureSCOTime'] = 5.0
            if 'AutoTuneRPYRates' not in cnf:
                cnf['AutoTuneRPYRates'] = ""
            if 'Wait_FSSDetect' not in cnf:
                cnf['Wait_FSSDetect'] = 2.5
            if 'Wait_DockApproach' not in cnf:
                cnf['Wait_DockApproach'] = 12.0
            if 'Wait_ShipStop' not in cnf:
                cnf['Wait_ShipStop'] = 3.0
            if 'Wait_OccludedReposition' not in cnf:
                cnf['Wait_OccludedReposition'] = 15.0
            if 'Wait_DSSScan' not in cnf:
                cnf['Wait_DSSScan'] = 7.0
            if 'Wait_PastSun' not in cnf:
                cnf['Wait_PastSun'] = 12.0
            if 'Wait_HeatDissipate' not in cnf:
                cnf['Wait_HeatDissipate'] = 5.0
            if 'Wait_AfterJump' not in cnf:
                cnf['Wait_AfterJump'] = 1.0
            self.config = cnf
            logger.debug("read AP json:" + str(cnf))
        else:
            write_json_file(self.config, filepath='./configs/AP.json')

    def load_ship_configs(self):
        """
        Load all the ship configs from the ship_configs.json file.
        @return: N/A
        """
        shp_cnf = read_json_file(filepath='./configs/ship_configs.json')

        # if we read
        # it then point to it, otherwise use the default table above
        if shp_cnf is not None:
            # Add default values for new entries
            if 'Ship_Configs' not in shp_cnf:
                shp_cnf['Ship_Configs'] = dict()
            self.ship_configs = shp_cnf
            logger.debug("read Ships Config json:" + str(shp_cnf))
        else:
            write_json_file(self.ship_configs, filepath='./configs/ship_configs.json')

        # Load ship configuration with proper hierarchy
        if self.jn:
            ship = self.jn.ship_state()['type']
            if ship:
                self.load_ship_configuration(ship)

    def update_ship_configs(self) -> bool:
        """ Update the user's ship configuration file.
        Returns True if the config was written, False when there is no ship
        to save (on foot / ship not detected yet)."""
        # Check if a ship and not a suit (on foot)
        if self.current_ship_type in ship_size_map:
            # Ensure ship entry exists in config
            if self.current_ship_type not in self.ship_configs['Ship_Configs']:
                self.ship_configs['Ship_Configs'][self.current_ship_type] = {}
                logger.debug(f"Created new ship config entry for: {self.current_ship_type}")

            self.current_ship_cfg = self.ship_configs['Ship_Configs'][self.current_ship_type]

            self.current_ship_cfg['PitchRate'] = self.pitchrate
            self.current_ship_cfg['RollRate'] = self.rollrate
            self.current_ship_cfg['YawRate'] = self.yawrate
            self.current_ship_cfg['SunPitchUp+Time'] = self.sunpitchuptime

            write_json_file(self.ship_configs, filepath='./configs/ship_configs.json')
            logger.debug(f"Saved ship config for: {self.current_ship_type}")
            return True
        return False

    def load_ship_configuration(self, ship_type):
        """ Load ship configuration with the following priority:
            1. User's ship values from ship_configs.json file
            2. Default ship values from default_ships_cfg_sc_50.json file
            3. Hardcoded default values
        """
        self.ap_ckb('log', f"Loading ship configuration for your {ship_type}")

        # Step 1: Use hardcoded defaults
        self.rollrate = 80.0
        self.pitchrate = 33.0
        self.yawrate = 8.0
        self.sunpitchuptime = 0.0
        logger.info(f"Loaded hardcoded default configuration for {ship_type}")

        # Step 2: Try to load defaults from ship file
        if ship_type in ship_rpy_sc_50:
            ship_defaults = ship_rpy_sc_50[ship_type]
            # Use default configuration - this means it's been modified and saved to ship_configs.json
            self.rollrate = ship_defaults.get('RollRate', 80.0)
            self.pitchrate = ship_defaults.get('PitchRate', 33.0)
            self.yawrate = ship_defaults.get('YawRate', 8.0)
            self.sunpitchuptime = ship_defaults.get('SunPitchUp+Time', 0.0)
            logger.info(f"Loaded default configuration for {ship_type} from default ship cfg file")

        # Add empty entry to ship_configs for future customization
        if ship_type not in self.ship_configs['Ship_Configs']:
            self.ship_configs['Ship_Configs'][ship_type] = dict()

        # Step 3: Check if we have custom config in ship_configs.json (skip if forcing defaults)
        current_ship_cfg = self.ship_configs['Ship_Configs'][ship_type]
        # Check if the custom config has actual values (not just empty dict)
        if any(key in current_ship_cfg for key in ['RollRate', 'PitchRate', 'YawRate', 'SunPitchUp+Time']):
            # Use custom configuration - this means it's been modified and saved to ship_configs.json
            self.rollrate = current_ship_cfg.get('RollRate', 80.0)
            self.pitchrate = current_ship_cfg.get('PitchRate', 33.0)
            self.yawrate = current_ship_cfg.get('YawRate', 8.0)
            self.sunpitchuptime = current_ship_cfg.get('SunPitchUp+Time', 0.0)
            logger.info(f"Loaded your custom configuration for {ship_type} from ship_configs.json")

        for spd_dmd in ['Speed0', 'Speed50', 'Speed100', 'SCSpeed0', 'SCSpeed50', 'SCSpeed100']:
            # Check RPY Calibration
            if spd_dmd not in current_ship_cfg:
                self.ap_ckb('log', "WARNING: Perform Roll/Pitch/Yaw Calibration on this ship.")
                current_ship_cfg[spd_dmd] = dict()

            spd_dmd_dict = current_ship_cfg[spd_dmd]
            if 'RollRate' not in spd_dmd_dict:
                self.ap_ckb('log', "WARNING: Perform Roll Calibration on this ship.")
                # Default roll rates at 5, 45 and 90 deg
                spd_dmd_dict['RollRate'] = {"5.0": self.rollrate / 2,
                                            "45.0": self.rollrate,
                                            "60.0": self.rollrate}
            if 'PitchRate' not in spd_dmd_dict:
                self.ap_ckb('log', "WARNING: Perform Pitch Calibration on this ship.")
                # Default pitch rates at 0.5, 30 and 90 deg
                spd_dmd_dict['PitchRate'] = {"0.5": self.pitchrate / 2,
                                             "30.0": self.pitchrate,
                                             "60.0": self.pitchrate}
            if 'YawRate' not in spd_dmd_dict:
                self.ap_ckb('log', "WARNING: Perform Yaw Calibration on this ship.")
                # Default yaw rates at 0.5, 30 and 90 deg
                spd_dmd_dict['YawRate'] = {"0.5": self.yawrate / 2,
                                           "30.0": self.yawrate,
                                           "60.0": self.yawrate}

    def get_status_lines(self) -> list[tuple[str, bool]]:
        """ Build the status lines shown in the overlay and the GUI mini panel.
        @return: A list of (text, highlight) tuples. """
        ap_mode = "Offline"
        if self.fsd_assist_enabled:
            ap_mode = "FSD Route Assist"
        elif self.sc_assist_enabled:
            ap_mode = "SC Assist"

        ship_state = self.jn.ship_state()['status']
        if ship_state is None:
            ship_state = '<init>'

        sclass = self.jn.ship_state()['star_class']
        if sclass is None:
            sclass = "<init>"

        location = self.jn.ship_state()['location']
        if location is None:
            location = "<init>"

        fuel = self.jn.ship_state()['fuel_percent']
        fuel_str = f"{fuel}%" if fuel is not None else "?"

        scoopable = " " + self.locale_safe('OVL_SCOOPABLE', '(scoopable)') if sclass in ['F', 'O', 'G', 'K', 'B', 'A', 'M'] else ""

        target = self.jn.ship_state()['target']
        if not target:
            target = "-"
        jumps_left = self.jn.ship_state()['jumps_remains']
        target_str = target if not jumps_left else f"{target} ({jumps_left} {self.locale_safe('OVL_JUMPS_LEFT', 'jumps left')})"

        lines = [
            (self.locale_safe('OVL_AP_MODE', 'AP MODE')+": "+ap_mode, False),
            (self.locale_safe('OVL_AP_STATUS', 'AP STATUS')+": "+self.ap_state, False),
            (self.locale_safe('OVL_SHIP', 'SHIP')+": "+ship_state+" | "+self.locale_safe('OVL_FUEL', 'FUEL')+": "+fuel_str, False),
            (self.locale_safe('OVL_CURRENT_SYSTEM', 'CURRENT SYSTEM')+": "+location+", "+sclass+scoopable, False),
            (self.locale_safe('OVL_TARGET', 'TARGET')+": "+target_str, False),
            ("{}: {} {} {} | {}: {:,.0f} ly".format(
                self.locale_safe('OVL_JUMPS', 'JUMPS'), self.jump_cnt, self.locale_safe('OVL_OF', 'of'),
                self.total_jumps, self.locale_safe('OVL_DIST', 'DIST'), self.total_dist_jumped), False),
            (self.locale_safe('OVL_ETA', 'ETA (to System)')+": "+self._str_eta, False),
        ]
        if self.config["ElwScannerEnable"]:
            lines.append((self.locale_safe('OVL_ELW_SCANNER', 'ELW SCANNER')+": "+self.fss_detected, False))
        if self.edsm_info:
            # Highlight a potentially undiscovered system
            lines.append((self.edsm_info, self.edsm_undiscovered))

        # FSS scan advisor: progress and the latest valuable bodies of the current system
        ship = self.jn.ship_state()
        if ship.get('fss_honk_done') or ship.get('scanned_bodies'):
            scanned = sum(1 for e in ship['scanned_bodies'].values() if e.get('has_scan'))
            total = ship.get('fss_body_count', 0)
            prog = f"{scanned}/{total}" if total else str(scanned)
            if ship.get('fss_all_found'):
                prog += " " + self.locale_safe('FSS_COMPLETE_MARK', 'DONE')
            lines.append((self.locale_safe('OVL_FSS_PROGRESS', 'FSS SCAN') + ": " + prog, False))
            for nm, marker in self._fss_valuables[-4:]:
                lines.append((f"  {nm}: {marker}", True))
        return lines

    def get_status_dict(self) -> dict:
        """ Structured telemetry snapshot, sourced from the same fields as
        get_status_lines() but returned as machine-readable JSON-friendly data
        (not pre-joined display strings) for the headless web server.
        Pure/read-only: no side effects. """
        if self.fsd_assist_enabled:
            ap_mode = "fsd"
        elif self.sc_assist_enabled:
            ap_mode = "sc"
        else:
            ap_mode = "offline"

        ship = self.jn.ship_state()
        star_class = ship['star_class']

        return {
            "ap_mode": ap_mode,
            "ap_state": self.ap_state,
            "ship_status": ship['status'],
            "fuel_percent": ship['fuel_percent'],
            "location": ship['location'],
            "star_class": star_class,
            "scoopable": bool(star_class in ['F', 'O', 'G', 'K', 'B', 'A', 'M']),
            "target": ship['target'],
            "jumps_remaining": ship['jumps_remains'],
            "jump_cnt": self.jump_cnt,
            "total_jumps": self.total_jumps,
            "total_dist_jumped": self.total_dist_jumped,
            "eta": self._str_eta,
            "elw_scanner": self.fss_detected if self.config["ElwScannerEnable"] else None,
            "edsm_info": self.edsm_info or None,
        }

    def update_overlay(self):
        """ Draw the overlay data on the ED Window """
        if self.config['OverlayTextEnable']:
            lines = self.get_status_lines()
            for i, (txt, highlight) in enumerate(lines, start=1):
                color = (0, 180, 0) if highlight else (136, 53, 0)
                self.overlay.overlay_text(str(i), txt, i, 1, color, -1)
            # Clear the unused line slots (e.g. when the ELW/EDSM/FSS lines disappear)
            for i in range(len(lines) + 1, 15):
                self.overlay.overlay_remove_text(str(i))
            self.overlay.overlay_paint()

    def update_ap_status(self, txt):
        self.ap_state = txt
        self.update_overlay()
        self.ap_ckb('statusline', txt)

    def process_config_settings(self):
        """ Update subclasses as necessary with config setting changes. """
        if self.keys:
            self.keys.activate_window = self.config['ActivateEliteEachKey']
            self.keys.key_mod_delay = self.config['Key_ModDelay']
            self.keys.key_def_hold_time = self.config['Key_DefHoldTime']
            self.keys.key_repeat_delay = self.config['Key_RepeatDelay']

        self.target_align_outer_lim = self.config['target_align_outer_lim']
        self.target_align_inner_lim = self.config['target_align_inner_lim']

        self.cv_view = self.config['Enable_CV_View']
        self.debug_show_compass_overlay = self.config['Debug_ShowCompassOverlay']
        self.debug_show_target_overlay = self.config['Debug_ShowTargetOverlay']
        self.debug_overlay = self.config['DebugOverlay']
        self.debug_ocr = self.config['DebugOCR']
        self.debug_images = self.config['DebugImages']
        self.auto_tune_rpy = self.config['AutoTuneRPYRates']

    def draw_match_rect(self, img, pt1, pt2, color, thick):
        """ Draws the matching rectangle within the image. """
        wid = pt2[0]-pt1[0]
        hgt = pt2[1]-pt1[1]

        if wid < 20:
            # cv2.rectangle(screen, pt, (pt[0] + compass_width, pt[1] + compass_height),  (0,0,255), 2)
            cv2.rectangle(img, (int(pt1[0]), int(pt1[1])), (int(pt2[0]), int(pt2[1])), color, thick)
        else:
            len_wid = wid/5
            len_hgt = hgt/5
            half_wid = wid/2
            half_hgt = hgt/2
            tic_len = thick-1
            # top
            cv2.line(img, (int(pt1[0]), int(pt1[1])), (int(pt1[0]+len_wid), int(pt1[1])), color, thick)
            cv2.line(img, (int(pt1[0]+(2*len_wid)), int(pt1[1])), (int(pt1[0]+(3*len_wid)), int(pt1[1])), color, 1)
            cv2.line(img, (int(pt1[0]+(4*len_wid)), int(pt1[1])), (int(pt2[0]), int(pt1[1])), color, thick)
            # top tic
            cv2.line(img, (int(pt1[0]+half_wid), int(pt1[1])), (int(pt1[0]+half_wid), int(pt1[1])-tic_len), color, thick)
            # bot
            cv2.line(img, (int(pt1[0]), int(pt2[1])), (int(pt1[0]+len_wid), int(pt2[1])), color, thick)
            cv2.line(img, (int(pt1[0]+(2*len_wid)), int(pt2[1])), (int(pt1[0]+(3*len_wid)), int(pt2[1])), color, 1)
            cv2.line(img, (int(pt1[0]+(4*len_wid)), int(pt2[1])), (int(pt2[0]), int(pt2[1])), color, thick)
            # bot tic
            cv2.line(img, (int(pt1[0]+half_wid), int(pt2[1])), (int(pt1[0]+half_wid), int(pt2[1])+tic_len), color, thick)
            # left
            cv2.line(img, (int(pt1[0]), int(pt1[1])), (int(pt1[0]), int(pt1[1]+len_hgt)), color, thick)
            cv2.line(img, (int(pt1[0]), int(pt1[1]+(2*len_hgt))), (int(pt1[0]), int(pt1[1]+(3*len_hgt))), color, 1)
            cv2.line(img, (int(pt1[0]), int(pt1[1]+(4*len_hgt))), (int(pt1[0]), int(pt2[1])), color, thick)
            # left tic
            cv2.line(img, (int(pt1[0]), int(pt1[1]+half_hgt)), (int(pt1[0]-tic_len), int(pt1[1]+half_hgt)), color, thick)
            # right
            cv2.line(img, (int(pt2[0]), int(pt1[1])), (int(pt2[0]), int(pt1[1]+len_hgt)), color, thick)
            cv2.line(img, (int(pt2[0]), int(pt1[1]+(2*len_hgt))), (int(pt2[0]), int(pt1[1]+(3*len_hgt))), color, 1)
            cv2.line(img, (int(pt2[0]), int(pt1[1]+(4*len_hgt))), (int(pt2[0]), int(pt2[1])), color, thick)
            # right tic
            cv2.line(img, (int(pt2[0]), int(pt1[1]+half_hgt)), (int(pt2[0]+tic_len), int(pt1[1]+half_hgt)), color, thick)

    def calibrate_region(self, range_low, range_high, range_step, threshold: float, reg_name: str, templ_name: str, no_overlay: bool = False):
        """ Find the best scale value in the given range of scales with the passed in threshold
        @param reg_name:
        @param range_low: Lowest scaling value (0-100%)
        @param range_high: Highest scaling value (0-100%)
        @param range_step: Scaling value step increment (0-100%) for each loop
        @param threshold: The minimum threshold to match (0.0 - 1.0)
        @param templ_name: The region name i.i 'compass' or 'target'
        @param no_overlay: Do not show overlay.
        @return:
        """
        scale = 0
        max_pick = 0
        i = range_low
        while i <= range_high:
            scale_x = float(i / 100)
            scale_y = scale_x

            # reload the templates with this scale value
            self.templ.reload_templates(scale_x, scale_y)

            # do image matching on the compass and the target
            image, (minVal, maxVal, minLoc, maxLoc), match = self.scrReg.match_template_in_region_x3(reg_name, templ_name)

            if not no_overlay:
                border = 10  # border to prevent the box from interfering with future matches
                reg_pos = self.scrReg.reg[reg_name]['rect']
                width = self.scrReg.templates.template[templ_name]['width'] + border + border
                height = self.scrReg.templates.template[templ_name]['height'] + border + border
                left = reg_pos[0] + maxLoc[0] - border
                top = reg_pos[1] + maxLoc[1] - border

                if maxVal > threshold and maxVal > max_pick:
                    # Draw box around region
                    self.overlay.overlay_rect(20, (left, top), (left + width, top + height), (0, 255, 0), 2)
                    self.overlay.overlay_floating_text(20, f'Match: {maxVal:5.4f}(%)', left, top - 25, (0, 255, 0))
                else:
                    # Draw box around region
                    self.overlay.overlay_rect(21, (left, top), (left + width, top + height), (255, 0, 0), 2)
                    self.overlay.overlay_floating_text(21, f'Match: {maxVal:5.4f}(%)', left, top - 25, (255, 0, 0))

                self.overlay.overlay_paint()

            # Check the match percentage
            if maxVal > threshold:
                if maxVal > max_pick:
                    max_pick = maxVal
                    scale = i
                    # self.ap_ckb('log', 'Cal: Found match:' + f'{max_pick:5.4f}' + "% with scale:" + f'{self.scr.scaleX:5.4f}')

            # Next range
            i = i + range_step

        return scale, max_pick

    def calibrate_target(self):
        """ Routine to find the optimal scaling values for the template images. """
        msg = 'Select OK to begin Calibration. You must be in space and have a star system targeted in center screen.'
        self.vce.say(msg)
        ans = messagebox.askokcancel('Calibration', msg)
        if not ans:
            return

        self.ap_ckb('log+vce', 'Calibration starting.')

        set_focus_elite_window()

        # Draw the target and compass regions on the screen
        key = 'target'
        targ_region = self.scrReg.reg[key]
        self.overlay.overlay_rect1('calib_target', targ_region['rect'], (0, 0, 255), 2, -1)
        self.overlay.overlay_floating_text('calib_target', key, targ_region['rect'][0], targ_region['rect'][1], (0, 0, 255), -1)
        self.overlay.overlay_paint()

        # Calibrate system target
        self.calibrate_target_worker()

        # Clean up
        self.overlay.overlay_remove_rect('calib_target')
        self.overlay.overlay_remove_floating_text('calib_target')
        self.overlay.overlay_paint()

        self.ap_ckb('log+vce', 'Calibration complete.')

    def calibrate_target_worker(self):
        """ Calibrate target and screen. """
        range_low = 50  # Minimum scale (30%)
        range_high = 200  # Maximum scale (200%)
        range_step = 1  # Scale increment to step (1%)
        scale_max = 0
        max_val = 0

        # loop through the test twice. Once over the wide scaling range at 1% increments and once over a
        # small scaling range at 0.1% increments.
        # Find out which scale factor meets the highest threshold value.
        for i in range(2):
            threshold = 0.0  # Minimum match is constant. Result will always be the highest match.
            scale, max_pick = self.calibrate_region(range_low, range_high, range_step, threshold, 'target', 'target')
            if scale != 0:
                scale_max = scale
                max_val = max_pick
                range_low = scale - 5  # Current scale - 5%
                range_high = scale + 5  # Current scale + 5%
                range_step = 0.1  # Scale increment to step (0.1%)
                if i == 1:
                    self.ap_ckb('log',
                                f'Target Cal: Best rough match: {max_val:5.4f}(%) at scale: {float(scale_max / 100):5.4f}')
                else:
                    self.ap_ckb('log',
                                f'Target Cal: Best fine match: {max_val:5.4f}(%) at scale: {float(scale_max / 100):5.4f}')

            else:
                break  # no match found with threshold

        # if we found a scaling factor that meets our criteria, then save it to the resolution.json file
        if max_val != 0:
            self.ap_ckb('log', f'Target Cal: Best match: {max_val:5.4f}(%) at scale: {self.scr.scaleX:5.4f}')
            self.scr.scaleX = float(scale_max / 100)
            self.scr.scaleY = self.scr.scaleX
            self.config['ScreenScale'] = round(self.scr.scaleX, 4)

            self.scr.write_config(
                data=None)  # None means the writer will use its own scales variable which we modified
        else:
            self.ap_ckb('log',
                        f'Target Cal: Insufficient matching to meet reliability, max % match: {max_val:5.4f}(%)')

        # reload the templates with the new (or previous value)
        self.templ.reload_templates(self.scr.scaleX, self.scr.scaleY)

    def have_destination(self, scr_reg) -> bool:
        """
        Check to see if the compass is on the screen.
        # TODO - remove this and use the status file destination. However, the status file destination does not...
        clear when the destination is unlocked, so it is possible to have the status with a destination and no...
        compass displayed. Don't know a way around this. So this is the best there is at the moment.
        """
        res = self.nav_service.get_compass_target_offset()
        if res:
            return True
        else:
            return False

    def sc_disengage_label_up(self, scr_reg) -> bool:
        """ look for messages like "PRESS [J] TO DISENGAGE" or "SUPERCRUISE OVERCHARGE ACTIVE",
         if in this region then return true.
        The aim of this function is to return that a message is there, and then use OCR to determine
        what the message is. This will only use the high CPU usage OCR when necessary."""
        dis_image, (minVal, maxVal, minLoc, maxLoc), match = scr_reg.match_template_in_region('disengage', 'disengage')

        pt = maxLoc

        width = scr_reg.templates.template['disengage']['width']
        height = scr_reg.templates.template['disengage']['height']

        # # Draw box around region
        # reg_rect = scr_reg.reg['disengage']['rect']
        # if self.debug_overlay:
        #     abs_rect = [pt[0] + reg_rect[0], pt[1] + reg_rect[1], pt[0] + reg_rect[0] + width, pt[1] + reg_rect[1] + height]
        #     self.overlay.overlay_rect1('sc_disengage_label_up', abs_rect, (0, 255, 0), 2)
        #     self.overlay.overlay_floating_text('sc_disengage_label_up', f'Match: {maxVal:5.4f} > {scr_reg.disengage_thresh}', abs_rect[0], abs_rect[1] - 25, (0, 255, 0))
        #     self.overlay.overlay_paint()

        if self.cv_view:
            self.draw_match_rect(dis_image, pt, (pt[0] + width, pt[1] + height), (0,255,0), 2)
            dis_image = cv2.rectangle(dis_image, (0, 0), (1000, 25), (0, 0, 0), -1)
            cv2.putText(dis_image, f'{maxVal:5.4f} > {scr_reg.disengage_thresh}', (1, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1, cv2.LINE_AA)
            cv2.imshow('sc_disengage_label_up', dis_image)
            cv2.moveWindow('sc_disengage_label_up', self.cv_view_x-460,self.cv_view_y+575)
            cv2.waitKey(1)

        if maxVal > scr_reg.disengage_thresh:
            return True
        else:
            return False

    def sc_disengage_ocr(self, scr_reg) -> bool:
        """ look for the "SUPERCRUISE OVERCHARGE ACTIVE" text using OCR, if in this region then return true. """
        # Do we have cockpit view? If not, return
        if self.status.get_gui_focus() != GuiFocusNoFocus:
            return False

        image = self.scr.get_screen_region(scr_reg.reg['disengage']['rect'])
        # TODO delete this line when COLOR_RGB2BGR is removed from get_screen()
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        mask = scr_reg.capture_region_filtered(self.scr, 'disengage')
        masked_image = cv2.bitwise_and(image, image, mask=mask)
        image = masked_image

        start_time = None
        if self.debug_overlay:
            start_time = time.time()

        # OCR the selected item
        sim_match = 0.35  # Similarity match 0.0 - 1.0 for 0% - 100%)
        sim = 0.0
        ocr_textlist = self.ocr.image_simple_ocr(image, 'disengage')
        if ocr_textlist is not None:
            sim = self.ocr.string_similarity(self.locale["PRESS_TO_DISENGAGE_MSG"], str(ocr_textlist))
            logger.debug(f"Disengage similarity with {str(ocr_textlist)} is {sim}")

        if sim > sim_match:
            self.ap_ckb('log+vce', 'Disengage Supercruise')
            self.keys.send('HyperSuperCombination')

        # Draw box around region
        if self.debug_overlay:
            elapsed_time = time.time() - start_time
            abs_rect = scr_reg.reg['disengage']['rect']
            self.overlay.overlay_rect1('sc_disengage_active', abs_rect, (0, 255, 0), 2)
            self.overlay.overlay_floating_text('sc_disengage_active', f'Diseng: {str(ocr_textlist)} ({round(elapsed_time, 4)} Secs)', abs_rect[0], abs_rect[1] - 25, (0, 255, 0))
            self.overlay.overlay_paint()

        if self.cv_view:
            image = cv2.rectangle(image, (0, 0), (1000, 30), (0, 0, 0), -1)
            cv2.putText(image, f'Text: {str(ocr_textlist)}', (1, 10), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1, cv2.LINE_AA)
            cv2.putText(image, f'Similarity: {sim:5.4f} > {sim_match}', (1, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1, cv2.LINE_AA)
            cv2.imshow('disengage2', image)
            cv2.moveWindow('disengage2', self.cv_view_x - 460, self.cv_view_y + 650)
            cv2.waitKey(30)

        if sim > sim_match:
            return True

        return False

    def start_sco_monitoring(self):
        """ Start Supercruise Overcharge Monitoring. This starts a parallel thread used to detect SCO
        until stop_sco_monitoring if called. """
        self._sc_sco_active_loop_enable = True

        if self._sc_sco_active_loop_thread is None or not self._sc_sco_active_loop_thread.is_alive():
            self._sc_sco_active_loop_thread = threading.Thread(target=self._sc_sco_active_loop, daemon=True)
            self._sc_sco_active_loop_thread.start()

    def stop_sco_monitoring(self):
        """ Stop Supercruise Overcharge Monitoring. """
        self._sc_sco_active_loop_enable = False

    def _sc_sco_active_loop(self):
        """ A loop to determine is Supercruise Overcharge is active.
        This runs on a separate thread monitoring the status in the background. """
        while self._sc_sco_active_loop_enable:
            # deactivate if not in SC
            if not self.status.get_flag(FlagsSupercruise):
                self.stop_sco_monitoring()
                break

            start_time = time.time()

            # Try to determine if the disengage/sco text is there
            sc_sco_is_active_ls = self.sc_sco_is_active

            # Check if SCO active in flags
            self.sc_sco_is_active = self.status.get_flag2(Flags2FsdScoActive)

            if self.sc_sco_is_active and not sc_sco_is_active_ls:
                self.ap_ckb('log+vce', "Supercruise Overcharge activated")
            if sc_sco_is_active_ls and not self.sc_sco_is_active:
                self.ap_ckb('log+vce', "Supercruise Overcharge deactivated")

            # Protection if SCO is active
            if self.sc_sco_is_active:
                if self.status.get_flag(FlagsOverHeating):
                    logger.info("SCO Aborting, overheating")
                    self.ap_ckb('log+vce', "SCO Aborting, overheating")
                    self.keys.send('UseBoostJuice')
                elif self.status.get_flag(FlagsLowFuel):
                    logger.info("SCO Aborting, < 25% fuel")
                    self.ap_ckb('log+vce', "SCO Aborting, < 25% fuel")
                    self.keys.send('UseBoostJuice')
                elif self.jn.ship_state()['fuel_percent'] < self.config['FuelThreasholdAbortAP']:
                    logger.info("SCO Aborting, < users low fuel threshold")
                    self.ap_ckb('log+vce', "SCO Aborting, < users low fuel threshold")
                    self.keys.send('UseBoostJuice')

            # Check SC Disengage, but only when not in SC Overcharge
            if not self.sc_sco_is_active:
                # Enable one or the other!
                # self._sc_disengage_active = self.sc_disengage(self.scrReg)

                # if self.sc_disengage_label_up(scr_reg):
                # If active, latch active flag and let it be reset when out of SC
                if not self._sc_disengage_active:
                    self._sc_disengage_active = self.sc_disengage_ocr(self.scrReg)
            # else:
            #     self._sc_disengage_active = False

            # Sleep upto 1 sec max. If OCR takes > 1 sec, there will be no delay
            elapsed_time = time.time() - start_time
            if elapsed_time < 1.0:
                sleep(1.0 - elapsed_time)

        # Reset disengage latch, in case it was latched.
        self._sc_disengage_active = False

    def _is_in_supercruise_or_space(self) -> bool:
        """Check if the ship is in supercruise or normal space using both journal state and status.json flags.
        The status.json flags update faster than the journal reader, so we check both to avoid race conditions.
        @return: True if in SC or Space, else False.
        """
        jn_status = self.jn.ship_state()['status']
        if jn_status == 'in_supercruise' or jn_status == 'in_space':
            return True
        if self.status.get_flag(FlagsSupercruise):
            return True
        if (not self.status.get_flag(FlagsDocked) and not self.status.get_flag(FlagsLanded)
                and not self.status.get_flag(FlagsFsdJump) and not self.status.get_flag(FlagsFsdCharging)):
            return True
        return False

    def occluded_reposition(self, scr_reg):
        """ Reposition is use when the target is occluded by a planet or other.
        We pitch 90 deg down for a bit, then up 90, this should make the target underneath us
        this is important because when we do nav_align() if it does not see the Nav Point
        in the compass (because it is a hollow circle), then it will pitch down, this will
        bring the target into view quickly. """
        self.ap_ckb('log+vce', 'Target occluded, repositioning.')
        self.set_throttle_0()
        self.ship_control.pitch_up_down(-90)

        # Speed away
        self.set_throttle_100()
        sleep(float(self.config['Wait_OccludedReposition']))

        self.set_throttle_0()
        self.ship_control.pitch_up_down(90)
        self.nav_service.compass_align(scr_reg)
        self.set_throttle_50()

    def logout(self):
        """ Performs menu action to log out of game """
        self.update_ap_status("Logout")
        self.keys.send_key('Down', SCANCODE["Key_Escape"])
        sleep(0.5)
        self.keys.send_key('Up', SCANCODE["Key_Escape"])
        sleep(0.5)
        self.keys.send('UI_Up')
        sleep(0.5)
        self.keys.send('UI_Select')
        sleep(0.5)
        self.keys.send('UI_Select')
        sleep(0.5)
        self.update_ap_status("Idle")

    def jump_to_system(self, scr_reg) -> bool:
        """ Jumps to the currently targeted system. Returns True if we successfully travel there, else False. """
        # Disabled the below because when docking, after a system was selected, the status file did not update, so the
        # current status was never updated.
        # # Current in game destination
        # status = self.status.get_cleaned_data()
        # destination_body = status['Destination_Body']  # The body number (0 for prim star)
        # destination_name = status['Destination_Name']  # The system/body/station/settlement name
        #
        # # Check we have a route and that we have a destination to a star (body 0).
        # # We can have one without the other.
        # if destination_body != 0 or destination_name == "":
        #     self.ap_ckb('log', "A valid destination system is not selected.")
        #     return False

        # Check if the current nav route is to the target system
        last_nav_route_sys = self.nav_route.get_last_system().upper()
        if last_nav_route_sys == '':
            self.ap_ckb('log', "A valid destination system is not selected.")
            return False

        # if we are starting docked at a station, we need to undock first
        if self.status.get_flag(FlagsDocked) or self.status.get_flag(FlagsLanded):
            self.docking_service.undock_seq()

        # Ensure we are in supercruise
        self.docking_service.sc_engage(False)

        # Route sent...  FSD Assist to that destination
        fin = self.jump_service.fsd_assist(scr_reg)
        if fin == FSDAssistReturn.Failed:
            return False

        return True

    def ctype_async_raise(self, thread_obj, exception):
        """ Raising an exception to the engine loop thread, so we can terminate its execution
        if thread was in a sleep, the exception seems to not be delivered
        @param thread_obj:
        @param exception:
        @return:
        """
        found = False
        target_tid = 0
        for tid, tobj in threading._active.items():
            if tobj is thread_obj:
                found = True
                target_tid = tid
                break

        if not found:
            # Thread already exited, nothing to interrupt
            return

        ret = ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(target_tid),
                                                         ctypes.py_object(exception))
        # ref: http://docs.python.org/c-api/init.html#PyThreadState_SetAsyncExc
        if ret == 0:
            raise ValueError("Invalid thread ID")
        elif ret > 1:
            # Huh? Why would we notify more than one threads?
            # Because we punch a hole into C level interpreter.
            # So it is better to clean up the mess.
            ctypes.pythonapi.PyThreadState_SetAsyncExc(target_tid, 0)
            raise SystemError("PyThreadState_SetAsyncExc failed")

    #
    # Setter routines for state variables
    #
    def set_fsd_assist(self, enable=True):
        if not enable and self.fsd_assist_enabled:
            if self.ap_thread is not None and self.ap_thread.is_alive():
                self.ctype_async_raise(self.ap_thread, EDAP_Interrupt)
        self.fsd_assist_enabled = enable

    def set_sc_assist(self, enable=True):
        if not enable and self.sc_assist_enabled:
            if self.ap_thread is not None and self.ap_thread.is_alive():
                self.ctype_async_raise(self.ap_thread, EDAP_Interrupt)
        self.sc_assist_enabled = enable

    def set_cv_view(self, enable=True, x=0, y=0):
        self.cv_view = enable
        self.config['Enable_CV_View'] = int(self.cv_view)  # update the config
        self.update_config()  # save the config
        if enable:
            self.cv_view_x = x
            self.cv_view_y = y
        else:
            cv2.destroyAllWindows()
            cv2.waitKey(50)

    def set_randomness(self, enable=False):
        self.config["EnableRandomness"] = enable

    def set_activate_elite_eachkey(self, enable=False):
        self.config["ActivateEliteEachKey"] = enable

    def set_automatic_logout(self, enable=False):
        self.config["AutomaticLogout"] = enable

    def set_overlay(self, enable=False):
        # TODO: apply the change without restarting the program
        self.config["OverlayTextEnable"] = enable
        if not enable:
            self.overlay.overlay_clear()

        self.overlay.overlay_paint()

    def set_voice(self, enable=False):
        if enable:
            self.vce.set_on()
        else:
            self.vce.set_off()

    def set_fss_scan(self, enable=False):
        self.config["ElwScannerEnable"] = enable

    def set_log_error(self, enable=False):
        self.config["LogDEBUG"] = False
        self.config["LogINFO"] = False
        logger.setLevel(logging.ERROR)

    def set_log_debug(self, enable=False):
        self.config["LogDEBUG"] = True
        self.config["LogINFO"] = False
        logger.setLevel(logging.DEBUG)

    def set_log_info(self, enable=False):
        self.config["LogDEBUG"] = False
        self.config["LogINFO"] = True
        logger.setLevel(logging.INFO)

    def quit(self):
        """ quit() is important to call to clean up, if we don't terminate the threads we created the AP will
        hang on exit have then kill python exec.
        @return:
        """
        self.keys.release_all_keys()
        if self.vce != None:
            self.vce.quit()
        if self.overlay != None:
            self.overlay.overlay_quit()
        self.terminate = True

    def engine_loop(self):
        """
        This function will execute in its own thread and will loop forever until the self.terminate flag is set
        @return:
        """
        while not self.terminate:
            # TODO - Remove these show compass/target all the time
            if self.debug_show_compass_overlay:
                self.nav_service.get_nav_offset(self.scrReg)
            if self.debug_show_target_overlay:
                self.nav_service.get_target_offset(self.scrReg, True)

            # TODO - Enable for test
            # self.start_sco_monitoring()

            # Ship calibration functions
            if self.ship_tst_roll_enabled:
                self.ship_control.ship_calibrate_roll()
                self.ship_tst_roll_enabled = False
            if self.ship_tst_pitch_enabled:
                self.ship_control.ship_calibrate_pitch()
                self.ship_tst_pitch_enabled = False
            if self.ship_tst_yaw_enabled:
                self.ship_control.ship_calibrate_yaw()
                self.ship_tst_yaw_enabled = False

            if self.fsd_assist_enabled:
                logger.debug("Running fsd_assist")
                set_focus_elite_window()
                self.update_overlay()
                self.jump_cnt = 0
                self.refuel_cnt = 0
                self.total_dist_jumped = 0
                self.total_jumps = 0
                fin = True
                # could be deep in call tree when user disables FSD, so need to trap that exception
                try:
                    fin = self.jump_service.fsd_assist(self.scrReg)
                except EDAP_Interrupt:
                    logger.debug("Caught stop exception")
                    self.keys.release_all_keys()
                except Exception as e:
                    logger.debug("FSD Assist trapped generic:"+str(e))
                    print("Trapped generic:"+str(e))
                    traceback.print_exc()

                self.stop_sco_monitoring()
                self.fsd_assist_enabled = False
                self.ap_ckb('fsd_stop')
                self.update_overlay()

                # if fsd_assist returned false then we are not finished, meaning we have an in system target
                # defined.  So lets enable Supercruise assist to get us there
                # Note: this is tricky, in normal FSD jumps the target is pretty much on the other side of Sun
                #  when we arrive, but not so when we are in the final system
                if fin == FSDAssistReturn.Partial:
                    self.ap_ckb("sc_start")

                # drop all out debug windows
                # cv2.destroyAllWindows()
                # cv2.waitKey(10)

            elif self.sc_assist_enabled:
                logger.debug("Running sc_assist")
                set_focus_elite_window()
                self.update_overlay()
                try:
                    self.update_ap_status("SC to Target")
                    self.docking_service.sc_assist(self.scrReg)
                except EDAP_Interrupt:
                    logger.debug("Caught stop exception")
                    self.keys.release_all_keys()
                except Exception as e:
                    print("Trapped generic:"+str(e))
                    logger.debug("SC Assist trapped generic:"+str(e))
                    traceback.print_exc()

                self.stop_sco_monitoring()
                logger.debug("Completed sc_assist")
                self.sc_assist_enabled = False
                self.ap_ckb('sc_stop')
                self.update_overlay()

            # Check once EDAPGUI loaded to prevent errors logging to the listbox before loaded
            if self.gui_loaded:
                # Check if ship has changed
                ship = self.jn.ship_state()['type']
                # Check if a ship and not a suit (on foot)
                if ship not in ship_size_map:
                    # Clear current ship
                    self.current_ship_type = None
                    self.current_ship_cfg = None
                else:
                    ship_fullname = get_ship_fullname(ship)

                    # Check if ship changed or just loaded
                    if ship != self.current_ship_type:
                        if self.current_ship_type is not None:
                            cur_ship_fullname = get_ship_fullname(self.current_ship_type)
                            self.ap_ckb('log+vce', f"Switched ship from your {cur_ship_fullname} to your {ship_fullname}.")
                        else:
                            self.ap_ckb('log+vce', f"Welcome aboard your {ship_fullname}.")

                        # Check for fuel scoop and advanced docking computer
                        if not self.jn.ship_state()['has_fuel_scoop']:
                            self.ap_ckb('log+vce', f"Warning, your {ship_fullname} is not fitted with a Fuel Scoop.")
                        if not self.jn.ship_state()['has_adv_dock_comp']:
                            self.ap_ckb('log+vce', f"Warning, your {ship_fullname} is not fitted with an Advanced Docking Computer.")
                        if self.jn.ship_state()['has_std_dock_comp']:
                            self.ap_ckb('log+vce', f"Warning, your {ship_fullname} is fitted with a Standard Docking Computer.")
                        if self.jn.ship_state()['has_supercruise_assist']:
                            self.ap_ckb('log+vce', f"Your {ship_fullname} is fitted with a Supercruise Assist module.")

                        # Store ship for change detection BEFORE loading config and GUI update
                        self.current_ship_type = ship

                        # Load ship configuration with proper hierarchy
                        self.load_ship_configuration(ship)

                        # Update current ship config
                        self.current_ship_cfg = self.ship_configs['Ship_Configs'][self.current_ship_type]

                        # Update GUI with ship config
                        self.ap_ckb('update_ship_cfg')

                        # Reload templates for this ship
                        self.templ.reload_templates(self.scr.scaleX, self.scr.scaleY)

            try:
                self.elw_advisor.poll_body_scans()
            except Exception as e:
                logger.debug(f'poll_body_scans failed: {e}')
            self.update_overlay()
            cv2.waitKey(10)
            # Catch EDAP_Interrupt raised while idle to prevent killing the engine loop
            try:
                sleep(1)
            except EDAP_Interrupt:
                logger.debug("EDAP_Interrupt caught in engine_loop idle")

    def set_throttle_0(self, repeat=1):
        if self.status.get_flag(FlagsSupercruise):
            self.speed_demand = 'SCSpeed0'
            self.ap_ckb('log', f"Setting throttle to 0% (in SC).")
        else:
            self.speed_demand = 'Speed0'
            self.ap_ckb('log', f"Setting throttle to 0%.")

        self.keys.send('SetSpeedZero', repeat)

    def set_throttle_50(self, repeat=1):
        if self.status.get_flag(FlagsSupercruise):
            self.speed_demand = 'SCSpeed50'
            self.ap_ckb('log', f"Setting throttle to 50% (in SC).")
        else:
            self.speed_demand = 'Speed50'
            self.ap_ckb('log', f"Setting throttle to 50%.")

        self.keys.send('SetSpeed50', repeat)

    def set_throttle_100(self, repeat=1):
        if self.status.get_flag(FlagsSupercruise):
            self.speed_demand = 'SCSpeed100'
            self.ap_ckb('log', f"Setting throttle to 100% (in SC).")
        else:
            self.speed_demand = 'Speed100'
            self.ap_ckb('log', f"Setting throttle to 100%.")

        self.keys.send('SetSpeed100', repeat)


def delete_old_log_files():
    """ Deleted old .log files from the main folder."""
    folder = '.'
    n = 5  # days

    current_time = time.time()
    day = 86400  # seconds in a day

    for filename in os.listdir(folder):
        file_path = os.path.join(folder, filename)
        if os.path.isfile(file_path):
            if filename.endswith('.log'):
                file_time = os.path.getmtime(file_path)
                if file_time < current_time - day * n:
                    print(f"Deleting file: '{file_path}'")
                    os.remove(file_path)


def strfdelta(tdelta, fmt='{H:02}h {M:02}m {S:02.0f}s', inputtype='timedelta'):
    """Convert a datetime.timedelta object or a regular number to a custom
    formatted string, just like the stftime() method does for datetime.datetime
    objects.

    The fmt argument allows custom formatting to be specified.  Fields can
    include seconds, minutes, hours, days, and weeks.  Each field is optional.

    Some examples:
        '{D:02}d {H:02}h {M:02}m {S:02.0f}s' --> '05d 08h 04m 02s' (default)
        '{W}w {D}d {H}:{M:02}:{S:02.0f}'     --> '4w 5d 8:04:02'
        '{D:2}d {H:2}:{M:02}:{S:02.0f}'      --> ' 5d  8:04:02'
        '{H}h {S:.0f}s'                       --> '72h 800s'

    The inputtype argument allows tdelta to be a regular number instead of the
    default, which is a datetime.timedelta object.  Valid inputtype strings:
        's', 'seconds',
        'm', 'minutes',
        'h', 'hours',
        'd', 'days',
        'w', 'weeks'
    """

    # Convert tdelta to integer seconds.
    if inputtype == 'timedelta':
        remainder = tdelta.total_seconds()
    elif inputtype in ['s', 'seconds']:
        remainder = float(tdelta)
    elif inputtype in ['m', 'minutes']:
        remainder = float(tdelta)*60
    elif inputtype in ['h', 'hours']:
        remainder = float(tdelta)*3600
    elif inputtype in ['d', 'days']:
        remainder = float(tdelta)*86400
    elif inputtype in ['w', 'weeks']:
        remainder = float(tdelta)*604800
    else:
        remainder = 0.0

    f = Formatter()
    desired_fields = [field_tuple[1] for field_tuple in f.parse(fmt)]
    possible_fields = ('Y', 'm', 'W', 'D', 'H', 'M', 'S', 'mS', 'µS')
    constants = {'Y': 86400*365.24, 'm': 86400*30.44, 'W': 604800, 'D': 86400, 'H': 3600, 'M': 60, 'S': 1, 'mS': 1/pow(10, 3), 'µS': 1/pow(10, 6)}
    values = {}
    for field in possible_fields:
        if field in desired_fields and field in constants:
            quotient, remainder = divmod(remainder, constants[field])
            values[field] = int(quotient) if field != 'S' else quotient + remainder
    return f.format(fmt, **values)


def get_timestamped_filename(prefix: str, suffix: str, extension: str):
    """ Get timestamped filename with milliseconds.
    @return: String in the format of 'prefix yyyy-mm-dd hh-mm-ss.xxx suffix.extension'
    """
    now = datetime.now()
    x = now.strftime("%Y-%m-%d %H-%M-%S.%f")[:-3]  # Date time with mS.
    if prefix != '':
        x = prefix + ' ' + x
    if suffix != '':
        x = x + ' ' + suffix
    x = x + "." + extension
    return x


def dummy_cb(msg, body=None):
    pass


#
# This main is for testing purposes.
#
def main():
    # handle = win32gui.FindWindow(0, "Elite - Dangerous (CLIENT)")
    # if handle != None:
    #    win32gui.SetForegroundWindow(handle)  # put the window in foreground

    delete_old_log_files()

    ed_ap = EDAutopilot(cb=dummy_cb, do_thread=False)

    # for x in range(10):
    #     ed_ap.keys.send('RollLeftButton', 0.04)
    # sleep(1)

    set_focus_elite_window()
    ed_ap.set_throttle_50()
    sleep(0.25)

    tar_off = ed_ap.nav_service.get_target_offset(ed_ap.scrReg)
    if tar_off:
        off = tar_off
        logger.debug(f"sc_target_align before: pit:{off['pit']} yaw: {off['yaw']} ")

    # ed_ap.rotateLeft(1)
    x = 10
    ed_ap.pitchrate = 16.0
    ed_ap.ship_control.pitch_up_down(-x)

    sleep(.5)

    tar_off = ed_ap.nav_service.get_target_offset(ed_ap.scrReg)
    if tar_off:
        off = tar_off
        logger.debug(f"sc_target_align after: pit:{off['pit']} yaw: {off['yaw']} ")

    sleep(.5)

    ed_ap.ship_control.pitch_up_down(x)

    # ed_ap.yawLeft(1)

    # for x in range(10):
    #     ed_ap.keys.send('PitchUpButton', 0.04)
    # sleep(1)
    # for x in range(10):
    #     ed_ap.keys.send('YawLeftButton', 0.04)
    #
    #     target_align(scrReg)
    #     print("Calling nav_align")
    #     ed_ap.nav_align(ed_ap.scrReg)
    #     ed_ap.fss_detect_elw(ed_ap.scrReg)
    #
    #     loc = get_destination_offset(scrReg)
    #     print("get_dest: " +str(loc))
    #     loc = get_nav_offset(scrReg)
    #     print("get_nav: " +str(loc))
    #     cv2.waitKey(0)
    #     print("Done nav")
    #     sleep(8)

    # ed_ap.overlay.overlay_quit()


if __name__ == "__main__":
    main()
