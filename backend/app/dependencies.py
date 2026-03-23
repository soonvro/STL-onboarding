from __future__ import annotations

from dataclasses import dataclass

import redis
from fastapi import Depends, HTTPException, Request, status

from automation.notion_api import NotionClient
from backend.app.auth import AdminAuthError, AdminAuthService
from backend.app.n8n_gateway import N8nWorkflowGateway
from backend.app.notion_gateway import NotionInquiryGateway
from backend.app.redis_store import RedisStateStore
from backend.app.services import InquiryService
from backend.app.settings import AppSettings


@dataclass(slots=True)
class AppContainer:
    settings: AppSettings
    auth_service: AdminAuthService
    inquiry_service: InquiryService
    closeables: list[object]

    def close(self) -> None:
        for closeable in reversed(self.closeables):
            close = getattr(closeable, "close", None)
            if callable(close):
                close()


def build_container(settings: AppSettings) -> AppContainer:
    notion_client = NotionClient(settings.notion_token, settings.notion_api_version)
    notion_gateway = NotionInquiryGateway(notion_client, settings.notion_data_source_id)
    redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    redis_store = RedisStateStore(redis_client)
    n8n_gateway = N8nWorkflowGateway(
        base_url=settings.n8n_base_url,
        shared_secret=settings.n8n_shared_secret,
        register_path=settings.n8n_webhook_register_path,
        complete_path=settings.n8n_webhook_complete_path,
        timeout_seconds=settings.n8n_timeout_seconds,
    )
    inquiry_service = InquiryService(
        redis_store=redis_store,
        notion_gateway=notion_gateway,
        n8n_gateway=n8n_gateway,
        notion_database_id=settings.notion_database_id,
        admin_notification_email=settings.admin_notification_email,
    )
    auth_service = AdminAuthService(settings.admin_jwt_secret, settings.admin_jwt_ttl_minutes)
    return AppContainer(
        settings=settings,
        auth_service=auth_service,
        inquiry_service=inquiry_service,
        closeables=[n8n_gateway, redis_store, notion_gateway],
    )


def get_container(request: Request) -> AppContainer:
    return request.app.state.container


def require_admin_session(
    request: Request,
    container: AppContainer = Depends(get_container),
) -> str:
    token = request.cookies.get(container.settings.admin_cookie_name)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="admin session required")
    try:
        container.auth_service.decode_token(token)
    except AdminAuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid admin session") from exc
    return token
