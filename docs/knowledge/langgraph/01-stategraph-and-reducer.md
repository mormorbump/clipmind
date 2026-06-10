# LangGraph: StateGraph・Reducer・Checkpointer

> 関連: ADR-0001, `docs/architecture.md` §3, Phase 1 / Phase 6

## なぜ LangGraph なのか

Ingest パイプラインのような **多段・分岐・部分失敗が前提のワークフロー** を、
asyncio で素朴に書くと以下が辛い。

| 困りごと | 素の asyncio | LangGraph |
|---|---|---|
| 状態遷移の可視化 | print/log を読み解く | グラフ図として可視化可能 |
| 並列ノードの結果合成 | dict をマニュアルでマージ | Reducer で自動マージ |
| 失敗箇所からの再開 | 自作 | `Checkpointer` 標準提供 |
| LLM トレース | 手動 | LangSmith と自動連携 |

LangGraph は単なる asyncio の薄いラッパではなく、**「LLM パイプライン特化の状態機械」** として設計されている点が肝。

---

## 1. StateGraph の三要素

### 1.1 State（型）

`TypedDict` で「全ノードが触るデータ構造」を一箇所に定義する。
ノードは State を受け取り、**部分的な更新（dict）** を返すと、LangGraph が State にマージする。

```python
class IngestState(TypedDict):
    video_id: str
    frames: list[Frame]
    transcripts: list[TranscriptSegment]
```

### 1.2 Node（関数）

`(state) -> dict` の純粋関数として書くのが理想。
副作用（DB 書き込み等）は state の値を読んだ上で外部に出す。

```python
def whisper_transcribe(state: IngestState) -> dict:
    segments = run_whisper(state["audio_path"])
    return {"transcripts": segments}   # State 全体ではなく "更新分" を返す
```

### 1.3 Edge（遷移）

```python
graph.add_edge("a", "b")                       # a 完了後 b へ
graph.add_edge(["a", "b", "c"], "fuse")        # 3 つの完了を待ってから fuse へ（fan-in）
graph.add_conditional_edges("validate", router, {"ok": "download", "skip": END})
```

---

## 2. Reducer — 並列ノードの罠と救済

**罠**: 並列ノード A・B が同じキー `errors` に書き込むと、デフォルトでは後勝ちで上書きされる。
片方の結果が**消える**。

**救済**: `Annotated[T, reducer]` を State に書くと、LangGraph は updates をマージ関数で集約する。

```python
from typing import Annotated
from operator import add

class IngestState(TypedDict):
    frames:      Annotated[list[Frame],    add]   # list 連結
    detections:  Annotated[list[Detection], add]
    errors:      Annotated[list[str],       add]
```

| よく使う Reducer | 効果 |
|---|---|
| `operator.add` | list / 数値の連結・加算 |
| `langgraph.graph.message.add_messages` | LangChain メッセージ用（ID 重複チェック・上書き対応） |
| 自作関数 | dict の deep merge、上限件数で truncate など |

**注意**: Reducer は **「同じ State キーへの複数 update」を統合する関数**。
単一ノードで返した dict そのものをマージするわけではない。

### 2.1 Reducer のシグネチャと呼ばれ方

```python
def reducer(current_value: T, update: T) -> T: ...
```

LangGraph は次のように呼ぶ:
1. State の現在値 = `current`
2. ノードが返した update = `update`
3. 新しい State 値 = `reducer(current, update)`

並列で複数 update が来た場合は順次適用される（順序は実行順依存なので、**可換な reducer** にしておくのが安全）。

### 2.2 自作 Reducer の例

#### dict のディープマージ

```python
def merge_dicts(a: dict, b: dict) -> dict:
    return {**a, **b}

class State(TypedDict):
    metadata: Annotated[dict, merge_dicts]
```

#### 件数 cap（古いものを切り捨てて肥大化を防ぐ）

```python
def append_with_cap(current: list, update: list, max_size: int = 1000) -> list:
    return (current + update)[-max_size:]

class State(TypedDict):
    log_buffer: Annotated[list[str], append_with_cap]
```

#### LangChain メッセージ用 `add_messages`

```python
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage

class ChatState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
```

単純連結ではなく、ID 重複チェック・上書き等の特別ロジック付き。
LangChain ベースの会話エージェントを LangGraph で書くときの定番。

### 2.3 命令型（ロック）vs 関数型（Reducer）

Reducer の思想は「**ロックで守る**」のではなく「**合成関数で衝突を起こさない**」設計に倒すこと。
map-reduce の reduce、Redux の reducer と同じ系譜。

| 命令型（ロック） | 関数型（Reducer） |
|---|---|
| 共有メモリを直接書き換え | 各ノードが「更新分」を返すだけ |
| ロックで排他 | 合成関数でマージ |
| デッドロック・競合のリスク | データロスのリスクのみ（reducer 設計で回避） |

並列ノードが触るキーをそもそも別にしておけば衝突は起きないので、
Reducer は「**衝突する場合の安全網**」として用意する。

### 2.4 Reducer の注意点

- **可換でない reducer は要注意**: `operator.add`（list 連結）は順序依存。並列実行では順序が保証されないので、各要素に `timestamp_ms` を持たせて後段でソートするのが定石（ClipMind もこの方式）
- **重い reducer は性能問題**: 大量データを毎回 deep merge すると O(n²)。「合成は単純な append、後処理で sort/unique」が無難
- **None 初期値**: `Annotated[list, add]` のキーに None が入っていると TypeError。State 初期化時に空 list を入れる
- **Reducer は State キーごとに独立**: 1 つの reducer を全キーに適用する手段はない（しなくていい）

---

## 3. Fan-out / Fan-in パターン

```
extract_frames ──┬─> transcribe       ─┐
                 ├─> detect_objects   ─┼─> fuse
                 └─> caption_frames   ─┘
```

```python
graph.add_edge("extract_frames", "transcribe")
graph.add_edge("extract_frames", "detect_objects")
graph.add_edge("extract_frames", "caption_frames")
graph.add_edge(["transcribe", "detect_objects", "caption_frames"], "fuse")
```

- リスト形式の `add_edge(["a","b","c"], "next")` が fan-in（全ノード完了待ち）
- LangGraph は依存関係から並列度を自動推定して並列実行する
- 各ノードが返す updates は Reducer で安全にマージされる

---

## 4. Checkpointer — 再開の仕組み

```python
from langgraph.checkpoint.sqlite import SqliteSaver
graph = graph.compile(checkpointer=SqliteSaver.from_conn_string("checkpoints.db"))
```

- `thread_id` ごとに State のスナップショットが SQLite に保存される
- Whisper のような重いノードが落ちても、**直前の checkpoint から再開可能**
- 1 動画 = 1 thread_id の運用が分かりやすい
- Production では PostgresSaver / RedisSaver も選べる

**運用の勘所**:
- 各ノードの境界が checkpoint 単位になるので、ノードを大きくしすぎると無駄なリトライが増える
- 逆に細かすぎると I/O が増える。「数分かかる重い処理」を 1 ノードにするのが目安

---

## 5. ハマりどころ

### 5.1 Reducer 忘れによる結果消失
- 並列ノードが同じキーに書く設計を見たら、まず Reducer の有無を疑う
- 単体テストでは並列実行の race が再現しないので、本番動作で初めて気づくことがある
- **デバッグ順**: (1) State キーに `Annotated[..., reducer]` が付いているか / (2) ノードが返す dict のキー名が State と一致しているか / (3) reducer の型が update の型と一致しているか
- LangSmith のトレースで「各ノードの入力 State / 出力 update / マージ後 State」を確認できる

### 5.2 State に重いオブジェクトを入れない
- 動画のバイナリ・大量のフレーム画像を State 直下に置くと、checkpoint が肥大化
- **Object Store の path だけ State に持つ**（実体は外）

### 5.3 ノード関数を非純粋にしすぎない
- 外部 API 呼び出しが伴うのは仕方ないが、グローバル変数や module level state を触るのは避ける
- 並列実行時に競合する

### 5.4 LangGraph のバージョン pin
- `langgraph >= 0.2, < 0.3` などレンジで pin（ADR-0001）
- マイナーバージョンで API が変わる時期があった

---

## 6. 実装で確認したいこと（Phase 1 / 6）

- [ ] fan-out で 3 ノード並列実行されているか LangSmith で確認
- [ ] Reducer 無しで実装してみて、結果が消える挙動を再現
- [ ] Whisper を意図的に落としてから checkpoint 再開
- [ ] 並列実行の速度向上を測定（直列の何倍か）

実装中に得られた具体数値・気づきは、この章末に追記していく。

---

## 7. 参考リンク

- 公式: https://langchain-ai.github.io/langgraph/
- StateGraph 概念: https://langchain-ai.github.io/langgraph/concepts/low_level/
- Checkpointer: https://langchain-ai.github.io/langgraph/concepts/persistence/
- ADR-0001（採用理由）: `../adr/0001-use-langgraph-from-start.md`

---

## 実践マーカー

- ✅ Phase 1 で実践
  - **State**: `IngestState`（TypedDict + Annotated[list, add] reducer）を `src/clipmind/graph/state.py` に定義
  - **ノード**: validate / extract_frames / extract_audio / transcribe / store の 5 つ
  - **直列パス**: Phase 1 では並列ノード無し（YAGNI、Phase 2 で YOLO/Caption が並列追加されると Reducer が活きる）
  - **Checkpointer**: `AsyncSqliteSaver.from_conn_string(.data/checkpoints/ingest.db)` を `async with` 内で構築 → `compile(checkpointer=...)`
- **罠 1 — LangGraph 1.x の型ナローイング不全**: `StateGraph[IngestState, ...].add_node(name, fn)` が `_Node[Never]` を期待してしまい、mypy strict で `Callable[[IngestState], Awaitable[IngestState]]` が通らない。`# type: ignore[arg-type]` で凌いだ。
  プレーンな関数（型注釈ありの validate 等）は通るが、明示的に型付けしたファクトリ関数の戻り値は落ちる。
- **罠 2 — `ainvoke(initial_state, config={...})` の overload 不一致**: LangGraph 1.2 の `Pregel.ainvoke` は overload が複雑で `config=dict` のキーワード推論が効きづらい。`# type: ignore[call-overload]` で凌いだ。
- **罠 3 — TypedDict + Annotated[list, add] 初期化**: 空 list を `[]` で渡すと `list[Never]` 推論で TypedDict 構築時に型エラー。`cast("list[Frame]", [])` 等で明示。
- 学び: **LangGraph の型サポートはまだ発展途上**。strict mypy では `# type: ignore` を一定許容するか、内部で `Any` を経由するヘルパで吸収する戦略が必要。

### ✅ Checkpointer resume 実証 (Phase 2 着手時)

`.context/experiment_checkpoint_resume.py` で実証した流れ:

```
1 回目: extract (成功・checkpoint) → transcribe (故意に raise) → graph 失敗
        state.next == ('transcribe',)   ← 再開地点が記録されている
2 回目: graph.ainvoke(None, config)     ← input=None + 同じ thread_id で resume
        → extract は再実行されず、transcribe からだけ続行して完走
```

ポイント:
- **resume は `ainvoke(None, config)`**。初期 State を渡し直すと「新しい実行」になってしまう
- `graph.aget_state(config)` で「どこまで進んだか (`state.next`)」と「checkpoint 済みの値」を確認できる
- checkpoint の単位はノード境界。だから extract_audio / transcribe を分割した（Whisper だけ落ちたとき音声抽出をやり直さない）

### ✅ fan-out / fan-in と Reducer の実働 (Phase 2)

Phase 2 で extract_frames の後段を 3 並列に拡張:

```
extract_frames ─┬→ extract_audio → transcribe ─┐
                ├→ detect_objects ─────────────┼→ store (fan-in)
                └→ caption_frames ─────────────┘
```

- fan-in は `graph.add_edge(["transcribe", "detect_objects", "caption_frames"], "store")` — リストを渡すと全ノード完了待ち
- 並列 3 経路がそれぞれ `errors` キーに書き込むため、`Annotated[list[str], add]` の Reducer がないと `InvalidUpdateError` になる — Phase 1 で「YAGNI すれすれ」と書いた前方互換がここで効いた
