# LLM プロバイダ抽象化・フォールバック・コスト最適化

> 関連: ADR-0003, `docs/architecture.md` §6, `docs/cost-estimation.md`, Phase 2

## なぜ複数プロバイダ対応するのか

1. **障害耐性**: 1 プロバイダの outage で全機能停止は避けたい
2. **コスト最適化**: モデル別に単価が桁で違う（Sonnet $3/M vs Haiku $0.80/M vs GPT-4o-mini $0.15/M in tokens）
3. **適材適所**: 1M context は Claude のみ、Embedding は OpenAI が安定
4. **ベンダーロックイン回避**

要求スキル「外部API統合」を **複数で経験する** ことが学習目的にも合致する。

---

## 1. 抽象化のレイヤー

```
[Application Code]
        │
        ▼
[LLMProvider Protocol]   ← Protocol で型のみ宣言
        │
   ┌────┴────┐
   ▼         ▼
[Anthropic] [OpenAI]    ← LangChain の ChatXxx を内部で利用
```

```python
from typing import Protocol

class LLMProvider(Protocol):
    async def complete(self, messages: list[Message], **kwargs) -> Completion: ...
    async def caption_image(self, image: bytes, prompt: str) -> str: ...
```

**設計原則**:
- 抽象化は **薄く**。プロバイダ固有機能（Anthropic Prompt Caching 等）を完全に隠蔽しない
- 必要なら `provider.supports("prompt_caching")` のような capability check を入れる
- 全部抽象化しようとすると過剰設計（YAGNI）

---

## 2. 用途別の最適選定（ClipMind）

| 用途 | 主モデル | フォールバック | 理由 |
|---|---|---|---|
| 対話 Agent | Claude Sonnet 4.6 | GPT-4o | 推論力・1M context |
| Fuse 要約 | Claude Haiku 4.5 | GPT-4o-mini | 安価で長文 OK |
| Frame Caption | GPT-4o-mini | Claude Haiku 4.5 | **大量呼び出しで最安** |
| Embedding | text-embedding-3-small | （無し）| 次元固定で切替不能 |
| Eval LLM-judge | GPT-4o | - | バイアス回避 |

ADR-0003 を参照。

---

## 3. リトライ戦略

```python
import tenacity

@tenacity.retry(
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_exponential(multiplier=1, min=2, max=30),
    retry=tenacity.retry_if_exception_type((RateLimitError, APIConnectionError)),
)
async def call_llm(...):
    ...
```

- **指数バックオフ**: 2s → 4s → 8s
- リトライ対象は **ネットワークエラーとレート制限のみ**。`InvalidRequestError` はリトライしても無駄
- 3 回失敗で別プロバイダへフォールバック

---

## 4. フォールバック実装

```python
async def caption_with_fallback(image: bytes) -> Caption:
    for provider in [openai_mini, claude_haiku]:  # 優先順
        try:
            return await provider.caption(image)
        except (RateLimitError, ServiceUnavailableError) as e:
            log.warning("provider %s failed: %s", provider.name, e)
            continue
    raise AllProvidersFailedError(...)
```

**注意**: フォールバック先で `result_quality` を必ずログに残す。
「全部 fallback で動いていた」状態を見落とすと精度評価が歪む。

---

## 5. コスト最適化テクニック

### 5.1 モデル階層化

```
質問の難易度を分類:
  - 単純な事実検索 → Haiku 4.5 ($0.80/M)
  - 標準的な対話   → GPT-4o-mini ($0.15/M)
  - 複雑な推論     → Sonnet 4.6 ($3/M)
```

分類自体に Haiku を使えば、ほぼ無料で振り分けできる。

### 5.2 Anthropic Prompt Caching

```python
{"role": "system", "content": [
    {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}},
    {"type": "text", "text": VIDEO_METADATA, "cache_control": {"type": "ephemeral"}},
]}
```

- 同一 prefix が 5 分以内に再利用されれば **入力トークン 90% 引き**
- 動画 1 本に対する複数フレーム caption / 複数質問で劇的に効く

### 5.3 Embedding キャッシュ

- 同じクエリの embedding を毎回計算しない
- Redis に SHA256(query) → vector で 24h キャッシュ

### 5.4 Rerank の条件付き実行

- Dense top-1 のスコアが閾値を超えていたら、上位がほぼ確定なので rerank をスキップ
- 平均レイテンシが下がる

### 5.5 フレーム選別の強化

- caption コストはフレーム数に線形
- シーンカット閾値を厳しくして 300 → 100 枚に絞れれば 1/3 になる

---

## 6. コスト計測

実装にコスト計測を **最初から入れる**。後付けは難しい。

```python
class CostTracker:
    def record(self, provider: str, model: str, in_tokens: int, out_tokens: int):
        cost = compute_cost(provider, model, in_tokens, out_tokens)
        prometheus_counter.labels(provider, model).inc(cost)
        self._sum += cost
```

- LangChain の callback で全 LLM 呼び出しに自動注入
- Prometheus に push して Grafana で可視化
- 1 動画 Ingest が $0.30 を超えたらアラート

→ 面接で「**運用コストどうなる？**」に**実測値**で答えられるようになる。

---

## 7. ハマりどころ

### 7.1 抽象化の過剰設計
- 全プロバイダの全機能を抽象化しようとすると infra コードが本体より太る
- 「**今使う 2 機能**」だけ抽象化、増えたら追加

### 7.2 Embedding を後で切り替えたくなる
- ADR-0003 で `text-embedding-3-small` 固定だが、将来 `large` に変えたくなる時が来る
- 全 embedding 再計算 + 全動画 re-ingest が必要 → 「再 ingest スクリプト」を最初から用意

### 7.3 レート制限の挙動がプロバイダで違う
- Anthropic: tokens/min と requests/min の 2 軸
- OpenAI: tier 別、tokens/min がメイン
- 両方を意識した backoff が必要

### 7.4 プロンプト互換性
- 同じプロンプトが Claude では動くが GPT では崩れる、を防ぐため
- **両プロバイダで eval を回し、回答品質に大差がないか** を初回で確認

---

## 8. 実装で確認したいこと

- [ ] OpenAI 障害時に Anthropic に自動切替されるか（chaos test）
- [ ] Prompt Caching 有無でのコスト差を実測（90% 引きが本当か）
- [ ] 1 動画 Ingest のコストが $0.10 以下に収まるか
- [ ] モデル階層化で平均コストが何 % 下がるか

---

## 9. 参考リンク

- LangChain ChatModels: https://python.langchain.com/docs/concepts/chat_models/
- Anthropic Pricing: https://www.anthropic.com/pricing
- OpenAI Pricing: https://openai.com/api/pricing/
- Anthropic Prompt Caching: https://docs.anthropic.com/claude/docs/prompt-caching
- ADR-0003: `../adr/0003-multi-llm-provider.md`

---

## 実践マーカー

- 未実装（Phase 2 で着手予定）
