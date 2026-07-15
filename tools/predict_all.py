"""Label ALL images with model predictions."""
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

results = model.predict(
    str(img_dir), save=False, save_txt=True, save_conf=False,
    conf=0.5, iou=0.5,
    project=str(DATASET), name="predict_all", exist_ok=True,
)

# Move labels
auto = DATASET / "predict_all" / "labels"
copied = 0
if auto.exists():
    for f in auto.glob("*.txt"):
        shutil.copy2(f, lbl_dir / f.name)
        copied += 1

# Clean
shutil.rmtree(auto.parent, ignore_errors=True)

empty = len(list(img_dir.glob("*.jpg"))) - copied
print(f"Done: {copied} images got labels, {empty} empty")
