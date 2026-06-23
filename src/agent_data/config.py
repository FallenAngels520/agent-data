from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values


@dataclass(frozen=True)
class Settings:
    llm_api_key: str
    llm_model: str
    llm_base_url: str | None = None
    llm_timeout_seconds: float = 120.0
    pdf_parser: str = "mineru"
    url_parser: str = "crawl4ai"
    mineru_base_url: str = "http://192.168.0.213:8000"
    mineru_timeout_seconds: float = 600.0
    mineru_start_page: int = 0
    mineru_end_page: int = 99999
    crawl4ai_base_url: str = "http://192.168.0.213:11235"
    crawl4ai_api_token: str | None = None
    crawl4ai_timeout_seconds: float = 300.0
    crawl4ai_poll_interval_seconds: float = 1.0
    allow_private_networks: bool = False
    max_download_bytes: int = 25 * 1024 * 1024

    @classmethod
    def from_env(cls) -> Settings:
        dotenv = dotenv_values(Path.cwd() / ".env")

        def value(name: str, default: str = "") -> str:
            environment = os.getenv(name)
            if environment is not None:
                return environment
            file_value = dotenv.get(name)
            return str(file_value) if file_value is not None else default

        api_key = value("LLM_API_KEY").strip()
        model = value("LLM_MODEL").strip()
        if not api_key:
            raise ValueError("LLM_API_KEY is required")
        if not model:
            raise ValueError("LLM_MODEL is required")
        return cls(
            llm_api_key=api_key,
            llm_model=model,
            llm_base_url=value("LLM_BASE_URL") or None,
            llm_timeout_seconds=float(value("LLM_TIMEOUT_SECONDS", "120")),
            pdf_parser=value("PDF_PARSER", "mineru"),
            url_parser=value("URL_PARSER", "crawl4ai"),
            mineru_base_url=value("MINERU_BASE_URL", "http://192.168.0.213:8000").rstrip("/"),
            mineru_timeout_seconds=float(value("MINERU_TIMEOUT_SECONDS", "600")),
            mineru_start_page=int(value("MINERU_START_PAGE", "0")),
            mineru_end_page=int(value("MINERU_END_PAGE", "99999")),
            crawl4ai_base_url=value("CRAWL4AI_BASE_URL", "http://192.168.0.213:11235").rstrip("/"),
            crawl4ai_api_token=value("CRAWL4AI_API_TOKEN") or None,
            crawl4ai_timeout_seconds=float(value("CRAWL4AI_TIMEOUT_SECONDS", "300")),
            crawl4ai_poll_interval_seconds=float(value("CRAWL4AI_POLL_INTERVAL_SECONDS", "1")),
            allow_private_networks=value("ALLOW_PRIVATE_NETWORKS", "false").lower()
            in {"1", "true", "yes"},
            max_download_bytes=int(value("MAX_DOWNLOAD_BYTES", str(25 * 1024 * 1024))),
        )
