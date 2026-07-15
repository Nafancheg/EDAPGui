"""Auto-label remaining unlabeled frames using trained model.

Run after prelabel_jetcone.py to fill in frames missed by HSV masks.
Uses the trained best.pt model for inference.

Usage:  python tools/auto_label_jetcone.py
"""
import sys
import os
import shutil
from pathlib import Path

from ultralytics import YOLO

REPO = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODEL_DIR = REPO / "Yolo26" / "jetcone-model"
DATASET = MODEL_DIR / "dataset" / "train"

model = YOLO(str(MODEL_DIR / "weights" / "best.pt"))

img_dir = DATASET / "images"
lbl_dir = DATASET / "labels"

# Run inference on ALL train images with the trained model
results = model.predict(
    str(img_dir), save=False, save_txt=True, save_conf=False,
    conf=0.5, iou=0.5,
    project=str(DATASET), name="auto_labels", exist_ok=True,
)

# Move predicted labels (overwrites existing)
auto_dir = DATASET / "auto_labels" / "labels"
copied = 0
if auto_dir.exists():
    for f in auto_dir.glob("*.txt"):
        shutil.copy2(f, lbl_dir / f.name)
        copied += 1

# Cleanup
shutil.rmtree(auto_dir.parent, ignore_errors=True)

total_img = len(list(img_dir.glob("*.jpg")))
total_lbl = len(list(lbl_dir.glob("*.txt")))
print(f"Done. {total_img} images, {total_lbl} labels, {copied} predicted by model")
