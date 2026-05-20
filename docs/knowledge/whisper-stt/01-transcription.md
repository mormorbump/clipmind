# 音声認識（STT）: Whisper / faster-whisper

> 関連: `docs/architecture.md` §3 transcribe, Phase 1

## STT が必要な理由

動画の **検索可能性は字幕（transcript）の質で 8 割決まる**。
人物の発言・ナレーションをテキスト化しないと、

- 「Q3 の結論」のような検索が完全に不可能
- LLM への文脈注入が物体ラベルだけになり、回答が薄くなる

OpenAI Whisper が 2022 年に出てから、**多言語の自動字幕化が「実用品質」に到達**した。

---

## 1. Whisper の系譜

| 実装 | 特徴 | 速度 | ClipMind での扱い |
|---|---|---|---|
| OpenAI Whisper（pip） | リファレンス実装、PyTorch | 標準 | 比較ベース |
| **faster-whisper** | CTranslate2 で高速化 | **~4 倍速** | **採用** |
| whisper.cpp | C++、ggml 量子化 | CPU で速い | macOS で検討 |
| WhisperX | 単語タイムスタンプ + 話者分離 | やや遅い | 将来検討 |

「`pip install openai-whisper`」より「**`pip install faster-whisper`**」が現代の事実上の標準。

---

## 2. モデルサイズの選び方

| モデル | パラメータ | VRAM | WER (en) | 用途 |
|---|---|---|---|---|
| `tiny`   | 39M  | 1GB | ~10% | 動作確認用 |
| `base`   | 74M  | 1GB | ~7%  | CPU 実用 |
| `small`  | 244M | 2GB | ~5%  | バランス |
| `medium` | 769M | 5GB | ~4%  | 高品質 |
| `large-v3` | 1550M | 10GB | ~3% | **本命** |

**ClipMind の戦略**:
- GPU あり → `large-v3`（高精度、~3 分/1時間動画）
- CPU only → `base`（中精度、~15 分/1時間動画）
- 自動切り替えを config で制御（architecture.md §6）

---

## 3. faster-whisper の使い方

```python
from faster_whisper import WhisperModel

model = WhisperModel("large-v3", device="cuda", compute_type="float16")
# device: "cuda" / "cpu" / "auto"
# compute_type: "float16" / "int8_float16" / "int8"

segments, info = model.transcribe(
    "audio.wav",
    beam_size=5,
    language="en",            # 自動検出も可
    word_timestamps=True,     # 単語単位の timestamp が必要なら True
    vad_filter=True,          # 無音区間を自動スキップ（高速化）
)

for s in segments:
    print(f"[{s.start:.2f} -> {s.end:.2f}] {s.text}")
```

**ポイント**:
- `vad_filter=True` で 1.3〜2 倍速くなる（沈黙が多い動画ほど効く）
- `compute_type="int8"` は精度が少し落ちるが CPU でも動く
- `word_timestamps=True` は重い。chunk 単位の timestamp で十分なら False

---

## 4. 言語と精度のクセ

### 4.1 多言語混在
- 1 動画に英語と日本語が混在すると Whisper はどちらかに引っ張られる
- セグメント単位で `language` を再判定する設計が必要なケースもある

### 4.2 専門用語・固有名詞
- 「ClipMind」のようなブランド名は当然 hallucinate する
- `initial_prompt` に固有名詞リストを渡すと改善:
  ```python
  model.transcribe(audio, initial_prompt="ClipMind, LangGraph, Qdrant")
  ```

### 4.3 静かな間に幻覚
- 無音区間で「Thank you for watching!」のような **典型句を捏造する** バグが知られている
- `vad_filter=True` で大幅に改善
- 後段で `no_speech_prob > 0.6` の segment を捨てるフィルタも有効

---

## 5. 評価: WER（Word Error Rate）

```
WER = (Sub + Del + Ins) / N_ref
```

- Sub/Del/Ins: 置換・削除・挿入の単語数
- N_ref: 正解の単語数

ClipMind では LibriSpeech test-clean + 自作日本語サンプルで測る（`docs/evaluation.md` §2.1）。
目標: 英語 < 8%, 日本語 < 15%。

ライブラリ:
```python
import jiwer
wer = jiwer.wer(reference, hypothesis)
```

---

## 6. ハマりどころ

### 6.1 音声抽出のサンプリングレート
- Whisper は 16kHz mono が前提
- ffmpeg で先に変換しておく:
  ```bash
  ffmpeg -i video.mp4 -vn -ac 1 -ar 16000 audio.wav
  ```

### 6.2 GPU メモリ枯渇（OOM）
- `large-v3` を 10GB 未満の GPU で動かそうとすると死ぬ
- `compute_type="int8_float16"` で半分以下になる
- 失敗を検知したら `medium` へ自動 fallback する設計が安全

### 6.3 Apple Silicon
- `faster-whisper` は MPS 直接サポートが弱い時期があった
- `whisper.cpp` の方が Mac で速いことも → 検討の価値あり

### 6.4 タイムスタンプのズレ
- VAD filter を入れると無音をスキップするが、内部時刻と実時刻がずれることはない（segments は実時刻で返る）
- ただし `word_timestamps=True` の精度は完璧ではないので、検索時は ±数秒の誤差を許容する設計に

---

## 7. 実装で確認したいこと

- [ ] base / small / medium / large-v3 で WER 比較
- [ ] vad_filter on/off で速度比較
- [ ] `initial_prompt` で固有名詞精度が改善するか
- [ ] 日本語含む動画で言語検出が正しく走るか

---

## 8. 参考リンク

- OpenAI Whisper: https://github.com/openai/whisper
- faster-whisper: https://github.com/SYSTRAN/faster-whisper
- whisper.cpp: https://github.com/ggerganov/whisper.cpp
- 評価: https://github.com/openai/whisper/blob/main/language-breakdown.svg

---

## 実践マーカー

- 未実装（Phase 1 で着手予定）
