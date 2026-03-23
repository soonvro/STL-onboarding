from __future__ import annotations

import re
from enum import Enum

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


def collapse_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def validate_not_blank(value: str, *, field_name: str) -> str:
    normalized = collapse_whitespace(value)
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


PHONE_PATTERN = re.compile(r"^\+?[0-9().\-\s]{7,20}$")


class InquiryStatus(str, Enum):
    REGISTERED = "등록됨"
    IN_PROGRESS = "처리중"
    COMPLETED = "완료됨"


class InquiryCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    phone: str = Field(min_length=1, max_length=30)
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=5000)

    @field_validator("name", "title", "body")
    @classmethod
    def validate_non_blank_fields(cls, value: str, info: object) -> str:
        field_name = getattr(info, "field_name", "field")
        return validate_not_blank(value, field_name=field_name)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        normalized = collapse_whitespace(value)
        if not PHONE_PATTERN.fullmatch(normalized):
            raise ValueError("phone must be a valid phone number")
        return normalized


class InquiryUpdateRequest(BaseModel):
    status: InquiryStatus
    resolution: str | None = Field(default=None, max_length=5000)

    @field_validator("resolution")
    @classmethod
    def normalize_resolution(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_not_blank(value, field_name="resolution")

    @model_validator(mode="after")
    def validate_completed_requires_resolution(self) -> "InquiryUpdateRequest":
        if self.status == InquiryStatus.COMPLETED and not self.resolution:
            raise ValueError("resolution is required when status is 완료됨")
        return self


class AdminLoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=500)


class MessageResponse(BaseModel):
    status: str = "ok"
    message: str


class InquiryCreateResponse(BaseModel):
    status: str = "ok"
    code: str = "created"
    request_id: str
    message: str
    admin_email_status: str | None = None
    notion_page_id: str | None = None


class ErrorResponse(BaseModel):
    status: str = "error"
    code: str
    message: str
    request_id: str | None = None


class AdminSessionResponse(BaseModel):
    status: str = "ok"
    authenticated: bool


class InquiryListItem(BaseModel):
    id: str
    name: str
    email: str
    phone: str
    title: str
    status: InquiryStatus
    created_at: str


class InquiryListResponse(BaseModel):
    items: list[InquiryListItem]
    next_cursor: str | None = None


class InquiryDetailResponse(BaseModel):
    id: str
    name: str
    email: str
    phone: str
    title: str
    body: str
    status: InquiryStatus
    resolution: str | None
    created_at: str
    updated_at: str


class InquiryUpdateResponse(BaseModel):
    status: str = "ok"
    message: str
    inquiry: InquiryDetailResponse
