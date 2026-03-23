from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass

from backend.app.models import InquiryCreateRequest, InquiryDetailResponse, InquiryStatus, InquiryUpdateRequest
from backend.app.n8n_gateway import (
    CompleteInquiryPayload,
    N8nWorkflowGateway,
    N8nWorkflowError,
    RegisterInquiryPayload,
)
from backend.app.notion_gateway import InquiryListPage, NotionInquiryGateway
from backend.app.redis_store import RedisStateStore


INQUIRY_STATE_PENDING = "pending"
INQUIRY_STATE_CONFIRMED = "confirmed"
INQUIRY_STATE_FAILED = "failed"


class InquiryServiceError(RuntimeError):
    error_code = "inquiry_service_error"


class DuplicateInquiryError(InquiryServiceError):
    """Raised when a duplicate inquiry is detected."""

    error_code = "duplicate_inquiry"


class InquiryProcessingError(InquiryServiceError):
    """Raised when an inquiry with the same dedup key is still processing."""

    error_code = "inquiry_processing"


class UpdateProcessingError(InquiryServiceError):
    """Raised when an inquiry status update is already processing."""

    error_code = "update_processing"


class InvalidTransitionError(InquiryServiceError):
    """Raised when an unsupported status transition is requested."""

    error_code = "invalid_transition"


class IntegrationFailureError(InquiryServiceError):
    """Raised when a downstream integration fails."""

    error_code = "integration_failure"


@dataclass(slots=True)
class CreateInquiryResult:
    request_id: str
    notion_page_id: str
    admin_email_status: str


@dataclass(slots=True)
class UpdateInquiryResult:
    inquiry: InquiryDetailResponse


@dataclass(slots=True)
class InquiryTransitionPlan:
    action: str
    next_status: InquiryStatus | None = None


@dataclass(slots=True)
class InquiryService:
    redis_store: RedisStateStore
    notion_gateway: NotionInquiryGateway
    n8n_gateway: N8nWorkflowGateway
    notion_database_id: str
    admin_notification_email: str
    inquiry_lock_retry_attempts: int = 5
    inquiry_lock_retry_delay_seconds: float = 0.4

    def create_inquiry(self, request: InquiryCreateRequest) -> CreateInquiryResult:
        dedup_key = compute_dedup_key(request.name, request.title)
        request_id = f"req-{uuid.uuid4().hex}"
        self._raise_if_confirmed(dedup_key)

        token = uuid.uuid4().hex
        self._acquire_inquiry_lock_or_raise(dedup_key, token)

        try:
            self._raise_if_confirmed(dedup_key)
            self._mark_pending(dedup_key, request_id)
            existing_page_id = self.notion_gateway.find_by_dedup_key(dedup_key)
            if existing_page_id:
                self._mark_confirmed(dedup_key, request_id, existing_page_id)
                raise self._duplicate_error()

            try:
                workflow_result = self.n8n_gateway.register_inquiry(
                    self._build_register_payload(request_id=request_id, dedup_key=dedup_key, request=request)
                )
            except N8nWorkflowError as exc:
                self._mark_failed(dedup_key, request_id, error_code="n8n_register_failed")
                raise IntegrationFailureError("문의 등록 워크플로우 호출에 실패했습니다.") from exc

            self._mark_confirmed(dedup_key, request_id, workflow_result.notion_page_id)
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
            raise UpdateProcessingError("상태 변경이 처리 중입니다. 잠시 후 다시 시도해주세요.")

        try:
            inquiry = self.notion_gateway.get_inquiry(notion_page_id)
            plan = self._build_transition_plan(current_status=inquiry.status, target_status=request.status)

            if plan.action == "noop":
                return UpdateInquiryResult(inquiry=inquiry)

            if plan.action == "update_status" and plan.next_status is not None:
                updated = self.notion_gateway.update_status(notion_page_id, status=plan.next_status)
                return UpdateInquiryResult(inquiry=updated)

            if plan.action == "complete_workflow":
                try:
                    workflow_result = self.n8n_gateway.complete_inquiry(
                        self._build_complete_payload(
                            notion_page_id=notion_page_id,
                            requester_email=inquiry.email,
                            resolution=request.resolution or "",
                        )
                    )
                except N8nWorkflowError as exc:
                    raise IntegrationFailureError("문의 완료 워크플로우 호출에 실패했습니다.") from exc

                updated = self.notion_gateway.get_inquiry(workflow_result.notion_page_id)
                return UpdateInquiryResult(inquiry=updated)

            raise InvalidTransitionError("지원하지 않는 상태 변경입니다.")
        finally:
            self.redis_store.release_page_lock(notion_page_id, token)

    def _build_register_payload(
        self,
        *,
        request_id: str,
        dedup_key: str,
        request: InquiryCreateRequest,
    ) -> RegisterInquiryPayload:
        return RegisterInquiryPayload(
            request_id=request_id,
            dedup_key=dedup_key,
            name=request.name,
            email=request.email,
            phone=request.phone,
            title=request.title,
            body=request.body,
            admin_email=self.admin_notification_email,
            notion_database_id=self.notion_database_id,
        )

    def _build_complete_payload(
        self,
        *,
        notion_page_id: str,
        requester_email: str,
        resolution: str,
    ) -> CompleteInquiryPayload:
        return CompleteInquiryPayload(
            request_id=f"req-{uuid.uuid4().hex}",
            notion_page_id=notion_page_id,
            resolution=resolution,
            requester_email=requester_email,
            admin_email=self.admin_notification_email,
        )

    def _build_transition_plan(
        self,
        *,
        current_status: InquiryStatus,
        target_status: InquiryStatus,
    ) -> InquiryTransitionPlan:
        if current_status == InquiryStatus.COMPLETED and target_status != InquiryStatus.COMPLETED:
            raise InvalidTransitionError("완료된 문의는 이전 상태로 되돌릴 수 없습니다.")
        if current_status == target_status:
            return InquiryTransitionPlan(action="noop")
        if target_status == InquiryStatus.REGISTERED:
            raise InvalidTransitionError("등록됨 상태로 되돌릴 수 없습니다.")
        if target_status == InquiryStatus.IN_PROGRESS:
            return InquiryTransitionPlan(action="update_status", next_status=InquiryStatus.IN_PROGRESS)
        if target_status == InquiryStatus.COMPLETED:
            return InquiryTransitionPlan(action="complete_workflow", next_status=InquiryStatus.COMPLETED)
        raise InvalidTransitionError("지원하지 않는 상태 변경입니다.")

    def _acquire_inquiry_lock_or_raise(self, dedup_key: str, token: str) -> None:
        if self.redis_store.acquire_inquiry_lock(dedup_key, token):
            return

        if self._wait_for_confirmed_state(dedup_key):
            raise self._duplicate_error()
        raise InquiryProcessingError("동일한 문의가 처리 중입니다. 잠시 후 다시 시도해주세요.")

    def _wait_for_confirmed_state(self, dedup_key: str) -> bool:
        for _ in range(self.inquiry_lock_retry_attempts):
            time.sleep(self.inquiry_lock_retry_delay_seconds)
            current_state = self.redis_store.get_inquiry_state(dedup_key)
            if current_state.get("status") == INQUIRY_STATE_CONFIRMED:
                return True
        return False

    def _raise_if_confirmed(self, dedup_key: str) -> None:
        current_state = self.redis_store.get_inquiry_state(dedup_key)
        if current_state.get("status") == INQUIRY_STATE_CONFIRMED:
            raise self._duplicate_error()

    def _mark_pending(self, dedup_key: str, request_id: str) -> None:
        self.redis_store.set_inquiry_state(dedup_key, status=INQUIRY_STATE_PENDING, request_id=request_id)

    def _mark_confirmed(self, dedup_key: str, request_id: str, notion_page_id: str) -> None:
        self.redis_store.set_inquiry_state(
            dedup_key,
            status=INQUIRY_STATE_CONFIRMED,
            request_id=request_id,
            notion_page_id=notion_page_id,
        )
        self.redis_store.record_page_mapping(notion_page_id, dedup_key)

    def _mark_failed(self, dedup_key: str, request_id: str, *, error_code: str) -> None:
        self.redis_store.set_inquiry_state(
            dedup_key,
            status=INQUIRY_STATE_FAILED,
            request_id=request_id,
            error_code=error_code,
        )

    def _duplicate_error(self) -> DuplicateInquiryError:
        return DuplicateInquiryError("동일한 이름과 제목의 문의가 이미 등록되어 있습니다.")


def compute_dedup_key(name: str, title: str) -> str:
    normalized_name = _normalize(name)
    normalized_title = _normalize(title)
    return hashlib.sha256(f"{normalized_name}:{normalized_title}".encode("utf-8")).hexdigest()


def _normalize(value: str) -> str:
    return " ".join(value.strip().lower().split())
