from __future__ import annotations

from fastapi import HTTPException, status

from backend.app.notion_gateway import InquiryNotFoundError
from backend.app.services import InquiryServiceError, IntegrationFailureError


def to_http_exception(exc: InquiryServiceError | InquiryNotFoundError) -> HTTPException:
    if isinstance(exc, InquiryNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="inquiry not found")

    if isinstance(exc, IntegrationFailureError):
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": exc.error_code, "message": str(exc)},
        )

    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": exc.error_code, "message": str(exc)},
    )
