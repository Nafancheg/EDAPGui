"""Auto-label unlabeled frames with higher confidence threshold."""
from ultralytics import YOLO
from pathlib import Path
import shutil

BASE = Path(r"C:\Users\nafan\Documents\ED_Autopilot\Yolo26\jetcone-model\dataset\train")
model = YOLO(str(BASE.parent.parent / "weights" / "best.pt"))

unlabeled = BASE / "unlabeled"
lbl_dir = BASE / "labels"
img_dir = BASE / "images"

results = model.predict(
    str(unlabeled), save=False, save_txt=True, save_conf=False,
    conf=0.5, iou=0.5,
    project=str(BASE), name="auto_labels2", exist_ok=True,
)
n = len(list(unlabeled.glob("*.jpg")))
print(f"Inference done on {n} images")

# Move labels
auto = BASE / "auto_labels2" / "labels"
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
for d in [BASE / "auto_labels", BASE / "auto_labels2"]:
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)

print(f"Done: {len(list(img_dir.glob('*.jpg')))} jpg, {len(list(lbl_dir.glob('*.txt')))} txt")
