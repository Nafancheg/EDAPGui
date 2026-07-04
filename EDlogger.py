import sys

import colorlog
import datetime
import logging
import os
from pathlib import Path

_log_dir = Path('logs')
_log_dir.mkdir(exist_ok=True)
_filename = str(_log_dir / 'autopilot.log')

# Move any logs left in the application root into the logs folder (migration from older versions).
for _old in Path('.').glob('autopilot*.log'):
    try:
        _old.rename(_log_dir / _old.name)
    except OSError:
        pass

# Rename existing log file to create new one.
if os.path.exists(_filename):
    t = os.path.getmtime(_filename)
    x = datetime.datetime.fromtimestamp(t).strftime('%Y-%m-%d %H-%M-%S')
    try:
        os.rename(_filename, str(_log_dir / f"autopilot {x}.log"))
    except OSError:
        pass

# Keep only the newest archived logs so the folder does not grow forever.
_keep_logs = 10
_archived = sorted(_log_dir.glob('autopilot 2*.log'), key=os.path.getmtime, reverse=True)
for _f in _archived[_keep_logs:]:
    try:
        _f.unlink()
    except OSError:
        pass

# Define the logging config.
logging.basicConfig(filename=_filename, level=logging.ERROR,
                    format='%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s',
                    datefmt='%H:%M:%S')

logger = colorlog.getLogger('ed_log')

# Change this to debug if want to see debug lines in log file
logger.setLevel(logging.INFO)    # change to INFO for more... DEBUG for much more
logger.info(f'Python version: {sys.version}')

# sys.stderr is None when running under pythonw.exe (no console attached).
# StreamHandler() defaults to sys.stderr, so skip it there to avoid crashing
# on the first log call instead of silently swallowing every console message.
if sys.stderr is not None:
    handler = logging.StreamHandler()
    handler.setLevel(logging.WARNING)  # change this to what is shown on console
    handler.setFormatter(
        colorlog.ColoredFormatter('%(log_color)s%(levelname)-8s%(reset)s %(white)s%(message)s',
            log_colors={
                'DEBUG':    'fg_bold_cyan',
                'INFO':     'fg_bold_green',
                'WARNING':  'bg_bold_yellow,fg_bold_blue',
                'ERROR':    'bg_bold_red,fg_bold_white',
                'CRITICAL': 'bg_bold_red,fg_bold_yellow',
    	},secondary_log_colors={}

        ))
    logger.addHandler(handler)

#logger.disabled = True
#logger.disabled = False

