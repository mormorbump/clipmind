# 観測性: LangSmith / OpenTelemetry / Prometheus

> 関連: `docs/architecture.md` §7, Phase 8

## 「動いた」と「観測できる」は違う

LLM アプリは **非決定的 + 多段 + 外部依存** の三重苦で、
print デバッグでは何も分からない状況に容易に陥る。

3 種類の観測対象を、それぞれ最適なツールで:

| 対象 | ツール | 何が見えるか |
|---|---|---|
| LLM / Agent / Chain 呼び出し | **LangSmith** | プロンプト・トークン・コスト・トレース |
| HTTP リクエスト・DB クエリ | **OpenTelemetry** | スパン・依存関係・レイテンシ |
| アプリメトリクス | **Prometheus** | カウンタ・ヒストグラム・ゲージ |

3 つは補完関係。1 つで全部見えるツールは（2026 年時点）まだない。

---

## 1. LangSmith — LLM 呼び出しの透視鏡

### 1.1 何が見えるか
- Agent の **思考連鎖**（LLM が何回 Tool を呼んだか）
- 各 LLM 呼び出しの **入出力 / トークン / コスト**
- 失敗ステップ（タイムアウト、stop_reason: refusal 等）
- バージョン違いの A/B 比較

### 1.2 セットアップ
環境変数 3 つで OK:

```bash
LANGSMITH_API_KEY=ls_...
LANGSMITH_TRACING=true
LANGSMITH_PROJECT=clipmind
```

LangChain / LangGraph は自動的にトレースを送信する（`@traceable` デコレータで pure 関数も対象化可）。

### 1.3 評価との連携
- LangSmith に「データセット」を登録 → CI から評価実行
- `docs/evaluation.md` の Eval バッチ結果を LangSmith に push できる

### 1.4 注意点
- SaaS のため **プロンプトに機密情報が乗ると外部送信される**
- 本番運用ではセルフホスト版（OSS）の検討も
- 開発フェーズでは Free tier で十分

---

## 2. OpenTelemetry — アプリ全体のトレース

### 2.1 役割分担
- LangSmith: LLM 周辺
- **OTel: HTTP, DB, Redis, Qdrant 等の「LLM 外」**

両者を `trace_id` で紐づければ、「ユーザーリクエスト → LLM 呼び出し」が一気通貫で見える。

### 2.2 セットアップ
```python
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor

FastAPIInstrumentor.instrument_app(app)
HTTPXClientInstrumentor().instrument()
RedisInstrumentor().instrument()
```

### 2.3 エクスポート先
- 開発: コンソール出力 or Jaeger（Docker で起動）
- 本番: Tempo / Honeycomb / DataDog 等

### 2.4 ClipMind での扱い
- Phase 8（運用）で導入
- 初期は LangSmith だけで十分なケースも多い（早期撤退ポイント、milestones.md §早期撤退）

---

## 3. Prometheus — アプリメトリクス

### 3.1 主要メトリクス（ClipMind）

```python
ingest_duration_seconds        # Histogram, label: stage
llm_tokens_total               # Counter, label: provider, model, type
llm_cost_usd_total             # Counter, label: provider, model
rag_recall_at_5                # Gauge, 評価バッチが定期 push
http_request_duration_seconds  # Histogram, label: route
```

### 3.2 セットアップ
```python
from prometheus_client import Counter, Histogram, generate_latest

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type="text/plain")
```

### 3.3 アラート例（本番運用）
- `rate(http_request_duration_seconds{route="/query", quantile="0.95"}[5m]) > 3`
- `rate(llm_cost_usd_total[1h]) > 1.0` （1 時間で $1 を超えたら通知）
- `rag_recall_at_5 < 0.6`

### 3.4 可視化
- Grafana で dashboard を作る
- `dashboard.json` を git 管理（再現性確保）

---

## 4. 3 つを束ねる `trace_id`

```
Client ──HTTP──> FastAPI
                   │ trace_id 生成 (OTel)
                   │
                   ▼
                Agent (LangChain)
                   │ trace_id を LangSmith にも propagate
                   │
                   ▼
                LLM API
                   │
                   ▼
                response { ..., "trace_id": "ls-trace-xxx" }
```

API レスポンスに **trace_id を含めて返す** のがコツ。
ユーザー報告の「変な回答」を即座にトレースできる。

---

## 5. ロギング基本

- 構造化ログ（JSON）を **最初から**。後で grep するときに天国と地獄
- `structlog` or `python-json-logger`
- フィールド: `timestamp, level, trace_id, video_id, stage, message, duration_ms`

```python
log.info("ingest_stage_complete", video_id=vid, stage="transcribe", duration_ms=4200)
```

---

## 6. ハマりどころ

### 6.1 LangSmith に PII が漏れる
- ユーザー入力をそのまま送ると個人情報が SaaS に乗る
- 必要なら **入出力をマスク** する callback を入れる

### 6.2 OTel の overhead
- 全 span を export すると本番でレイテンシが増える
- サンプリング（例: 10%）を設定

### 6.3 Prometheus の cardinality 爆発
- ラベルに `user_id` のような無限の値を入れると metric が肥大化
- ラベルは「**有限の集合**」（model 名、stage 名など）に限る

### 6.4 メトリクス・トレース・ログがバラバラ
- `trace_id` を全箇所で透過させるのが鍵
- contextvar / OTel の context propagation に乗せる

---

## 7. 実装で確認したいこと

- [ ] LangSmith で 1 質問のトレースが見える
- [ ] LangSmith の trace_id が API レスポンスに含まれる
- [ ] Prometheus `/metrics` が公開されている
- [ ] Grafana dashboard で ingest_duration がステージ別に見える
- [ ] エラー発生時に trace_id 1 つで全層を追える

---

## 8. 参考リンク

- LangSmith: https://docs.smith.langchain.com/
- OpenTelemetry Python: https://opentelemetry.io/docs/languages/python/
- Prometheus Python client: https://github.com/prometheus/client_python
- structlog: https://www.structlog.org/

---

## 実践マーカー

- 未実装（Phase 8 で着手予定）
