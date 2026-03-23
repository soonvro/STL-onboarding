from __future__ import annotations

from dataclasses import dataclass


DATABASE_PROPERTY_SPECS: dict[str, str] = {
    "Title": "title",
    "Name": "rich_text",
    "Email": "email",
    "Phone": "phone_number",
    "Body": "rich_text",
    "DedupKey": "rich_text",
    "Resolution": "rich_text",
    "CreatedAt": "created_time",
    "UpdatedAt": "last_edited_time",
}

CREATABLE_DATABASE_PROPERTIES: dict[str, dict[str, object]] = {
    "Title": {"title": {}},
    "Name": {"rich_text": {}},
    "Email": {"email": {}},
    "Phone": {"phone_number": {}},
    "Body": {"rich_text": {}},
    "DedupKey": {"rich_text": {}},
    "Resolution": {"rich_text": {}},
    "CreatedAt": {"created_time": {}},
    "UpdatedAt": {"last_edited_time": {}},
}

STATUS_PROPERTY_NAME = "Status"
STATUS_PROPERTY_TYPE = "status"
STATUS_OPTION_NAMES = ["Registered", "In Progress", "Completed"]
FORBIDDEN_PROPERTY_NAMES = ["RequestId"]
STATUS_NAME_MAPPING = {
    "등록됨": "Registered",
    "처리중": "In Progress",
    "완료됨": "Completed",
}


@dataclass(slots=True)
class SchemaIssue:
    property_name: str
    message: str

    def render(self) -> str:
        return f"{self.property_name}: {self.message}"


def _property_type(property_object: dict[str, object]) -> str | None:
    property_type = property_object.get("type")
    return property_type if isinstance(property_type, str) else None


def _status_option_names(property_object: dict[str, object]) -> list[str]:
    status_object = property_object.get("status")
    if not isinstance(status_object, dict):
        return []

    options = status_object.get("options")
    if not isinstance(options, list):
        return []

    names: list[str] = []
    for option in options:
        if isinstance(option, dict):
            name = option.get("name")
            if isinstance(name, str):
                names.append(name)
    return names


def validate_data_source_schema(
    properties: dict[str, dict[str, object]],
    *,
    require_status: bool,
) -> list[SchemaIssue]:
    issues: list[SchemaIssue] = []

    for property_name, expected_type in DATABASE_PROPERTY_SPECS.items():
        actual = properties.get(property_name)
        if actual is None:
            issues.append(SchemaIssue(property_name, f"missing required property of type {expected_type}"))
            continue

        actual_type = _property_type(actual)
        if actual_type != expected_type:
            issues.append(
                SchemaIssue(property_name, f"expected type {expected_type}, found {actual_type or 'unknown'}")
            )

    for property_name in FORBIDDEN_PROPERTY_NAMES:
        if property_name in properties:
            issues.append(SchemaIssue(property_name, "unexpected property; remove it from the Notion data source"))

    if not require_status:
        return issues

    status_property = properties.get(STATUS_PROPERTY_NAME)
    if status_property is None:
        issues.append(
            SchemaIssue(
                STATUS_PROPERTY_NAME,
                "missing required property; create it manually in Notion UI as a status property",
            )
        )
        return issues

    actual_status_type = _property_type(status_property)
    if actual_status_type != STATUS_PROPERTY_TYPE:
        issues.append(
            SchemaIssue(
                STATUS_PROPERTY_NAME,
                f"expected type {STATUS_PROPERTY_TYPE}, found {actual_status_type or 'unknown'}",
            )
        )
        return issues

    option_names = _status_option_names(status_property)
    if option_names != STATUS_OPTION_NAMES:
        issues.append(
            SchemaIssue(
                STATUS_PROPERTY_NAME,
                "expected options "
                + ", ".join(STATUS_OPTION_NAMES)
                + "; found "
                + (", ".join(option_names) if option_names else "none"),
            )
        )

    return issues
