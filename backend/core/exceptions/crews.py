from http import HTTPStatus
from core.exceptions.base import NanaNaluException


class CrewError(NanaNaluException):
    """Base exception for crew errors"""

    def __init__(
        self,
        message: str,
        error_code: str | None = "crew_error",
        status_code: int | None = HTTPStatus.INTERNAL_SERVER_ERROR,
        details: dict | None = None,
    ):
        super().__init__(message, error_code, status_code, details)


class CrewNotFoundError(CrewError):
    """Raised when crew doesn't exist in database"""

    def __init__(self, crew_id: int):
        super().__init__(
            message=f"Crew with id '{crew_id}' not found",
            error_code="crew_not_found",
            status_code=HTTPStatus.NOT_FOUND,
            details={"crew_id": crew_id},
        )


class CrewQuotaExceededError(CrewError):
    """Raised when user has reached their max crew limit"""

    def __init__(self, user_id: int, current_count: int, max_allowed: int):
        super().__init__(
            message=f"Crew limit reached ({current_count}/{max_allowed}). Upgrade your tier for more crews.",
            error_code="crew_quota_exceeded",
            status_code=HTTPStatus.FORBIDDEN,
            details={
                "user_id": user_id,
                "current_count": current_count,
                "max_allowed": max_allowed,
            },
        )


class CrewFullError(CrewError):
    """Raised when crew has reached max member capacity"""

    def __init__(self, crew_id: int, current_count: int, max_members: int):
        super().__init__(
            message=f"Crew is full ({current_count}/{max_members} members).",
            error_code="crew_full",
            status_code=HTTPStatus.FORBIDDEN,
            details={
                "crew_id": crew_id,
                "current_count": current_count,
                "max_members": max_members,
            },
        )


class AlreadyCrewMemberError(CrewError):
    """Raised when user is already a member of the crew"""

    def __init__(self, user_id: int, crew_id: int):
        super().__init__(
            message="You are already a member of this crew",
            error_code="already_crew_member",
            status_code=HTTPStatus.CONFLICT,
            details={"user_id": user_id, "crew_id": crew_id},
        )


class NotCrewMemberError(CrewError):
    """Raised when user is not a member of the crew"""

    def __init__(self, user_id: int, crew_id: int):
        super().__init__(
            message="You are not a member of this crew",
            error_code="not_crew_member",
            status_code=HTTPStatus.FORBIDDEN,
            details={"user_id": user_id, "crew_id": crew_id},
        )


class CrewPermissionError(CrewError):
    """Raised when user doesn't have permission for a crew action"""

    def __init__(self, user_id: int, crew_id: int, action: str):
        super().__init__(
            message=f"You don't have permission to {action} this crew",
            error_code="crew_permission_denied",
            status_code=HTTPStatus.FORBIDDEN,
            details={"user_id": user_id, "crew_id": crew_id, "action": action},
        )


class CannotRemoveCreatorError(CrewError):
    """Raised when attempting to remove the crew creator"""

    def __init__(self, crew_id: int):
        super().__init__(
            message="Cannot remove the crew creator. Transfer ownership first or delete the crew.",
            error_code="cannot_remove_creator",
            status_code=HTTPStatus.FORBIDDEN,
            details={"crew_id": crew_id},
        )
