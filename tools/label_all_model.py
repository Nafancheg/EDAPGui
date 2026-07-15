"""One-shot: split captures → train/val + model inference."""
import os, shutil, random
from pathlib import Path
from ultralytics import YOLO

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / 'Yolo26/jetcone-model/captures'
DST = REPO / 'Yolo26/jetcone-model/dataset'
MODEL_PATH = REPO / 'Yolo26/jetcone-model/weights/best.pt'

files = [f for f in os.listdir(SRC) if f.lower().endswith(('.jpg','.jpeg','.png'))]
random.shuffle(files)
split = int(len(files) * 0.2)
val_files, train_files = files[:split], files[split:]

for subset, flist in [('train', train_files), ('val', val_files)]:
    img_dir = DST / subset / 'images'
    lbl_dir = DST / subset / 'labels'
    img_dir.mkdir(parents=True, exist_ok=True)
    lbl_dir.mkdir(parents=True, exist_ok=True)
    for f in flist:
        shutil.copy2(SRC / f, img_dir / f)
    print(f'{subset}: {len(flist)} images copied')

model = YOLO(str(MODEL_PATH))
for subset, flist in [('train', train_files), ('val', val_files)]:
    img_dir = DST / subset / 'images'
    lbl_dir = DST / subset / 'labels'
    results = model.predict(str(img_dir), save=False, save_txt=True, save_conf=False,
        conf=0.3, iou=0.5, project=str(DST / subset), name='auto', exist_ok=True)
    auto = DST / subset / 'auto' / 'labels'
    copied = 0
    if auto.exists():
        for f in auto.glob('*.txt'):
            shutil.copy2(f, lbl_dir / f.name)
            copied += 1
        shutil.rmtree(auto.parent)
    print(f'{subset}: {copied} labels / {len(flist)} images')

print('Done.')
