import logging
from typing import Callable, Awaitable, Any, Literal
from types import TracebackType

logger = logging.getLogger(__name__)


class SagaContext:
    """
    Context manager for orchestrating multi-step operations with automatic rollback.

    Implements the Saga pattern for distributed transactions across multiple services,
    databases, and external APIs. When operations span systems that don't support
    traditional ACID transactions (Redis + Database + Email API), this provides
    compensating transaction capabilities.

    Key Concepts:
        - Forward operations: Normal business logic (create user, send email, etc.)
        - Compensating actions: Rollback functions that undo completed steps
        - Execution order: Rollbacks run in REVERSE order of registration

    Example:
        ```python
        async with SagaContext() as saga:
            # Step 1: Issue tokens
            tokens = await auth_service._issue_auth_token_pair(user)
            saga.add_rollback(
                auth_service._revoke_refresh_token,
                tokens.refresh_token,
                user.id
            )

            # Step 2: Create magic link
            magic_token = await magic_link_service.create_link(...)
            saga.add_rollback(
                magic_link_service.invalidate_link,
                "email_verification",
                magic_token
            )

            # Step 3: Send email (if this fails, steps 1-2 auto-rollback)
            await email_service.send_email_verification(...)
        ```

    When to Use:
        - Operations span multiple services/datastores
        - No single database transaction can cover all steps
        - Later steps can fail after earlier steps succeed
        - You need predictable cleanup on failure

    When NOT to Use:
        - Single database operations (use DB transactions instead)
        - All operations are in the same transactional boundary
        - Rollback isn't necessary or possible
    """

    def __init__(self):
        """Initialize empty list of compensating actions."""
        self._rollback_actions: list[
            tuple[Callable[..., Awaitable[Any]], tuple[Any, ...], dict[str, Any]]
        ] = []

    def add_rollback(
        self,
        action: Callable[..., Awaitable[Any]],
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """
        Register a compensating action to execute if the saga fails.

        Rollback actions are executed in REVERSE order of registration (LIFO).
        This ensures proper cleanup: if you create A then B, you undo B then A.

        Args:
            action: Async function to call during rollback
            *args: Positional arguments to pass to the action
            **kwargs: Keyword arguments to pass to the action

        Example:
            ```python
            saga.add_rollback(delete_user, user_id)
            saga.add_rollback(revoke_token, token, user_id=123)
            ```
        """
        self._rollback_actions.append((action, args, kwargs))
        logger.debug(
            f"Registered rollback action: {action.__name__}",
            extra={"total_actions": len(self._rollback_actions)},
        )

    async def __aenter__(self) -> "SagaContext":
        """Enter the saga context."""
        logger.debug("Saga started")
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> Literal[False]:
        """
        Exit the saga context, executing rollbacks if an exception occurred.

        If no exception: saga succeeded, no rollbacks needed
        If exception: execute all registered compensating actions in reverse order

        Args:
            exc_type: Exception class (if exception occurred)
            exc_val: Exception instance (if exception occurred)
            exc_tb: Exception traceback (if exception occurred)

        Returns:
            False to propagate the original exception after rollbacks complete
        """
        if exc_type is not None:
            logger.warning(
                f"Saga failed with {exc_type.__name__}, executing {len(self._rollback_actions)} compensating actions",
                extra={"exception": str(exc_val)},
            )

            # execute compensating transactions in reverse order (LIFO)
            for action, args, kwargs in reversed(self._rollback_actions):
                try:
                    await action(*args, **kwargs)
                    logger.debug(f"Rollback action {action.__name__} succeeded")
                except Exception as rollback_error:
                    # log but don't raise - we're already handling the original error
                    # failing rollbacks shouldn't mask the original exception
                    logger.error(
                        f"Rollback action {action.__name__} failed during saga compensation",
                        extra={
                            "action": action.__name__,
                            "rollback_error": str(rollback_error),
                            "original_error": str(exc_val),
                        },
                        exc_info=rollback_error,
                    )
        else:
            logger.debug("Saga completed successfully, no rollbacks needed")

        # return False to propagate the original exception
        return False
