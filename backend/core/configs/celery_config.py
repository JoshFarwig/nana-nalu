from pydantic import BaseModel, ConfigDict, Field


class CeleryConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    # TODO: set up config for celery once we get there
    # refer to https://docs.celeryq.dev/en/v5.5.3/userguide/configuration.html

    # NOTE: for production, run worker in the background as described in daemonization,
    # could setup celery beat/worker in same container with daemonization
    # https://docs.celeryq.dev/en/v5.5.3/userguide/daemonizing.html#daemonizing

    # general settings
    # task_routes: dict[str, str]
    # task_annotations: dict[str, str]

    # container mode - controls task/dependency loading
    # set via CELERY__WORKER env var:
    #   - true: worker mode - imports all tasks and dependencies (SQLAlchemy, numpy, etc.)
    #   - false: scheduler mode - lazy loads task names only (beat/flower)
    worker: bool = False

    # worker settings
    worker_pool: str = "prefork"
    worker_concurrency: int = 2
    worker_max_tasks_per_child: int = 100
