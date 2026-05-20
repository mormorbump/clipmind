# マルチモーダル LLM: Vision Captioning

> 関連: ADR-0003, `docs/architecture.md` §3.2 caption_frames, Phase 2

## マルチモーダル LLM とは

テキストだけでなく **画像（・音声・動画）** を入力に取れる LLM。
ClipMind では「フレーム画像 → 自然言語キャプション」に使う。

| モデル | コンテキスト | 強み |
|---|---|---|
| Claude Sonnet 4.6 (Vision) | 1M tokens | 長文・推論強い、画像読解が緻密 |
| Claude Haiku 4.5 | 200k tokens | 高速・安価 |
| GPT-4o | 128k tokens | 画像理解が高精度 |
| GPT-4o-mini | 128k tokens | **超低コスト**、大量バッチ向き |

ClipMind は **コスト最適化のため GPT-4o-mini をデフォルト**、
品質要求が高い場合のみ Claude Sonnet（ADR-0003）。

---

## 1. なぜキャプションを LLM でやるのか

### 1.1 動画 → テキスト変換が必要な理由

RAG は最終的に embedding で検索する。Embedding は基本テキスト用。
**フレーム画像をそのまま検索可能にするには、テキスト化が必要**。

選択肢:

| 手法 | コスト | 精度 |
|---|---|---|
| YOLO のラベル列挙のみ | 無料 | 物体しか拾えない（人, ノートPC...） |
| BLIP / CLIP captioning | ローカル GPU | 一般的 caption が出る |
| **マルチモーダル LLM** | API | **シーンの意味・関係性まで記述** |

ClipMind は **YOLO（物体）+ LLM caption（意味）** を併用して fuse する設計（architecture.md §3）。

### 1.2 Caption の質が RAG 精度を決める

- 「人物 A が登場するシーン」のような検索は、caption に「a man in blue shirt」と書かれているかで決まる
- 雑な caption だと検索が空振りする
- **プロンプト設計で精度の半分は決まる**

---

## 2. プロンプト設計

### 2.1 悪い例

```
このフレームを説明してください。
```

→ 「A person standing.」のような無価値な caption が返る。

### 2.2 良い例（ClipMind 想定）

```
あなたは動画フレームの記述を書く専門家です。
以下のフレームについて、後続の検索で使えるよう、3-4 文で記述してください。

含めるべき要素:
- 主要な人物（服装・行動）
- 主要な物体・場所
- 場面・状況（屋内/屋外、時間帯、雰囲気）
- 画面に写っているテキスト（スライド・字幕など）があれば原文で

避けること:
- 推測（「楽しそう」「悲しそう」など主観）
- 一般的な前置き（「この画像には...」）
```

ポイント:
- **構造化した観点** を箇条書きで指示
- 「**避けること**」を明示することで雑な出力を防ぐ
- 検索に使う前提を明示

### 2.3 出力フォーマット強制

```
以下の JSON で返してください:
{"caption": "...", "ocr_texts": ["..."], "main_objects": ["..."]}
```

- LLM の自由文だけだと後段でパースしにくい
- Anthropic / OpenAI 共に **構造化出力** がサポートされている
- ただし Vision + JSON は精度が落ちる場合があるので評価で確認

---

## 3. コスト最適化

### 3.1 モデル階層化

```
キャプションの重要度に応じて:
  通常フレーム → GPT-4o-mini (~$0.0002/枚)
  キーフレーム（シーン冒頭など）→ Claude Sonnet (~$0.006/枚)
  フォールバック → GPT-4o-mini → Haiku の順で再試行
```

`docs/cost-estimation.md` の試算では、デフォルト GPT-4o-mini で **1 時間動画 $0.06**。
全部 Sonnet にすると **$1.80**（30 倍）。

### 3.2 Prompt Caching（Anthropic）

System prompt + 動画メタデータを **cache_control** で固定すると、2 回目以降の入力トークンが 90% 引き。

```python
messages=[{
    "role": "system",
    "content": [{
        "type": "text",
        "text": SYSTEM_PROMPT,
        "cache_control": {"type": "ephemeral"}
    }]
}]
```

- 5 分間有効
- 同じ動画の複数フレームを連続キャプションする時に効く

### 3.3 並列実行

300 枚のフレームを直列に呼ぶと数十分かかる。
**asyncio.gather + 適切な並列度**（10〜20）で時短。
レート制限に当たったら指数バックオフ。

### 3.4 フレーム選別の強化

シーンカット検出の閾値を厳しくして 300 → 100 枚にできれば、
それだけでコスト 1/3。

---

## 4. 画像入力の作法

### 4.1 Anthropic（Claude）

```python
{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}}
# または
{"type": "image", "source": {"type": "url", "url": "https://..."}}
```

### 4.2 OpenAI

```python
{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}
```

### 4.3 解像度の落とし所

- フル HD（1920×1080）をそのまま送ると無駄
- 内部で 768〜1024 px 程度にリサイズして十分（モデル側でも自動 downsample される）
- リサイズすればトークン数も減ってコスト削減

---

## 5. ハマりどころ

### 5.1 部分失敗を Ingest 全体停止にしない
- 1 枚のキャプション失敗で 300 枚分の処理を捨てるのは無駄
- Ingest pipeline は **「失敗フレームは null caption で先に進める」** が原則（architecture.md §6）

### 5.2 プロバイダ依存の機能を素朴に使うと移行できない
- Anthropic の Prompt Caching を Claude 専用 path で使うのは OK
- ただし「OpenAI に切り替えたら速度・コストどうなるか」も評価しておく

### 5.3 NSFW・著作物コンテンツへの応答拒否
- LLM が安全フィルタで応答拒否することがある
- レスポンスに `stop_reason: "refusal"` が来たら、キャプションを `null` にしてスキップ

### 5.4 OCR 精度
- Claude / GPT-4o は OCR もそこそこ得意だが、傾いた文字や小さい字は弱い
- 厳密な OCR が必要なら Tesseract / DocLayout を別途併用

---

## 6. 実装で確認したいこと

- [ ] GPT-4o-mini と Claude Sonnet の caption を 50 枚比較（CLIP Score）
- [ ] Prompt Caching 有無でのコスト差を実測
- [ ] 並列度 1 / 5 / 20 でのスループット測定
- [ ] フレーム解像度 512 / 768 / 1024 で精度差があるか

---

## 7. 参考リンク

- Anthropic Vision: https://docs.anthropic.com/claude/docs/vision
- OpenAI Vision: https://platform.openai.com/docs/guides/vision
- Anthropic Prompt Caching: https://docs.anthropic.com/claude/docs/prompt-caching
- ADR-0003: `../adr/0003-multi-llm-provider.md`

---

## 実践マーカー

- 未実装（Phase 2 で着手予定）
