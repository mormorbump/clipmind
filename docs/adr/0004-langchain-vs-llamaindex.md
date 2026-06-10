# ADR 0004: LangChain vs LlamaIndex の使い分け

## ステータス
Accepted — 2026-06-10（LlamaIndex 比較実装は scope out、根拠は改訂履歴参照）

## コンテキスト

要求スキルに「LangChain、LlamaIndex 等ライブラリを用いたエージェント開発経験」とあり、
両方に触れて差を語れる状態にしたい。ただし個人プロジェクトでスコープが肥大化するのは避けたい。

現状、両ライブラリの得意分野はおおまかに:

| 領域 | LangChain | LlamaIndex |
|---|---|---|
| Agent (Tool-calling) | ◎ エコシステム成熟 | ○ 後発、機能は揃っている |
| Retriever / Index | ○ 基本機能 | ◎ 多彩（KG index, tree, etc）|
| Orchestration | ◎ LangGraph | △ Workflow はあるが新しい |
| プロンプト管理 | LangSmith | - |
| ドキュメント | 豊富 | 豊富 |

## 検討した選択肢

### A. LangChain のみ
- Pros: 習得コスト集中、本プロジェクトでの一貫性
- Cons: 要求スキル「LlamaIndex」が未カバー

### B. LlamaIndex のみ
- Pros: RAG は得意
- Cons: LangGraph が使えない、要求スキル「LangGraph」が弱くなる

### C. LangChain をメインにし、Retriever 1 つだけ LlamaIndex で実装して比較
- Pros: 両方触れつつ、スコープ爆発を避けられる
- Cons: 少量だと「触っただけ」と見られるリスク

## 決定（暫定）

**C を採用**。

具体的には:
- **Agent / Orchestration: LangChain + LangGraph**
- **RAG Retriever の比較実装: LlamaIndex**
  - 既存の Dense 検索を LlamaIndex の `VectorStoreIndex` + `QdrantVectorStore` で再実装
  - 両 Retriever を同じ評価セットで測り、Recall@5 / MRR / レイテンシを比較

面接で語れる形（想定）:
> 「LangChain の Retriever は素朴な抽象だが、LlamaIndex は QueryEngine の階層が深く、
> Hybrid / Sub-question 等のパターンが組み込みで用意されている。ただし Qdrant のような
> 外部ベクトル DB を使うと、LangChain の VectorStore 抽象の方が操作が直接的で、
> 本プロジェクトでは LangChain 側を主軸にした」

## 影響・トレードオフ

- Phase 7（1日）のみに限定。工数圧迫したら scope out も可
- scope out した場合でも、本 ADR に「検討したが見送った根拠」を残せば、
  面接で「なぜ LlamaIndex を使わなかった？」に答えられる

## 再検討トリガー

- LlamaIndex 側で本プロジェクトに有用な新機能（動画特化 Reader 等）が出た場合
- RAG 精度が行き詰まり、別アーキテクチャが必要になった場合

## 改訂履歴

- **2026-06-10**: Accepted に確定。Phase 3〜5 の実装結果を踏まえ、**LlamaIndex の比較実装は見送り**:
  1. Phase 3 で Qdrant の Query API (prefetch + RRF fusion) を**直接**使う構成になった。
     ハイブリッド検索・フィルタ・named vectors はクライアント直叩きが最も表現力が高く、
     LlamaIndex の `VectorStoreIndex` を挟むと Query API の RRF fusion が抽象に隠れて逆に書きづらい
  2. Agent は LangChain 1.x `create_agent`（LangGraph ベース）で実装済み。Orchestration も LangGraph。
     ここに LlamaIndex を足すと依存とメンテ面の複雑さだけ増える
  3. 評価基盤 (Phase 4) は SegmentIndex 抽象に対して動くので、
     将来 LlamaIndex Retriever を足した場合も同じハーネスで比較可能（再開コストは低い）

  面接想定回答: 「LlamaIndex は QueryEngine の階層が深く RAG パターンが組み込みで豊富だが、
  本プロジェクトは Qdrant の Query API（RRF fusion・named vectors）を直接使う構成にしたため、
  中間抽象を挟む利点よりも表現力の損失が大きかった。評価ハーネスは Retriever 抽象に対して
  作ってあるので、必要になれば LlamaIndex 実装を 0.5 日で追加比較できる」
