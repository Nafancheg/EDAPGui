# pythonw.exe has no console, so sys.stdout/stderr are None. Redirect them to
# a null stream before anything else imports, otherwise the first print() or
# console log write anywhere in the app crashes it with no visible error.
import sys
import os
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')

# import queue
# import threading
# import kthread
# from datetime import datetime
# from time import sleep
# import cv2
# import json
# from pathlib import Path
import subprocess
from typing import TypedDict

import keyboard
import webbrowser
# import requests


# from PIL import Image, ImageGrab, ImageTk
import tkinter as tk
from tkinter import filedialog as fd
# from tkinter import messagebox
from tkinter import ttk
import sv_ttk
import pywinstyles
import sys  # Do not delete - prevents a 'super' error from tktoolip.
from tktooltip import ToolTip  # In requirements.txt as 'tkinter-tooltip'.

from EDAPCalibration import Calibration
from EDAPColonizeEditor import ColonizeEditorTab
# from OCR import RegionCalibration
# from Voice import *
# from MousePt import MousePoint

# from Image_Templates import *
# from Screen import *
# from Screen_Regions import *
# from EDKeys import *
# from EDJournal import *
from ED_AP import *
from EDAPWaypointEditor import WaypointEditorTab

from EDlogger import logger
from RPYLineEditor import line_editor

"""
File:EDAPGui.py

Description:
User interface for controlling the ED Autopilot

Note:
Ideas taken from:  https://github.com/skai2/EDAutopilot

 HotKeys:
    Home - Start FSD Assist
    INS  - Start SC Assist
    PG UP - Start Robigo Assist
    End - Terminate any ongoing assist (FSD, SC, AFK)

Author: sumzer0@yahoo.com
"""

# ---------------------------------------------------------------------------
# must be updated with a new release so that the update check works properly!
# contains the names of the release.
EDAP_VERSION = "V1.9.3"
# depending on how release versions are best marked you could also change it to the release tag, see function check_update.
# ---------------------------------------------------------------------------

FORM_TYPE_CHECKBOX = 0
FORM_TYPE_SPINBOX = 1
FORM_TYPE_ENTRY = 2


def str_to_float(input_str: str) -> float:
    try:
        return float(input_str)
    except ValueError:
        return 0.0  # Assign a default value on error


class SubRegion(TypedDict):
    """ """
    rect: list[float]
    text: str


class Objects(TypedDict):
    """ """
    width: float
    height: float
    text: str


class MyRegion(TypedDict):
    """ """
    rect: list[float]
    text: str
    readonly: bool
    regions: dict[str, SubRegion]
    objects: dict[str, Objects]


class APGui:

    def __init__(self, root):
        self.statusbar = None
        self.root = root
        root.title("EDAutopilot " + EDAP_VERSION)
        # root.overrideredirect(True)
        # root.geometry("400x550")
        # root.configure(bg="blue")
        root.protocol("WM_DELETE_WINDOW", self.close_window)
        root.resizable(False, False)

        self.tooltips = {
            'FSD Route Assist': "Will execute your route. \nAt each jump the sequence will perform some fuel scooping.",
            'Supercruise Assist': "Will keep your ship pointed to target, \nyou target can only be a station for the autodocking to work.",
            'Waypoint Assist': "When selected, will prompt for the waypoint file. \nThe waypoint file contains System names that \nwill be entered into Galaxy Map and route plotted.",
            'Robigo Assist': "",
            'DSS Assist': "When selected, will perform DSS scans while you are traveling between stars.",
            'Single Waypoint Assist': "",
            'ELW Scanner': "Will perform FSS scans while FSD Assist is traveling between stars. \nIf the FSS shows a signal in the region of Earth, \nWater or Ammonia type worlds, it will announce that discovery.",
            'AFK Combat Assist': "Used with a AFK Combat ship in a Rez Zone.",
            'RollRate': "Roll rate your ship has in deg/sec. Higher the number the more maneuverable the ship.",
            'PitchRate': "Pitch (up/down) rate your ship has in deg/sec. Higher the number the more maneuverable the ship.",
            'YawRate': "Yaw rate (rudder) your ship has in deg/sec. Higher the number the more maneuverable the ship.",
            'SunPitchUp+Time': "This field are for ship that tend to overheat. \nProviding 1-2 more seconds of Pitch up when avoiding the Sun \nwill overcome this problem.",
            'Sun Bright Threshold': "The low level for brightness detection, \nrange 0-255, want to mask out darker items",
            'Nav Align Tries': "How many attempts the ap should make at alignment.",
            'Jump Tries': "How many attempts the ap should make to jump.",
            'Docking Retries': "How many attempts to make to dock.",
            'Wait For Autodock': "After docking granted, \nwait this amount of time for us to get docked with autodocking",
            'Start FSD': "Button to start FSD route assist.",
            'Start SC': "Button to start Supercruise assist.",
            'Start Robigo': "Button to start Robigo assist.",
            'Stop All': "Button to stop all assists.",
            'Refuel Threshold': "If fuel level get below this level, \nit will attempt refuel.",
            'Scoop Timeout': "Number of second to wait for full tank, \nmight mean we are not scooping well or got a small scooper",
            'Fuel Threshold Abort': "Level at which AP will terminate, \nbecause we are not scooping well.",
            'X Offset': "Offset left the screen to start place overlay text.",
            'Y Offset': "Offset down the screen to start place overlay text.",
            'Font Size': "Font size of the overlay.",
            'Calibrate': "Will iterate through a set of scaling values \ngetting the best match for your system. \nSee HOWTO-Calibrate.md",
            'Cap Mouse XY': "This will provide the StationCoord value of the Station in the SystemMap. \nSelecting this button and then clicking on the Station in the SystemMap \nwill return the x,y value that can be pasted in the waypoints file",
            'Debug Overlay': "Enables debug data to be displayed over the \nElite Dangerous screen while playing the game.",
            'Debug OCR': "Enables OCR debug output to be stored in the 'ocr_output' folder.",
            'Debug Images': "Enables debug images to be stored in the 'debug_output' folder.",
            'Modifier Key Delay': "Delay for key modifiers to ensure modifier is detected before/after the key.",
            'Default Hold Time': "Default hold time for a key press.",
            'Repeat Key Delay': "Delay between key press repeats.",
            'FSS Detect Wait': "Wait (sec) after entering FSS mode \nbefore capturing the screen for ELW detection.",
            'Dock Approach Time': "Time (sec) at 50% throttle to get within 7.5km \nof the station before requesting docking.",
            'Ship Stop Wait': "Wait (sec) for the ship to come to a stop \nafter setting throttle to zero.",
            'Occluded Reposition Time': "Time (sec) at 100% throttle to fly clear \nwhen the target is occluded by a planet.",
            'DSS Scan Time': "Time (sec) to hold the DSS (honk) button. \nThe scan takes roughly 6 seconds.",
            'Past Sun Time': "Time (sec) at 100% throttle to get away \nfrom the sun after a jump.",
            'Heat Dissipate Time': "Extra time (sec) to let heat dissipate before \nusing the FSD (when ELW scanner is disabled).",
            'After Jump Wait': "Wait (sec) after a jump completes to allow \ngraphics to stabilize and accept inputs.",
            'GalMap Select Delay': "Delay (sec) selecting the system \nwhen in the galaxy map.",
            'Planet Departure SCO Time': "SCO boost time (sec) when leaving a planet.",
            'FC Departure Time': "Extra time (sec) to fly away from a Fleet Carrier.",
        }

        self.gui_loaded = False
        self.log_buffer = queue.Queue()
        self.callback('log', f'Starting ED Autopilot {EDAP_VERSION}.')

        self.ed_ap = EDAutopilot(cb=self.callback)
        self.ed_ap.robigo.set_single_loop(self.ed_ap.config['Robigo_Single_Loop'])
        self.locale = self.ed_ap.locale

        self.form_locale_keys = {
            'FSD Route Assist': 'GUI_FIELD_FSD_ROUTE_ASSIST',
            'Supercruise Assist': 'GUI_FIELD_SUPERCRUISE_ASSIST',
            'Waypoint Assist': 'GUI_FIELD_WAYPOINT_ASSIST',
            'Robigo Assist': 'GUI_FIELD_ROBIGO_ASSIST',
            'AFK Combat Assist': 'GUI_FIELD_AFK_COMBAT_ASSIST',
            'DSS Assist': 'GUI_FIELD_DSS_ASSIST',
            'Sun Bright Threshold': 'GUI_FIELD_SUN_BRIGHT_THRESHOLD',
            'Nav Align Tries': 'GUI_FIELD_NAV_ALIGN_TRIES',
            'Jump Tries': 'GUI_FIELD_JUMP_TRIES',
            'Docking Retries': 'GUI_FIELD_DOCKING_RETRIES',
            'Wait For Autodock': 'GUI_FIELD_WAIT_FOR_AUTODOCK',
            'Start FSD': 'GUI_FIELD_START_FSD',
            'Start SC': 'GUI_FIELD_START_SC',
            'Start Robigo': 'GUI_FIELD_START_ROBIGO',
            'Stop All': 'GUI_FIELD_STOP_ALL',
            'Refuel Threshold': 'GUI_FIELD_REFUEL_THRESHOLD',
            'Scoop Timeout': 'GUI_FIELD_SCOOP_TIMEOUT',
            'Fuel Threshold Abort': 'GUI_FIELD_FUEL_THRESHOLD_ABORT',
            'X Offset': 'GUI_FIELD_X_OFFSET',
            'Y Offset': 'GUI_FIELD_Y_OFFSET',
            'Font Size': 'GUI_FIELD_FONT_SIZE',
            'Modifier Key Delay': 'GUI_FIELD_MODIFIER_KEY_DELAY',
            'Default Hold Time': 'GUI_FIELD_DEFAULT_HOLD_TIME',
            'Repeat Key Delay': 'GUI_FIELD_REPEAT_KEY_DELAY',
            'FSS Detect Wait': 'GUI_FIELD_WAIT_FSS_DETECT',
            'Dock Approach Time': 'GUI_FIELD_WAIT_DOCK_APPROACH',
            'Ship Stop Wait': 'GUI_FIELD_WAIT_SHIP_STOP',
            'Occluded Reposition Time': 'GUI_FIELD_WAIT_OCCLUDED_REPOSITION',
            'DSS Scan Time': 'GUI_FIELD_WAIT_DSS_SCAN',
            'Past Sun Time': 'GUI_FIELD_WAIT_PAST_SUN',
            'Heat Dissipate Time': 'GUI_FIELD_WAIT_HEAT_DISSIPATE',
            'After Jump Wait': 'GUI_FIELD_WAIT_AFTER_JUMP',
            'GalMap Select Delay': 'GUI_FIELD_GALMAP_SELECT_DELAY',
            'Planet Departure SCO Time': 'GUI_FIELD_PLANET_DEPARTURE_SCO_TIME',
            'FC Departure Time': 'GUI_FIELD_FC_DEPARTURE_TIME',
        }
        # self.calibrator = RegionCalibration(root, self.ed_ap, cb=self.callback)
        self.calibration = None

        self.ocr_calibration_data = {}

        self.mouse = MousePoint()

        self.checkboxvar = {}
        self.radiobuttonvar = {}
        self.entries = {}
        self.lab_ck = {}
        self.single_waypoint_system = tk.StringVar()
        self.single_waypoint_station = tk.StringVar()
        self.throttle_var = tk.StringVar()
        self.language_var = tk.StringVar()
        self.throttle_combo = None
        self.throttle_keys = []
        self._global_shopping_list_tab = None
        self.waypoint_editor_tab = None
        self.colonize_tab = None
        self._nb = None

        self.FSD_A_running = False
        self.SC_A_running = False
        self.WP_A_running = False
        self.RO_A_running = False
        self.DSS_A_running = False
        self.SWP_A_running = False

        self.mini_panel = None
        self.mini_info = None
        self.mini_edsm = None

        self.cv_view = False

        self.msgList = self.gui_gen(root)

        self.checkboxvar['Enable Randomness'].set(self.ed_ap.config['EnableRandomness'])
        self.checkboxvar['Activate Elite for each key'].set(self.ed_ap.config['ActivateEliteEachKey'])
        self.checkboxvar['Automatic logout'].set(self.ed_ap.config['AutomaticLogout'])
        self.checkboxvar['Enable Overlay'].set(self.ed_ap.config['OverlayTextEnable'])
        self.checkboxvar['Enable Voice'].set(self.ed_ap.config['VoiceEnable'])
        self.checkboxvar['ELW Scanner'].set(self.ed_ap.config['ElwScannerEnable'])
        self.checkboxvar['Enable Hotkeys'].set(self.ed_ap.config['HotkeysEnable'])
        self.checkboxvar['Debug Overlay'].set(self.ed_ap.config['DebugOverlay'])
        self.checkboxvar['Debug OCR'].set(self.ed_ap.config['DebugOCR'])
        self.checkboxvar['Debug Images'].set(self.ed_ap.config['DebugImages'])
        self.checkboxvar['AFKCombat AttackAtWill'].set(self.ed_ap.config['AFKCombat_AttackAtWill'])
        self.checkboxvar['Fast Travel'].set(self.ed_ap.config.get('FastTravelMode', False))

        self.radiobuttonvar['dss_button'].set(self.ed_ap.config['DSSButton'])
        self.language_var.set(self.ed_ap.config['Language'])

        self.entries['ship']['SunPitchUp+Time'].delete(0, tk.END)

        self.entries['autopilot']['Sun Bright Threshold'].delete(0, tk.END)
        self.entries['autopilot']['Nav Align Tries'].delete(0, tk.END)
        self.entries['autopilot']['Jump Tries'].delete(0, tk.END)
        self.entries['autopilot']['Docking Retries'].delete(0, tk.END)
        self.entries['autopilot']['Wait For Autodock'].delete(0, tk.END)

        self.entries['refuel']['Refuel Threshold'].delete(0, tk.END)
        self.entries['refuel']['Scoop Timeout'].delete(0, tk.END)
        self.entries['refuel']['Fuel Threshold Abort'].delete(0, tk.END)

        self.entries['overlay']['X Offset'].delete(0, tk.END)
        self.entries['overlay']['Y Offset'].delete(0, tk.END)
        self.entries['overlay']['Font Size'].delete(0, tk.END)

        self.entries['buttons']['Start FSD'].delete(0, tk.END)
        self.entries['buttons']['Start SC'].delete(0, tk.END)
        self.entries['buttons']['Start Robigo'].delete(0, tk.END)
        self.entries['buttons']['Stop All'].delete(0, tk.END)

        self.entries['keys']['Modifier Key Delay'].delete(0, tk.END)
        self.entries['keys']['Default Hold Time'].delete(0, tk.END)
        self.entries['keys']['Repeat Key Delay'].delete(0, tk.END)

        game_waits_config_map = {
            'FSS Detect Wait': 'Wait_FSSDetect',
            'Dock Approach Time': 'Wait_DockApproach',
            'Ship Stop Wait': 'Wait_ShipStop',
            'Occluded Reposition Time': 'Wait_OccludedReposition',
            'DSS Scan Time': 'Wait_DSSScan',
            'Past Sun Time': 'Wait_PastSun',
            'Heat Dissipate Time': 'Wait_HeatDissipate',
            'After Jump Wait': 'Wait_AfterJump',
            'GalMap Select Delay': 'GalMap_SystemSelectDelay',
            'Planet Departure SCO Time': 'PlanetDepartureSCOTime',
            'FC Departure Time': 'FCDepartureTime',
        }
        for field, cfg_key in game_waits_config_map.items():
            self.entries['game_waits'][field].delete(0, tk.END)
            self.entries['game_waits'][field].insert(0, float(self.ed_ap.config[cfg_key]))

        self.entries['ship']['SunPitchUp+Time'].insert(0, float(self.ed_ap.sunpitchuptime))

        self.entries['autopilot']['Sun Bright Threshold'].insert(0, int(self.ed_ap.config['SunBrightThreshold']))
        self.entries['autopilot']['Nav Align Tries'].insert(0, int(self.ed_ap.config['NavAlignTries']))
        self.entries['autopilot']['Jump Tries'].insert(0, int(self.ed_ap.config['JumpTries']))
        self.entries['autopilot']['Docking Retries'].insert(0, int(self.ed_ap.config['DockingRetries']))
        self.entries['autopilot']['Wait For Autodock'].insert(0, int(self.ed_ap.config['WaitForAutoDockTimer']))
        self.entries['refuel']['Refuel Threshold'].insert(0, int(self.ed_ap.config['RefuelThreshold']))
        self.entries['refuel']['Scoop Timeout'].insert(0, int(self.ed_ap.config['FuelScoopTimeOut']))
        self.entries['refuel']['Fuel Threshold Abort'].insert(0, int(self.ed_ap.config['FuelThreasholdAbortAP']))
        self.entries['overlay']['X Offset'].insert(0, int(self.ed_ap.config['OverlayTextXOffset']))
        self.entries['overlay']['Y Offset'].insert(0, int(self.ed_ap.config['OverlayTextYOffset']))
        self.entries['overlay']['Font Size'].insert(0, int(self.ed_ap.config['OverlayTextFontSize']))

        self.entries['buttons']['Start FSD'].insert(0, str(self.ed_ap.config['HotKey_StartFSD']))
        self.entries['buttons']['Start SC'].insert(0, str(self.ed_ap.config['HotKey_StartSC']))
        self.entries['buttons']['Start Robigo'].insert(0, str(self.ed_ap.config['HotKey_StartRobigo']))
        self.entries['buttons']['Stop All'].insert(0, str(self.ed_ap.config['HotKey_StopAllAssists']))

        self.entries['keys']['Modifier Key Delay'].insert(0, float(self.ed_ap.config['Key_ModDelay']))
        self.entries['keys']['Default Hold Time'].insert(0, float(self.ed_ap.config['Key_DefHoldTime']))
        self.entries['keys']['Repeat Key Delay'].insert(0, float(self.ed_ap.config['Key_RepeatDelay']))

        if self.ed_ap.config['LogDEBUG']:
            self.radiobuttonvar['debug_mode'].set("Debug")
        elif self.ed_ap.config['LogINFO']:
            self.radiobuttonvar['debug_mode'].set("Info")
        else:
            self.radiobuttonvar['debug_mode'].set("Error")

        # Hotkeys
        self.setup_hotkeys()

        # check for updates
        self.check_updates()

        sleep(0.25)  # Added because the custom tkinter takes longer to load? Without, you occasionally get errors
        # that the main thread is not in main loop.
        self.ed_ap.gui_loaded = True
        self.gui_loaded = True
        # Send a log entry which will flush out the buffer.
        self.callback('log', 'ED Autopilot loaded successfully.')

    def setup_hotkeys(self):
        """ Enable or disable hotkeys.
        Global trap for these keys, the 'end' key will stop any current AP action the 'home' key will start the
        FSD Assist. May want another to start SC Assist.
        """
        # Remove all the hotkeys. Adding a dummy hotkey will eliminate an error if none had been configured.
        keyboard.add_hotkey(' ', print)
        keyboard.remove_all_hotkeys()

        if self.ed_ap.config['HotkeysEnable']:
            # Add the desired hotkeys
            keyboard.add_hotkey(self.ed_ap.config['HotKey_StopAllAssists'], self.stop_all_assists)
            keyboard.add_hotkey(self.ed_ap.config['HotKey_StartFSD'], self.callback, args=('fsd_start', None))
            keyboard.add_hotkey(self.ed_ap.config['HotKey_StartSC'], self.callback, args=('sc_start', None))
            keyboard.add_hotkey(self.ed_ap.config['HotKey_StartRobigo'], self.callback, args=('robigo_start', None))

            # TODO - Enable these to allow pips to be controlled by EDAP when using the defined keys (tbd).
            # keyboard.add_hotkey('up', self.callback, args=('up', None))
            # keyboard.add_hotkey('down', self.callback, args=('down', None))
            # keyboard.add_hotkey('left', self.callback, args=('left', None))
            # keyboard.add_hotkey('right', self.callback, args=('right', None))

    # callback from the EDAP, to configure GUI items
    def callback(self, msg, body=None):
        if msg == 'log':
            self.log_msg(body)
        elif msg == 'log+vce':
            self.log_msg(body)
            self.ed_ap.vce.say(body)
        elif msg == 'statusline':
            self.update_statusline(body)
        elif msg == 'fsd_stop':
            logger.debug("Detected 'fsd_stop' callback msg")
            self.checkboxvar['FSD Route Assist'].set(0)
            self.check_cb('FSD Route Assist')
        elif msg == 'fsd_start':
            self.checkboxvar['FSD Route Assist'].set(1)
            self.check_cb('FSD Route Assist')
        elif msg == 'sc_stop':
            logger.debug("Detected 'sc_stop' callback msg")
            self.checkboxvar['Supercruise Assist'].set(0)
            self.check_cb('Supercruise Assist')
        elif msg == 'sc_start':
            self.checkboxvar['Supercruise Assist'].set(1)
            self.check_cb('Supercruise Assist')
        elif msg == 'waypoint_stop':
            logger.debug("Detected 'waypoint_stop' callback msg")
            self.checkboxvar['Waypoint Assist'].set(0)
            self.check_cb('Waypoint Assist')
        elif msg == 'waypoint_start':
            self.checkboxvar['Waypoint Assist'].set(1)
            self.check_cb('Waypoint Assist')
        elif msg == 'robigo_stop':
            logger.debug("Detected 'robigo_stop' callback msg")
            self.checkboxvar['Robigo Assist'].set(0)
            self.check_cb('Robigo Assist')
        elif msg == 'robigo_start':
            self.checkboxvar['Robigo Assist'].set(1)
            self.check_cb('Robigo Assist')
        elif msg == 'afk_stop':
            logger.debug("Detected 'afk_stop' callback msg")
            self.checkboxvar['AFK Combat Assist'].set(0)
            self.check_cb('AFK Combat Assist')
        elif msg == 'dss_start':
            logger.debug("Detected 'dss_start' callback msg")
            self.checkboxvar['DSS Assist'].set(1)
            self.check_cb('DSS Assist')
        elif msg == 'dss_stop':
            logger.debug("Detected 'dss_stop' callback msg")
            self.checkboxvar['DSS Assist'].set(0)
            self.check_cb('DSS Assist')
        elif msg == 'single_waypoint_stop':
            logger.debug("Detected 'single_waypoint_stop' callback msg")
            self.checkboxvar['Single Waypoint Assist'].set(0)
            self.check_cb('Single Waypoint Assist')

        elif msg == 'stop_all_assists':
            logger.debug("Detected 'stop_all_assists' callback msg")

            self.checkboxvar['FSD Route Assist'].set(0)
            self.check_cb('FSD Route Assist')

            self.checkboxvar['Supercruise Assist'].set(0)
            self.check_cb('Supercruise Assist')

            self.checkboxvar['Waypoint Assist'].set(0)
            self.check_cb('Waypoint Assist')

            self.checkboxvar['Robigo Assist'].set(0)
            self.check_cb('Robigo Assist')

            self.checkboxvar['AFK Combat Assist'].set(0)
            self.check_cb('AFK Combat Assist')

            self.checkboxvar['DSS Assist'].set(0)
            self.check_cb('DSS Assist')

            self.checkboxvar['Single Waypoint Assist'].set(0)
            self.check_cb('Single Waypoint Assist')

        elif msg == 'jumpcount':
            self.update_jumpcount(body)
        elif msg == 'update_ship_cfg':
            self.root.after(0, self.update_ship_cfg)
        elif msg == 'load_waypoints':
            # TODO - Enable this at some point to auto load the previous waypoints on startup. Not called at the moment.
            self.waypoint_editor_tab.editor_load_waypoint_file(body)
        elif msg == 'up':
            # TODO - Enable these to allow pips to be controlled by EDAP when using the defined keys (tbd). Not called at the moment.
            print('up')
            if ((self.ed_ap.status.get_flag(FlagsInMainShip) or self.ed_ap.status.get_flag(FlagsInFighter))
                    and self.ed_ap.status.get_gui_focus() == GuiFocusNoFocus):
                self.ed_ap.keys.send('ResetPowerDistribution')
                self.ed_ap.keys.send('IncreaseEnginesPower', repeat=3)
        elif msg == 'down':
            print('down')
            if ((self.ed_ap.status.get_flag(FlagsInMainShip) or self.ed_ap.status.get_flag(FlagsInFighter))
                    and self.ed_ap.status.get_gui_focus() == GuiFocusNoFocus):
                self.ed_ap.keys.send('ResetPowerDistribution')
        elif msg == 'left':
            print('left')
            if ((self.ed_ap.status.get_flag(FlagsInMainShip) or self.ed_ap.status.get_flag(FlagsInFighter))
                    and self.ed_ap.status.get_gui_focus() == GuiFocusNoFocus):
                self.ed_ap.keys.send('ResetPowerDistribution')
                self.ed_ap.keys.send('IncreaseSystemsPower', repeat=3)
        elif msg == 'right':
            print('right')
            if ((self.ed_ap.status.get_flag(FlagsInMainShip) or self.ed_ap.status.get_flag(FlagsInFighter))
                    and self.ed_ap.status.get_gui_focus() == GuiFocusNoFocus):
                self.ed_ap.keys.send('ResetPowerDistribution')
                self.ed_ap.keys.send('IncreaseWeaponsPower', repeat=3)

    def update_ship_cfg(self):
        """
        Load up the display with what we read from ED_AP for the current ship.
        Triggered when the ship is changed.
        @return:
        """
        self.entries['ship']['SunPitchUp+Time'].delete(0, tk.END)
        self.entries['ship']['SunPitchUp+Time'].insert(0, self.ed_ap.sunpitchuptime)

        if self.ed_ap.current_ship_cfg:
            self.throttle_keys = [key for key, value in self.ed_ap.current_ship_cfg.items() if 'Speed' in key]
            self.throttle_combo['values'] = self.throttle_keys

    def calibrate_callback(self):
        self.ed_ap.calibrate_target()

    def quit(self):
        logger.debug("Entered: quit")
        self.close_window()

    def close_window(self):
        logger.debug("Entered: close_window")
        self.stop_fsd()
        self.stop_sc()
        self.ed_ap.quit()
        sleep(0.1)
        self.root.destroy()

    # this routine is to stop any current autopilot activity
    def stop_all_assists(self):
        logger.debug("Entered: stop_all_assists")
        self.callback('stop_all_assists')

    def start_fsd(self):
        logger.debug("Entered: start_fsd")
        self.ed_ap.set_fsd_assist(True)
        self.FSD_A_running = True
        self.log_msg("FSD Route Assist start")
        self.ed_ap.vce.say("FSD Route Assist On")

    def stop_fsd(self):
        logger.debug("Entered: stop_fsd")
        self.ed_ap.set_fsd_assist(False)
        self.FSD_A_running = False
        self.log_msg("FSD Route Assist stop")
        self.ed_ap.vce.say("FSD Route Assist Off")
        self.update_statusline("Idle")

    def start_sc(self):
        logger.debug("Entered: start_sc")
        self.ed_ap.set_sc_assist(True)
        self.SC_A_running = True
        self.log_msg("SC Assist start")
        self.ed_ap.vce.say("Supercruise Assist On")

    def stop_sc(self):
        logger.debug("Entered: stop_sc")
        self.ed_ap.set_sc_assist(False)
        self.SC_A_running = False
        self.log_msg("SC Assist stop")
        self.ed_ap.vce.say("Supercruise Assist Off")
        self.update_statusline("Idle")

    def start_waypoint(self):
        logger.debug("Entered: start_waypoint")
        self.ed_ap.set_waypoint_assist(True)
        self.WP_A_running = True
        self.log_msg("Waypoint Assist start")
        self.ed_ap.vce.say("Waypoint Assist On")

    def stop_waypoint(self):
        logger.debug("Entered: stop_waypoint")
        self.ed_ap.set_waypoint_assist(False)
        self.WP_A_running = False
        self.log_msg("Waypoint Assist stop")
        self.ed_ap.vce.say("Waypoint Assist Off")
        self.update_statusline("Idle")

    def start_robigo(self):
        logger.debug("Entered: start_robigo")
        self.ed_ap.set_robigo_assist(True)
        self.RO_A_running = True
        self.log_msg("Robigo Assist start")
        self.ed_ap.vce.say("Robigo Assist On")

    def stop_robigo(self):
        logger.debug("Entered: stop_robigo")
        self.ed_ap.set_robigo_assist(False)
        self.RO_A_running = False
        self.log_msg("Robigo Assist stop")
        self.ed_ap.vce.say("Robigo Assist Off")
        self.update_statusline("Idle")

    def start_dss(self):
        logger.debug("Entered: start_dss")
        self.ed_ap.set_dss_assist(True)
        self.DSS_A_running = True
        self.log_msg("DSS Assist start")
        self.ed_ap.vce.say("DSS Assist On")

    def stop_dss(self):
        logger.debug("Entered: stop_dss")
        self.ed_ap.set_dss_assist(False)
        self.DSS_A_running = False
        self.log_msg("DSS Assist stop")
        self.ed_ap.vce.say("DSS Assist Off")
        self.update_statusline("Idle")

    def start_single_waypoint_assist(self):
        """ The debug command to go to a system or station or both."""
        logger.debug("Entered: start_single_waypoint_assist")
        system = self.single_waypoint_system.get()
        station = self.single_waypoint_station.get()

        if system != "" or station != "":
            self.ed_ap.set_single_waypoint_assist(system, station, True)
            self.SWP_A_running = True
            self.log_msg("Single Waypoint Assist start")
            self.ed_ap.vce.say("Single Waypoint Assist On")

    def stop_single_waypoint_assist(self):
        """ The debug command to go to a system or station or both."""
        logger.debug("Entered: stop_single_waypoint_assist")
        self.ed_ap.set_single_waypoint_assist("", "", False)
        self.SWP_A_running = False
        self.log_msg("Single Waypoint Assist stop")
        self.ed_ap.vce.say("Single Waypoint Assist Off")
        self.update_statusline("Idle")

    def about(self):
        webbrowser.open_new("https://github.com/SumZer0-git/EDAPGui")

    def check_for_updates(self, repo_path):
        try:
            # Fetch the latest changes from the remote repository
            subprocess.run(["git", "fetch"], cwd=repo_path, check=True, capture_output=True)

            # Get the current commit hash of the local repository
            local_hash = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_path, capture_output=True, text=True,
                                        check=True).stdout.strip()

            # Get the commit hash of the remote repository
            remote_hash = subprocess.run(["git", "rev-parse", "origin/HEAD"], cwd=repo_path, capture_output=True,
                                         text=True, check=True).stdout.strip()

            # Compare the commit hashes
            if local_hash != remote_hash:
                print("The repository has been updated. Please clone it again to get the latest version.")
                return True
            else:
                print("The repository is up to date.")
                return False

        except subprocess.CalledProcessError as e:
            print(f"Error checking for updates: {e}")
            return False
        except FileNotFoundError:
            print("Git command not found. Please ensure Git is installed and in your system's PATH.")
            return False

    def check_updates(self):
        # response = requests.get("https://api.github.com/repos/SumZer0-git/EDAPGui/releases/latest")
        # if EDAP_VERSION != response.json()["name"]:
        #     mb = messagebox.askokcancel("Update Check", "A new release version is available. Download now?")
        #     if mb == True:
        #         webbrowser.open_new("https://github.com/SumZer0-git/EDAPGui/releases/latest")

        # Example usage:
        # repo_path = "/path/to/your/local/repo"
        repo_path = "./"
        updates_available = self.check_for_updates(repo_path)

        if updates_available:
            # Optionally, provide further instructions or automate the cloning process
            self.log_msg("=====================================================")
            self.log_msg("========== An update to EDAP is available ===========")
            self.log_msg("==== Click 'Check for Updates' on the Debug tab, ====")
            self.log_msg("====== or go directly to the EDAP Github page =======")
            self.log_msg("=====================================================")

            # print("You can use the following command to clone the repository again:")
            # print("git clone <repository_url> <new_directory_name>")
        else:
            self.log_msg("You have the latest version of EDAP!")

    def on_throttle_select(self, event):
        # The actual logi cis done on the edit curve buttons.
        pass

    def on_language_select(self, event):
        new_lang = self.language_var.get()
        self.ed_ap.config['Language'] = new_lang
        self.ed_ap.locale.change_language(new_lang)
        self.log_msg(f"Language set to '{new_lang}'. New log messages will use it immediately; "
                     f"restart EDAPGui for the interface labels to update.")

    def open_changelog(self):
        webbrowser.open_new("https://github.com/SumZer0-git/EDAPGui/blob/main/ChangeLog.md")

    def open_discord(self):
        webbrowser.open_new("https://discord.gg/HCgkfSc")

    def open_logfile(self):
        os.startfile('autopilot.log')

    def log_msg(self, msg):
        message = datetime.now().strftime("%H:%M:%S: ") + msg

        try:
            if not self.gui_loaded:
                # Store message in queue
                self.log_buffer.put(message)
                logger.info(msg)
            else:
                # Add queued messages to the list
                while not self.log_buffer.empty():
                    self.msgList.insert(tk.END, self.log_buffer.get())

                self.msgList.insert(tk.END, message)
                self.msgList.yview(tk.END)
                logger.info(msg)
        except:
            # Store message in queue
            self.log_buffer.put(message)
            logger.info(msg)

    def set_statusbar(self, txt):
        self.statusbar.configure(text=txt)

    def update_jumpcount(self, txt):
        self.jumpcount.configure(text=txt)

    def update_statusline(self, txt):
        self.status.configure(text=self.t('GUI_STATUS_PREFIX', 'Status: ') + txt)
        self.log_msg(f"Status update: {txt}")

    def toggle_mini_panel(self):
        """ Show/hide the compact always-on-top control panel over the game. """
        if self.mini_panel is not None and self.mini_panel.winfo_exists():
            self.mini_panel.destroy()
            self.mini_panel = None
            self.mini_info = None
            self.mini_edsm = None
            return
        self.create_mini_panel()

    def create_mini_panel(self):
        """ A small borderless always-on-top panel with the main assist toggles,
        so the user can control the autopilot without switching to the main window.
        Requires the game to run in Borderless/Windowed mode (as EDAP already does). """
        panel = tk.Toplevel(self.root)
        panel.overrideredirect(True)
        panel.attributes('-topmost', True)
        panel.attributes('-alpha', 0.88)
        panel.configure(bg='#101010')
        panel.geometry('+80+80')
        self.mini_panel = panel

        # Drag handle / title bar
        bar = tk.Frame(panel, bg='#2a2a2a')
        bar.pack(fill='x')
        tk.Label(bar, text='EDAP', bg='#2a2a2a', fg='#ff8800',
                 font=('Arial', 8, 'bold')).pack(side='left', padx=5)
        btn_close = tk.Label(bar, text=' ✕ ', bg='#2a2a2a', fg='#cccccc', cursor='hand2')
        btn_close.pack(side='right')
        btn_close.bind('<Button-1>', lambda e: self.toggle_mini_panel())

        def start_drag(e):
            panel._drag_x = e.x_root - panel.winfo_x()
            panel._drag_y = e.y_root - panel.winfo_y()

        def do_drag(e):
            panel.geometry(f'+{e.x_root - panel._drag_x}+{e.y_root - panel._drag_y}')

        bar.bind('<Button-1>', start_drag)
        bar.bind('<B1-Motion>', do_drag)

        body = tk.Frame(panel, bg='#101010')
        body.pack(padx=4, pady=4)

        def mk_toggle(col, text, field, on_color='#ff8800', on_bg='#5a3000'):
            b = tk.Checkbutton(body, text=text, indicatoron=False, width=5,
                               variable=self.checkboxvar[field],
                               command=(lambda f=field: self.check_cb(f)),
                               bg='#242424', fg=on_color, selectcolor=on_bg,
                               activebackground='#333333', activeforeground=on_color,
                               relief='flat', bd=0, font=('Arial', 9, 'bold'))
            b.grid(row=0, column=col, padx=2)
            return b

        mk_toggle(0, 'FSD', 'FSD Route Assist')
        mk_toggle(1, 'SC', 'Supercruise Assist')
        mk_toggle(2, 'WP', 'Waypoint Assist')
        btn_stop = tk.Button(body, text=self.t('MINI_BTN_STOP', 'STOP'), width=5,
                             command=self.stop_all_assists, bg='#5c1010', fg='white',
                             activebackground='#7c2020', activeforeground='white',
                             relief='flat', bd=0, font=('Arial', 9, 'bold'))
        btn_stop.grid(row=0, column=3, padx=2)
        mk_toggle(4, self.t('MINI_BTN_FAST', 'FAST'), 'Fast Travel', on_color='#30c030', on_bg='#124012')

        # Status/overlay info block, refreshed periodically
        self.mini_info = tk.Label(panel, text='', bg='#101010', fg='#e0a060',
                                  font=('Consolas', 9), justify='left', anchor='w')
        self.mini_info.pack(fill='x', padx=6, pady=(0, 2))
        self.mini_edsm = tk.Label(panel, text='', bg='#101010', fg='#30d030',
                                  font=('Consolas', 9, 'bold'), justify='left', anchor='w')
        self._mini_panel_tick()

    def _mini_panel_tick(self):
        """ Periodic refresh of the mini panel info block with the same data as the overlay. """
        if self.mini_panel is None or not self.mini_panel.winfo_exists():
            return
        try:
            lines = self.ed_ap.get_status_lines()
            normal = [t for t, hl in lines if not hl]
            highlighted = [t for t, hl in lines if hl]
            self.mini_info.configure(text='\n'.join(normal))
            if highlighted:
                self.mini_edsm.configure(text='\n'.join(highlighted))
                self.mini_edsm.pack(fill='x', padx=6, pady=(0, 4))
            else:
                self.mini_edsm.pack_forget()
        except Exception as e:
            logger.debug(f'mini panel tick failed: {e}')
        self.root.after(1000, self._mini_panel_tick)

    def t(self, key: str, default: str) -> str:
        if key is None:
            return default
        try:
            return self.locale[key]
        except Exception:
            return default

    def field_text(self, field: str) -> str:
        return self.t(self.form_locale_keys.get(field), field)

    def ship_throttle_0(self):
        self.ed_ap.set_throttle_0()

    def ship_throttle_50(self):
        self.ed_ap.set_throttle_50()

    def ship_throttle_100(self):
        self.ed_ap.set_throttle_100()

    def edit_roll_curve(self):
        # Get current ship roll curve
        if self.ed_ap.current_ship_cfg:
            # Get the selected speed from the combobox
            selected_throttle = self.throttle_var.get()  # i.e. SCSpeed50 etc.
            if selected_throttle in self.ed_ap.current_ship_cfg:
                spd_dmd_dict = self.ed_ap.current_ship_cfg[selected_throttle]
                if 'RollRate' in spd_dmd_dict:
                    curve = spd_dmd_dict['RollRate']
                    # Edit the curve
                    new_curve = line_editor(curve, f"{selected_throttle} - Roll curve")
                    if new_curve is not None:
                        if messagebox.askyesno("RPY curve", "Keep the changes made to curve? If Yes, remember to save."):
                            spd_dmd_dict['RollRate'] = new_curve
            else:
                messagebox.showinfo("EDAP", "Select a Throttle setting in the dropdown above.")

    def edit_pit_curve(self):
        # Get current ship pitch curve
        if self.ed_ap.current_ship_cfg:
            # Get the selected speed from the combobox
            selected_throttle = self.throttle_var.get()  # i.e. SCSpeed50 etc.
            if selected_throttle in self.ed_ap.current_ship_cfg:
                spd_dmd_dict = self.ed_ap.current_ship_cfg[selected_throttle]
                if 'PitchRate' in spd_dmd_dict:
                    curve = spd_dmd_dict['PitchRate']
                    # Edit the curve
                    new_curve = line_editor(curve, f"{selected_throttle} - Pitch curve")
                    if new_curve is not None:
                        if messagebox.askyesno("RPY curve", "Keep the changes made to curve? If Yes, remember to save."):
                            spd_dmd_dict['PitchRate'] = new_curve
            else:
                messagebox.showinfo("EDAP", "Select a Throttle setting in the dropdown above.")

    def edit_yaw_curve(self):
        # Get current ship yaw curve
        if self.ed_ap.current_ship_cfg:
            # Get the selected speed from the combobox
            selected_throttle = self.throttle_var.get()  # i.e. SCSpeed50 etc.
            if selected_throttle in self.ed_ap.current_ship_cfg:
                spd_dmd_dict = self.ed_ap.current_ship_cfg[selected_throttle]
                if 'YawRate' in spd_dmd_dict:
                    curve = spd_dmd_dict['YawRate']
                    # Edit the curve
                    new_curve = line_editor(curve, f"{selected_throttle} - Pitch curve")
                    if new_curve is not None:
                        if messagebox.askyesno("RPY curve", "Keep the changes made to curve? If Yes, remember to save."):
                            spd_dmd_dict['YawRate'] = new_curve
            else:
                messagebox.showinfo("EDAP", "Select a Throttle setting in the dropdown above.")

    def tuning_align_target(self):
        """
        Aligns to the target for tuning.
        @return: N/A
        """
        self.ed_ap.compass_align(self.ed_ap.scrReg)

    def save_settings(self):
        self.entry_update(None)
        self.ed_ap.update_config()
        self.ed_ap.update_ship_configs()
        self.calibration.save_ocr_calibration_data()
        self.log_msg("Saved all settings.")

    def load_settings(self):
        self.ed_ap.load_ship_configs()

    def open_help(self):
        # Determine the active Tab
        tab_text = self._nb.tab(self._nb.select(), "text")

        if tab_text == "Main":
            webbrowser.open_new("https://github.com/SumZer0-git/EDAPGui/blob/main/docs/Main.md")
        elif tab_text == "Settings":
            webbrowser.open_new("https://github.com/SumZer0-git/EDAPGui/blob/main/docs/Settings.md")
        elif tab_text == self.t('GUI_TAB_GAME', 'Game'):
            webbrowser.open_new("https://github.com/SumZer0-git/EDAPGui/blob/main/docs/Settings.md")
        elif tab_text == "Debug/Test":
            webbrowser.open_new("https://github.com/SumZer0-git/EDAPGui/blob/main/docs/DebugTest.md")
        elif tab_text == "Calibration":
            webbrowser.open_new("https://github.com/SumZer0-git/EDAPGui/blob/main/docs/Calibration.md")
        elif tab_text == "Waypoints":
            webbrowser.open_new("https://github.com/SumZer0-git/EDAPGui/blob/main/docs/WaypointEditor.md")
        elif tab_text == "Colonization":
            webbrowser.open_new("https://github.com/SumZer0-git/EDAPGui/blob/main/docs/ColonizationEditor.md")
        elif tab_text == "TCE":
            webbrowser.open_new("https://github.com/SumZer0-git/EDAPGui/blob/main/docs/TCE.md")
        else:
            messagebox.showwarning("Warning", f"No match for tab text '{tab_text}'. Please report to developers.")
            webbrowser.open_new("https://github.com/SumZer0-git/EDAPGui/blob/main/docs/Main.md")


    def entry_update(self, event):
        """
        # new data was added to a field, re-read them all for simple logic
        @param event: A dummy argument required the calling function.
        @return: Nothing
        """
        try:
            self.ed_ap.sunpitchuptime = float(self.entries['ship']['SunPitchUp+Time'].get())

            self.ed_ap.config['SunBrightThreshold'] = int(self.entries['autopilot']['Sun Bright Threshold'].get())
            self.ed_ap.config['NavAlignTries'] = int(self.entries['autopilot']['Nav Align Tries'].get())
            self.ed_ap.config['JumpTries'] = int(self.entries['autopilot']['Jump Tries'].get())
            self.ed_ap.config['DockingRetries'] = int(self.entries['autopilot']['Docking Retries'].get())
            self.ed_ap.config['WaitForAutoDockTimer'] = int(self.entries['autopilot']['Wait For Autodock'].get())
            self.ed_ap.config['RefuelThreshold'] = int(self.entries['refuel']['Refuel Threshold'].get())
            self.ed_ap.config['FuelScoopTimeOut'] = int(self.entries['refuel']['Scoop Timeout'].get())
            self.ed_ap.config['FuelThreasholdAbortAP'] = int(self.entries['refuel']['Fuel Threshold Abort'].get())
            self.ed_ap.config['OverlayTextXOffset'] = int(self.entries['overlay']['X Offset'].get())
            self.ed_ap.config['OverlayTextYOffset'] = int(self.entries['overlay']['Y Offset'].get())
            self.ed_ap.config['OverlayTextFontSize'] = int(self.entries['overlay']['Font Size'].get())
            self.ed_ap.config['HotKey_StartFSD'] = str(self.entries['buttons']['Start FSD'].get())
            self.ed_ap.config['HotKey_StartSC'] = str(self.entries['buttons']['Start SC'].get())
            self.ed_ap.config['HotKey_StartRobigo'] = str(self.entries['buttons']['Start Robigo'].get())
            self.ed_ap.config['HotKey_StopAllAssists'] = str(self.entries['buttons']['Stop All'].get())
            self.ed_ap.config['VoiceEnable'] = self.checkboxvar['Enable Voice'].get()
            self.ed_ap.config['ElwScannerEnable'] = self.checkboxvar['ELW Scanner'].get()
            self.ed_ap.config['DebugOverlay'] = self.checkboxvar['Debug Overlay'].get()
            self.ed_ap.config['AFKCombat_AttackAtWill'] = self.checkboxvar['AFKCombat AttackAtWill'].get()
            self.ed_ap.config['HotkeysEnable'] = self.checkboxvar['Enable Hotkeys'].get()
            self.ed_ap.config['DebugOCR'] = self.checkboxvar['Debug OCR'].get()
            self.ed_ap.config['DebugImages'] = self.checkboxvar['Debug Images'].get()
            self.ed_ap.config['Key_ModDelay'] = float(self.entries['keys']['Modifier Key Delay'].get())
            self.ed_ap.config['Key_DefHoldTime'] = float(self.entries['keys']['Default Hold Time'].get())
            self.ed_ap.config['Key_RepeatDelay'] = float(self.entries['keys']['Repeat Key Delay'].get())
            self.ed_ap.config['AutoTuneRPYRates'] = self.checkboxvar['Enable Auto-tune RPY'].get()
            self.ed_ap.config['Wait_FSSDetect'] = float(self.entries['game_waits']['FSS Detect Wait'].get())
            self.ed_ap.config['Wait_DockApproach'] = float(self.entries['game_waits']['Dock Approach Time'].get())
            self.ed_ap.config['Wait_ShipStop'] = float(self.entries['game_waits']['Ship Stop Wait'].get())
            self.ed_ap.config['Wait_OccludedReposition'] = float(self.entries['game_waits']['Occluded Reposition Time'].get())
            self.ed_ap.config['Wait_DSSScan'] = float(self.entries['game_waits']['DSS Scan Time'].get())
            self.ed_ap.config['Wait_PastSun'] = float(self.entries['game_waits']['Past Sun Time'].get())
            self.ed_ap.config['Wait_HeatDissipate'] = float(self.entries['game_waits']['Heat Dissipate Time'].get())
            self.ed_ap.config['Wait_AfterJump'] = float(self.entries['game_waits']['After Jump Wait'].get())
            self.ed_ap.config['GalMap_SystemSelectDelay'] = float(self.entries['game_waits']['GalMap Select Delay'].get())
            self.ed_ap.config['PlanetDepartureSCOTime'] = float(self.entries['game_waits']['Planet Departure SCO Time'].get())
            self.ed_ap.config['FCDepartureTime'] = float(self.entries['game_waits']['FC Departure Time'].get())

            # Process config[] settings to update classes as necessary
            self.ed_ap.process_config_settings()
        except:
            messagebox.showinfo("Exception", "Invalid float entered")

    def check_cb(self, field):
        """ Check checkbox
            ckbox.state:(ACTIVE | DISABLED)
            ('FSD Route Assist', 'Supercruise Assist', 'Enable Voice', 'Enable CV View')
        """
        # print("got event:",  checkboxvar['FSD Route Assist'].get(), " ", str(FSD_A_running))
        if field == 'FSD Route Assist':
            if self.checkboxvar['FSD Route Assist'].get() == 1 and self.FSD_A_running == False:
                self.lab_ck['AFK Combat Assist'].config(state='disabled')
                self.lab_ck['Supercruise Assist'].config(state='disabled')
                self.lab_ck['Waypoint Assist'].config(state='disabled')
                self.lab_ck['Robigo Assist'].config(state='disabled')
                self.lab_ck['DSS Assist'].config(state='disabled')
                self.start_fsd()

            elif self.checkboxvar['FSD Route Assist'].get() == 0 and self.FSD_A_running == True:
                self.stop_fsd()
                self.lab_ck['Supercruise Assist'].config(state='active')
                self.lab_ck['AFK Combat Assist'].config(state='active')
                self.lab_ck['Waypoint Assist'].config(state='active')
                self.lab_ck['Robigo Assist'].config(state='active')
                self.lab_ck['DSS Assist'].config(state='active')

        if field == 'Supercruise Assist':
            if self.checkboxvar['Supercruise Assist'].get() == 1 and self.SC_A_running == False:
                self.lab_ck['FSD Route Assist'].config(state='disabled')
                self.lab_ck['AFK Combat Assist'].config(state='disabled')
                self.lab_ck['Waypoint Assist'].config(state='disabled')
                self.lab_ck['Robigo Assist'].config(state='disabled')
                self.lab_ck['DSS Assist'].config(state='disabled')
                self.start_sc()

            elif self.checkboxvar['Supercruise Assist'].get() == 0 and self.SC_A_running == True:
                self.stop_sc()
                self.lab_ck['FSD Route Assist'].config(state='active')
                self.lab_ck['AFK Combat Assist'].config(state='active')
                self.lab_ck['Waypoint Assist'].config(state='active')
                self.lab_ck['Robigo Assist'].config(state='active')
                self.lab_ck['DSS Assist'].config(state='active')

        if field == 'Waypoint Assist':
            if self.checkboxvar['Waypoint Assist'].get() == 1 and self.WP_A_running == False:
                self.lab_ck['FSD Route Assist'].config(state='disabled')
                self.lab_ck['Supercruise Assist'].config(state='disabled')
                self.lab_ck['AFK Combat Assist'].config(state='disabled')
                self.lab_ck['Robigo Assist'].config(state='disabled')
                self.lab_ck['DSS Assist'].config(state='disabled')
                self.start_waypoint()

            elif self.checkboxvar['Waypoint Assist'].get() == 0 and self.WP_A_running == True:
                self.stop_waypoint()
                self.lab_ck['FSD Route Assist'].config(state='active')
                self.lab_ck['Supercruise Assist'].config(state='active')
                self.lab_ck['AFK Combat Assist'].config(state='active')
                self.lab_ck['Robigo Assist'].config(state='active')
                self.lab_ck['DSS Assist'].config(state='active')

        if field == 'Robigo Assist':
            if self.checkboxvar['Robigo Assist'].get() == 1 and self.RO_A_running == False:
                self.lab_ck['FSD Route Assist'].config(state='disabled')
                self.lab_ck['Supercruise Assist'].config(state='disabled')
                self.lab_ck['AFK Combat Assist'].config(state='disabled')
                self.lab_ck['Waypoint Assist'].config(state='disabled')
                self.lab_ck['DSS Assist'].config(state='disabled')
                self.start_robigo()

            elif self.checkboxvar['Robigo Assist'].get() == 0 and self.RO_A_running == True:
                self.stop_robigo()
                self.lab_ck['FSD Route Assist'].config(state='active')
                self.lab_ck['Supercruise Assist'].config(state='active')
                self.lab_ck['AFK Combat Assist'].config(state='active')
                self.lab_ck['Waypoint Assist'].config(state='active')
                self.lab_ck['DSS Assist'].config(state='active')

        if field == 'AFK Combat Assist':
            if self.checkboxvar['AFK Combat Assist'].get() == 1:
                self.ed_ap.set_afk_combat_assist(True)
                self.log_msg("AFK Combat Assist start")
                self.lab_ck['FSD Route Assist'].config(state='disabled')
                self.lab_ck['Supercruise Assist'].config(state='disabled')
                self.lab_ck['Waypoint Assist'].config(state='disabled')
                self.lab_ck['Robigo Assist'].config(state='disabled')
                self.lab_ck['DSS Assist'].config(state='disabled')

            elif self.checkboxvar['AFK Combat Assist'].get() == 0:
                self.ed_ap.set_afk_combat_assist(False)
                self.log_msg("AFK Combat Assist stop")
                self.lab_ck['FSD Route Assist'].config(state='active')
                self.lab_ck['Supercruise Assist'].config(state='active')
                self.lab_ck['Waypoint Assist'].config(state='active')
                self.lab_ck['Robigo Assist'].config(state='active')
                self.lab_ck['DSS Assist'].config(state='active')

        if field == 'DSS Assist':
            if self.checkboxvar['DSS Assist'].get() == 1:
                self.lab_ck['FSD Route Assist'].config(state='disabled')
                self.lab_ck['AFK Combat Assist'].config(state='disabled')
                self.lab_ck['Supercruise Assist'].config(state='disabled')
                self.lab_ck['Waypoint Assist'].config(state='disabled')
                self.lab_ck['Robigo Assist'].config(state='disabled')
                self.start_dss()

            elif self.checkboxvar['DSS Assist'].get() == 0:
                self.stop_dss()
                self.lab_ck['FSD Route Assist'].config(state='active')
                self.lab_ck['Supercruise Assist'].config(state='active')
                self.lab_ck['AFK Combat Assist'].config(state='active')
                self.lab_ck['Waypoint Assist'].config(state='active')
                self.lab_ck['Robigo Assist'].config(state='active')

        if self.checkboxvar['Enable Randomness'].get():
            self.ed_ap.set_randomness(True)
        else:
            self.ed_ap.set_randomness(False)

        if self.checkboxvar['Activate Elite for each key'].get():
            self.ed_ap.set_activate_elite_eachkey(True)
            self.ed_ap.keys.activate_window = True
        else:
            self.ed_ap.set_activate_elite_eachkey(False)
            self.ed_ap.keys.activate_window = False

        if self.checkboxvar['Automatic logout'].get():
            self.ed_ap.set_automatic_logout(True)
        else:
            self.ed_ap.set_automatic_logout(False)

        if self.checkboxvar['Enable Overlay'].get():
            self.ed_ap.set_overlay(True)
        else:
            self.ed_ap.set_overlay(False)

        if self.checkboxvar['Enable Voice'].get():
            self.ed_ap.set_voice(True)
        else:
            self.ed_ap.set_voice(False)

        if self.checkboxvar['ELW Scanner'].get():
            self.ed_ap.set_fss_scan(True)
        else:
            self.ed_ap.set_fss_scan(False)

        if self.checkboxvar['Enable CV View'].get() == 1:
            self.cv_view = True
            x = self.root.winfo_x() + self.root.winfo_width() + 4
            y = self.root.winfo_y()
            self.ed_ap.set_cv_view(True, x, y)
        else:
            self.cv_view = False
            self.ed_ap.set_cv_view(False)

        self.ed_ap.config['DSSButton'] = self.radiobuttonvar['dss_button'].get()

        if self.radiobuttonvar['debug_mode'].get() == "Error":
            self.ed_ap.set_log_error(True)
        elif self.radiobuttonvar['debug_mode'].get() == "Debug":
            self.ed_ap.set_log_debug(True)
        elif self.radiobuttonvar['debug_mode'].get() == "Info":
            self.ed_ap.set_log_info(True)

        if field == 'Single Waypoint Assist':
            if self.checkboxvar['Single Waypoint Assist'].get() == 1 and self.SWP_A_running == False:
                self.start_single_waypoint_assist()
            elif self.checkboxvar['Single Waypoint Assist'].get() == 0 and self.SWP_A_running == True:
                self.stop_single_waypoint_assist()

        if field == 'Debug Overlay':
            if self.checkboxvar['Debug Overlay'].get():
                self.ed_ap.debug_overlay = True
            else:
                self.ed_ap.debug_overlay = False

        self.ed_ap.config['AFKCombat_AttackAtWill'] = self.checkboxvar['AFKCombat AttackAtWill'].get()

        if field == 'Enable Hotkeys':
            self.ed_ap.config['HotkeysEnable'] = self.checkboxvar['Enable Hotkeys'].get()
            self.setup_hotkeys()

        if field == 'Debug OCR':
            self.ed_ap.debug_ocr = self.checkboxvar['Debug OCR'].get()

        if field == 'Debug Images':
            self.ed_ap.debug_images = self.checkboxvar['Debug Images'].get()

        if field == 'Enable Auto-tune RPY':
            self.ed_ap.config['AutoTuneRPYRates'] = self.checkboxvar['Enable Auto-tune RPY'].get()

        if field == 'Fast Travel':
            self.ed_ap.config['FastTravelMode'] = bool(self.checkboxvar['Fast Travel'].get())

    def makeform(self, win: ttk.LabelFrame, f_type: int, fields, r: int = 0, inc: float = 1, r_from: float = 0,
                 rto: float = 1000):
        entries = {}
        win.columnconfigure(1, weight=1)

        for fld in fields:
            display_fld = self.field_text(fld)
            if f_type == FORM_TYPE_CHECKBOX:
                self.checkboxvar[fld] = tk.IntVar()
                lab = ttk.Checkbutton(win, text=display_fld, variable=self.checkboxvar[fld],
                                      command=(lambda field=fld: self.check_cb(field)))
                self.lab_ck[fld] = lab
                lab.grid(row=r, column=0, columnspan=2, padx=2, pady=2, sticky=tk.W)
            else:
                lab = ttk.Label(win, text=display_fld + ": ")
                if f_type == FORM_TYPE_SPINBOX:
                    ent = ttk.Spinbox(win, width=10, from_=r_from, to=rto, increment=inc, justify=tk.RIGHT)
                else:
                    ent = ttk.Entry(win, width=10, justify=tk.RIGHT)
                ent.bind('<FocusOut>', self.entry_update)
                ent.insert(0, "0")
                lab.grid(row=r, column=0, padx=2, pady=2, sticky=tk.W)
                ent.grid(row=r, column=1, padx=2, pady=2, sticky=tk.E)
                entries[fld] = ent

            lab = ToolTip(lab, msg=self.tooltips[fld], delay=1.0, bg="#808080", fg="#FFFFFF")
            r += 1
        return entries

    def create_game_tab(self, page):
        """ Creates the 'Game' tab: game control bindings, AP wait times and current game settings. """
        game_waits_entry_fields = ('FSS Detect Wait', 'Dock Approach Time', 'Ship Stop Wait',
                                   'Occluded Reposition Time', 'DSS Scan Time', 'Past Sun Time',
                                   'Heat Dissipate Time', 'After Jump Wait', 'GalMap Select Delay',
                                   'Planet Departure SCO Time', 'FC Departure Time')

        # Game control bindings block (left column)
        blk_bindings = ttk.LabelFrame(page, text=self.t('GUI_GROUP_GAME_CONTROLS', 'GAME CONTROL BINDINGS'), padding=(10, 5))
        blk_bindings.grid(row=0, column=0, rowspan=2, padx=10, pady=5, sticky="NSEW")
        blk_bindings.grid_columnconfigure(0, weight=1)
        blk_bindings.grid_rowconfigure(1, weight=1)

        self.bindings_file_var = tk.StringVar()
        lbl_binds_file = ttk.Label(blk_bindings, textvariable=self.bindings_file_var, wraplength=400)
        lbl_binds_file.grid(row=0, column=0, columnspan=2, padx=2, pady=2, sticky=tk.W)

        columns = ('binding', 'key', 'status')
        self.bindings_tree = ttk.Treeview(blk_bindings, columns=columns, show='headings', height=18)
        self.bindings_tree.heading('binding', text=self.t('GUI_COL_BINDING', 'Binding'))
        self.bindings_tree.heading('key', text=self.t('GUI_COL_KEY', 'Key'))
        self.bindings_tree.heading('status', text=self.t('GUI_COL_STATUS', 'Status'))
        self.bindings_tree.column('binding', width=330, anchor=tk.W)
        self.bindings_tree.column('key', width=150, anchor=tk.W)
        self.bindings_tree.column('status', width=100, anchor=tk.CENTER)
        self.bindings_tree.grid(row=1, column=0, padx=2, pady=2, sticky="NSEW")
        scroll_bindings = ttk.Scrollbar(blk_bindings, orient=tk.VERTICAL, command=self.bindings_tree.yview)
        scroll_bindings.grid(row=1, column=1, sticky="NS")
        self.bindings_tree.configure(yscrollcommand=scroll_bindings.set)

        btn_reload_binds = ttk.Button(blk_bindings, text=self.t('GUI_BTN_RELOAD_BINDINGS', 'Reload bindings from game'),
                                      command=self.reload_game_bindings)
        btn_reload_binds.grid(row=2, column=0, columnspan=2, padx=2, pady=5, sticky="EW")

        btn_assign_keys = ttk.Button(blk_bindings, text=self.t('GUI_BTN_ASSIGN_MISSING_KEYS', 'Auto-assign missing keys (into free slots)'),
                                     command=self.assign_missing_keys)
        btn_assign_keys.grid(row=3, column=0, columnspan=2, padx=2, pady=2, sticky="EW")

        self.populate_bindings_tree()

        # AP waits block (right column)
        blk_waits = ttk.LabelFrame(page, text=self.t('GUI_GROUP_AP_WAITS', 'AP WAITS/DELAYS (sec)'), padding=(10, 5))
        blk_waits.grid(row=0, column=1, padx=10, pady=5, sticky="NSEW")
        self.entries['game_waits'] = self.makeform(blk_waits, FORM_TYPE_SPINBOX, game_waits_entry_fields, 0, 0.5, 0.0, 600.0)

        # Current game settings block (right column)
        blk_game_settings = ttk.LabelFrame(page, text=self.t('GUI_GROUP_GAME_SETTINGS', 'CURRENT GAME SETTINGS'), padding=(10, 5))
        blk_game_settings.grid(row=1, column=1, padx=10, pady=5, sticky="NSEW")
        blk_game_settings.grid_columnconfigure(1, weight=1)

        game_setting_rows = (
            ('resolution', self.t('GUI_LABEL_GAME_RESOLUTION', 'Resolution:')),
            ('screen_mode', self.t('GUI_LABEL_GAME_SCREEN_MODE', 'Screen mode:')),
            ('monitor', self.t('GUI_LABEL_GAME_MONITOR', 'Monitor:')),
            ('fov', self.t('GUI_LABEL_GAME_FOV', 'FOV:')),
            ('brightness', self.t('GUI_LABEL_GAME_BRIGHTNESS', 'Interface brightness:')),
            ('nav_icons', self.t('GUI_LABEL_GAME_NAV_ICONS', 'Location status icons:')),
            ('game_language', self.t('GUI_LABEL_GAME_LANGUAGE', 'Game language:')),
        )
        self.game_setting_vars = {}
        self.game_setting_labels = {}
        for i, (key, label_text) in enumerate(game_setting_rows):
            lbl = ttk.Label(blk_game_settings, text=label_text)
            lbl.grid(row=i, column=0, padx=2, pady=2, sticky=tk.W)
            self.game_setting_vars[key] = tk.StringVar(value='-')
            lbl_val = ttk.Label(blk_game_settings, textvariable=self.game_setting_vars[key])
            lbl_val.grid(row=i, column=1, padx=2, pady=2, sticky=tk.W)
            self.game_setting_labels[key] = lbl_val

        btn_refresh_game = ttk.Button(blk_game_settings, text=self.t('GUI_BTN_REFRESH_GAME_SETTINGS', 'Refresh game settings'),
                                      command=self.refresh_game_settings)
        btn_refresh_game.grid(row=len(game_setting_rows), column=0, columnspan=2, padx=2, pady=5, sticky="EW")

        self.refresh_game_settings(log=False)

    def populate_bindings_tree(self):
        """ Fills the game control bindings table from the loaded .binds file. """
        keys = self.ed_ap.keys
        self.bindings_tree.delete(*self.bindings_tree.get_children())

        binds_file = keys.get_latest_keybinds()
        self.bindings_file_var.set(self.t('GUI_LABEL_BINDS_FILE', 'Bindings file: ')
                                   + (binds_file if binds_file else self.t('GUI_BINDS_FILE_NOT_FOUND', 'not found')))

        ok_text = self.t('GUI_BINDING_OK', 'OK')
        missing_text = self.t('GUI_BINDING_MISSING', 'NOT ASSIGNED')
        for binding in keys.keys_to_obtain:
            readable = self.t('GUI_BIND_' + binding, '')
            display_name = f"{readable} ({binding})" if readable else binding
            key_name = keys.get_binding_display_name(binding)
            if key_name:
                self.bindings_tree.insert('', tk.END, values=(display_name, key_name, ok_text))
            else:
                self.bindings_tree.insert('', tk.END, values=(display_name, '-', missing_text), tags=('missing',))
        self.bindings_tree.tag_configure('missing', foreground='#e04747')

    def reload_game_bindings(self):
        """ Re-reads the latest .binds file from the game and refreshes the bindings table. """
        try:
            self.ed_ap.keys.reload_bindings()
            self.log_msg(self.t('LOG_BINDINGS_RELOADED', 'Game key bindings reloaded.'))
        except Exception as e:
            self.log_msg(self.t('LOG_BINDINGS_RELOAD_FAILED', 'Failed to reload game key bindings: ') + str(e))
        self.populate_bindings_tree()

    def assign_missing_keys(self):
        """ Auto-assigns free keyboard keys to AP actions without a keyboard binding,
        writing them into free Primary/Secondary slots of the game .binds file. """
        confirm_text = self.t('GUI_ASSIGN_KEYS_CONFIRM',
                              'This will write free keyboard keys into empty Primary/Secondary slots of the game '
                              'bindings file for the actions the autopilot needs. Joystick/HOTAS bindings are kept. '
                              'A backup copy of the file will be created.\n\n'
                              'IMPORTANT: Close Elite Dangerous first, or restart it afterwards, otherwise the game '
                              'will not pick up (and may overwrite) the changes.\n\nContinue?')
        if not messagebox.askyesno("EDAP", confirm_text):
            return
        try:
            result = self.ed_ap.keys.assign_missing_keyboard_binds()
        except Exception as e:
            self.log_msg(self.t('LOG_KEYS_ASSIGN_FAILED', 'Failed to auto-assign keyboard keys: ') + str(e))
            messagebox.showerror("EDAP", self.t('LOG_KEYS_ASSIGN_FAILED', 'Failed to auto-assign keyboard keys: ') + str(e))
            return

        if not result['assigned'] and not result['skipped']:
            messagebox.showinfo("EDAP", self.t('GUI_ASSIGN_KEYS_RESULT_NONE',
                                               'All autopilot actions already have keyboard bindings.'))
            return

        lines = []
        if result['assigned']:
            lines.append(self.t('GUI_ASSIGN_KEYS_RESULT_ASSIGNED', 'Assigned keys:'))
            for action, key in result['assigned'].items():
                readable = self.t('GUI_BIND_' + action, '')
                display = f"{readable} ({action})" if readable else action
                lines.append(f"  {display}: {key.replace('Key_', '')}")
            self.log_msg(self.t('LOG_BINDS_BACKUP', 'Bindings backup created: ') + result['backup'])
        if result['skipped']:
            lines.append('')
            lines.append(self.t('GUI_ASSIGN_KEYS_RESULT_SKIPPED', 'Skipped (no free slot, assign manually in game):'))
            for action in result['skipped']:
                readable = self.t('GUI_BIND_' + action, '')
                display = f"{readable} ({action})" if readable else action
                lines.append(f"  {display}")
        lines.append('')
        lines.append(self.t('GUI_ASSIGN_KEYS_RESTART_NOTE', 'Restart Elite Dangerous for the changes to take effect.'))
        msg = '\n'.join(lines)
        self.log_msg(msg)
        messagebox.showinfo("EDAP", msg)
        self.populate_bindings_tree()

    def refresh_game_settings(self, log=True):
        """ Re-reads the game settings files (graphics/player) and updates the display. """
        warn_color = '#e04747'
        default_color = ttk.Style().lookup('TLabel', 'foreground') or ''

        def set_value(key, value, warn=False):
            self.game_setting_vars[key].set(value)
            self.game_setting_labels[key].configure(foreground=warn_color if warn else default_color)

        try:
            gfx = EDGraphicsSettings()
            self.ed_ap.gfx_settings = gfx
            set_value('resolution', f"{gfx.screenwidth} x {gfx.screenheight}")
            set_value('screen_mode', gfx.fullscreen_str, warn=gfx.fullscreen_str.upper() != 'BORDERLESS')
            set_value('monitor', str(gfx.monitor))
            set_value('fov', str(gfx.fov))
        except Exception as e:
            for key in ('resolution', 'screen_mode', 'monitor', 'fov'):
                set_value(key, '?', warn=True)
            if log:
                self.log_msg(self.t('LOG_GFX_SETTINGS_READ_FAILED', 'Failed to read game graphics settings: ') + str(e))

        try:
            player = EDPlayerSettings(self.callback, locale=self.locale)
            self.ed_ap.player_settings = player
            brightness = float(player.dashboard_gui_brightness)
            set_value('brightness', f"{brightness:.2f}", warn=brightness < 1.0)
            icons_hidden = int(player.hide_location_icons) == 1
            set_value('nav_icons',
                      self.t('GUI_GAME_ICONS_HIDDEN', 'Hidden') if icons_hidden else self.t('GUI_GAME_ICONS_SHOWN', 'Shown'),
                      warn=icons_hidden)
        except Exception as e:
            for key in ('brightness', 'nav_icons'):
                set_value(key, '?', warn=True)
            if log:
                self.log_msg(self.t('LOG_PLAYER_SETTINGS_READ_FAILED', 'Failed to read game player settings: ') + str(e))

        # The actual game session language comes from the journal Fileheader (the player
        # settings file only holds the in-game override, which is usually inactive).
        # OCR strings come from the active EDAP locale file, so the game language must
        # match what that locale's screen-text strings are written for.
        expected_lang = self.t('OCR_GAME_LANGUAGE', 'English')
        game_lang = ''
        if self.ed_ap.jn:
            game_lang = self.ed_ap.jn.get_game_language().split('/')[0]
        if game_lang:
            set_value('game_language', game_lang, warn=game_lang != expected_lang)
        else:
            set_value('game_language', '?', warn=True)

    def gui_gen(self, win):

        modes_check_fields = ('FSD Route Assist', 'Supercruise Assist', 'Waypoint Assist', 'Robigo Assist', 'AFK Combat Assist', 'DSS Assist')
        autopilot_entry_fields = ('Sun Bright Threshold', 'Nav Align Tries', 'Jump Tries', 'Docking Retries', 'Wait For Autodock')
        buttons_entry_fields = ('Start FSD', 'Start SC', 'Start Robigo', 'Stop All')
        refuel_entry_fields = ('Refuel Threshold', 'Scoop Timeout', 'Fuel Threshold Abort')
        overlay_entry_fields = ('X Offset', 'Y Offset', 'Font Size')
        keys_entry_fields = ('Modifier Key Delay', 'Default Hold Time', 'Repeat Key Delay')

        # notebook pages
        blk_top_buttons = ttk.Frame(win)
        blk_top_buttons.grid(row=0, column=0, padx=10, pady=5, sticky="EW")
        blk_top_buttons.columnconfigure(0)
        blk_top_buttons.columnconfigure(1, weight=1)

        btn_load = ttk.Button(blk_top_buttons, text=self.t('GUI_BTN_LOAD_ALL_SETTINGS', 'Load All Settings'), command=self.load_settings)
        btn_load.grid(row=0, column=0, padx=5, pady=5, sticky="W")
        btn_save = ttk.Button(blk_top_buttons, text=self.t('GUI_BTN_SAVE_ALL_SETTINGS', 'Save All Settings'), command=self.save_settings, style="Accent.TButton")
        btn_save.grid(row=0, column=1, padx=2, pady=5, sticky="W")
        ttk.Button(blk_top_buttons, text=self.t('GUI_BTN_ONLINE_HELP', 'Online HELP'), command=self.open_help, style="Accent.TButton").grid(row=0, column=2, padx=5, pady=10, sticky=tk.E)

        self._nb = ttk.Notebook(win)
        self._nb.grid(row=1, padx=10, pady=5, sticky="NSEW")

        page0 = ttk.Frame(self._nb)
        page0.grid_columnconfigure(0, weight=1)
        page0.grid_rowconfigure(0, weight=0)
        page0.grid_rowconfigure(1, weight=0)
        page0.grid_rowconfigure(2, weight=1)  # Log row
        self._nb.add(page0, text=self.t('GUI_TAB_MAIN', 'Main'))  # main page

        page1 = ttk.Frame(self._nb)
        page1.grid_columnconfigure(0, weight=1)
        self._nb.add(page1, text=self.t('GUI_TAB_SETTINGS', 'Settings'))  # options page

        # === Game Tab (controls, AP waits, current game settings) ===
        page_game = ttk.Frame(self._nb)
        page_game.grid_columnconfigure([0, 1], weight=1)
        self._nb.add(page_game, text=self.t('GUI_TAB_GAME', 'Game'))
        self.create_game_tab(page_game)

        page2 = ttk.Frame(self._nb)
        page2.grid_columnconfigure([0, 1], weight=1)
        self._nb.add(page2, text=self.t('GUI_TAB_DEBUG_TEST', 'Debug/Test'))  # debug/test page

        # === Calibration Tab ===
        page_calibration = ttk.Frame(self._nb)
        page_calibration.grid_columnconfigure(0, weight=1)
        self._nb.add(page_calibration, text=self.t('GUI_TAB_CALIBRATION', 'Calibration'))
        # self.create_calibration_tab(page_calibration)
        self.calibration = Calibration(self.ed_ap, self.callback)
        self.calibration.create_calibration_tab(page_calibration)
        # self.calibration_tab.frame.pack(fill="both", expand=True)

        # === Waypoint Editor Tab ===
        page_waypoint_editor = ttk.Frame(self._nb)
        page_waypoint_editor.grid_columnconfigure(0, weight=1)
        self._nb.add(page_waypoint_editor, text=self.t('GUI_TAB_WAYPOINTS', 'Waypoints'))
        self.waypoint_editor_tab = WaypointEditorTab(page_waypoint_editor, self.ed_ap.waypoint)
        self.waypoint_editor_tab.frame.pack(fill="both", expand=True)

        # === Colonization Editor Tab ===
        tab_colonize_editor = ttk.Frame(self._nb)
        tab_colonize_editor.grid_columnconfigure(0, weight=1)
        self._nb.add(tab_colonize_editor, text=self.t('GUI_TAB_COLONIZATION', 'Colonization'))
        self.colonize_tab = ColonizeEditorTab(self.ed_ap, self.callback)
        self.colonize_tab.create_waypoints_tab(tab_colonize_editor)
        self.colonize_tab.frame.pack(fill="both", expand=True)

        # === TCE Integration ===
        page_tce_integration = ttk.Frame(self._nb)
        page_tce_integration.grid_columnconfigure(0, weight=1)
        self._nb.add(page_tce_integration, text=self.t('GUI_TAB_TCE', 'TCE'))
        tce_integration_tab = self.ed_ap.tce_integration.create_gui_tab(self, page_tce_integration)

        # === MAIN TAB ===
        # main options block
        blk_main = ttk.Frame(page0)
        blk_main.grid(row=0, column=0, padx=10, pady=5, sticky="NSEW")
        blk_main.columnconfigure([0, 1], weight=1, minsize=100, uniform="group1")

        # ap mode checkboxes block
        blk_modes = ttk.LabelFrame(blk_main, text=self.t('GUI_GROUP_MODE', 'MODE'), padding=(10, 5))
        blk_modes.grid(row=0, column=0, padx=2, pady=2, sticky="NSEW")
        self.makeform(blk_modes, FORM_TYPE_CHECKBOX, modes_check_fields)

        ttk.Separator(blk_modes, orient='horizontal').grid(row=20, column=0, columnspan=2, sticky="EW", pady=4)
        self.checkboxvar['Fast Travel'] = tk.BooleanVar()
        cb_fast = ttk.Checkbutton(blk_modes, text=self.t('GUI_CHK_FAST_TRAVEL', 'Fast Travel Mode (skip scans)'),
                                  variable=self.checkboxvar['Fast Travel'],
                                  command=(lambda field='Fast Travel': self.check_cb(field)))
        cb_fast.grid(row=21, column=0, columnspan=2, sticky=tk.W)
        btn_mini = ttk.Button(blk_modes, text=self.t('GUI_BTN_MINI_PANEL', 'Mini Panel (over game)'),
                              command=self.toggle_mini_panel)
        btn_mini.grid(row=22, column=0, columnspan=2, sticky="EW", pady=4)

        # ship values block
        blk_ship = ttk.LabelFrame(blk_main, text=self.t('GUI_GROUP_SHIP', 'SHIP'), padding=(10, 5))
        blk_ship.grid(row=0, column=1, padx=2, pady=2, sticky="NSEW")

        lbl_sun_pitch_up = ttk.Label(blk_ship, text=self.t('GUI_LABEL_SUN_PITCH_UP_TIME', 'SunPitchUp +/- Time:'))
        lbl_sun_pitch_up.grid(row=1, column=0, pady=3, sticky=tk.W)
        spn_sun_pitch_up = ttk.Spinbox(blk_ship, width=10, from_=-100, to=100, increment=0.5, justify=tk.RIGHT)
        spn_sun_pitch_up.grid(row=1, column=1, padx=2, pady=2, sticky=tk.E)
        spn_sun_pitch_up.bind('<FocusOut>', self.entry_update)
        self.entries['ship'] = {}
        self.entries['ship']['SunPitchUp+Time'] = spn_sun_pitch_up

        lbl_calibrate_note = ttk.Label(blk_ship, text=self.t('GUI_LABEL_SHIP_RPY_TUNING_NOTE', "Ship RPY Tuning:\n1. Enable Auto-tune.\n"
                                                      "2. Fly until until response is correct.\n"
                                                      "3. Use Align to Target button to fine tune.\n"
                                                      "4a. Use Throttle dropdown to select and...\n"
                                                      "4b. Edit Curve if necessary and save changes.\n"
                                  "5. Disable Auto-tune."))
        lbl_calibrate_note.grid(row=2, columnspan=2, pady=5, sticky=tk.W)

        self.checkboxvar['Enable Auto-tune RPY'] = tk.BooleanVar()
        self.checkboxvar['Enable Auto-tune RPY'].set(bool(self.ed_ap.config['AutoTuneRPYRates']))
        cb_auto_tune_rpy = ttk.Checkbutton(blk_ship, text=self.t('GUI_CHK_ENABLE_AUTO_TUNE_RPY', 'Enable Auto-tune RPY'),
                                           variable=self.checkboxvar['Enable Auto-tune RPY'],
                                           command=(lambda field='Enable Auto-tune RPY': self.check_cb(field)))
        cb_auto_tune_rpy.grid(row=3, column=0, padx=2, pady=2, sticky=tk.W)

        btn_speed_0 = ttk.Button(blk_ship, text=self.t('GUI_BTN_THROTTLE_0', '0% Throttle'), command=self.ship_throttle_0)
        btn_speed_0.grid(row=4, column=0, padx=2, pady=12, columnspan=1, sticky="NSEW")
        btn_speed_50 = ttk.Button(blk_ship, text=self.t('GUI_BTN_THROTTLE_50', '50% Throttle'), command=self.ship_throttle_50)
        btn_speed_50.grid(row=4, column=1, padx=2, pady=12, columnspan=1, sticky="NSEW")
        btn_speed_100 = ttk.Button(blk_ship, text=self.t('GUI_BTN_THROTTLE_100', '100% Throttle'), command=self.ship_throttle_100)
        btn_speed_100.grid(row=5, column=0, padx=2, pady=2, columnspan=1, sticky="NSEW")

        btn_align_target = ttk.Button(blk_ship, text=self.t('GUI_BTN_ALIGN_TO_TARGET', 'Align to Target'), command=self.tuning_align_target)
        btn_align_target.grid(row=6, column=0, padx=2, pady=2, columnspan=2, sticky="NSEW")

        ttk.Label(blk_ship, text=self.t('GUI_LABEL_THROTTLE', 'Throttle:')).grid(row=7, column=0, padx=5, pady=5, sticky=tk.W)

        self.throttle_var = tk.StringVar()
        self.throttle_combo = ttk.Combobox(blk_ship, textvariable=self.throttle_var, values=self.throttle_keys)
        self.throttle_combo.grid(row=7, column=1, padx=5, pady=5, sticky="EW")
        self.throttle_combo.bind("<<ComboboxSelected>>", self.on_throttle_select)


        # btn_tst_roll = ttk.Button(blk_ship, text='4. Gather Roll Rates', command=self.ship_tst_roll)
        # btn_tst_roll.grid(row=10, column=0, padx=2, pady=2, columnspan=1, sticky="NSEW")
        btn_roll_edit = ttk.Button(blk_ship, text=self.t('GUI_BTN_EDIT_ROLL_CURVE', 'Edit Roll Curve'), command=self.edit_roll_curve)
        btn_roll_edit.grid(row=10, column=0, padx=2, pady=2, columnspan=2, sticky="NSEW")

        # lbl_calibrate_note2 = ttk.Label(blk_ship, text="Tune Pitch & Yaw:\n1. Set speed above.\n"
        #                                                "2. Target remote System.\n"
        #                                                "3. Maneuver target to center of screen (and compass).")
        # lbl_calibrate_note2.grid(row=11, columnspan=2, pady=5, sticky=tk.W)
        # btn_tst_pitch = ttk.Button(blk_ship, text='4. Gather Pitch Rates', command=self.ship_tst_pitch)
        # btn_tst_pitch.grid(row=12, column=0, padx=2, pady=2, columnspan=1, sticky="NSEW")
        btn_pit_edit = ttk.Button(blk_ship, text=self.t('GUI_BTN_EDIT_PITCH_CURVE', 'Edit Pitch Curve'), command=self.edit_pit_curve)
        btn_pit_edit.grid(row=12, column=0, padx=2, pady=2, columnspan=2, sticky="NSEW")
        # btn_tst_yaw = ttk.Button(blk_ship, text='6. Gather Yaw Rates', command=self.ship_tst_yaw)
        # btn_tst_yaw.grid(row=13, column=0, padx=5, pady=2, columnspan=1, sticky="NSEW")
        btn_yaw_edit = ttk.Button(blk_ship, text=self.t('GUI_BTN_EDIT_YAW_CURVE', 'Edit Yaw Curve'), command=self.edit_yaw_curve)
        btn_yaw_edit.grid(row=13, column=0, padx=2, pady=2, columnspan=2, sticky="NSEW")

        # log window
        log = ttk.LabelFrame(page0, text=self.t('GUI_GROUP_LOG', 'LOG'), padding=(10, 5))
        log.grid(row=2, column=0, padx=10, pady=5, sticky="NSEW")
        log.grid_columnconfigure(0, weight=1)
        log.grid_rowconfigure(0, weight=1)
        y_scrollbar = ttk.Scrollbar(log)
        y_scrollbar.grid(row=0, column=1, sticky="NSE")
        x_scrollbar = ttk.Scrollbar(log, orient="horizontal")
        x_scrollbar.grid(row=1, column=0, sticky="EW")
        mylist = tk.Listbox(log, width=100, yscrollcommand=y_scrollbar.set, xscrollcommand=x_scrollbar.set)
        mylist.grid(row=0, column=0, sticky="NSEW")
        y_scrollbar.config(command=mylist.yview)
        x_scrollbar.config(command=mylist.xview)

        # === SETTINGS TAB ===
        # settings block
        blk_settings = ttk.Frame(page1)
        blk_settings.grid(row=0, column=0, padx=10, pady=5, sticky="EW")
        blk_settings.columnconfigure([0, 1], weight=1, minsize=100, uniform="group1")

        # autopilot settings block
        blk_ap = ttk.LabelFrame(blk_settings, text=self.t('GUI_GROUP_AUTOPILOT', 'AUTOPILOT'), padding=(10, 5))
        blk_ap.grid(row=0, column=0, padx=2, pady=2, sticky="NSEW")
        self.entries['autopilot'] = self.makeform(blk_ap, FORM_TYPE_SPINBOX, autopilot_entry_fields)
        self.checkboxvar['Enable Randomness'] = tk.BooleanVar()
        cb_random = ttk.Checkbutton(blk_ap, text=self.t('GUI_CHK_ENABLE_RANDOMNESS', 'Enable Randomness'), variable=self.checkboxvar['Enable Randomness'], command=(lambda field='Enable Randomness': self.check_cb(field)))
        cb_random.grid(row=5, column=0, columnspan=2, sticky=tk.W)
        self.checkboxvar['Automatic logout'] = tk.BooleanVar()
        cb_logout = ttk.Checkbutton(blk_ap, text=self.t('GUI_CHK_AUTOMATIC_LOGOUT', 'Automatic logout'), variable=self.checkboxvar['Automatic logout'], command=(lambda field='Automatic logout': self.check_cb(field)))
        cb_logout.grid(row=6, column=0, columnspan=2, sticky=tk.W)

        lbl_language = ttk.Label(blk_ap, text=self.t('GUI_LABEL_LANGUAGE', 'Language:'))
        lbl_language.grid(row=7, column=0, pady=3, sticky=tk.W)
        self.language_combo = ttk.Combobox(blk_ap, textvariable=self.language_var,
                                            values=sorted(self.ed_ap.locale.available_languages),
                                            state='readonly', width=8)
        self.language_combo.grid(row=7, column=1, padx=2, pady=2, sticky=tk.E)
        self.language_combo.bind('<<ComboboxSelected>>', self.on_language_select)

        # buttons settings block
        blk_buttons = ttk.LabelFrame(blk_settings, text=self.t('GUI_GROUP_BUTTONS', 'BUTTONS'), padding=(10, 5))
        blk_buttons.grid(row=0, column=1, padx=2, pady=2, sticky="NSEW")
        blk_dss = ttk.Frame(blk_buttons)
        blk_dss.grid(row=0, column=0, columnspan=2, padx=0, pady=0, sticky="NSEW")
        lb_dss = ttk.Label(blk_dss, text=self.t('GUI_LABEL_DSCANNER_BUTTON', 'D-Scanner (Honk) Button: '))
        lb_dss.grid(row=0, column=0, sticky=tk.W)
        self.radiobuttonvar['dss_button'] = tk.StringVar()
        rb_dss_primary = ttk.Radiobutton(blk_dss, text=self.t('GUI_RB_PRIMARY', 'Primary'), variable=self.radiobuttonvar['dss_button'], value="Primary", command=(lambda field='dss_button': self.check_cb(field)))
        rb_dss_primary.grid(row=0, column=1, sticky=tk.W)
        rb_dss_secondary = ttk.Radiobutton(blk_dss, text=self.t('GUI_RB_SECONDARY', 'Secondary'), variable=self.radiobuttonvar['dss_button'], value="Secondary", command=(lambda field='dss_button': self.check_cb(field)))
        rb_dss_secondary.grid(row=1, column=1, sticky=tk.W)
        self.checkboxvar['Enable Hotkeys'] = tk.BooleanVar()
        cb_enable = ttk.Checkbutton(blk_buttons, text=self.t('GUI_CHK_ENABLE_HOTKEYS', 'Enable Hotkeys (toggle after hotkey change)'), variable=self.checkboxvar['Enable Hotkeys'], command=(lambda field='Enable Hotkeys': self.check_cb(field)))
        cb_enable.grid(row=2, column=0, columnspan=2, sticky=tk.W)
        self.entries['buttons'] = self.makeform(blk_buttons, FORM_TYPE_ENTRY, buttons_entry_fields, 3)

        # refuel settings block
        blk_fuel = ttk.LabelFrame(blk_settings, text=self.t('GUI_GROUP_FUEL', 'FUEL'), padding=(10, 5))
        blk_fuel.grid(row=1, column=0, padx=2, pady=2, sticky="NSEW")
        self.entries['refuel'] = self.makeform(blk_fuel, FORM_TYPE_SPINBOX, refuel_entry_fields)

        # overlay settings block
        blk_overlay = ttk.LabelFrame(blk_settings, text=self.t('GUI_GROUP_OVERLAY', 'OVERLAY'), padding=(10, 5))
        blk_overlay.grid(row=1, column=1, padx=2, pady=2, sticky="NSEW")
        self.checkboxvar['Enable Overlay'] = tk.BooleanVar()
        cb_enable = ttk.Checkbutton(blk_overlay, text=self.t('GUI_CHK_ENABLE', 'Enable'), variable=self.checkboxvar['Enable Overlay'], command=(lambda field='Enable Overlay': self.check_cb(field)))
        cb_enable.grid(row=0, column=0, columnspan=2, sticky=tk.W)
        self.entries['overlay'] = self.makeform(blk_overlay, FORM_TYPE_SPINBOX, overlay_entry_fields, 1, 1.0, 0.0, 3000.0)

        # Keys settings block
        blk_keys = ttk.LabelFrame(blk_settings, text=self.t('GUI_GROUP_KEYS', 'KEYS'), padding=(10, 5))
        blk_keys.grid(row=2, column=0, padx=2, pady=2, sticky="NSEW")
        self.checkboxvar['Activate Elite for each key'] = tk.BooleanVar()
        cb_activate_elite = ttk.Checkbutton(blk_keys, text=self.t('GUI_CHK_ACTIVATE_ELITE_EACH_KEY', 'Activate Elite for each key'), variable=self.checkboxvar['Activate Elite for each key'], command=(lambda field='Activate Elite for each key': self.check_cb(field)))
        cb_activate_elite.grid(row=0, column=0, columnspan=2, sticky=tk.W)
        self.entries['keys'] = self.makeform(blk_keys, FORM_TYPE_SPINBOX, keys_entry_fields, 1, 0.01)

        # voice settings block
        blk_voice = ttk.LabelFrame(blk_settings, text=self.t('GUI_GROUP_VOICE', 'VOICE'), padding=(10, 5))
        blk_voice.grid(row=3, column=0, padx=2, pady=2, sticky="NSEW")
        self.checkboxvar['Enable Voice'] = tk.BooleanVar()
        cb_enable = ttk.Checkbutton(blk_voice, text=self.t('GUI_CHK_ENABLE', 'Enable'), variable=self.checkboxvar['Enable Voice'], command=(lambda field='Enable Voice': self.check_cb(field)))
        cb_enable.grid(row=0, column=0, columnspan=2, sticky=tk.W)

        # ELW Scanner settings block
        blk_voice = ttk.LabelFrame(blk_settings, text=self.t('GUI_GROUP_ELW_SCANNER', 'ELW SCANNER'), padding=(10, 5))
        blk_voice.grid(row=3, column=1, padx=2, pady=2, sticky="NSEW")
        self.checkboxvar['ELW Scanner'] = tk.BooleanVar()
        cb_enable = ttk.Checkbutton(blk_voice, text=self.t('GUI_CHK_ENABLE', 'Enable'), variable=self.checkboxvar['ELW Scanner'], command=(lambda field='ELW Scanner': self.check_cb(field)))
        cb_enable.grid(row=0, column=0, columnspan=2, sticky=tk.W)

        # AFK Combat settings block
        blk_afk_combat = ttk.LabelFrame(blk_settings, text=self.t('GUI_GROUP_AFK_COMBAT', 'AFK Combat'), padding=(10, 5))
        blk_afk_combat.grid(row=4, column=0, padx=2, pady=2, sticky="NSEW")
        self.checkboxvar['AFKCombat AttackAtWill'] = tk.BooleanVar()
        cb_enable = ttk.Checkbutton(blk_afk_combat, text=self.t('GUI_CHK_COMMAND_SLF_ATTACK_AT_WILL', 'Command SLF to Attack At Will'), variable=self.checkboxvar['AFKCombat AttackAtWill'], command=(lambda field='AFKCombat AttackAtWill': self.check_cb(field)))
        cb_enable.grid(row=0, column=0, columnspan=2, sticky=tk.W)

        # ==== DEBUG/TEST TAB ====
        # File Actions
        blk_file_actions = ttk.LabelFrame(page2, text=self.t('GUI_GROUP_FILE_ACTIONS', 'File Actions'), padding=(10, 5))
        blk_file_actions.grid(row=0, column=0, padx=10, pady=5, sticky="NSEW")
        self.checkboxvar['Enable CV View'] = tk.IntVar()
        self.checkboxvar['Enable CV View'].set(int(self.ed_ap.config['Enable_CV_View']))
        cb_enable_cv_view = ttk.Checkbutton(blk_file_actions, text=self.t('GUI_CHK_ENABLE_CV_VIEW', 'Enable CV View'), variable=self.checkboxvar['Enable CV View'], command=(lambda field='Enable CV View': self.check_cb(field)))
        cb_enable_cv_view.grid(row=2, column=0, padx=2, pady=2, sticky=tk.W)
        btn_restart = ttk.Button(blk_file_actions, text=self.t('GUI_BTN_RESTART', 'Restart'), command=self.restart_program)
        btn_restart.grid(row=3, column=0, padx=2, pady=2, sticky=tk.W)
        btn_exit = ttk.Button(blk_file_actions, text=self.t('GUI_BTN_EXIT', 'Exit'), command=self.close_window)
        btn_exit.grid(row=4, column=0, padx=2, pady=2, sticky=tk.W)

        # Help Actions
        blk_help_actions = ttk.LabelFrame(page2, text=self.t('GUI_GROUP_HELP_ACTIONS', 'Help Actions'), padding=(10, 5))
        blk_help_actions.grid(row=0, column=1, padx=10, pady=5, sticky="NSEW")
        btn_check_updates = ttk.Button(blk_help_actions, text=self.t('GUI_BTN_CHECK_UPDATES', 'Check for Updates'), command=self.check_updates)
        btn_check_updates.grid(row=0, column=0, padx=2, pady=2, sticky=tk.W)
        btn_view_changelog = ttk.Button(blk_help_actions, text=self.t('GUI_BTN_VIEW_CHANGELOG', 'View Changelog'), command=self.open_changelog)
        btn_view_changelog.grid(row=1, column=0, padx=2, pady=2, sticky=tk.W)
        btn_join_discord = ttk.Button(blk_help_actions, text=self.t('GUI_BTN_JOIN_DISCORD', 'Join Discord'), command=self.open_discord)
        btn_join_discord.grid(row=2, column=0, padx=2, pady=2, sticky=tk.W)
        btn_about = ttk.Button(blk_help_actions, text=self.t('GUI_BTN_ABOUT', 'About'), command=self.about)
        btn_about.grid(row=3, column=0, padx=2, pady=2, sticky=tk.W)

        # # debug block
        # blk_debug = ttk.Frame(page2)
        # blk_debug.grid(row=1, column=0, padx=10, pady=5, sticky=(tk.E, tk.W))
        # blk_debug.columnconfigure([0, 1], weight=1, minsize=100, uniform="group2")

        # Debug Settings frame
        blk_debug_settings = ttk.LabelFrame(page2, text=self.t('GUI_GROUP_DEBUG_SETTINGS', 'Debug Settings'), padding=(10, 5))
        blk_debug_settings.grid(row=1, column=0, padx=10, pady=5, sticky="NSEW")
        self.radiobuttonvar['debug_mode'] = tk.StringVar()
        rb_debug_debug = ttk.Radiobutton(blk_debug_settings, text=self.t('GUI_RB_DEBUG_INFO_ERRORS', 'Debug + Info + Errors'), variable=self.radiobuttonvar['debug_mode'], value="Debug", command=(lambda field='debug_mode': self.check_cb(field)))
        rb_debug_debug.grid(row=0, column=1, columnspan=2, sticky=tk.W)
        rb_debug_info = ttk.Radiobutton(blk_debug_settings, text=self.t('GUI_RB_INFO_ERRORS', 'Info + Errors'), variable=self.radiobuttonvar['debug_mode'], value="Info", command=(lambda field='debug_mode': self.check_cb(field)))
        rb_debug_info.grid(row=1, column=1, columnspan=2, sticky=tk.W)
        rb_debug_error = ttk.Radiobutton(blk_debug_settings, text=self.t('GUI_RB_ERRORS_ONLY_DEFAULT', 'Errors only (default)'), variable=self.radiobuttonvar['debug_mode'], value="Error", command=(lambda field='debug_mode': self.check_cb(field)))
        rb_debug_error.grid(row=2, column=1, columnspan=2, sticky=tk.W)
        btn_open_logfile = ttk.Button(blk_debug_settings, text=self.t('GUI_BTN_OPEN_LOG_FILE', 'Open Log File'), command=self.open_logfile)
        btn_open_logfile.grid(row=3, column=0, padx=2, pady=2, columnspan=2, sticky="NSEW")

        # Single Waypoint Assist frame
        blk_single_waypoint_asst = ttk.LabelFrame(page2, text=self.t('GUI_GROUP_SINGLE_WAYPOINT_ASSIST', 'Single Waypoint Assist'), padding=(10, 5))
        blk_single_waypoint_asst.grid(row=1, column=1, padx=10, pady=5, sticky="NSEW")
        blk_single_waypoint_asst.columnconfigure(0, weight=1, minsize=10)
        blk_single_waypoint_asst.columnconfigure(1, weight=3, minsize=10)

        lbl_system = ttk.Label(blk_single_waypoint_asst, text=self.t('GUI_LABEL_SYSTEM', 'System:'))
        lbl_system.grid(row=0, column=0, padx=2, pady=2, columnspan=1, sticky="NSEW")
        txt_system = ttk.Entry(blk_single_waypoint_asst, textvariable=self.single_waypoint_system)
        txt_system.grid(row=0, column=1, padx=2, pady=2, columnspan=1, sticky="NSEW")
        lbl_station = ttk.Label(blk_single_waypoint_asst, text=self.t('GUI_LABEL_STATION', 'Station:'))
        lbl_station.grid(row=1, column=0, padx=2, pady=2, columnspan=1, sticky="NSEW")
        txt_station = ttk.Entry(blk_single_waypoint_asst, textvariable=self.single_waypoint_station)
        txt_station.grid(row=1, column=1, padx=2, pady=2, columnspan=1, sticky="NSEW")
        self.checkboxvar['Single Waypoint Assist'] = tk.BooleanVar()
        cb_single_waypoint = ttk.Checkbutton(blk_single_waypoint_asst, text=self.t('GUI_CHK_SINGLE_WAYPOINT_ASSIST', 'Single Waypoint Assist'), variable=self.checkboxvar['Single Waypoint Assist'], command=(lambda field='Single Waypoint Assist': self.check_cb(field)))
        cb_single_waypoint.grid(row=2, column=0, padx=2, pady=2, columnspan=2, sticky="NSEW")

        blk_debug_buttons = ttk.Frame(page2)
        blk_debug_buttons.grid(row=2, column=0, columnspan=2, padx=10, pady=5, sticky="NSEW")
        blk_debug_buttons.columnconfigure([0, 1], weight=1, minsize=100)

        self.checkboxvar['Debug Overlay'] = tk.BooleanVar()
        cb_debug_overlay = ttk.Checkbutton(blk_debug_buttons, text=self.t('GUI_CHK_DEBUG_OVERLAY', 'Debug Overlay'), variable=self.checkboxvar['Debug Overlay'], command=(lambda field='Debug Overlay': self.check_cb(field)))
        cb_debug_overlay.grid(row=6, column=0, padx=2, pady=2, columnspan=2, sticky="NSEW")
        tip = ToolTip(cb_debug_overlay, msg=self.tooltips['Debug Overlay'], delay=1.0, bg="#808080", fg="#FFFFFF")

        self.checkboxvar['Debug OCR'] = tk.BooleanVar()
        cb_debug_ocr = ttk.Checkbutton(blk_debug_buttons, text=self.t('GUI_CHK_DEBUG_OCR', "Debug OCR - Writes OCR output to 'ocr-output' folder"), variable=self.checkboxvar['Debug OCR'], command=(lambda field='Debug OCR': self.check_cb(field)))
        cb_debug_ocr.grid(row=7, column=0, padx=2, pady=2, columnspan=2, sticky="NSEW")
        tip = ToolTip(cb_debug_ocr, msg=self.tooltips['Debug OCR'], delay=1.0, bg="#808080", fg="#FFFFFF")

        self.checkboxvar['Debug Images'] = tk.BooleanVar()
        cb_debug_images = ttk.Checkbutton(blk_debug_buttons, text=self.t('GUI_CHK_DEBUG_IMAGES', "Debug Images - Writes debug images to 'debug-output' folder"), variable=self.checkboxvar['Debug Images'], command=(lambda field='Debug Images': self.check_cb(field)))
        cb_debug_images.grid(row=8, column=0, padx=2, pady=2, columnspan=2, sticky="NSEW")
        tip = ToolTip(cb_debug_images, msg=self.tooltips['Debug Images'], delay=1.0, bg="#808080", fg="#FFFFFF")

        # === Status Bar ===
        statusbar = ttk.Frame(win)
        statusbar.grid(row=4, column=0)
        self.status = ttk.Label(win, text=self.t('GUI_STATUS_PREFIX', 'Status: '), relief=tk.SUNKEN, anchor=tk.W, justify=tk.LEFT, width=29)
        self.jumpcount = ttk.Label(statusbar, text="<info> ", relief=tk.SUNKEN, anchor=tk.W, justify=tk.LEFT, width=40)
        self.status.pack(in_=statusbar, side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.jumpcount.pack(in_=statusbar, side=tk.RIGHT, fill=tk.Y, expand=False)

        return mylist

    def restart_program(self):
        logger.debug("Entered: restart_program")
        print("restart now")

        self.stop_fsd()
        self.stop_sc()
        self.ed_ap.quit()
        sleep(0.1)

        import sys
        print("argv was", sys.argv)
        print("sys.executable was", sys.executable)
        print("restart now")

        import os
        os.execv(sys.executable, ['python'] + sys.argv)


def apply_theme_to_titlebar(root):
    version = sys.getwindowsversion()

    if version.major == 10 and version.build >= 22000:
        # Set the title bar color to the background color on Windows 11 for better appearance
        pywinstyles.change_header_color(root, "#1c1c1c" if sv_ttk.get_theme() == "dark" else "#fafafa")
    elif version.major == 10:
        pywinstyles.apply_style(root, "dark" if sv_ttk.get_theme() == "dark" else "normal")

        # A hacky way to update the title bar's color on Windows 10 (it doesn't update instantly like on Windows 11)
        root.wm_attributes("-alpha", 0.99)
        root.wm_attributes("-alpha", 1)


def main():
    #   handle = win32gui.FindWindow(0, "Elite - Dangerous (CLIENT)")
    #   if handle != None:
    #       win32gui.SetForegroundWindow(handle)  # put the window in foreground

    root = tk.Tk()
    app = APGui(root)

    sv_ttk.set_theme("dark")

    # Remove focus outline from tabs by setting focuscolor to the background color
    style = ttk.Style()
    bg_color = "#1c1c1c" if sv_ttk.get_theme() == "dark" else "#fafafa"
    style.configure("TNotebook.Tab", focuscolor=bg_color)

    # if sys.platform == "win32":
    #     apply_theme_to_titlebar(root)

    root.mainloop()


if __name__ == "__main__":
    main()
