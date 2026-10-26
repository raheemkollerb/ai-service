from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SYSTEM_PROMPT = (
    "Anda adalah asisten AI internal platform Research Control Center (RCC) milik BRIN. "
    "Bantu administrator riset menganalisis data, tren, dan kinerja periset. Jawab dengan "
    "bahasa Indonesia yang profesional, ringkas, dan berbasis data yang diberikan. Jika suatu "
    "pertanyaan membutuhkan data platform yang belum tersedia dalam percakapan ini, sampaikan "
    "batasan tersebut dan sarankan pengguna membuka halaman atau filter terkait. Jangan "
    "mengarang angka, nama, atau referensi."
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    host: str = "0.0.0.0"
    port: int = 8100
    environment: str = "development"

    service_key: str

    llm_base_url: str = "http://host.docker.internal:11434/v1"
    llm_api_key: str = "ollama"
    llm_model: str = "qwen3:30b-a3b"
    llm_temperature: float = 0.7
    llm_max_tokens: int = 2048
    llm_timeout: float = 120.0
    llm_system_prompt: str = DEFAULT_SYSTEM_PROMPT
    llm_max_history_messages: int = 20
    llm_max_message_chars: int = 8000

    cors_origins: str = "http://localhost:3000,http://localhost:8080"

    @property
    def is_development(self) -> bool:
        return self.environment.strip().lower() == "development"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
