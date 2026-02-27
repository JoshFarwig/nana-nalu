from http import HTTPStatus
from core.exceptions.base import NanaNaluException


class ConditionProfileError(NanaNaluException):
    """Base exception for condition profile errors"""

    def __init__(
        self,
        message: str,
        error_code: str | None = "condtion_profile_error",
        status_code: int | None = HTTPStatus.INTERNAL_SERVER_ERROR,
        details: dict | None = None,
    ):
        super().__init__(message, error_code, status_code, details)


class ConditionProfileNotFoundError(ConditionProfileError):
    def __init__(self, identifier: int | set | str, field: str):
        super().__init__(
            message=f"Condition profile with {field} '{identifier}' could not be found.",
            error_code="condition_profile_not_found",
            status_code=HTTPStatus.NOT_FOUND,
            details={"field": field, "value": str(identifier)},
        )


class ConditionProfilePermissionError(ConditionProfileError):
    def __init__(self, user_id: int, condition_profile_id: int, action: str):
        super().__init__(
            message=f"You don't have permission to {action} this condition profile",
            error_code="condition_profile_permission_denied",
            status_code=HTTPStatus.FORBIDDEN,
            details={
                "user_id": user_id,
                "condition_profile_id": condition_profile_id,
                "action": action,
            },
        )
