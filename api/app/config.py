from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        env_ignore_empty=True,
    )

    app_env: Literal["dev", "test", "prod"] = "dev"
    public_base_url: str = "http://localhost:8088"
    allowed_origin: str = "http://localhost:8088"

    database_url: str = "postgresql+psycopg://fwdflow:fwdflow_dev@127.0.0.1:15433/fwdflow"
    database_url_test: str = "postgresql+psycopg://fwdflow:fwdflow_dev@127.0.0.1:15433/fwdflow_test"
    # Bắt buộc đặt trong .env trước khi chạy migration 0012 (LOGIN role cho AI #3)
    nlq_ops_password: str = ""
    nlq_finance_password: str = ""

    # Mật khẩu chung cho tài khoản demo (scripts/seed_demo.py, e2e); để trống thì seed từ chối chạy
    seed_password: str = ""

    session_cookie_name: str = "__Host-sid"
    files_dir: Path = REPO_ROOT / "data" / "files"
    max_upload_bytes: int = 20 * 1024 * 1024

    smtp_host: str = "127.0.0.1"
    smtp_port: int = 1025
    smtp_from: str = "FwdFlow <no-reply@fwdflow.local>"
    smtp_starttls: bool = False
    smtp_user: str | None = None
    smtp_password: SecretStr = SecretStr("")
    mailpit_api_url: str = "http://127.0.0.1:8025"  # chỉ test đọc hộp thư Mailpit

    ai_external_enabled: bool = True
    anthropic_api_key: str = ""
    llm_mode: Literal["live", "record", "replay"] = "replay"
    # Nhà cung cấp LLM: anthropic (Claude, trả phí) hoặc gemini (Google AI Studio, có gói miễn phí)
    llm_provider: Literal["anthropic", "gemini"] = "anthropic"
    gemini_api_key: str = ""
    gemini_model_extraction: str = "gemini-2.5-flash"
    gemini_model_hs: str = "gemini-2.5-flash"
    gemini_model_nlq: str = "gemini-2.5-flash"
    claude_model_extraction: str = "claude-opus-5"
    claude_model_hs: str = "claude-opus-5"
    claude_model_nlq: str = "claude-opus-5"
    # AI #2: mô hình embedding cục bộ (tải một lần vào models/bge-m3, không commit) và ngưỡng abstain theo cosine
    embed_model_dir: Path = REPO_ROOT / "models" / "bge-m3"
    embed_preload: bool = False
    # Tạm: cosine top-1 của mô tả thật 0,43–0,60, của chuỗi vô nghĩa 0,38–0,46; Task 12.6b chọn lại trên dev
    hs_tau: float = 0.35
    claude_effort_extraction: Literal["low", "medium", "high", "xhigh", "max"] = "high"
    extraction_max_tokens: int = 8000
    llm_fixture_dir: Path = REPO_ROOT / "api" / "tests" / "fixtures" / "llm"
    crosscheck_weight_tolerance: float = 0.005
    consignee_similarity_threshold: float = 0.85
    ai_daily_token_budget: int = 2_000_000
    fx_usd_vnd: int = 25_400

    # Chỉ test / e2e: cố định "hôm nay" cho mọi truy vấn phụ thuộc ngày
    app_today: date | None = None

    @model_validator(mode="after")
    def _prod_needs_https(self) -> "Settings":
        """QR trên nhãn in ra trỏ tới `public_base_url`, nên ở prod phải là https."""
        if self.app_env == "prod" and not self.public_base_url.startswith("https://"):
            raise ValueError("PUBLIC_BASE_URL phải bắt đầu bằng https:// khi APP_ENV=prod")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
