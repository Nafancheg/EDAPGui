"""
Jet cone training dataset builder.

Three modes, auto-detected from the argument:
  python tools/jetcone_dataset.py                              → interactive screen capture
  python tools/jetcone_dataset.py clip.mp4                     → extract frames from local video
  python tools/jetcone_dataset.py "https://youtube.com/..."    → download + extract frames

YouTube download requires yt-dlp:  pip install yt-dlp
Frames go to Yolo26/jetcone-model/captures/ for annotation.

Quality: downloads best mp4 ≤1440p (higher resolution is overkill — YOLO trains at 640²
and the jet cone is a large bright feature visible even at 720p). Variety of angles and
star types matters far more than pixel count.
"""

import os
import subprocess
import sys
import time
from datetime import datetime

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(REPO_ROOT, "Yolo26", "jetcone-model", "captures")
os.makedirs(OUT_DIR, exist_ok=True)

FRAME_EVERY = 30   # extract every N-th frame (~1/sec at 30fps)
YT_FORMAT = "bestvideo[height<=1440][ext=mp4]+bestaudio[ext=m4a]/best[height<=1440][ext=mp4]/best[height<=1440]"


# ── YouTube download ────────────────────────────────────────────────────────
def download_youtube(url: str, out_dir: str) -> str | None:
    """Download a YouTube video via yt-dlp. Returns path to the downloaded file."""
    if not isinstance(url, str) or not url.startswith("http"):
        return None
    print(f"Downloading: {url}")
    try:
        subprocess.run(
            ["yt-dlp", "--version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("ERROR: yt-dlp not found. Install it:")
        print("  pip install yt-dlp")
        return None

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    tmpl = os.path.join(out_dir, f"yt_{ts}_%(title)s.%(ext)s")
    result = subprocess.run(
        ["yt-dlp", "-f", YT_FORMAT, "-o", tmpl, "--no-playlist", url],
        capture_output=True, text=True, cwd=out_dir)
    if result.returncode != 0:
        print(f"yt-dlp failed:\n{result.stderr}")
        return None

    # Find the downloaded file (name contains the video title — not predictable)
    for f in sorted(os.listdir(out_dir), reverse=True):
        if f.startswith(f"yt_{ts}_") and f.endswith(".mp4"):
            path = os.path.join(out_dir, f)
            size_mb = os.path.getsize(path) / (1024 * 1024)
            print(f"Downloaded: {f} ({size_mb:.1f} MB)")
            return path
    print("ERROR: could not locate downloaded file.")
    return None


# ── Frame extraction ────────────────────────────────────────────────────────
def extract_frames(video_path: str, every_n: int = FRAME_EVERY) -> int:
    """Extract every Nth frame from a video file. Returns frame count."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"ERROR: cannot open video: {video_path}")
        return 0

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    duration = total_frames / fps if fps > 0 else 0
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    print(f"Video: {w}×{h}, {fps:.0f}fps, {total_frames} frames, {duration:.0f}s")
    print(f"Extracting every {every_n}th frame...")

    prefix = os.path.splitext(os.path.basename(video_path))[0]
    # sanitise prefix
    prefix = "".join(c if c.isalnum() or c in "_-" else "_" for c in prefix)[:60]

    count = 0
    idx = 0
    last_pct = -1
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if idx % every_n == 0:
            fname = f"{prefix}_{idx:06d}.jpg"
            cv2.imwrite(os.path.join(OUT_DIR, fname), frame,
                        [cv2.IMWRITE_JPEG_QUALITY, 92])
            count += 1
        idx += 1

        # progress
        pct = int(idx / total_frames * 100) if total_frames else 0
        if pct != last_pct and pct % 10 == 0:
            print(f"  {pct}% ({idx}/{total_frames}) — {count} frames saved")
            last_pct = pct

    cap.release()
    print(f"Done. {count} frames saved to {OUT_DIR}")
    return count


# ── Interactive screen capture (original mode) ──────────────────────────────
def _find_ed_window():
    try:
        import win32gui
        def cb(hwnd, wnds):
            if win32gui.IsWindowVisible(hwnd) and "Elite - Dangerous" in win32gui.GetWindowText(hwnd):
                wnds.append(hwnd)
            return True
        wnds = []
        win32gui.EnumWindows(cb, wnds)
        return wnds[0] if wnds else None
    except ImportError:
        return None


def _capture_screen(hwnd):
    import ctypes
    import win32gui, win32ui

    left, top, right, bottom = win32gui.GetClientRect(hwnd)
    w, h = right - left, bottom - top
    if w <= 0 or h <= 0:
        return None

    hdc = win32gui.GetWindowDC(hwnd)
    mfc = win32ui.CreateDCFromHandle(hdc)
    save = mfc.CreateCompatibleDC()
    bmp = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(mfc, w, h)
    save.SelectObject(bmp)

    # PrintWindow via ctypes (removed from win32gui in newer pywin32)
    PW_CLIENTONLY = 2
    ctypes.windll.user32.PrintWindow(hwnd, save.GetSafeHdc(), PW_CLIENTONLY)

    info = bmp.GetInfo()
    bits = bmp.GetBitmapBits(True)
    img = np.frombuffer(bits, dtype=np.uint8).reshape((info['bmHeight'], info['bmWidth'], 4))
    img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    # Cleanup GDI objects
    win32gui.DeleteObject(bmp.GetHandle())
    save.DeleteDC()
    mfc.DeleteDC()
    win32gui.ReleaseDC(hwnd, hdc)
    return img


def interactive_capture():
    print("Jet Cone interactive capture")
    print("  SPACE = capture   ESC = quit")
    print(f"  Output: {OUT_DIR}")

    hwnd = _find_ed_window()
    if hwnd is None:
        print("ERROR: Elite Dangerous window not found. Start the game first.")
        return

    print("Ready — fly near a neutron star jet cone and press SPACE.")

    count = 0
    last = 0.0
    while True:
        img = _capture_screen(hwnd)
        if img is None:
            time.sleep(0.2)
            continue
        preview = cv2.resize(img, (0, 0), fx=0.4, fy=0.4)
        cv2.putText(preview, f"Saved: {count}  [SPACE=cap ESC=quit]",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 200), 2)
        cv2.imshow("Jet Cone Capture", preview)
        key = cv2.waitKey(50) & 0xFF
        if key == 27:
            break
        elif key == 32 and time.time() - last > 0.5:
            last = time.time()
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            fname = f"jetcone_{ts}.jpg"
            cv2.imwrite(os.path.join(OUT_DIR, fname), img,
                        [cv2.IMWRITE_JPEG_QUALITY, 92])
            count += 1
            print(f"  [{count}] {fname}")

    cv2.destroyAllWindows()
    print(f"Done. {count} frames captured.")


# ── main ────────────────────────────────────────────────────────────────────
def main():
    if len(sys.argv) > 1:
        arg = sys.argv[1]
    else:
        interactive_capture()
        return

    # Auto-detect: URL → download + extract; .mp4/.avi/.mkv → extract
    if arg.startswith("http://") or arg.startswith("https://"):
        video_path = download_youtube(arg, OUT_DIR)
        if video_path is None:
            return
    elif os.path.isfile(arg) and arg.lower().endswith((".mp4", ".avi", ".mkv", ".mov", ".webm")):
        video_path = arg
    else:
        print(f"Usage:")
        print(f"  {sys.argv[0]}                              — interactive capture")
        print(f"  {sys.argv[0]} clip.mp4                     — extract frames from video")
        print(f"  {sys.argv[0]} \"https://youtube.com/...\"    — download + extract")
        return

    extract_frames(video_path)
    print("\nNext: annotate frames with labelImg or Roboflow, then train:")
    print("  yolo train data=Yolo26/jetcone-model/data.yaml model=yolo26n.pt epochs=100")


if __name__ == "__main__":
    main()
