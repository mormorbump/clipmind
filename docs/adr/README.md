# Architecture Decision Records (ADR)

> 大きめの意思決定は全てここに残す。書式は Michael Nygard の古典 ADR 形式に従う。

## 索引

| # | タイトル | ステータス |
|---|---|---|
| 0001 | [LangGraph を Phase 1 着手時から採用する](0001-use-langgraph-from-start.md) | Accepted |
| 0002 | [Vector DB は Qdrant に単一化する](0002-vector-db-qdrant-single.md) | Accepted |
| 0003 | [マルチLLMプロバイダ対応（Anthropic + OpenAI）](0003-multi-llm-provider.md) | Accepted |
| 0004 | [LangChain vs LlamaIndex の使い分け](0004-langchain-vs-llamaindex.md) | Proposed |
| 0005 | [YouTube ダウンロードをサポートしない](0005-youtube-tos-policy.md) | Accepted |
| 0006 | [評価戦略: Ragas + 自作データセット](0006-evaluation-strategy.md) | Accepted |
| 0007 | [Python 3.11 + uv + ruff/mypy/pytest をツールチェーン標準](0007-toolchain.md) | Accepted |
| 0008 | [ORM は SQLModel + SQLAlchemy 2.x async](0008-orm-sqlmodel.md) | Accepted |
| 0009 | [ObjectStore Protocol で動画/フレーム保存を抽象化](0009-object-store-protocol.md) | Accepted |

## 書き方

各 ADR は以下の構成を守る:

```
# ADR NNNN: タイトル

## ステータス
Proposed / Accepted / Deprecated / Superseded by ADR-XXXX

## コンテキスト
なぜこの意思決定が必要なのか、現状と制約

## 検討した選択肢
A, B, C とそれぞれの Pros/Cons

## 決定
選んだ選択肢と、その理由

## 影響・トレードオフ
この決定で諦めたもの、将来の再検討トリガー
```
