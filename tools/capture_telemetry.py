"""
tools/capture_telemetry.py

Standalone telemetry capture harness (Phase 7.0 "capture harness").

Purpose
-------
Records the raw Elite Dangerous live data streams (Status.json, NavRoute.json,
Journal.*.log) during real play into a newline-delimited JSON (.jsonl) replay
log. This gives later phases (fuel sensor-fusion, watchdog) realistic replay
data to develop and test against, instead of only the static mocks produced
by tools/setup_mock_env.ps1.

This script is intentionally standalone and lightweight: it does NOT import
ED_AP, EDAPGui, OCR, or tkinter (or any other GUI/vision dependency), and it
only opens the game's live files for reading. It is safe to run alongside a
live autopilot session -- it never writes to the game's files and never
interferes with the running autopilot.

Path resolution
----------------
The ED "Saved Games" data dir is resolved the same way the rest of the repo
does it (see EDJournal.py / StatusParser.py / NavRouteParser.py): via the
Windows SavedGames known-folder API (WindowsKnownPaths.py, stdlib ctypes
only -- no heavy deps), falling back to the conventional
"%USERPROFILE%\\Saved Games" path if that lookup isn't available (e.g. not
running on Windows). Use --ed-dir to point at a different directory (for
example a mocked environment produced by tools/setup_mock_env.ps1).

Usage examples
--------------
    # Run with the repo's venv, from the repo root, until Ctrl-C:
    .\\venv\\Scripts\\python.exe tools\\capture_telemetry.py

    # Faster polling, auto-stop after 60s (useful for scripted/CI testing):
    .\\venv\\Scripts\\python.exe tools\\capture_telemetry.py --interval 0.5 --duration 60

    # Point at a different ED data dir:
    .\\venv\\Scripts\\python.exe tools\\capture_telemetry.py --ed-dir "D:\\mock\\Elite Dangerous"

    # Only capture specific journal event types (default is "capture all"):
    .\\venv\\Scripts\\python.exe tools\\capture_telemetry.py --journal-events FSDJump,Docked,Location

Output
------
Writes captures/session_<UTC-timestamp>.jsonl at the repo root (or --out-dir).
Each line is a single JSON object:
    {"ts": "<ISO-8601 UTC>", "source": "status"|"navroute"|"journal", "data": <parsed-json-or-raw-line>}
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def resolve_ed_dir() -> Path:
    """Resolve the Elite Dangerous 'Saved Games' data dir the same way the
    rest of the repo does (WindowsKnownPaths.get_path(FOLDERID.SavedGames)).
    Falls back to the conventional %USERPROFILE%\\Saved Games path if that
    lookup fails or isn't available (e.g. non-Windows)."""
    try:
        if str(REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT))
        from WindowsKnownPaths import FOLDERID, UserHandle, get_path

        base = get_path(FOLDERID.SavedGames, UserHandle.current)
        return Path(base) / "Frontier Developments" / "Elite Dangerous"
    except Exception:
        return Path.home() / "Saved Games" / "Frontier Developments" / "Elite Dangerous"


def utc_now_iso() -> str:
    """Current UTC time as an ISO-8601 string with millisecond precision."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _hash_obj(obj) -> str:
    """Stable hash of a parsed-JSON value, used to dedupe unchanged snapshots."""
    try:
        blob = json.dumps(obj, sort_keys=True, default=str).encode("utf-8", errors="replace")
    except Exception:
        blob = repr(obj).encode("utf-8", errors="replace")
    return hashlib.sha1(blob).hexdigest()


class RecordWriter:
    """Appends {"ts", "source", "data"} records to a .jsonl file, flushing
    after every write so a Ctrl-C (or crash) never loses buffered records."""

    def __init__(self, path: Path):
        self.path = path
        self._fh = open(path, "a", encoding="utf-8", newline="\n")
        self.counts: dict[str, int] = {"status": 0, "navroute": 0, "journal": 0}

    def write(self, source: str, data) -> None:
        record = {"ts": utc_now_iso(), "source": source, "data": data}
        self._fh.write(json.dumps(record, default=str) + "\n")
        self._fh.flush()
        self.counts[source] = self.counts.get(source, 0) + 1

    def close(self) -> None:
        self._fh.close()


class FilePoller:
    """Polls a JSON file (Status.json / NavRoute.json) and writes a record
    only when its parsed content changes since the last write. Missing files
    or files caught mid-write (JSON parse errors) are silently skipped and
    retried on the next tick -- this never raises."""

    def __init__(self, path: Path, source: str):
        self.path = path
        self.source = source
        self._last_hash: str | None = None

    def poll(self, writer: RecordWriter) -> None:
        if not self.path.exists():
            return
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return  # missing or mid-write; try again next tick
        digest = _hash_obj(data)
        if digest != self._last_hash:
            self._last_hash = digest
            writer.write(self.source, data)


class JournalTailer:
    """Tails the newest Journal.*.log file in the ED data dir, emitting one
    'journal' record per new complete line since the last poll. Handles the
    active journal rotating to a newer file (a newer Journal.*.log appearing
    causes it to close the old handle and continue from the new file)."""

    def __init__(self, ed_dir: Path, event_filter: set[str] | None = None):
        self.ed_dir = ed_dir
        self.event_filter = event_filter
        self.current_path: Path | None = None
        self._fh = None
        self._offset = 0

    def _latest_journal(self) -> Path | None:
        try:
            candidates = [p for p in self.ed_dir.glob("Journal.*.log") if p.is_file()]
        except OSError:
            return None
        if not candidates:
            return None
        return max(candidates, key=lambda p: p.stat().st_mtime)

    def _switch_to(self, path: Path) -> None:
        if self._fh is not None:
            try:
                self._fh.close()
            except OSError:
                pass
        self.current_path = path
        self._offset = 0
        try:
            self._fh = open(path, "rb")
        except OSError:
            self._fh = None
            self.current_path = None

    def poll(self, writer: RecordWriter) -> None:
        latest = self._latest_journal()
        if latest is None:
            return
        if self.current_path is None or latest != self.current_path:
            self._switch_to(latest)
        if self._fh is None:
            return

        try:
            self._fh.seek(self._offset)
            chunk = self._fh.read()
        except OSError:
            return
        if not chunk:
            return

        # Only consume whole lines -- a trailing partial line (file mid-write)
        # is left for the next poll so it's never parsed truncated.
        last_newline = chunk.rfind(b"\n")
        if last_newline == -1:
            return
        complete, consumed = chunk[: last_newline + 1], last_newline + 1
        self._offset += consumed

        for raw_line in complete.split(b"\n"):
            if not raw_line.strip():
                continue
            line = raw_line.decode("utf-8", errors="replace").strip()
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                writer.write("journal", {"raw": line})
                continue
            if self.event_filter and obj.get("event") not in self.event_filter:
                continue
            writer.write("journal", obj)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture ED live telemetry (Status.json, NavRoute.json, Journal.*.log) "
                    "to a newline-delimited JSON replay log.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--ed-dir", type=str, default=None,
        help="Elite Dangerous 'Saved Games' data dir (default: auto-resolved, same as the rest of the repo)",
    )
    parser.add_argument(
        "--interval", type=float, default=1.0,
        help="Poll interval in seconds (default: 1.0)",
    )
    parser.add_argument(
        "--duration", type=float, default=None,
        help="Auto-stop after N seconds (default: run until Ctrl-C)",
    )
    parser.add_argument(
        "--out-dir", type=str, default=None,
        help="Output directory for capture files (default: <repo_root>/captures)",
    )
    parser.add_argument(
        "--journal-events", type=str, default=None,
        help="Comma-separated list of journal event types to keep (default: capture all lines)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    ed_dir = Path(args.ed_dir) if args.ed_dir else resolve_ed_dir()
    out_dir = Path(args.out_dir) if args.out_dir else (REPO_ROOT / "captures")
    out_dir.mkdir(parents=True, exist_ok=True)

    session_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"session_{session_ts}.jsonl"

    event_filter: set[str] | None = None
    if args.journal_events:
        event_filter = {e.strip() for e in args.journal_events.split(",") if e.strip()}

    writer = RecordWriter(out_path)
    status_poller = FilePoller(ed_dir / "Status.json", "status")
    navroute_poller = FilePoller(ed_dir / "NavRoute.json", "navroute")
    journal_tailer = JournalTailer(ed_dir, event_filter)

    print(f"capture_telemetry: ED dir = {ed_dir}")
    print(f"capture_telemetry: output = {out_path}")
    print(
        "capture_telemetry: interval={:.2f}s duration={} journal_events={}".format(
            args.interval,
            args.duration if args.duration is not None else "unbounded",
            ",".join(sorted(event_filter)) if event_filter else "all",
        )
    )

    start = time.monotonic()
    last_heartbeat = start
    heartbeat_interval = 10.0
    try:
        while True:
            status_poller.poll(writer)
            navroute_poller.poll(writer)
            journal_tailer.poll(writer)

            now = time.monotonic()
            if now - last_heartbeat >= heartbeat_interval:
                print(
                    "capture_telemetry: heartbeat status={} navroute={} journal={}".format(
                        writer.counts.get("status", 0),
                        writer.counts.get("navroute", 0),
                        writer.counts.get("journal", 0),
                    )
                )
                last_heartbeat = now

            if args.duration is not None and (now - start) >= args.duration:
                print("capture_telemetry: duration elapsed, stopping.")
                break

            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("capture_telemetry: interrupted, shutting down.")
    finally:
        writer.close()

    print(
        "capture_telemetry: wrote {} (status={} navroute={} journal={})".format(
            out_path,
            writer.counts.get("status", 0),
            writer.counts.get("navroute", 0),
            writer.counts.get("journal", 0),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
