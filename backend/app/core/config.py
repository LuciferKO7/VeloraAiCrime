import os
from pathlib import Path

from pydantic import BaseModel

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent


def load_env_file():
    env_file = ROOT_DIR / ".env"
    if env_file.exists():
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, rest = line.partition("=")
                    k = k.strip()
                    v = rest.split("#", 1)[0].strip()
                    if k and k not in os.environ:
                        os.environ[k] = v


load_env_file()


class Settings(BaseModel):
    APP_ENV: str = os.getenv("APP_ENV", "development")
    SERVICE_KEY: str = os.getenv("SERVICE_KEY", "")
    JWT_SECRET: str = os.getenv("JWT_SECRET", "")
    JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))
    FRONTEND_ORIGIN: str = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
    BACKEND_URL: str = os.getenv("BACKEND_URL", "http://localhost:8000")
    ML_SERVICE_URL: str = os.getenv("ML_SERVICE_URL", "http://localhost:8001")
    SPEECH_SERVICE_URL: str = os.getenv("SPEECH_SERVICE_URL", "http://localhost:8002")
    OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://localhost:11434")

    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./backend/data/velora.db")
    STORAGE_DIR: str = os.getenv("STORAGE_DIR", "./backend/storage")

    SEED_PASSWORD_ADMIN: str = os.getenv("SEED_PASSWORD_ADMIN", "")
    SEED_PASSWORD_SUPERVISOR: str = os.getenv("SEED_PASSWORD_SUPERVISOR", "")
    SEED_PASSWORD_INVESTIGATOR: str = os.getenv("SEED_PASSWORD_INVESTIGATOR", "")
    SEED_PASSWORD_ARTIST: str = os.getenv("SEED_PASSWORD_ARTIST", "")
    SEED_PASSWORD_AUDITOR: str = os.getenv("SEED_PASSWORD_AUDITOR", "")

    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL_FAST: str = os.getenv("GEMINI_MODEL_FAST", "")
    GEMINI_MODEL_SMART: str = os.getenv("GEMINI_MODEL_SMART", "")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "")
    LLM_PROVIDER_MODE: str = os.getenv("LLM_PROVIDER_MODE", "auto")
    LLM_TIMEOUT_S: int = int(os.getenv("LLM_TIMEOUT_S", "12"))
    LLM_MAX_RETRIES: int = int(os.getenv("LLM_MAX_RETRIES", "1"))
    GEMINI_RPM: int = int(os.getenv("GEMINI_RPM", "8"))
    LLM_CACHE_TTL_S: int = int(os.getenv("LLM_CACHE_TTL_S", "3600"))

    def validate_secrets(self):
        if not self.SERVICE_KEY:
            raise ValueError("SERVICE_KEY must not be empty")
        if not self.JWT_SECRET or len(self.JWT_SECRET) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters long")


settings = Settings()
