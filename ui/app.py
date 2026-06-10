"""ClipMind — Streamlit UI.

起動:
    uv run --group ui streamlit run ui/app.py

前提: API (uv run uvicorn clipmind.api.main:app) と docker compose のサービスが起動済み.
"""

from __future__ import annotations

import time
from typing import Any

import streamlit as st

try:
    from ui.api_client import ApiError, ClipMindClient, format_ms
except ModuleNotFoundError:
    # `streamlit run ui/app.py` ではプロジェクト root ではなく ui/ が sys.path に入るため
    from api_client import ApiError, ClipMindClient, format_ms  # type: ignore[no-redef]

st.set_page_config(
    page_title="ClipMind",
    page_icon="🎬",
    layout="wide",
    # "auto": モバイルでは折りたたむ. "expanded" 固定だと狭幅でサイドバーが
    # コンテンツ全面を覆い、タブ操作をブロックする (実ブラウザ検証で発覚)
    initial_sidebar_state="auto",
)

# ----------------------------------------------------------------------
# sidebar: 接続先 + ヘルス + 動画セレクタ
# ----------------------------------------------------------------------

with st.sidebar:
    st.title("🎬 ClipMind")
    st.caption("動画を取り込み、自然言語で検索・質問する")

    api_base = st.text_input("API URL", value="http://localhost:8000")
    client = ClipMindClient(api_base)

    # ヘルス: データの信頼性シグナルを常時表示
    try:
        health = client.health()
        deps: dict[str, str] = health.get("deps", {})
        ok = health.get("status") == "healthy"
        # 注意: 三項演算子で書くと式文になり、Streamlit の magic が戻り値の
        # DeltaGenerator をサイドバーに描画してしまう. 必ず if 文で書く.
        if ok:
            st.success("API: healthy", icon="✅")
        else:
            st.warning("API: degraded", icon="⚠️")
        icon = {"ok": "🟢", "error": "🔴", "skipped": "⚪"}
        st.caption("  ".join(f"{icon.get(state, '⚪')} {name}" for name, state in deps.items()))
    except ApiError as e:
        st.error(f"API に接続できません\n\n{e}")
        st.stop()

    st.divider()

    # 動画セレクタ
    try:
        videos: list[dict[str, Any]] = client.list_videos()
    except ApiError as e:
        st.error(f"動画一覧の取得に失敗: {e}")
        videos = []

    if videos:
        labels = {
            v["video_id"]: (
                f"{v['video_id'][:8]}…  ({v['status']}, "
                f"frames {v['frame_count']}, segs {v['transcript_segment_count']})"
            )
            for v in videos
        }
        selected_video: str | None = st.selectbox(
            "対象の動画",
            options=list(labels.keys()),
            format_func=lambda vid: labels[vid],
        )
    else:
        selected_video = None
        st.info("まだ動画がありません。「取り込み」タブからアップロードしてください。")

    if st.button("↻ 一覧を更新", width="stretch"):
        st.rerun()


def _frame_url(video_id: str, start_ms: int) -> str | None:
    """検索ヒットの時刻に最も近いキーフレーム URL (静的配信のフルパス)."""
    frame = client.get_nearest_frame(video_id, start_ms)
    if frame is None:
        return None
    return f"{client.base_url}{frame['frame_url']}"


# ----------------------------------------------------------------------
# main: 取り込み / 検索 / 質問
# ----------------------------------------------------------------------

tab_ingest, tab_search, tab_ask = st.tabs(["📥 取り込み", "🔍 検索", "💬 質問"])

# --- 取り込み ----------------------------------------------------------
with tab_ingest:
    st.subheader("動画の取り込み")
    st.caption(
        "アップロードすると キーフレーム抽出 → 音声書き起こし → 物体検知 → "
        "ベクトルインデックス が実行されます (LangGraph パイプライン)。"
    )

    uploaded = st.file_uploader(
        "mp4 / mov / mkv / webm (最大 2GB)",
        type=["mp4", "mov", "mkv", "webm"],
        accept_multiple_files=False,
    )

    if uploaded is not None and st.button("取り込み開始", type="primary"):
        progress_bar = st.progress(0.0, text="アップロード中…")
        try:
            # 同期 Ingest: レスポンスが返った時点で完了している.
            # ENABLE_ASYNC_INGEST=true の場合は即 201 が返り、以降は進捗ポーリング.
            result = client.upload_video(
                uploaded.name, uploaded.getvalue(), uploaded.type or "video/mp4"
            )
            video_id = result["video_id"]

            # 非同期モードのときだけ進捗が動く. 同期なら即 completed が返る.
            for _ in range(600):  # 最大 10 分ポーリング
                event = client.get_progress(video_id)
                stage = event.get("stage", "unknown")
                progress = float(event.get("progress", 0.0))
                if stage == "completed":
                    progress_bar.progress(1.0, text="完了")
                    break
                if stage == "unknown":
                    # 同期 Ingest (進捗イベントなし) → ステータスを直接確認
                    detail = client.get_video(video_id)
                    if detail["status"] in ("completed", "failed"):
                        progress_bar.progress(1.0, text=f"status: {detail['status']}")
                        break
                progress_bar.progress(min(progress, 1.0), text=f"stage: {stage}")
                time.sleep(1.0)

            detail = client.get_video(video_id)
            if detail["status"] == "failed":
                st.error(f"Ingest が失敗しました (video_id: {video_id})")
            else:
                st.success(
                    f"取り込み完了 — frames: {detail['frame_count']}, "
                    f"transcript segments: {detail['transcript_segment_count']}"
                )
                st.code(video_id, language=None)
                st.rerun()
        except ApiError as e:
            progress_bar.empty()
            if e.status_code == 409:
                st.warning(f"同一ファイルが登録済みです: {e.message}")
            else:
                st.error(f"取り込みに失敗しました: {e}")

# --- 検索 --------------------------------------------------------------
with tab_search:
    st.subheader("セグメント検索")
    if selected_video is None:
        st.info("先に動画を取り込んでください。")
    else:
        with st.form("search_form"):
            col_q, col_mode, col_k = st.columns([6, 2, 2])
            query_text = col_q.text_input(
                "検索クエリ", placeholder="例: プレゼンターが結果を見せた場面"
            )
            mode = col_mode.radio("モード", ["hybrid", "dense"], horizontal=True)
            top_k = col_k.slider("件数", 1, 20, 5)
            submitted = st.form_submit_button("検索", type="primary")

        if submitted and query_text.strip():
            try:
                with st.spinner("検索中…"):
                    result = client.query(
                        selected_video, query_text.strip(), mode=mode, top_k=top_k
                    )
                hits = result["hits"]
                if not hits:
                    st.info(
                        "ヒットなし。動画に音声/キャプションが無いか、"
                        "クエリと内容が離れている可能性があります。"
                    )
                for hit in hits:
                    with st.container(border=True):
                        col_img, col_body = st.columns([1, 4])
                        url = _frame_url(selected_video, hit["start_ms"])
                        if url:
                            col_img.image(url, width="stretch")
                        else:
                            col_img.caption("(no frame)")
                        col_body.markdown(
                            f"**{format_ms(hit['start_ms'])} – {format_ms(hit['end_ms'])}**"
                            f"  ·  score `{hit['score']:.3f}`"
                        )
                        col_body.write(hit["text"])
            except ApiError as e:
                if e.status_code == 503:
                    st.error(f"検索バックエンド (Qdrant) に接続できません: {e.message}")
                else:
                    st.error(f"検索に失敗しました: {e}")

# --- 質問 (Agent チャット) ---------------------------------------------
with tab_ask:
    st.subheader("Agent に質問")
    if selected_video is None:
        st.info("先に動画を取り込んでください。")
    else:
        if "chat" not in st.session_state:
            st.session_state.chat = []  # list[tuple[role, content]]

        for role, content in st.session_state.chat:
            with st.chat_message(role):
                st.write(content)

        question = st.chat_input("この動画について質問…")
        if question:
            st.session_state.chat.append(("user", question))
            with st.chat_message("user"):
                st.write(question)
            with st.chat_message("assistant"):
                try:
                    with st.spinner("回答を生成中… (検索ツールを使います)"):
                        result = client.ask(selected_video, question)
                    answer = result["answer"]
                    st.write(answer)
                    st.session_state.chat.append(("assistant", answer))
                except ApiError as e:
                    if e.status_code == 503:
                        msg = (
                            "Agent は LLM API キー未設定のため利用できません。"
                            "`.env` に `ANTHROPIC_API_KEY` または `OPENAI_API_KEY` を"
                            "設定して API を再起動してください。"
                        )
                        st.warning(msg)
                        st.session_state.chat.append(("assistant", msg))
                    else:
                        st.error(f"Agent の呼び出しに失敗: {e}")
