"""YOLOv8 による物体検知.

ultralytics は重量級依存なので関数内 lazy import.
モデル (yolov8n.pt ~6MB) は初回実行時に自動ダウンロードされる.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ultralytics import YOLO  # type: ignore[attr-defined]


@dataclass(frozen=True)
class Detection:
    """1 フレーム内の検知結果 1 件."""

    label: str
    confidence: float
    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2


@lru_cache(maxsize=1)
def _load_model(model_name: str = "yolov8n.pt") -> YOLO:
    from ultralytics import YOLO  # type: ignore[attr-defined]

    return YOLO(model_name)


def detect_objects(
    jpeg_bytes: bytes,
    *,
    model_name: str = "yolov8n.pt",
    min_confidence: float = 0.4,
) -> list[Detection]:
    """JPEG バイト列に対して YOLO 検知を行い、Detection 列を返す.

    Args:
        jpeg_bytes: extract_keyframes が出力した JPEG
        model_name: ultralytics モデル名 (n=nano が最軽量)
        min_confidence: これ未満の検知は捨てる
    """
    import cv2
    import numpy as np

    arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        msg = "failed to decode JPEG bytes"
        raise ValueError(msg)

    model = _load_model(model_name)
    results: Any = model.predict(frame, verbose=False)

    detections: list[Detection] = []
    for result in results:
        names = result.names
        for box in result.boxes:
            conf = float(box.conf[0])
            if conf < min_confidence:
                continue
            cls_id = int(box.cls[0])
            x1, y1, x2, y2 = (int(v) for v in box.xyxy[0])
            detections.append(
                Detection(
                    label=str(names.get(cls_id, str(cls_id))),
                    confidence=conf,
                    bbox=(x1, y1, x2, y2),
                )
            )
    return detections
