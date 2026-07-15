"""Label ALL images with model predictions."""
from ultralytics import YOLO
from pathlib import Path
import shutil

BASE = Path(r"C:\Users\nafan\Documents\ED_Autopilot\Yolo26\jetcone-model\dataset\train")
model = YOLO(str(BASE.parent.parent / "weights" / "best.pt"))

img_dir = BASE / "images"
lbl_dir = BASE / "labels"

results = model.predict(
    str(img_dir), save=False, save_txt=True, save_conf=False,
    conf=0.5, iou=0.5,
    project=str(BASE), name="predict_all", exist_ok=True,
)

# Move labels
auto = BASE / "predict_all" / "labels"
copied = 0
if auto.exists():
    for f in auto.glob("*.txt"):
        shutil.copy2(f, lbl_dir / f.name)
        copied += 1

# Clean
shutil.rmtree(auto.parent, ignore_errors=True)

print(f"Done: {copied} images got labels, {110 - copied} empty")
