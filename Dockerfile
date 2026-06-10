# ClipMind API サーバ用イメージ。
# uv で依存を固定インストールし、uvicorn で FastAPI を起動する。
# k8s-action の PR プレビュー環境（preview-pr-<N> namespace）でも使われる。
FROM python:3.12-slim AS runtime

# opencv が実行時に必要とする共有ライブラリ。
# ultralytics が GUI 版 opencv-python を引き込むため X11 系も必要
# （headless 版だけなら libglib2.0-0 で済む）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libgl1 \
    libxcb1 \
    libsm6 \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.7 /uv /usr/local/bin/uv

WORKDIR /app

# 依存だけ先に解決して docker layer cache を効かせる
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# アプリ本体（alembic はマイグレーション用に同梱）
COPY src/ src/
COPY alembic.ini ./
COPY alembic/ alembic/
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000
CMD ["uvicorn", "clipmind.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
