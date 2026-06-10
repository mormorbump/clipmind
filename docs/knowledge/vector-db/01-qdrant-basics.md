# Vector DB: Qdrant の基本と運用

> 関連: ADR-0002, `docs/architecture.md` §5, Phase 3

## ベクトル DB は何のためにある？

「Embedding 同士のコサイン類似度を高速に求めたい」のが本質。
NumPy で総当たり（ANN: 近似最近傍探索）すれば動くが、

- 数百万件の embedding になると 1 検索が秒級になる
- 永続化・スレッドセーフ・並行更新を全部自作するのは現実的でない

これを **HNSW などの ANN インデックス + ストレージ + サーバ** としてパッケージ化したのが Vector DB。

---

## 1. なぜ Qdrant か（要約）

詳細は ADR-0002。要点だけ:

| 候補 | 採否 | 理由 |
|---|---|---|
| Pinecone | 不採用 | SaaS のみ、ローカル検証できない |
| Chroma | 不採用 | sparse vector 非対応、本番運用に弱い |
| Qdrant | **採用** | OSS / Rust / Sparse + Dense / Docker で起動 |
| pgvector | 不採用 | sparse 非対応、ハイブリッド構築が煩雑 |
| Milvus | 不採用 | クラスタ構成が重い、個人プロジェクトには過剰 |

**Qdrant を選ぶと、開発も本番も同じ Docker で動く** のが最大の利点。

---

## 2. データモデルの基礎

### 2.1 Collection

```python
client.create_collection(
    collection_name="clipmind_segments",
    vectors_config={"dense": VectorParams(size=1536, distance=Distance.COSINE)},
    sparse_vectors_config={"bm25": SparseVectorParams()},
)
```

- 1 collection に複数の名前付きベクトル（dense / bm25 / image_embed 等）を持てる
- 異なる用途を **別 collection に分けるか / 同じに入れるか** は設計判断
  - ClipMind では「全動画の全 segment」を 1 collection に集約

### 2.2 Point（レコード）

```python
PointStruct(
    id=segment_id,
    vector={"dense": [0.1, ...], "bm25": SparseVector(...)},
    payload={
        "video_id": "vid_abc",
        "start_ms": 120000,
        "end_ms": 125000,
        "transcript": "...",
        "objects": ["person", "laptop"],
    },
)
```

- `payload` は JSON で何でも入る → メタデータを丸ごと持たせると便利
- ただし「巨大バイナリ」はオブジェクトストレージに置き、Qdrant には URL だけ

### 2.3 Payload Index

`video_id` でフィルタ検索する場合、payload index を張ると劇的に速くなる:

```python
client.create_payload_index(
    collection_name="clipmind_segments",
    field_name="video_id",
    field_schema=PayloadSchemaType.KEYWORD,
)
```

---

## 3. ハイブリッド検索 in Qdrant

```python
client.query_points(
    collection_name="clipmind_segments",
    prefetch=[
        Prefetch(query=dense_vec,  using="dense", limit=20),
        Prefetch(query=sparse_vec, using="bm25",  limit=20),
    ],
    query=FusionQuery(fusion=Fusion.RRF),
    limit=10,
)
```

- `prefetch` で複数戦略の候補を先取り
- `FusionQuery` でランクを統合（RRF）
- アプリ側で 2 回検索して merge する手作業が不要

---

## 4. Sparse Vector（BM25）の作り方

Qdrant は **TF/IDF の値を含んだ sparse vector** をそのまま受け取る。
事前にトークナイズ＋スコア計算するのはアプリ側の役目。

選択肢:
- `qdrant_client.fastembed` — Qdrant 公式の軽量 BM25/TF-IDF
- `sentence-transformers` の `SparseEncoder`
- 自作（pure Python の BM25）

ClipMind は最初は `fastembed` を採用、評価で精度が足りなければ差し替える方針。

---

## 5. 運用 Tips

### 5.1 起動とヘルスチェック

```yaml
# docker-compose.yml
qdrant:
  image: qdrant/qdrant:latest
  ports: ["6333:6333"]
  volumes:
    - ./qdrant_storage:/qdrant/storage
```

ヘルスチェック: `GET http://localhost:6333/healthz`

### 5.2 スナップショットでバックアップ

- Web UI（`http://localhost:6333/dashboard`）からスナップショット作成
- API: `POST /collections/{name}/snapshots`
- リストア時は別 collection 名で展開してから rename が安全

### 5.3 大量 upsert の速度

- バッチ単位で 100〜500 件ずつ upsert する
- `wait=False` で fire-and-forget にすると速い（耐久性は若干落ちる）

### 5.4 距離関数の選択

| 用途 | 推奨 |
|---|---|
| 文章 embedding（OpenAI / Cohere） | Cosine |
| 画像 embedding（CLIP 等） | Cosine |
| 数値特徴量 | Euclidean |

OpenAI `text-embedding-3-small` は L2 正規化済みなので、Cosine == Dot product で同じ結果になる。

---

## 6. ハマりどころ

### 6.1 Vector の次元不一致
- Collection 作成時の `size` と upsert 時の vector 長が違うとエラー
- Embedding モデルを変えるなら collection ごと作り直し

### 6.2 Payload index を貼り忘れ
- 数十万件で `video_id` フィルタが激遅になり気付く
- 設計時に「フィルタする全フィールド」を index 候補にしておく

### 6.3 Disk vs In-memory
- Qdrant はデフォルトで disk-backed。RAM-only にすると速いが永続性なし
- 開発では disk のままで十分

### 6.4 Snapshot の volume 場所
- Docker 内の `/qdrant/storage` を host にマウントしないとデータが揮発

---

## 7. 実装で確認したいこと

- [ ] 1 動画 30 segments を upsert → query で取れる
- [ ] payload filter `video_id == "..."` の前後で検索速度比較
- [ ] sparse + dense ハイブリッドの結果が dense 単独と異なることを確認
- [ ] スナップショットで restore できる

---

## 8. 参考リンク

- Qdrant 公式: https://qdrant.tech/documentation/
- Hybrid Search: https://qdrant.tech/documentation/concepts/hybrid-queries/
- Sparse Vectors: https://qdrant.tech/articles/sparse-vectors/
- ADR-0002: `../adr/0002-vector-db-qdrant-single.md`

---

## 実践マーカー

- ✅ Phase 3 で実践 (`src/clipmind/rag/indexer.py`)
  - **named vectors**: 1 コレクションに dense ("dense") + sparse ("bm25") を同居
  - **sparse は IDF modifier 必須**: `SparseVectorParams(modifier=Modifier.IDF)` を忘れると BM25 スコアが正しく計算されない
  - **コレクション名にモデルタグ**: `segments__fastembed_bge_small_en_v1_5` のように embedding モデルを刻み、ベクトル空間の混在を構造的に防止 (ADR-0010)
  - **決定的 point ID**: `uuid5(namespace, f"{video_id}:{start_ms}")` で再 Ingest 時に同じ窓を上書き。重複が増えない
  - **Query API**: `query_points(prefetch=[dense, sparse], query=FusionQuery(RRF))` でハイブリッド検索をサーバー側 1 リクエストで完結
  - **payload フィルタ**: `FieldCondition(key="video_id", match=...)` を prefetch 両方に適用（fusion 後のフィルタでは prefetch 件数が無駄になる）
- 罠: `AsyncQdrantClient` を閉じ忘れるとテストで event loop 警告。テストでは finally で `close()`
