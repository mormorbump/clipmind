# ADR 0003: マルチ LLM プロバイダ対応（Anthropic + OpenAI）

## ステータス
Accepted — 2026-04-25

## コンテキスト

LLM 呼び出しを単一プロバイダに固定すると以下の問題がある:
- 障害・レート制限時に処理が止まる
- モデル別の得意分野を使い分けられない
- ベンダーロックイン

特にフレームキャプションは **300 枚 × 1 時間動画** の大量呼び出しになるため、
コスト面で**単価の安いモデル**（GPT-4o-mini, Claude Haiku）の選択肢が必要。

要求スキルにある「外部API統合」を証明する上でも、複数プロバイダ対応は価値が高い。

## 検討した選択肢

### A. Anthropic のみ
- Pros: 1M context の Sonnet が動画全体要約に使える、Vision 品質が高い
- Cons: コスト高、障害時のフォールバック無し

### B. OpenAI のみ
- Pros: GPT-4o-mini が圧倒的に安い、エコシステムが広い
- Cons: Claude 独自の機能（prompt caching の柔軟性、1M context）が使えない

### C. 両対応 + フォールバック
- Pros: コストとクオリティを目的別に使い分けられる、片方の障害に耐える
- Cons: 抽象化コスト、プロンプト互換性の維持

### D. LiteLLM / LangChain の `ChatAnthropic` / `ChatOpenAI` を直接使う
- Pros: 抽象化を自作しなくて済む
- Cons: LiteLLM はもう一層依存が増える。LangChain は Agent で使うのでプロジェクト方針と整合

## 決定

**C + D**: プロジェクト内部では `LLMProvider` Protocol を薄く定義し、
実装は LangChain の `ChatAnthropic` / `ChatOpenAI` を使う。

### 使い分け戦略

| 用途 | 主 | フォールバック |
|---|---|---|
| 対話Agent（高品質必要） | Claude Sonnet 4.6 | GPT-4o |
| fuse要約（長文） | Claude Haiku 4.5 | GPT-4o-mini |
| フレームキャプション（大量） | GPT-4o-mini | Claude Haiku 4.5 |
| Embedding | OpenAI text-embedding-3-small | (無し — 他の埋め込みモデルはスキーマ互換性なし) |

### プロバイダ障害時
1. 3 回までリトライ（指数バックオフ）
2. それでも失敗なら別プロバイダへ自動切替
3. 両方失敗ならジョブを failed にし、再実行キューへ

## 影響・トレードオフ

- プロンプトは両方で動くように、プロバイダ固有機能（Anthropic の system caching 等）の利用を制限
  - ただし Anthropic の Prompt Caching は**コスト削減効果が大**なので、重要な用途では Anthropic 固定で使う
- 統合テストで両プロバイダ叩くと CI コストが増える → 本番APIを叩くテストは別ワークフローに分離

## Embedding モデル

Embedding はプロバイダ切替が難しい（ベクトル次元・空間が異なる）ため、
**text-embedding-3-small に固定**。将来切替時は全 embedding の再計算が必要になる点を
リスクとして明記。
