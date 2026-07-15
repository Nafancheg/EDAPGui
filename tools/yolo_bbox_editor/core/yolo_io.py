"""YOLO format I/O — reads and writes normalized bounding box label files."""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class YOLOLabel:
    class_id: int
    x_center: float
    y_center: float
    width: float
    height: float


@dataclass
class ImageRecord:
    """One image with its labels and file paths."""
    image_path: Path
    label_path: Path
    labels: list[YOLOLabel] = field(default_factory=list)
    dirty: bool = False


def read_labels(label_path: Path) -> list[YOLOLabel]:
    """Parse a YOLO label file. Returns empty list if file missing."""
    labels: list[YOLOLabel] = []
    if not label_path.exists():
        return labels
    with open(label_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 5:
                continue
            labels.append(YOLOLabel(
                class_id=int(parts[0]),
                x_center=float(parts[1]),
                y_center=float(parts[2]),
                width=float(parts[3]),
                height=float(parts[4]),
            ))
    return labels


def write_labels(label_path: Path, labels: list[YOLOLabel]) -> None:
    """Write labels in YOLO format (normalized, 6 decimal places)."""
    label_path.parent.mkdir(parents=True, exist_ok=True)
    with open(label_path, "w", encoding="utf-8") as f:
        for lbl in labels:
            f.write(
                f"{lbl.class_id} "
                f"{lbl.x_center:.6f} {lbl.y_center:.6f} "
                f"{lbl.width:.6f} {lbl.height:.6f}\n"
            )


def scan_folder(folder: Path) -> list[ImageRecord]:
    """Scan a folder for images and matching label files.
    
    Looks for:
      - folder/images/ + folder/labels/
      - folder/ (side-by-side .jpg + .txt)
    """
    exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    images_dir = folder / "images"
    labels_dir = folder / "labels"

    records: list[ImageRecord] = []

    if images_dir.exists() and images_dir.is_dir():
        # Standard YOLO structure: images/ + labels/
        for img_path in sorted(images_dir.iterdir()):
            if img_path.suffix.lower() not in exts:
                continue
            label_path = labels_dir / (img_path.stem + ".txt")
            records.append(ImageRecord(
                image_path=img_path,
                label_path=label_path,
                labels=read_labels(label_path),
            ))
    else:
        # Side-by-side: images and txt in the same folder
        for img_path in sorted(folder.iterdir()):
            if img_path.suffix.lower() not in exts:
                continue
            label_path = folder / (img_path.stem + ".txt")
            records.append(ImageRecord(
                image_path=img_path,
                label_path=label_path,
                labels=read_labels(label_path),
            ))

    return records
