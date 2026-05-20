# 動画前処理: シーンカット検出・キーフレーム抽出・物体検知

> 関連: `docs/architecture.md` §3, Phase 1 / 2

## なぜ「全フレーム」を処理しないのか

30fps の動画 1 時間 = **108,000 フレーム**。
これを全部 LLM に送ると:

- コストが爆発（GPT-4o-mini でも $20+ になる）
- LLM のレート制限に確実に引っかかる
- 隣接フレームはほぼ同じ内容で **冗長**

→ **「意味のある代表フレーム」だけを残す** のが動画前処理の主目的。

ClipMind では 1 時間 → 300 フレーム程度（1/360）まで間引く（`docs/cost-estimation.md`）。

---

## 1. シーンカット検出（Shot Boundary Detection）

「カメラが切り替わった瞬間」を検出して、**シーンの境界** を見つける。
境界の前後フレームが「キーフレーム候補」になる。

### 1.1 ヒストグラム差分法（古典・軽量）

```python
import cv2
import numpy as np

def hist_diff(frame_a, frame_b):
    h_a = cv2.calcHist([frame_a], [0,1,2], None, [8,8,8], [0,256]*3)
    h_b = cv2.calcHist([frame_b], [0,1,2], None, [8,8,8], [0,256]*3)
    h_a = cv2.normalize(h_a, h_a).flatten()
    h_b = cv2.normalize(h_b, h_b).flatten()
    return cv2.compareHist(h_a, h_b, cv2.HISTCMP_CHISQR)
```

- フレーム間の色ヒストグラムの距離が閾値を超えたら「カット」
- 閾値はデータ依存。動画ジャンルで調整（ニュース番組 vs アニメ）
- CPU だけで動く、GPU 不要

### 1.2 PySceneDetect（実用ライブラリ）

```python
from scenedetect import detect, ContentDetector
scenes = detect("video.mp4", ContentDetector(threshold=27.0))
```

- ヒストグラム + コンテンツベース検出器が組み込み
- ClipMind の Phase 1 はこれをラップして使うのが現実的

### 1.3 ニューラルネット系（高精度・重い）

- TransNetV2 等。シーンカット精度が高いが GPU 必須
- ClipMind は当面採用しない（YAGNI）

---

## 2. キーフレーム抽出

シーンカット検出後、各シーンから **代表フレームを 1〜数枚** 選ぶ。

### 2.1 シンプルな選び方
- **シーン中央**: シーン開始 + 終了の真ん中の 1 枚
- **シーン冒頭**: カット直後の 1 枚（情報量が高いことが多い）

### 2.2 情報量ベース
- フレームの「鮮鋭度」（Laplacian variance）が高いものを選ぶ → ぼけてない
- 動きが少ないフレーム（直前との差分が小さい）を選ぶ → 安定したフレーム

```python
def laplacian_var(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.Laplacian(gray, cv2.CV_64F).var()
```

### 2.3 シーン長で動的に枚数調整
- 5 秒以下のシーン → 1 枚
- 5〜30 秒のシーン → 中央 1 枚 + 末尾 1 枚
- 30 秒超 → 5 秒ごとに 1 枚

ClipMind では「**1 分あたり平均 5 フレーム**」のルールを目安に調整（cost-estimation.md）。

---

## 3. YOLO（You Only Look Once）— 物体検知

「画像内のどこに何があるか」を bbox 付きで返す。
Ultralytics の `yolov8` シリーズが現役の標準。

### 3.1 モデルサイズの選び方

| モデル | パラメータ | mAP@0.5 (COCO) | 速度 (CPU) |
|---|---|---|---|
| `yolov8n` | 3.2M | ~0.62 | 速い |
| `yolov8s` | 11.2M | ~0.70 | 中 |
| `yolov8m` | 25.9M | ~0.75 | 遅い（GPU 推奨） |

**ClipMind は `yolov8n` から始め、評価で精度不足なら `s` に上げる**。

### 3.2 使い方

```python
from ultralytics import YOLO

model = YOLO("yolov8n.pt")
results = model(frame_image, conf=0.4, iou=0.5)

for r in results:
    for box in r.boxes:
        label = model.names[int(box.cls)]
        confidence = float(box.conf)
        bbox = box.xyxy[0].tolist()
```

### 3.3 動画への適用

- フレーム単位で順次推論する素朴な方式で OK（ClipMind は 300 フレーム/動画なので速い）
- 大規模化したら ByteTrack で **物体追跡**（同一人物を時系列で追う）も視野

### 3.4 ラベル設計
- COCO のデフォルト 80 クラス（person, car, laptop, ...）でほぼ十分
- 特化用途（例: ロゴ検知）が必要なら、Roboflow 等で fine-tune する話に発展

---

## 4. fuse — 時系列マージ

並列で取れた以下の 4 系統を **時間窓** で束ねる:

1. キーフレーム（時刻つき画像 path）
2. 字幕（Whisper）
3. 物体検知（YOLO ラベル + bbox）
4. キャプション（マルチモーダル LLM）

```python
for window in sliding_windows(start=0, end=duration, width=5_000, stride=5_000):
    yield {
        "start_ms": window.start,
        "end_ms": window.end,
        "transcript": " ".join(t.text for t in transcripts if window.contains(t)),
        "objects":    list({d.label for d in detections if window.contains(d)}),
        "captions":   [c.text for c in captions if window.contains(c)],
        "key_frame":  pick_most_informative(frames in window),
    }
```

**この segment が RAG の chunk 単位になる**（→ rag/01-hybrid-search.md）。

ウィンドウ幅は実験で決める（`docs/evaluation.md` §3.4: 5s / 15s / 30s / 60s 比較）。

---

## 5. ハマりどころ

### 5.1 OpenCV のメモリリーク
- `cv2.VideoCapture` を release し忘れると、長時間 Ingest でメモリが膨らむ
- with-statement パターンを使うか、try/finally で確実に release

### 5.2 H.265 / VP9 の codec 不足
- macOS デフォルトの OpenCV ビルドは codec が限定的
- `pip install opencv-python-headless` だけでは足りないことも
- `ffmpeg` を別途インストールしてフレーム抽出だけ ffmpeg に任せる手もアリ

### 5.3 Apple Silicon での YOLO
- `device='mps'` で Metal 経由 GPU 推論可能
- ただし `mps` バックエンドは一部 ops 未対応で fallback することがある
- 計測してから決める

### 5.4 シーンカット閾値の動画ジャンル依存
- スポーツ（カット多い）と講義（カット少ない）で同じ閾値は合わない
- ジャンル別プリセット or 動的調整を検討

---

## 6. 実装で確認したいこと

- [ ] 1 時間動画でフレーム数が ~300 程度に収まるか（cost-estimation.md の前提）
- [ ] PySceneDetect の閾値を 3 段階で比較
- [ ] yolov8n と yolov8s の mAP / 速度差を実測
- [ ] fuse window 幅を 5/15/30s で Recall@5 比較

---

## 7. 参考リンク

- OpenCV: https://docs.opencv.org/4.x/
- PySceneDetect: https://www.scenedetect.com/
- Ultralytics YOLO: https://docs.ultralytics.com/
- ByteTrack: https://github.com/ifzhang/ByteTrack

---

## 実践マーカー

- 未実装（Phase 1 / 2 で着手予定）
