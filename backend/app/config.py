from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NEUAURA_", env_file=ROOT / ".env", extra="ignore")
    data_dir: Path = ROOT / "local-data"
    database_url: str = ""
    max_upload_mb: int = Field(default=50, ge=1, le=500)
    max_duration_seconds: int = Field(default=600, ge=1, le=7200)
    retain_audio: bool = False
    retention_days: int = 30
    language: str = "en"
    whisper_model_path: Path = ROOT / "models/faster-whisper-tiny.en"
    whisper_compute_type: str = "int8"
    extraction_provider: str = "ollama"
    llm_base_url: str = "http://127.0.0.1:11434"
    llm_model: str = "qwen3:4b"
    llm_api_key: str = ""
    llm_think: bool | None = False
    llm_context_length: int = Field(default=8192, ge=2048, le=32768)
    allow_cloud: bool = False
    secure_cookies: bool = False
    worker_enabled: bool = True
    session_hours: int = Field(default=12, ge=1, le=168)
    allowed_hosts: list[str] = ["localhost", "127.0.0.1", "[::1]", "testserver"]

    def model_post_init(self, __context):
        for name in ("data_dir", "whisper_model_path"):
            path = getattr(self, name)
            if not path.is_absolute():
                setattr(self, name, ROOT / path)
        if not self.database_url:
            self.database_url = URL.create("sqlite", database=str(self.data_dir / "neuaura.sqlite3")).render_as_string(hide_password=False)
        if not 1 <= self.retention_days <= 3650:
            raise ValueError("retention_days must be between 1 and 3650")
