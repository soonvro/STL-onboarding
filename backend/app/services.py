from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass

from backend.app.models import InquiryCreateRequest, InquiryDetailResponse, InquiryStatus, InquiryUpdateRequest
from backend.app.n8n_gateway import CompleteWorkflowResult, N8nWorkflowGateway, N8nWorkflowError, RegisterWorkflowResult
from backend.app.notion_gateway import InquiryListPage, InquiryNotFoundError, NotionInquiryGateway
from backend.app.redis_store import RedisStateStore


class DuplicateInquiryError(RuntimeError):
    """Raised when a duplicate inquiry is detected."""


class InquiryProcessingError(RuntimeError):
    """Raised when an inquiry with the same dedup key is still processing."""


class InvalidTransitionError(RuntimeError):
    """Raised when an unsupported status transition is requested."""


class IntegrationFailureError(RuntimeError):
    """Raised when a downstream integration fails."""


@dataclass(slots=True)
class CreateInquiryResult:
    request_id: str
    notion_page_id: str
    admin_email_status: str


@dataclass(slots=True)
class UpdateInquiryResult:
    inquiry: InquiryDetailResponse


@dataclass(slots=True)
class InquiryService:
    redis_store: RedisStateStore
    notion_gateway: NotionInquiryGateway
    n8n_gateway: N8nWorkflowGateway
    notion_database_id: str
    admin_notification_email: str

    def create_inquiry(self, request: InquiryCreateRequest) -> CreateInquiryResult:
        dedup_key = compute_dedup_key(request.name, request.title)
        request_id = f"req-{uuid.uuid4().hex}"
        current_state = self.redis_store.get_inquiry_state(dedup_key)
        if current_state.get("status") == "confirmed":
            raise DuplicateInquiryError("동일한 이름과 제목의 문의가 이미 등록되어 있습니다.")

        token = uuid.uuid4().hex
        if not self.redis_store.acquire_inquiry_lock(dedup_key, token):
            for _ in range(5):
                time.sleep(0.4)
                state = self.redis_store.get_inquiry_state(dedup_key)
                if state.get("status") == "confirmed":
                    raise DuplicateInquiryError("동일한 이름과 제목의 문의가 이미 등록되어 있습니다.")
            raise InquiryProcessingError("동일한 문의가 처리 중입니다. 잠시 후 다시 시도해주세요.")

        try:
            current_state = self.redis_store.get_inquiry_state(dedup_key)
            if current_state.get("status") == "confirmed":
                raise DuplicateInquiryError("동일한 이름과 제목의 문의가 이미 등록되어 있습니다.")

            self.redis_store.set_inquiry_state(dedup_key, status="pending", request_id=request_id)
            existing_page_id = self.notion_gateway.find_by_dedup_key(dedup_key)
            if existing_page_id:
                self.redis_store.set_inquiry_state(
                    dedup_key,
                    status="confirmed",
                    request_id=request_id,
                    notion_page_id=existing_page_id,
                )
                self.redis_store.record_page_mapping(existing_page_id, dedup_key)
                raise DuplicateInquiryError("동일한 이름과 제목의 문의가 이미 등록되어 있습니다.")

            try:
                workflow_result = self.n8n_gateway.register_inquiry(
                    {
                        "request_id": request_id,
                        "dedup_key": dedup_key,
                        "name": request.name,
                        "email": request.email,
                        "phone": request.phone,
                        "title": request.title,
                        "body": request.body,
                        "admin_email": self.admin_notification_email,
                        "notion_database_id": self.notion_database_id,
                    }
                )
            except N8nWorkflowError as exc:
                self.redis_store.set_inquiry_state(
                    dedup_key,
                    status="failed",
                    request_id=request_id,
                    error_code="n8n_register_failed",
                )
                raise IntegrationFailureError("문의 등록 워크플로우 호출에 실패했습니다.") from exc

            self.redis_store.set_inquiry_state(
                dedup_key,
                status="confirmed",
                request_id=request_id,
                notion_page_id=workflow_result.notion_page_id,
            )
            self.redis_store.record_page_mapping(workflow_result.notion_page_id, dedup_key)
            return CreateInquiryResult(
                request_id=request_id,
                notion_page_id=workflow_result.notion_page_id,
                admin_email_status=workflow_result.admin_email_status,
            )
        finally:
            self.redis_store.release_inquiry_lock(dedup_key, token)

    def list_inquiries(self, *, status: InquiryStatus | None, cursor: str | None, page_size: int) -> InquiryListPage:
        return self.notion_gateway.list_inquiries(status=status, cursor=cursor, page_size=page_size)

    def get_inquiry(self, notion_page_id: str) -> InquiryDetailResponse:
        return self.notion_gateway.get_inquiry(notion_page_id)

    def update_inquiry(self, notion_page_id: str, request: InquiryUpdateRequest) -> UpdateInquiryResult:
        token = uuid.uuid4().hex
        if not self.redis_store.acquire_page_lock(notion_page_id, token):
            raise InquiryProcessingError("상태 변경이 처리 중입니다. 잠시 후 다시 시도해주세요.")

        try:
            inquiry = self.notion_gateway.get_inquiry(notion_page_id)
            if inquiry.status == InquiryStatus.COMPLETED and request.status != InquiryStatus.COMPLETED:
                raise InvalidTransitionError("완료된 문의는 이전 상태로 되돌릴 수 없습니다.")
            if inquiry.status == request.status:
                return UpdateInquiryResult(inquiry=inquiry)
            if request.status == InquiryStatus.REGISTERED:
                raise InvalidTransitionError("등록됨 상태로 되돌릴 수 없습니다.")

            if request.status == InquiryStatus.IN_PROGRESS:
                updated = self.notion_gateway.update_status(notion_page_id, status=InquiryStatus.IN_PROGRESS)
                return UpdateInquiryResult(inquiry=updated)

            if request.status == InquiryStatus.COMPLETED:
                try:
                    workflow_result = self.n8n_gateway.complete_inquiry(
                        {
                            "request_id": f"req-{uuid.uuid4().hex}",
                            "notion_page_id": notion_page_id,
                            "resolution": request.resolution,
                            "requester_email": inquiry.email,
                            "admin_email": self.admin_notification_email,
                        }
                    )
                except N8nWorkflowError as exc:
                    raise IntegrationFailureError("문의 완료 워크플로우 호출에 실패했습니다.") from exc

                updated = self.notion_gateway.get_inquiry(workflow_result.notion_page_id)
                return UpdateInquiryResult(inquiry=updated)

            raise InvalidTransitionError("지원하지 않는 상태 변경입니다.")
        finally:
            self.redis_store.release_page_lock(notion_page_id, token)


def compute_dedup_key(name: str, title: str) -> str:
    normalized_name = _normalize(name)
    normalized_title = _normalize(title)
    return hashlib.sha256(f"{normalized_name}:{normalized_title}".encode("utf-8")).hexdigest()


def _normalize(value: str) -> str:
    return " ".join(value.strip().lower().split())
