"""OpenCV を使った自前ヒストグラム差分シーンカット検出 + キーフレーム抽出.

knowledge/video-processing/01 §1.1 の方針 (PySceneDetect ではなく自前) を採用.

アルゴリズム:
  1. 1 フレームずつ読み、HSV ヒストグラムを計算
  2. 直前のキーフレームと `compareHist(..., HISTCMP_BHATTACHARYYA)` で差分
  3. 差分が `threshold` 以上 かつ 直前のキーフレームから `min_gap_frames` 以上空いていれば採用
  4. index 0 は無条件にキーフレームとして採用
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass(frozen=True)
class ExtractedFrame:
    """抽出されたキーフレーム 1 枚."""

    index: int
    timestamp_ms: int
    jpeg_bytes: bytes


def _hsv_hist(frame_bgr: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [50, 60], [0, 180, 0, 256])
    cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
    return hist


def extract_keyframes(
    video_path: Path,
    *,
    threshold: float = 0.4,
    min_gap_frames: int = 5,
    jpeg_quality: int = 85,
) -> list[ExtractedFrame]:
    """`video_path` から自前ヒストグラム差分でキーフレームを返す.

    Args:
        video_path: 入力動画
        threshold: BHATTACHARYYA 距離の閾値 (0..1, 大きいほど差分が大きい)
        min_gap_frames: 直前キーフレームから最低限空けるフレーム数
        jpeg_quality: 出力 JPEG の quality

    Returns:
        抽出順に並んだ ExtractedFrame の list
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        msg = f"cannot open video: {video_path}"
        raise RuntimeError(msg)

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality]

    keyframes: list[ExtractedFrame] = []
    prev_hist: np.ndarray | None = None
    last_keyframe_idx = -min_gap_frames
    idx = 0

    try:
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                break

            current_hist = _hsv_hist(frame)

            adopt = False
            if idx == 0:
                adopt = True
            elif prev_hist is not None and idx - last_keyframe_idx >= min_gap_frames:
                diff = float(cv2.compareHist(prev_hist, current_hist, cv2.HISTCMP_BHATTACHARYYA))
                if diff >= threshold:
                    adopt = True

            if adopt:
                ok_enc, buf = cv2.imencode(".jpg", frame, encode_params)
                if ok_enc:
                    timestamp_ms = int(idx * 1000 / fps)
                    keyframes.append(
                        ExtractedFrame(
                            index=idx,
                            timestamp_ms=timestamp_ms,
                            jpeg_bytes=buf.tobytes(),
                        )
                    )
                    prev_hist = current_hist
                    last_keyframe_idx = idx

            idx += 1
    finally:
        cap.release()

    return keyframes
