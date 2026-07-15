"""Auto-label unlabeled frames with higher confidence threshold.

For images in dataset/train/unlabeled/ — runs model inference and moves
results to labels/ and images back to images/.

Usage:  python tools/auto_label2.py
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

unlabeled = DATASET / "unlabeled"
lbl_dir = DATASET / "labels"
img_dir = DATASET / "images"

if not unlabeled.exists():
    print(f"No unlabeled dir at {unlabeled}")
    print("Place .jpg files without labels in dataset/train/unlabeled/ first.")
    sys.exit(0)

results = model.predict(
    str(unlabeled), save=False, save_txt=True, save_conf=False,
    conf=0.5, iou=0.5,
    project=str(DATASET), name="auto_labels2", exist_ok=True,
)
n = len(list(unlabeled.glob("*.jpg")))
print(f"Inference done on {n} images")

# Move labels
auto = DATASET / "auto_labels2" / "labels"
copied = 0
if auto.exists():
    for f in auto.glob("*.txt"):
        shutil.copy2(f, lbl_dir / f.name)
        copied += 1
    print(f"Copied {copied} labels")

# Move images back
for f in unlabeled.glob("*.jpg"):
    shutil.move(str(f), str(img_dir / f.name))

# Clean old folders
for d in [DATASET / "auto_labels", DATASET / "auto_labels2"]:
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)

# Remove empty unlabeled dir
if unlabeled.exists():
    try:
        unlabeled.rmdir()
    except OSError:
        pass

print(f"Done: {len(list(img_dir.glob('*.jpg')))} jpg, {len(list(lbl_dir.glob('*.txt')))} txt")
