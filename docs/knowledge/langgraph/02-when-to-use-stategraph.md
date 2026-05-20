# StateGraph をいつ使うか — Agent Loop との使い分け

> 関連: `01-stategraph-and-reducer.md`, ADR-0001, `docs/architecture.md` §3 / §4
> 関連 Phase: 1, 5, 6

## 結論（先に）

| 入力の構造 | 手順 | 推奨 |
|---|---|---|
| **事前に決まっている**（動画 → 既知の成果物） | 定型 | **StateGraph（LangGraph）** |
| **入力次第で変わる**（ユーザーの自由質問） | LLM が動的に判断 | **Agent Loop（LangChain）** |

「**LLM の判断**で動かす」と「**宣言したグラフ**で動かす」の使い分けが本質。

---

## 1. Agent Loop の限界

```python
# シンプルな Agent Loop
while True:
    response = llm.invoke(messages)
    if response.tool_calls:
        results = run_tools(response.tool_calls)
        messages += [response, *results]
    else:
        return response.content
```

これは **「次に何するか」を毎ターン LLM に判断させる** モデル。
利点は柔軟性。欠点は:

- **不確実性**: LLM が想定外の Tool を選ぶ / Tool 呼び忘れる
- **コスト**: 判断のたびに LLM 呼び出しが入る
- **並列化が困難**: 並列で 3 タスク同時実行を LLM に毎回正しく指示するのは至難
- **再現性**: 同じ入力でも実行パスがブレる
- **再開困難**: ループ途中の状態を取り出すのが煩雑

**入力に対する処理手順が事前に決まっているなら、LLM に毎回考えさせるのは無駄**。

---

## 2. StateGraph が刺さる条件

入力の構造と手順があらかじめ把握できているとき、以下を満たすなら StateGraph 一択:

### (a) 入力 → 成果物の写像が決まっている
ClipMind Ingest:
```
input:  動画（mp4 等）
output: { frames, transcripts, detections, captions, timeline, embeddings }
```
**毎回同じ構造の成果物**が必要。LLM に「次何する？」を聞く必要がない。

### (b) State として「何を作っていくか」を宣言できる
```python
class IngestState(TypedDict):
    frames:       Annotated[list[Frame], add]
    transcripts:  Annotated[list[TranscriptSegment], add]
    detections:   Annotated[list[Detection], add]
    captions:     Annotated[list[Caption], add]
```

- 各キーが「埋めるべきスロット」
- どのノードがどのスロットを埋めるかも事前に決まっている
- 並列で別キーに書く設計 → 衝突しない（→ Reducer で安全合成）

### (c) 並列化のメリットが大きい
- transcribe / detect_objects / caption_frames は依存しないので並列可能
- 直列なら 10 分、並列なら 4 分といった効果
- LLM 判断ループでこれを正しく並列化させるのは事実上不可能

### (d) 再開可能性が必要
- 1 時間動画の Ingest が Whisper で落ちる → fuse 以降だけやり直したい
- Checkpointer を入れれば自動でこれが実現される

### (e) コストと信頼性が読める
- 各ノードで使う LLM・モデル・コストを設計時に決定できる
- 「LLM の気分次第で Sonnet が呼ばれてコストが跳ねる」が起きない

---

## 3. Agent Loop が刺さる条件

逆に、**入力次第で必要な処理が変わる**場合は Agent Loop が向く:

### ClipMind Query Agent の例

ユーザーの自由質問:
- 「人物Aが登場するシーン」 → `filter_by_object("person")` + 時刻ソート
- 「結論は？」 → `hybrid_search("結論")` + 末尾セグメント取得 + 要約
- 「05:23 で何が起きた？」 → `filter_by_time(...)` + `get_frame_image(...)`

**質問 → 必要な Tool 列の写像が事前に列挙できない**。
これを LLM の判断に任せるのが Agent Loop の強み。

| 観点 | StateGraph | Agent Loop |
|---|---|---|
| 入力構造 | 事前に決まる | ユーザー入力次第 |
| 手順 | 定型 | 動的 |
| 並列 | 設計時に決定 | LLM が判断（弱い） |
| 再開 | Checkpointer で容易 | 状態を取り出しにくい |
| コスト | 予測可能 | 質問依存でブレる |
| 柔軟性 | 低い | 高い |

---

## 4. ClipMind がこの使い分けを採用している

`docs/architecture.md` §3 と §4 を並べて読むと意図が見える:

| コンポーネント | 実装 | 理由 |
|---|---|---|
| **Ingest パイプライン**（§3） | LangGraph StateGraph | 入力構造が決まる・並列化したい・再開したい |
| **Query Agent**（§4） | LangChain `create_tool_calling_agent` | 質問次第で Tool 選択が変わる |

これは「**LangGraph があるから何でも StateGraph で書く**」ではなく、
**「決定的ワークフロー = StateGraph、動的判断 = Agent Loop」を意図的に分けた設計**。

---

## 5. 判断フローチャート

```
新しい機能を作るとき:

  入力 → 出力の写像は事前に決まっているか？
         │
    ┌────┴────┐
   YES        NO
    │          │
    ▼          ▼
  並列・再開・分岐の必要は？   LLM の動的判断が必要
    │                          → Agent Loop
   ┌┴┐
  YES NO
   │  │
   ▼  ▼
 StateGraph  単純な関数・パイプラインで十分
            （asyncio.gather でも書ける）
```

「LangGraph か Agent Loop か」の前に、**「そもそもライブラリが必要か？」** を問うのも忘れない。

---

## 5.5 Human-in-the-loop の 2 種類 — 対話型 vs 承認フロー型

「対話があれば全部 StateGraph」は誤解。Human-in-the-loop には 2 種類あって、**StateGraph が必須なのは後者だけ**:

### (A) 対話型 HITL — Claude Code / ChatGPT / ClipMind Query Agent

```
LLM 応答 → 完全に return → ユーザーが次のメッセージ入力 → 次のターン開始
```

- ターン境界が自然なブロッキングポイント
- 各ターンで `messages` 配列を保つだけで履歴が成立
- **Agent Loop で十分**。StateGraph 不要

### (B) 承認フロー型 HITL — 金融取引承認 / 医療レコメンド承認

```
LLM が tool_call 予定 → 実行手前で一時停止 → 人間が承認 → 続き再開
```

- 1 つの作業の **途中** で人間の判断を挟みたい
- **数時間〜数日跨ぐ非同期承認** の場合、プロセスを落としても再開できる必要あり
- → **StateGraph + Checkpointer + `interrupt_before`** の出番

```python
graph = graph.compile(
    checkpointer=checkpointer,
    interrupt_before=["risky_action"],   # このノード手前で停止
)
result = graph.invoke(input, config={"configurable": {"thread_id": "..."}})
# 人間承認後
result = graph.invoke(None, config={"configurable": {"thread_id": "..."}})
```

### 即応型なら Agent Loop + callback で十分

Claude Code の「Bash 実行前の permission prompt」のような **即応型の Tool 承認**は、StateGraph 不要:

```python
async for event in agent.astream_events(...):
    if event["event"] == "on_tool_start":
        approved = await ask_user_permission(event["name"], event["data"]["input"])
        if not approved:
            raise UserRejectedToolError()
```

- LangChain の `on_tool_start` callback で挟むだけで実装可能
- ただし「**プロセスを落とすと承認待ち状態が消える**」のが弱点

### LangGraph interrupt の固有価値

> **数時間〜数日の長期非同期承認を、プロセスをまたいで保持できる**

これが Agent Loop + callback では実現困難な、StateGraph + Checkpointer の真価。

### 整理表

| パターン | 例 | 実装 |
|---|---|---|
| 単発質問応答 | curl で 1 回叩く API | 単純な `llm.invoke()` |
| 対話、ターン境界が自然 | ChatGPT、ClipMind Query Agent | **Agent Loop** |
| 対話 + Tool 実行前承認（即応型） | Claude Code | **Agent Loop + callback** |
| 対話 + 長期非同期承認 | 「上司が明日承認するまで待つ」業務フロー | **StateGraph + Checkpointer + interrupt** |
| 多段ワークフロー（決定的） | ClipMind Ingest、PDF OCR→翻訳→要約 | **StateGraph** |
| 多段ワークフロー + 並列 + 再開 | ClipMind Ingest（並列ノードあり） | **StateGraph + Reducer + Checkpointer** |

ClipMind Query Agent は (A) なので Agent Loop で十分。Claude Code でさえ即応型 callback で実現できることに注意。

---

## 5.55 「Agent Loop + 履歴永続化」で StateGraph 不要では？— 正直な比較

> Claude Code の `/resume` で前回の続きから指示できるなら、StateGraph + Checkpointer の優位性は実質薄いのでは？

**対話型 AI に限れば、この指摘は基本的に正しい**。
Claude Code / ChatGPT / ClipMind Query Agent のような対話システムでは、
**Agent Loop + messages 永続化（= /resume 相当）で十分実用**。

| | Agent Loop + messages 永続化 | StateGraph + Checkpointer |
|---|---|---|
| 状態の保存 | messages 配列 | 構造化 State 全体 |
| 再開方法 | messages を LLM に渡し、LLM が「続き」を判断 | checkpoint から決定的に次ノード実行 |
| 並列実行 | ❌ | ✅ |
| 対話用途 | **十分** | オーバーキル |

### 差が顕在化する 4 条件（無監督ワークフロー）

StateGraph の優位性が **明確に出る**のは、次の 4 つが揃った時:

#### (A) 人間が常時監督していない
- 対話型: ユーザーが画面を見ている → LLM の誤判断は次ターンで訂正可能
- 無監督バッチ: 訂正する人がいない → LLM の判断ミスが致命的

#### (B) Tool 実行コストが高い
- 軽い Tool: LLM が誤って二度呼んでも問題ない（数百ms / 数セント）
- Whisper transcribe: 数分 + GPU 消費 → 誤再呼び出しは致命的
- StateGraph は「completed なノードは決定的にスキップ」を**コードで保証**

#### (C) 並列実行を活用したい
- Agent Loop は LLM が逐次判断するので原理的に直列
- 「3 並列ノードのうち 1 つだけ再実行」のような部分再実行を LLM に正しく指示するのは事実上不可能

#### (D) 状態の構造が複雑
- 多次元の State（`frames`, `transcripts`, `detections`, `captions`, `timeline`...）
- messages 配列に埋め込んで LLM に再判定させるより、**構造化 State として直接アクセス**する方が決定的

### Claude Code 方式で ClipMind Ingest を書いたら何が起きるか（思考実験）

```
ユーザー: 動画 vid_abc を ingest して
LLM: tool_call(extract_frames) → 完了
LLM: tool_call(transcribe) → Whisper OOM で失敗
[/resume]
LLM: 「messages 見るに extract_frames は完了、transcribe で失敗。再実行するか」
     tool_call(transcribe) → 成功
LLM: 「次は detect_objects... 並列実行できないから直列で」
     tool_call(detect_objects) → 完了
     tool_call(caption_frames) → 完了
```

問題:
1. **再開のたびに LLM が messages 全部読み直すコスト**（数千〜数万トークン × 毎回）
2. **並列実行が LLM の制約で直列化**（速度 2〜3 倍劣化）
3. **LLM が誤って同じ Tool を二度呼ぶリスク**
4. **State が messages の中に埋もれる**

StateGraph 版: `Checkpointer → completed ノード skip → transcribe から決定的再開 → 残り 2 つを並列実行`。
**LLM の判断ループが介在しない**ので決定的・高速・低コスト・並列。

### コスト構造の本質的な違い

「再開時に LLM がコンテキストを再判断するコスト」を:
- **対話型**: ユーザーは数秒待てる、コストも数セント → 許容
- **無監督・大量回**: 1 日 1000 回再開なら無視できないコスト → 構造化 State で代替

### 整理: ご指摘がどこまで正しいか

| シーン | StateGraph 優位性 |
|---|---|
| 対話型 AI（Claude Code, ChatGPT, ClipMind Query Agent）| **薄い**。Agent Loop + 履歴永続化で十分 |
| 短いワークフロー（数ステップ、人間監督下）| 薄い |
| **無監督の長期ワークフロー**（夜間バッチ、ETL、ClipMind Ingest）| **明確に優位** |
| **並列実行が必要** | **明確に優位** |
| **Tool 実行コストが高い** | **明確に優位** |
| 長期非同期承認（数日待つ業務フロー） | 明確に優位 |

普段触れる対話型 AI の世界では「StateGraph 優位性が薄い」のは事実。
ClipMind の **Ingest（無監督・並列・コスト高）** は逆側のケースで、優位性が決定的に出る。
**Ingest = StateGraph、Query Agent = Agent Loop** という使い分けの根拠もここにある。

---

## 5.6 「割り込み」はどう実装されているか — 3 層のメカニズム

「Agent Loop の途中でユーザーが処理を止められるのは、while 文で常に ESC をチェックしているから？」
答えは **「半分 Yes、ただし実装は 3 層に分かれている」**。

### 層 1: OS シグナル（Ctrl+C）

```python
while True:
    response = llm.invoke(messages)  # ← Ctrl+C が来た瞬間、ここで KeyboardInterrupt が raise
    print(response)
```

- Ctrl+C は **OS が SIGINT シグナル** をプロセスに送る仕組み
- Python ランタイムが裏で signal handler を持ち、ループの任意の行で `KeyboardInterrupt` 例外を発生させる
- **コード側で「ESC チェック」を書く必要はない**。OS が割り込む

### 層 2: AsyncIO Task のキャンセル（ESC キー）

ESC は普通の文字入力なので OS シグナルではない。並行タスクで監視 + キャンセル:

```python
async def chat_loop():
    task = asyncio.create_task(stream_llm_response())   # ストリーム処理を task 化

    while not task.done():
        if key_pressed() == "ESC":
            task.cancel()                                # CancelledError を投げる
            break
        await asyncio.sleep(0.01)
```

- 「LLM ストリーム処理」と「キー入力監視」を **2 つの task として並行実行**
- ESC で `task.cancel()` を呼ぶと、ストリーム処理側に `CancelledError` が伝播
- 1 つの while で全部やるのではなく、**並行構造**で実現

### 層 3: アプリレベルの await ブロック（Tool 承認）

割り込みではなく、**ループ自体が `await` で待つ**:

```python
async def agent_loop(user_input):
    response = await llm.invoke(messages)
    if response.tool_calls:
        for tool_call in response.tool_calls:
            approved = await ask_user_permission(tool_call)   # ← ユーザー応答まで await が解除されない
            if approved:
                result = await execute_tool(tool_call)
```

- `await` の間、イベントループは他の仕事を進められる
- ユーザーが Yes/No を押した瞬間に await が解除されてループが進む

### 3 層の対応関係

| 何が起きる | どの層で実装 |
|---|---|
| Ctrl+C で全停止 | 層 1: OS シグナル → KeyboardInterrupt |
| ESC でストリーム停止 | 層 2: 並行 task の cancel |
| Tool 実行前の Y/N 承認 | 層 3: `await` でブロック |

この 3 つの組み合わせで「**LLM が秒単位で応答中でも割り込める**」「**ユーザー応答を待つ間プロセスが他の仕事を進められる**」が両立する。

「**StateGraph の interrupt は層 3 の永続化版**」と理解すると整理しやすい:

| | 層 3 (await) | StateGraph interrupt |
|---|---|---|
| 待機中の状態保持 | プロセスメモリ | Checkpointer で永続化 |
| プロセス停止に耐えるか | ❌ | ✅ |
| 実装複雑性 | 低 | 中 |
| 適する待ち時間 | 秒〜分 | 時間〜日 |

---

## 6. ハイブリッドパターン（参考）

実は両者は **混ぜて使える**。

- StateGraph の特定ノードが内部で Agent Loop を走らせる
- 例: Ingest の `caption_frames` ノードの中で、LLM が「画像が見えなければ OCR Tool に切り替え」のように動的判断

ClipMind の現設計は混ぜていないが、将来的に「動画ジャンルを LLM が判断して fuse 戦略を切り替える」のような分岐が出てきたら、conditional edge + 内部 Agent の合わせ技になる。

---

## 7. 実装で確認したいこと

- [ ] Ingest を StateGraph で書いたとき、各ノードが「何を入れて何を返すか」が型で読める
- [ ] Query Agent を Agent Loop で書いたとき、ユーザーの 5 種類の質問パターンが全部 1 つの実装で動く
- [ ] StateGraph 側のコストが事前見積もりと一致する（LLM の判断ブレがない）
- [ ] Query Agent 側のコストが質問依存でブレる量を計測

---

## 8. 一行サマリ

> **入力の構造が決まっているなら StateGraph で宣言的に。決まっていないなら Agent Loop で LLM に判断させる。**
> ClipMind は前者を Ingest、後者を Query に割り当てている。

---

## 実践マーカー

- 未実装（Phase 1: Ingest StateGraph、Phase 5: Query Agent Loop）
