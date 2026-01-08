from http import HTTPStatus
from core.exceptions.base import NanaNaluException


class AccountTierError(NanaNaluException):
    """Base exception for forecast errors"""

    def __init__(
        self,
        message: str,
        error_code: str | None = "acccount_tier_error",
        status_code: int | None = HTTPStatus.INTERNAL_SERVER_ERROR,
        details: dict | None = None,
    ):
        super().__init__(message, error_code, status_code, details)


class AccountTierNotFoundError(AccountTierError):
    def __init__(self, identifier: int | str, field: str):
        """
        Args:
            identifier: The value that was searched for (value of the ID or name)
            field: The field that was searched ("id" or "name")
        """
        super().__init__(
            message=f"Account tier with {field} '{identifier}' not found",
            error_code="account_tier_not_found",
            status_code=HTTPStatus.NOT_FOUND,
            details={"field": field, "value": str(identifier)},
        )
