"""
FastAPI AI Gateway - Configuration
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings"""

    # Server
    host: str = "0.0.0.0"
    port: int = 8100
    environment: str = "development"

    # Security — service key (X-Service-Key, dipakai BFF Express)
    service_key: str

    # LLM lokal (runtime OpenAI-compatible: Ollama, vLLM, llama.cpp server)
    llm_base_url: str = "http://host.docker.internal:11434/v1"
    llm_api_key: str = "ollama"
    llm_model: str = "qwen3:30b-a3b"
    llm_temperature: float = 0.7
    llm_max_tokens: int = 2048
    llm_timeout: float = 120.0

    # Batasan konteks dan riwayat (minimum data, doc konsep 3.4)
    llm_system_prompt: str = (
        "Anda adalah asisten AI internal platform Research Control Center (RCC) "
        "milik BRIN. Bantu administrator riset menganalisis data, tren, dan "
        "kinerja periset. Jawab dengan bahasa Indonesia yang profesional, "
        "ringkas, dan berbasis data yang diberikan. Jika suatu pertanyaan "
        "membutuhkan data platform yang belum tersedia dalam percakapan ini, "
        "sampaikan batasan tersebut dan sarankan pengguna membuka halaman atau "
        "filter terkait. Jangan mengarang angka, nama, atau referensi."
    )
    llm_max_history_messages: int = 20
    llm_max_message_chars: int = 8000

    # CORS (origin BFF yang boleh memanggil)
    cors_origins: str = "http://localhost:3000,http://localhost:8080"

    # Analytics tools (Tahap 2 — katalog § 3 & guardrail § 5, spec tahap-2-analytics-tools.md)
    # HTTP(s) http://<IP-platform>:8000 di server platform; wajib saat tools aktif
    analytics_url: str = ""
    # Allowlist nama tool, CSV; kosong = fitur tools mati total (deny-by-default)
    ai_tools: str = ""
    # Guardrail loop tool
    tool_max_calls: int = 2          # maksimum tool per prompt
    tool_timeout: float = 15.0       # detik per request analytics
    tool_result_max_chars: int = 4000  # batas observasi per tool masuk konteks model

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()
