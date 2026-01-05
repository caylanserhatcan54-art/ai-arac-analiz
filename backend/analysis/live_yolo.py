# backend/analysis/live_yolo.py
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

# Optional dependency: ultralytics
try:
    from ultralytics import YOLO  # type: ignore
except Exception:
    YOLO = None


DEFAULT_DAMAGE_LABELS = {
    # You can tune this list based on your model training
    "scratch", "dent", "crack", "broken", "damage", "bumper_damage", "door_dent",
    "headlight_broken", "taillight_broken", "paint_peel",
}


class YoloDetector:
    def __init__(self, model_path: str):
        if YOLO is None:
            raise RuntimeError("Ultralytics yüklü değil. (pip install ultralytics)")
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"YOLO modeli bulunamadı: {model_path}")
        self.model = YOLO(model_path)

    def predict(self, image_path: str, conf: float = 0.25, iou: float = 0.45) -> List[Dict[str, Any]]:
        """
        Returns list of detections:
          [{label, conf, box:[x1,y1,x2,y2]}, ...]
        """
        results = self.model.predict(source=image_path, conf=conf, iou=iou, verbose=False)
        dets: List[Dict[str, Any]] = []
        if not results:
            return dets
        r0 = results[0]
        if r0.boxes is None:
            return dets

        names = getattr(self.model, "names", None) or getattr(r0, "names", None) or {}
        for b in r0.boxes:
            cls = int(b.cls.item()) if hasattr(b.cls, "item") else int(b.cls)
            label = names.get(cls, str(cls))
            score = float(b.conf.item()) if hasattr(b.conf, "item") else float(b.conf)
            xyxy = b.xyxy[0].tolist() if hasattr(b.xyxy[0], "tolist") else list(b.xyxy[0])
            dets.append({"label": label, "conf": score, "box": [float(x) for x in xyxy]})
        return dets
