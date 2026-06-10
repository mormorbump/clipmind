# LangChain: Tool-calling Agent

> 関連: ADR-0004, `docs/architecture.md` §4, Phase 5

## なぜ Agent なのか

ユーザーの質問は **「単発の検索 → 回答」では完結しない** ことが多い。

- 「人物Aが登場した全シーン」→ 物体ラベル絞り込み + 時刻ソート + 要約
- 「結論は何？」→ 後半セグメント取得 + 要約

このように **「検索→絞り込み→要約」を LLM が動的に組み立てる** のが Agent の役割。
Agent は LLM 自身が「次にどの Tool を呼ぶか」を決定するループ。

---

## 1. Tool-calling の仕組み

```
[user] ──► [LLM] ──► tool_call (hybrid_search, query="...")
                       │
                       ▼
                    [Tool]  ←  関数として実行
                       │
                       ▼ result
                     [LLM] ──► tool_call (filter_by_object, ...)  ← 続けてもよい
                       │
                       ▼ 最終応答
                    [user]
```

LLM の出力は **テキスト or 構造化された tool_call** の 2 種類。
`tool_call` を検出したら LangChain が該当関数を呼び、結果を **AssistantMessage の tool_result** として LLM に戻す。
LLM が「もう Tool は不要」と判断するまでループ。

これが Anthropic / OpenAI の双方で標準化されている **Function Calling / Tool Use API** の上に載っている。

---

## 2. Tool 設計の鉄則

### 2.1 粒度

| 悪い | 良い |
|---|---|
| 1 Tool で何でもできる（`run_query`） | 用途別に分ける（`hybrid_search` / `filter_by_time`） |
| 30 個の Tool | **5〜7 個** に絞る（多いと LLM が迷子） |

ClipMind の Tool 一覧（architecture.md §4.2）:
- `hybrid_search`（query 検索）
- `filter_by_time` / `filter_by_object`（絞り込み）
- `get_frame_image` / `summarize_segment` / `get_video_metadata`（補助）

### 2.2 入出力の型

- **Pydantic で厳密に**。LLM がスキーマを読んで使うので、説明文が雑だと挙動も雑になる
- 戻り値も JSON-serializable に統一（巨大バイナリは URL 参照に）

```python
class HybridSearchInput(BaseModel):
    query: str = Field(..., description="自然言語検索クエリ")
    top_k: int = Field(5, ge=1, le=20, description="上位 N 件")
    video_id: str | None = Field(None, description="特定動画に絞る場合")
```

### 2.3 説明文（docstring）が一番大事

LLM は `description` を読んで「いつこの Tool を使うか」を判断する。
日本語で 1〜2 行で「**どんな時に使うか / 入力と出力**」を書く。

---

## 3. `create_tool_calling_agent` の構造

```python
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_anthropic import ChatAnthropic

llm = ChatAnthropic(model="claude-sonnet-4-6")
tools = [hybrid_search, filter_by_time, ...]
prompt = ChatPromptTemplate.from_messages([
    ("system", "あなたは動画コンテンツのアシスタント..."),
    MessagesPlaceholder("chat_history"),
    ("user", "{input}"),
    MessagesPlaceholder("agent_scratchpad"),
])

agent = create_tool_calling_agent(llm, tools, prompt)
executor = AgentExecutor(agent=agent, tools=tools, max_iterations=5)
```

- `agent_scratchpad`: tool_call の履歴を LLM に見せるためのプレースホルダ（詳細は §3.5）
- `max_iterations`: 無限ループ防止（5〜10 が目安）
- `chat_history`: 過去の対話を渡す（Redis 等で persist）

### 3.5 agent_scratchpad — Agent の「作業メモ帳」

LLM はステートレス。1 回の `llm.invoke()` だけでは、前回 Tool を呼んだ事実も、その結果も覚えていない。
Agent ループは複数回 LLM を呼ぶので、**ターン毎に「これまでに何を呼んで、何が返ってきたか」を毎回プロンプトに詰め直す**必要がある。
これを担うのが `agent_scratchpad` プレースホルダ。

#### ループの中身

```
ターン 1:
  [system] [chat_history] [user 質問] [scratchpad: 空]
  → LLM: tool_call(hybrid_search, ...)

ターン 2:
  [system] [chat_history] [user 質問]
  [scratchpad:
     AIMessage(tool_calls=[hybrid_search(...)])
     ToolMessage(result=[...])
  ]
  → LLM: tool_call(summarize_segment, ...)

ターン 3:
  [scratchpad: 上記 + summarize_segment の AI/Tool ペア]
  → LLM: 最終テキスト応答（tool_call なし）→ ループ終了
```

#### chat_history と agent_scratchpad の違い

| プレースホルダ | スコープ | 中身 |
|---|---|---|
| `chat_history` | 複数の会話ターンを跨ぐ（Redis 永続） | 過去の user / assistant メッセージ |
| `agent_scratchpad` | **1 質問の中の Agent ループ内のみ**（毎回ゼロから） | tool_call + tool_result の連鎖 |

#### Tool-calling Agent と旧 ReAct Agent の差

- **`create_tool_calling_agent`（現代の主流）**: scratchpad は構造化 messages
  （`AIMessage(tool_calls=...)` + `ToolMessage(...)`）として詰まる
- **旧 `create_react_agent`（テキストベース）**: scratchpad は
  `Thought: ... Action: ... Observation: ...` の文字列
- Anthropic / OpenAI の API が tool_call を構造化で返すため、前者が主流

#### よくある落とし穴

- **プロンプトに `MessagesPlaceholder("agent_scratchpad")` を書き忘れる**
  → LLM が前ターンの tool_call/result を見られず、同じ Tool を無限に呼ぶ／結果を無視する
  → 症状が分かりにくいバグになる。テンプレ作成時に必ず入れる
- **scratchpad の肥大化**
  → ループが長引いたり Tool が大量データを返すとコンテキスト溢れ
  → Tool 側で件数を絞る、`max_iterations` を絞る

#### 命名の意図

人間が難しい問題を解く時に紙に途中計算を書く「メモ帳」と同じ。
LLM もループの中で「**さっき何を調べて、結果はこうだった、だから次はこうしよう**」を書き留めながら進む。
LangChain が自動で詰めてくれるので、開発者は `MessagesPlaceholder("agent_scratchpad")` を書いておくだけ。

---

## 4. 会話履歴の保持

```python
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_redis import RedisChatMessageHistory

with_history = RunnableWithMessageHistory(
    executor,
    lambda session_id: RedisChatMessageHistory(session_id),
    input_messages_key="input",
    history_messages_key="chat_history",
)
```

- session_id 単位でメッセージを Redis に蓄積
- TTL を設定して放置 session を自動削除

---

## 5. ストリーミング応答

```python
async for event in executor.astream_events({"input": q}, version="v2"):
    if event["event"] == "on_chat_model_stream":
        yield event["data"]["chunk"].content    # トークン
    elif event["event"] == "on_tool_start":
        yield {"tool": event["name"], "args": event["data"]["input"]}
```

- `astream_events` でトークン・Tool call・Tool result を逐次取り出せる
- WebSocket でクライアントへ流す（`docs/api-spec.md` §3.2）

---

## 6. ハマりどころ

### 6.1 Tool 名の衝突
- 関数名と LangChain の登録名がずれてエラーになる。`@tool` デコレータの name を明示

### 6.2 巨大なレスポンス
- Tool が 100 件のセグメントを返すと、LLM のコンテキストを圧迫
- **Tool 側で top_k を強制**、要約は専用 Tool（`summarize_segment`）に分離

### 6.3 引用の付与
- 回答にタイムスタンプ引用が必要なら、Tool の戻り値に `citation` フィールドを入れて、
  System Prompt で「必ず citation を含めること」と指示

### 6.4 思考の冗長化
- max_iterations を緩めすぎると LLM が無限に Tool を呼ぶ
- 5〜7 で十分なケースが多い

---

## 6.5 AgentExecutor 内部の正体

ブラックボックスに見えるが、中身は素直なループ:

```python
async def run(input):
    intermediate = []  # tool_call と結果のペア
    for _ in range(max_iterations):
        response = await agent.ainvoke({
            "input": input,
            "intermediate_steps": intermediate,   # ← agent_scratchpad に展開される
        })
        if response.return_values:                # 最終応答（tool_call なし）
            return response.return_values
        for tool_call in response.tool_calls:
            result = await tools[tool_call.name].ainvoke(tool_call.args)
            intermediate.append((tool_call, result))
    raise MaxIterationsError()
```

要するに「**LLM 呼ぶ → tool_call があれば実行 → 結果を次の LLM 入力に注入**」を繰り返すだけ。

→ これが「**Agent Loop は状態機械にする必要がない**」と言える理由
（cf. `../langgraph/02-when-to-use-stategraph.md`）。
入力構造が動的なので、宣言的グラフで縛るより LLM の判断に任せる方が向いている。

---

## 7. LangChain vs LlamaIndex（簡易）

詳細は ADR-0004。要点:

| 領域 | 強み |
|---|---|
| LangChain | Agent / Tool / LangGraph 連携 / LangSmith |
| LlamaIndex | Retriever 階層が深い（Sub-question, KG index 等） |

**ClipMind では Agent と Orchestration は LangChain、Retriever 比較で LlamaIndex を一部採用**（Phase 7）。

---

## 8. 実装で確認したいこと

- [ ] Tool を 3 個から始め、必要に応じて追加
- [ ] LangSmith で 1 質問あたりの tool_call 数を観測
- [ ] 引用 timestamp の正答率を Eval で測る
- [ ] ストリーミング応答の TTFT < 2s

---

## 9. 参考リンク

- LangChain Agents: https://python.langchain.com/docs/concepts/agents/
- Tool-calling: https://python.langchain.com/docs/concepts/tool_calling/
- Anthropic Tool Use: https://docs.anthropic.com/claude/docs/tool-use
- ADR-0004: `../adr/0004-langchain-vs-llamaindex.md`

---

## 実践マーカー

- ✅ Phase 5 で実践 (`src/clipmind/agents/`)
  - **Toolbox パターン**: Tool の実体ロジックは `QueryToolbox` クラスのメソッドにし、LangChain `@tool` ラッパーは `build_tools()` で生成。**Tool 単体を LLM なしでテストできる**のが利点
  - **5 Tool**: hybrid_search / filter_by_time / filter_by_object / get_frame_image / get_video_metadata。summarize_segment は Tool にせず Agent の応答生成に内製させた（Tool を増やすより選択ミスが減る）
  - **LangChain 1.x の `create_agent`**: 旧 `create_tool_calling_agent` + `AgentExecutor` は langchain-classic に移動済み。1.x では `from langchain.agents import create_agent` が標準で、**内部は LangGraph の Agent Loop**。knowledge/langgraph/02 の整理（対話 = 動的ツール選択 → Agent Loop）と実装が一致した
  - **モデル選択 (ADR-0003)**: 対話 Agent は Claude Sonnet 優先、無ければ GPT-4o。キーが無ければ `AgentUnavailableError` → API は 503
  - 実 LLM での応答テストは `@pytest.mark.e2e` (キー投入後に実行)
