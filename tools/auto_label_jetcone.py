"""Auto-label remaining unlabeled frames using trained model."""
from ultralytics import YOLO
from pathlib import Path
import shutil

BASE = Path(r"C:\Users\nafan\Documents\ED_Autopilot\Yolo26\jetcone-model\dataset\train")
model = YOLO(str(BASE.parent.parent / "weights" / "best.pt"))

# Run inference with higher confidence threshold to avoid spam
results = model.predict(
    str(unlabeled_dir), save=False, save_txt=True, save_conf=False,
    conf=0.5, iou=0.5,
    project=str(BASE), name="auto_labels2", exist_ok=True,
)
n = len(list(unlabeled_dir.glob("*.jpg")))
print(f"Inference done on {n} images")

# Move predicted labels
auto_dir = BASE / "auto_labels2" / "labels"
if auto_dir.exists():
    copied = 0
    for f in auto_dir.glob("*.txt"):
        shutil.copy2(f, lbl_dir / f.name)
        copied += 1
    print(f"Copied {copied} labels to {lbl_dir}")

# Remove old auto_labels if exists
old_auto = BASE / "auto_labels"
if old_auto.exists():
    shutil.rmtree(old_auto, ignore_errors=True)
unlabeled_dir = BASE / "unlabeled"
lbl_dir = BASE / "labels"
img_dir = BASE / "images"

# Run inference
results = model.predict(
    str(unlabeled_dir), save=False, save_txt=True, save_conf=False,
    project=str(BASE), name="auto_labels", exist_ok=True,
)
n = len(list(unlabeled_dir.glob("*.jpg")))
print(f"Inference done on {n} images")

# Move predicted labels
auto_dir = BASE / "auto_labels" / "labels"
if auto_dir.exists():
    for f in auto_dir.glob("*.txt"):
        shutil.copy2(f, lbl_dir / f.name)
    print(f"Labels moved to {lbl_dir}")

# Move images back
for f in unlabeled_dir.glob("*.jpg"):
    shutil.move(str(f), str(img_dir / f.name))

total_img = len(list(img_dir.glob("*.jpg")))
total_lbl = len(list(lbl_dir.glob("*.txt")))
print(f"Done. {total_img} images, {total_lbl} labels")
