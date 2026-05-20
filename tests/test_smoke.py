"""Phase 0 smoke test: パッケージが import でき、entry point が存在することを確認."""

from clipmind import main
from clipmind.config import Settings, get_settings


def test_main_is_callable() -> None:
    """`clipmind.main` が呼び出し可能であること."""
    assert callable(main)


def test_settings_loads_with_defaults() -> None:
    """`.env` が無い環境でも Settings がデフォルトで構築できること."""
    settings = get_settings()
    assert isinstance(settings, Settings)
    assert settings.qdrant_url.startswith("http://")
    assert settings.langsmith_project == "clipmind"
