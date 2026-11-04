"""
Security utilities — service-to-service auth.
"""
from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader
from app.core.config import get_settings

settings = get_settings()

api_key_header = APIKeyHeader(name="X-Service-Key", auto_error=True)


async def verify_service_key(api_key: str = Security(api_key_header)) -> str:
    """
    Verify service-to-service API key (biasanya dikirim oleh Express BFF).

    auto_error memastikan header hilang juga menjadi 403, bukan 500.
    """
    if api_key != settings.service_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid service key",
        )
    return api_key
