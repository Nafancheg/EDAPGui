"""
Auto-prelabel jet cone frames with HSV + brightness masks.
Generates YOLO-format labels for the dataset.

Classes:
  0: core   — star's bright center (intensity threshold + largest contour)
  1: jetcone — blue-white plasma cone (HSV mask)

Run:  python tools/prelabel_jetcone.py
"""
import os
import sys
import random
import shutil

import cv2
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "Yolo26", "jetcone-model", "captures")
DST = os.path.join(REPO, "Yolo26", "jetcone-model", "dataset")
TRAIN_IMG = os.path.join(DST, "train", "images")
TRAIN_LBL = os.path.join(DST, "train", "labels")
VAL_IMG   = os.path.join(DST, "val", "images")
VAL_LBL   = os.path.join(DST, "val", "labels")

SPLIT = 0.2  # 20% validation

for d in (TRAIN_IMG, TRAIN_LBL, VAL_IMG, VAL_LBL):
    os.makedirs(d, exist_ok=True)


def label_frame(img_path: str, out_dir: str) -> int:
    """Generate YOLO .txt label for one frame. Returns number of labels written."""
    img = cv2.imread(img_path)
    if img is None:
        return 0
    h, w = img.shape[:2]

    labels = []

    # ── core detection: brightest round-ish region ──
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Threshold: top 15% brightest pixels
    thresh_val = np.percentile(gray, 85)
    _, mask = cv2.threshold(gray, thresh_val, 255, cv2.THRESH_BINARY)
    # Dilate to merge nearby bright spots
    mask = cv2.dilate(mask, np.ones((5, 5), np.uint8), iterations=2)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if contours:
        largest = max(contours, key=cv2.contourArea)
        x, y, bw, bh = cv2.boundingRect(largest)
        area_ratio = (bw * bh) / (w * h)
        # Must be a reasonable size for a star (not full-screen)
        if 0.002 < area_ratio < 0.4:
            cx = (x + bw / 2) / w
            cy = (y + bh / 2) / h
            nw = bw / w
            nh = bh / h
            labels.append(f"0 {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}")

    # ── jetcone detection: HSV blue-white mask ──
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    lower = np.array([90, 20, 180])
    upper = np.array([140, 255, 255])
    mask = cv2.inRange(hsv, lower, upper)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Take up to 2 largest jet-like contours
    jet_contours = sorted(contours, key=cv2.contourArea, reverse=True)[:2]
    for cnt in jet_contours:
        x, y, bw, bh = cv2.boundingRect(cnt)
        area_ratio = (bw * bh) / (w * h)
        if bw > 30 and bh > 30 and area_ratio < 0.6:
            cx = (x + bw / 2) / w
            cy = (y + bh / 2) / h
            nw = bw / w
            nh = bh / h
            labels.append(f"1 {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}")

    # Write label file
    if labels:
        name = os.path.splitext(os.path.basename(img_path))[0]
        lbl_path = os.path.join(out_dir, name + ".txt")
        with open(lbl_path, 'w') as f:
            f.write("\n".join(labels))
    return len(labels)


def main():
    files = [f for f in os.listdir(SRC) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    if not files:
        print(f"No images found in {SRC}")
        return

    random.shuffle(files)
    split_idx = int(len(files) * SPLIT)
    val_files = files[:split_idx]
    train_files = files[split_idx:]

    total_labels = 0
    skipped = 0

    for subset, file_list, img_dir, lbl_dir in [
        ("train", train_files, TRAIN_IMG, TRAIN_LBL),
        ("val",   val_files,   VAL_IMG,   VAL_LBL),
    ]:
        for f in file_list:
            src = os.path.join(SRC, f)
            shutil.copy2(src, os.path.join(img_dir, f))
            n = label_frame(src, lbl_dir)
            if n == 0:
                skipped += 1
            total_labels += n

        print(f"  {subset}: {len(file_list)} images → {img_dir}")

    print(f"Total labels: {total_labels}")
    if skipped:
        print(f"Skipped {skipped} frames (no objects detected) — review manually")
    print(f"\nDataset ready at: {DST}")
    print("Next:  yolo train data=Yolo26/jetcone-model/data.yaml model=yolo26n.pt epochs=100")


if __name__ == "__main__":
    main()
