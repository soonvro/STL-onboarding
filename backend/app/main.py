from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware

from backend.app.dependencies import AppContainer, build_container, get_container, require_admin_session
from backend.app.models import (
    AdminLoginRequest,
    AdminSessionResponse,
    ErrorResponse,
    InquiryCreateRequest,
    InquiryCreateResponse,
    InquiryDetailResponse,
    InquiryListResponse,
    InquiryStatus,
    InquiryUpdateRequest,
    InquiryUpdateResponse,
    MessageResponse,
)
from backend.app.notion_gateway import InquiryNotFoundError
from backend.app.services import (
    DuplicateInquiryError,
    InquiryProcessingError,
    IntegrationFailureError,
    InvalidTransitionError,
)
from backend.app.settings import AppSettings


@asynccontextmanager
async def _lifespan(container: AppContainer) -> AsyncIterator[None]:
    try:
        yield
    finally:
        container.close()


def create_app(settings: AppSettings | None = None, container: AppContainer | None = None) -> FastAPI:
    settings = settings or AppSettings()
    container = container or build_container(settings)

    app = FastAPI(title="Q&A Backend API", version="0.1.0", lifespan=lambda _app: _lifespan(container))
    app.state.container = container

    if settings.backend_allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.backend_allowed_origins,
            allow_credentials=settings.backend_cors_allow_credentials,
            allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["*"],
        )

    @app.get("/")
    def root() -> dict[str, str]:
        return {"service": "qna-backend", "status": "ok"}

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post(
        "/api/v1/inquiries",
        response_model=InquiryCreateResponse,
        responses={
            409: {"model": ErrorResponse},
            502: {"model": ErrorResponse},
        },
        status_code=status.HTTP_201_CREATED,
    )
    def create_inquiry(
        request: InquiryCreateRequest,
        container: AppContainer = Depends(get_container),
    ) -> InquiryCreateResponse:
        try:
            result = container.inquiry_service.create_inquiry(request)
        except DuplicateInquiryError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "duplicate_inquiry", "message": str(exc)},
            ) from exc
        except InquiryProcessingError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "inquiry_processing", "message": str(exc)},
            ) from exc
        except IntegrationFailureError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"code": "integration_failure", "message": str(exc)},
            ) from exc

        return InquiryCreateResponse(
            request_id=result.request_id,
            message="문의가 등록되었습니다.",
            admin_email_status=result.admin_email_status,
            notion_page_id=result.notion_page_id,
        )

    @app.post("/api/v1/admin/session", response_model=AdminSessionResponse)
    def create_admin_session(
        request: AdminLoginRequest,
        response: Response,
        container: AppContainer = Depends(get_container),
    ) -> AdminSessionResponse:
        if not container.auth_service.verify_password(request.password, container.settings.admin_password):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid password")
        token = container.auth_service.issue_token()
        response.set_cookie(
            key=container.settings.admin_cookie_name,
            value=token,
            httponly=True,
            secure=container.settings.admin_cookie_secure,
            samesite=container.settings.admin_cookie_samesite,
            max_age=container.settings.admin_jwt_ttl_minutes * 60,
            path="/",
        )
        return AdminSessionResponse(authenticated=True)

    @app.get("/api/v1/admin/session", response_model=AdminSessionResponse)
    def get_admin_session(
        container: AppContainer = Depends(get_container),
        _: str = Depends(require_admin_session),
    ) -> AdminSessionResponse:
        return AdminSessionResponse(authenticated=True)

    @app.delete("/api/v1/admin/session", response_model=MessageResponse)
    def delete_admin_session(
        response: Response,
        container: AppContainer = Depends(get_container),
    ) -> MessageResponse:
        response.delete_cookie(
            key=container.settings.admin_cookie_name,
            path="/",
            httponly=True,
            secure=container.settings.admin_cookie_secure,
            samesite=container.settings.admin_cookie_samesite,
        )
        return MessageResponse(message="관리자 세션이 종료되었습니다.")

    @app.get("/api/v1/admin/inquiries", response_model=InquiryListResponse)
    def list_inquiries(
        status_filter: InquiryStatus | None = Query(default=None, alias="status"),
        cursor: str | None = None,
        page_size: int = Query(default=20, ge=1, le=100),
        container: AppContainer = Depends(get_container),
        _: str = Depends(require_admin_session),
    ) -> InquiryListResponse:
        page = container.inquiry_service.list_inquiries(status=status_filter, cursor=cursor, page_size=page_size)
        return InquiryListResponse(items=page.items, next_cursor=page.next_cursor)

    @app.get("/api/v1/admin/inquiries/{notion_page_id}", response_model=InquiryDetailResponse)
    def get_inquiry(
        notion_page_id: str,
        container: AppContainer = Depends(get_container),
        _: str = Depends(require_admin_session),
    ) -> InquiryDetailResponse:
        try:
            return container.inquiry_service.get_inquiry(notion_page_id)
        except InquiryNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="inquiry not found") from exc

    @app.patch(
        "/api/v1/admin/inquiries/{notion_page_id}",
        response_model=InquiryUpdateResponse,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 502: {"model": ErrorResponse}},
    )
    def update_inquiry(
        notion_page_id: str,
        request: InquiryUpdateRequest,
        container: AppContainer = Depends(get_container),
        _: str = Depends(require_admin_session),
    ) -> InquiryUpdateResponse:
        try:
            result = container.inquiry_service.update_inquiry(notion_page_id, request)
        except InquiryNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="inquiry not found") from exc
        except InquiryProcessingError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "update_processing", "message": str(exc)},
            ) from exc
        except InvalidTransitionError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "invalid_transition", "message": str(exc)},
            ) from exc
        except IntegrationFailureError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"code": "integration_failure", "message": str(exc)},
            ) from exc

        return InquiryUpdateResponse(message="문의 상태가 반영되었습니다.", inquiry=result.inquiry)

    return app
