"""
Async and Sync repository variants coexist for different runtime contexts.

Async repos serve the FastAPI application layer where concurrent I/O matters.
Sync repos serve Prefect workflow tasks, which are lighter-weight per-workflow
and don't benefit from async nearly as much as the API does.
"""
