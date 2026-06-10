"""ClipMind API の薄いクライアント (Streamlit UI 用).

UI からの全リクエストをここに集約し、タイムアウト・エラー整形を統一する.
"""

from __future__ import annotations

from typing import Any

import httpx

DEFAULT_BASE_URL = "http://localhost:8000"


class ApiError(Exception):
    """API 呼び出し失敗 (UI 表示用に整形済み).

    注意: frozen dataclass を Exception にすると、raise 時に Python が
    `exc.__traceback__` を代入できず FrozenInstanceError になる (実ブラウザ検証で発覚).
    """

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(f"[{status_code}] {message}")
        self.status_code = status_code
        self.message = message


class ClipMindClient:
    """同期 httpx クライアント (Streamlit はスクリプト実行モデルなので同期で十分)."""

    def __init__(self, base_url: str = DEFAULT_BASE_URL) -> None:
        self.base_url = base_url.rstrip("/")

    def _request(self, method: str, path: str, *, timeout: float = 30.0, **kw: Any) -> Any:
        try:
            resp = httpx.request(method, f"{self.base_url}{path}", timeout=timeout, **kw)
        except httpx.ConnectError as e:
            raise ApiError(0, f"API に接続できません ({self.base_url}): {e}") from e
        except httpx.TimeoutException as e:
            raise ApiError(0, f"API がタイムアウトしました: {e}") from e
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text
            raise ApiError(resp.status_code, str(detail))
        return resp.json()

    # --- health -------------------------------------------------------
    def health(self) -> dict[str, Any]:
        return dict(self._request("GET", "/health", timeout=5.0))

    # --- videos -------------------------------------------------------
    def list_videos(self) -> list[dict[str, Any]]:
        return list(self._request("GET", "/api/v1/videos"))

    def get_video(self, video_id: str) -> dict[str, Any]:
        return dict(self._request("GET", f"/api/v1/videos/{video_id}"))

    def upload_video(self, filename: str, data: bytes, mime: str) -> dict[str, Any]:
        # 同期 Ingest は Whisper 込みで数分かかり得るので長め
        return dict(
            self._request(
                "POST",
                "/api/v1/videos",
                files={"file": (filename, data, mime)},
                timeout=1800.0,
            )
        )

    def get_progress(self, video_id: str) -> dict[str, Any]:
        return dict(self._request("GET", f"/api/v1/videos/{video_id}/progress", timeout=5.0))

    def get_nearest_frame(self, video_id: str, timestamp_ms: int) -> dict[str, Any] | None:
        try:
            return dict(
                self._request(
                    "GET",
                    f"/api/v1/videos/{video_id}/frame",
                    params={"timestamp_ms": timestamp_ms},
                    timeout=5.0,
                )
            )
        except ApiError as e:
            if e.status_code == 404:
                return None
            raise

    # --- search / ask -------------------------------------------------
    def query(
        self, video_id: str, query: str, *, mode: str = "hybrid", top_k: int = 5
    ) -> dict[str, Any]:
        return dict(
            self._request(
                "POST",
                f"/api/v1/videos/{video_id}/query",
                json={"query": query, "mode": mode, "top_k": top_k},
                timeout=60.0,
            )
        )

    def ask(self, video_id: str, question: str) -> dict[str, Any]:
        return dict(
            self._request(
                "POST",
                f"/api/v1/videos/{video_id}/ask",
                json={"question": question},
                timeout=120.0,
            )
        )


def format_ms(ms: int) -> str:
    """ミリ秒 → mm:ss 表記."""
    total_s = ms // 1000
    return f"{total_s // 60:02d}:{total_s % 60:02d}"
