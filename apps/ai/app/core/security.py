from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from app.core.config import get_settings

_api_key_header = APIKeyHeader(name="X-Service-Key", auto_error=False)


async def verify_service_key(api_key: str | None = Security(_api_key_header)) -> None:
    settings = get_settings()
    if not api_key or api_key != settings.service_key:
        raise HTTPException(status_code=403, detail="X-Service-Key tidak valid atau tidak diberikan.")
