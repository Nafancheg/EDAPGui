from __future__ import annotations

import json
import os

from EDlogger import logger


def write_json_file(data, filepath: str):
    # Note: No file existence check - allow creating new config files on first run
    if data is None:
        return False
    try:
        with open(filepath, "w", encoding='utf-8') as fp:
            json.dump(data, fp, indent=4)
            return True
    except Exception as e:
        logger.warning(f"write_json_file error for filepath '{filepath}':" + str(e))
        return False


def read_json_file(filepath: str):
    if not os.path.exists(filepath):
        return None

    s = None
    try:
        with open(filepath, "r", encoding='utf-8') as fp:
            s = json.load(fp)
    except Exception as e:
        logger.warning(f"read_json_file error for filepath '{filepath}':" + str(e))
    return s
