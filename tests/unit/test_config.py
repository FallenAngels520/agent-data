import pytest

from agent_data.config import Settings


def test_settings_use_approved_parser_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "secret")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    settings = Settings.from_env()
    assert settings.pdf_parser == "mineru"
    assert settings.url_parser == "crawl4ai"
    assert settings.mineru_base_url == "http://192.168.0.213:8000"
    assert settings.mineru_end_page == 99999
    assert settings.crawl4ai_base_url == "http://192.168.0.213:11235"


def test_settings_require_llm_credentials(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    with pytest.raises(ValueError, match="LLM_API_KEY"):
        Settings.from_env()


def test_settings_load_current_directory_dotenv(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    (tmp_path / ".env").write_text(
        "LLM_API_KEY=from-file\nLLM_MODEL=file-model\nLLM_BASE_URL=https://example.test\n",
        encoding="utf-8",
    )
    settings = Settings.from_env()
    assert settings.llm_api_key == "from-file"
    assert settings.llm_model == "file-model"
    assert settings.llm_base_url == "https://example.test"


def test_environment_variables_override_dotenv(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LLM_API_KEY", "from-environment")
    monkeypatch.setenv("LLM_MODEL", "environment-model")
    (tmp_path / ".env").write_text(
        "LLM_API_KEY=from-file\nLLM_MODEL=file-model\n",
        encoding="utf-8",
    )
    settings = Settings.from_env()
    assert settings.llm_api_key == "from-environment"
    assert settings.llm_model == "environment-model"


def test_settings_load_crawl4ai_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "secret")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("URL_PARSER", "trafilatura")
    monkeypatch.setenv("CRAWL4AI_BASE_URL", "http://192.168.0.213:11235")
    monkeypatch.setenv("CRAWL4AI_API_TOKEN", "token")
    monkeypatch.setenv("CRAWL4AI_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("CRAWL4AI_POLL_INTERVAL_SECONDS", "0.5")

    settings = Settings.from_env()

    assert settings.url_parser == "trafilatura"
    assert settings.crawl4ai_base_url == "http://192.168.0.213:11235"
    assert settings.crawl4ai_api_token == "token"
    assert settings.crawl4ai_timeout_seconds == 45
    assert settings.crawl4ai_poll_interval_seconds == 0.5
