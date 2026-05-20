# ClipMind

> 動画コンテンツを対話型で検索・質問できるマルチエージェントRAGシステム

動画（ローカルファイル / Creative Commons動画 / YouTube URLオプション対応）を投入すると、
OpenCV によるフレーム抽出、YOLO による物体検知、Whisper による音声書き起こし、
マルチモーダルLLMによるシーン理解を経てベクトルDBに保存し、
「動画の05:23で何が起きた？」「この動画で人物Aが登場した全シーンは？」のように
自然言語で検索・質問できる。

---

## これは何？（学習プロジェクト）

以下の要求スキルを **一つの統合アプリで** カバーすることを目的に設計された個人ポートフォリオ。

### カバーするスキル

**必須**
- LLMアプリケーション実装
- LangChain によるエージェント開発（+ LlamaIndex との比較検証あり）
- FastAPI ベースの API 設計、外部API 統合（Anthropic / OpenAI / YouTube Data API v3）

**歓迎**
- 映像解析: OpenCV によるシーンカット検出、YOLOv8 による物体検知
- マルチモーダルAI: Claude Vision / GPT-4o によるフレームキャプショニング
- ベクトルDB: Qdrant を用いたハイブリッド検索RAG（BM25 + Dense）
- LangGraph: 並列ノード + 状態マージによるマルチエージェント・オーケストレーション

詳細な実装箇所とのマッピング: [docs/skills-mapping.md](docs/skills-mapping.md)

---

## ドキュメント索引

| ドキュメント | 内容 |
|---|---|
| [docs/architecture.md](docs/architecture.md) | システム構成、LangGraphノード設計、データフロー |
| [docs/requirements.md](docs/requirements.md) | 機能要件・非機能要件 |
| [docs/api-spec.md](docs/api-spec.md) | REST / WebSocket API仕様 |
| [docs/skills-mapping.md](docs/skills-mapping.md) | 要求スキル → 実装箇所の対応表 |
| [docs/evaluation.md](docs/evaluation.md) | RAG評価戦略（Recall@k, Ragas, LLM-as-judge） |
| [docs/quality-assurance.md](docs/quality-assurance.md) | テスト方針、CI/CD、lint/型チェック |
| [docs/cost-estimation.md](docs/cost-estimation.md) | 1時間動画あたりのAPI/計算コスト試算 |
| [docs/milestones.md](docs/milestones.md) | 実装ロードマップ（現実的な工数見積） |
| [docs/learning-log.md](docs/learning-log.md) | 実装中の学びログ（面接用エピソード化） |
| [docs/adr/](docs/adr/) | アーキテクチャ意思決定記録 |
| [docs/knowledge/](docs/knowledge/) | トピック別の概念ノート（学習用） |

---

## ステータス

**現在: 設計フェーズ**

実装は [docs/milestones.md](docs/milestones.md) の Phase 順に進める。

---

## ライセンス / 法的注意

- 本リポジトリのコードは MIT を想定
- **YouTube 動画のダウンロード機能は既定で無効**。YouTube利用規約上、明示的にダウンロードは禁止されているため、本プロジェクトでは「メタデータ取得（YouTube Data API v3 経由）」のみを合法的に利用する
- 動画投入は (a) ローカルファイル、(b) Creative Commons / Public Domain 動画、(c) 自身が権利保有する動画 を前提
- 詳細は [docs/adr/0005-youtube-tos-policy.md](docs/adr/0005-youtube-tos-policy.md)
