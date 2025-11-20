# Async Code with Celery Workers: Production Patterns and Technical Considerations

**Celery does not officially support native async/await patterns with asyncio**, despite earlier promises in the 4.x documentation. This fundamental limitation shapes every architectural decision when combining FastAPI's async capabilities with Celery's synchronous task model. The optimal approach requires separate connection pools for FastAPI and Celery, careful worker initialization using the correct signals, and understanding when multiprocessing—not threading—delivers true performance gains for CPU-bound operations.

This reality impacts how you structure async SQLAlchemy engines, manage connection pools, and handle async Redis managers. Production systems successfully navigate these constraints by keeping FastAPI fully async, wrapping async operations in Celery tasks with `asyncio.run()`, and using **separate engines with NullPool or small connection pools (2-3 connections) for Celery workers**. For CPU-intensive operations like xarray/GRIB parsing, `asyncio.to_thread()` provides minimal benefit due to Python's Global Interpreter Lock—multiprocessing with ProcessPoolExecutor delivers 10× better performance. The key is understanding that FastAPI and Celery represent fundamentally different concurrency models that must be bridged carefully rather than forcibly unified.

## Sharing async SQLAlchemy engines between FastAPI and Celery workers

The cardinal rule is simple: **never share AsyncEngine instances between FastAPI and Celery workers**. This stems from both concurrency model incompatibilities and multiprocessing constraints around connection pooling. FastAPI operates with async/await throughout its request handling, requiring AsyncEngine with AsyncAdaptedQueuePool. Celery tasks, by contrast, are synchronous by default and should use standard synchronous engines even when wrapping async code internally.

The recommended pattern uses completely separate engine instances. FastAPI gets an async engine configured with substantial connection pooling since it handles many concurrent HTTP requests—typically `pool_size=20` with `max_overflow=30`. Celery workers use synchronous engines with either NullPool (safest) or minimal pooling like `pool_size=2` and `max_overflow=3`. This separation prevents the most common production failure: sharing pooled database connections across process boundaries. When a prefork worker process starts, it inherits the parent's connection pool containing open TCP connections. These file descriptors work across process boundaries but cause catastrophic failures when multiple processes attempt concurrent access to the same underlying socket connection.

SQLAlchemy's official documentation provides three approaches for multiprocessing safety. The first and simplest is using NullPool, which creates a fresh connection for each operation without any connection reuse. While this incurs higher overhead, it eliminates shared connection problems entirely. Production configurations for Celery workers look like this:

```python
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

celery_engine = create_engine(
    "postgresql://user:pass@host/dbname",
    poolclass=NullPool,
    pool_pre_ping=True
)
```

The second approach maintains small connection pools but requires calling `engine.dispose(close=False)` in each worker process during initialization. This method, added in SQLAlchemy 1.4.33, clears the child process's inherited connection pool without affecting the parent process. Implementation uses Celery's `worker_process_init` signal:

```python
from celery.signals import worker_process_init, worker_process_shutdown

@worker_process_init.connect
def init_worker(**kwargs):
    from database import celery_engine
    celery_engine.dispose(close=False)

@worker_process_shutdown.connect
def shutdown_worker(**kwargs):
    from database import celery_engine
    celery_engine.dispose()
```

The third approach implements process-level connection detection using SQLAlchemy events, tracking which process ID owns each connection and raising DisconnectionError when a connection from another process is detected. This prevents connection sharing but requires more complex event handler setup.

For FastAPI, the async engine initialization remains straightforward. The async session factory uses context managers to ensure proper cleanup, typically implemented as a FastAPI dependency. Critical configuration includes `expire_on_commit=False` to prevent additional database queries when accessing already-loaded objects after commit, and proper disposal during application shutdown to prevent "Event loop is closed" warnings. The complete pattern separates concerns cleanly: FastAPI handles async HTTP with its own connection pool, Celery handles background work with isolated per-process connection management, and both connect to the same database through different engines.

## Using asyncio.run() versus asyncio.to_thread() in Celery tasks

The distinction between these two functions reveals a fundamental truth about Celery's async limitations and the correct patterns for bridging synchronous task execution with async code. Celery tasks are synchronous functions—even when decorated with `@celery_app.task`, they execute in a synchronous context. This means you cannot directly define async tasks using `async def` with standard Celery pools. The workaround pattern wraps async logic inside synchronous task functions.

`asyncio.run()` serves as the entry point for executing async code from synchronous contexts. It creates a new event loop, runs the provided coroutine until completion, then closes the event loop. This makes it the natural choice for Celery tasks with the prefork pool:

```python
@celery_app.task
def fetch_data_task(url: str):
    async def fetch():
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                return await response.json()
    
    return asyncio.run(fetch())
```

The critical limitation is that `asyncio.run()` cannot be called when an event loop is already running. This becomes problematic if you use Celery with gevent or eventlet pools, which maintain their own event loops. Attempting `asyncio.run()` in these contexts raises `RuntimeError: This event loop is already running`. For gevent/eventlet pools, alternatives include using the pool's native concurrency primitives or more complex workarounds with `asyncio.new_event_loop()` and manual event loop management.

`asyncio.to_thread()`, introduced in Python 3.9, serves an entirely different purpose. It's designed to run blocking I/O operations in a separate thread without blocking the event loop. The official documentation explicitly states it's "primarily intended to be used for executing IO-bound functions/methods that would otherwise block the event loop." This function is a coroutine that must be awaited, meaning it only makes sense when you're already in an async context with a running event loop.

The confusion arises when developers attempt to use `asyncio.to_thread()` inside Celery tasks for CPU-bound operations. This fundamentally misunderstands both the function's purpose and Python's threading limitations. Even if you create a running event loop in your Celery task and await `asyncio.to_thread()` for CPU-intensive work, the Global Interpreter Lock ensures only one thread executes Python bytecode at a time. Benchmarks demonstrate that threading actually slows CPU-bound operations: a CPU-intensive task taking 35 seconds synchronously takes 39 seconds with threading due to context switching overhead.

The correct pattern for CPU-bound operations in Celery tasks uses ProcessPoolExecutor, which provides true parallelism by running code in separate Python interpreter processes, each with its own GIL. When you need to call CPU-intensive async code from Celery tasks, wrap the ProcessPoolExecutor usage in an async function and execute it with `asyncio.run()`. This pattern enables concurrent CPU-bound operations while maintaining compatibility with Celery's synchronous task model.

## Connection pool sizing strategies for Celery workers with async database connections

Calculating appropriate connection pool sizes requires understanding the multiplication effect across worker processes. With prefork workers, each process maintains its own connection pool. A common mistake is configuring generous pool sizes that multiply across workers, exhausting database connection limits. The formula is straightforward: total possible connections equals the number of worker processes multiplied by pool_size plus max_overflow per process.

Consider a deployment with 10 Celery worker processes. If each uses the default QueuePool with `pool_size=5` and `max_overflow=10`, your application could open up to 150 simultaneous database connections (10 × 15). Most PostgreSQL installations default to 100 maximum connections, immediately causing "too many connections" errors under moderate load. This multiplication trap catches many production deployments.

The conservative approach for Celery workers uses small pools or NullPool. For workers that make infrequent database queries, NullPool provides the safest option with minimal overhead. Each database operation opens a fresh connection and closes it upon completion. While this eliminates connection reuse benefits, it guarantees process safety and prevents connection exhaustion. Production configurations pair this with `pool_pre_ping=True` for connection health checks and `pool_recycle=3600` to prevent stale connections:

```python
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

celery_engine = create_engine(
    DATABASE_URL,
    poolclass=NullPool,
    pool_pre_ping=True,
    echo=False
)
```

When tasks make frequent database calls, small persistent pools provide better performance while maintaining safety. The recommended configuration uses `pool_size=2` with `max_overflow=3` per worker process. This balances connection reuse benefits against the connection count multiplication. Ten workers with this configuration reach a maximum of 50 total connections—well within typical database limits while providing adequate concurrency for most workloads. The key requirement is calling `engine.dispose(close=False)` in `worker_process_init` to clear inherited connections from the parent process.

For FastAPI with async SQLAlchemy, connection pool sizing follows different principles since the application typically runs as a single process (or a small number of processes behind a load balancer). Here, generous pooling makes sense: `pool_size=20` with `max_overflow=30` supports 50 concurrent database operations per process. The AsyncEngine automatically uses AsyncAdaptedQueuePool, which is asyncio-compatible. The standard QueuePool is incompatible with async engines and should never be explicitly specified for async database connections.

The decision matrix for pool configuration depends on your workload characteristics. Low-concurrency background tasks with infrequent database access should use NullPool for maximum simplicity and safety. Medium-concurrency workers making regular database queries benefit from small pools (2-5 connections) with proper initialization. Only single-process async applications should use large pools (20+ connections). High-concurrency gevent/eventlet workers need substantial pooling because a single process runs many concurrent greenlets—configure `pool_size=20` or higher since you're not multiplying across processes.

A critical but often overlooked consideration is monitoring actual connection usage in production. PostgreSQL provides `pg_stat_activity` to view active connections, while MySQL offers `SHOW PROCESSLIST`. Tracking idle connections versus active connections helps optimize pool sizes. Many production issues stem from idle connections accumulating due to tasks that don't properly close sessions. Implementing proper session lifecycle management in Celery tasks, typically through a base task class with `after_return` cleanup, prevents these leaks.

## Worker initialization signals: worker_init versus worker_process_init with prefork pool

These two signals fire at different points in the worker lifecycle and in different processes, creating common confusion that leads to production bugs. Understanding when each signal executes is critical for correct resource initialization, especially for database connections and async infrastructure.

`worker_init` fires once when the worker instance starts, executing in the main worker process before any child processes are forked. With the prefork pool, this means the signal runs in the parent process that manages child worker processes but does not execute in those child processes themselves. This signal is appropriate for global configuration that applies to the entire worker instance—loading configuration files, setting up logging infrastructure, or registering signal handlers. It is **not** appropriate for initializing resources that will be used by tasks, since tasks execute in child processes.

A critical platform-specific issue exists on Windows: child processes in the prefork pool do not emit `worker_init` signals at all (GitHub issue #7573). This Windows-specific behavior means any initialization code in `worker_init` handlers will not run in the processes actually executing tasks. Cross-platform applications must use `worker_process_init` for any task-critical initialization.

`worker_process_init` solves the child process initialization problem by firing in each pool child process when it starts. With prefork pools, this signal runs once per child process, making it the correct location for per-process resource initialization. Database connections, thread-local state, and async infrastructure should initialize here. The signal includes a timeout constraint: handlers must complete within 4 seconds by default, configurable via `worker_proc_alive_timeout` since Celery 4.4.0. Exceeding this timeout causes worker startup failures.

The behavior across pool types reveals why signal choice matters. With prefork (default), `worker_init` runs in the main process only while `worker_process_init` runs in each child process. With solo, eventlet, or gevent pools, `worker_init` runs but `worker_process_init` never fires since these pools don't use multiprocessing. The threads pool behaves similarly to prefork, with `worker_process_init` firing in each thread. This pool-specific behavior means initialization logic must account for which pool types your deployment uses.

The correct pattern for database connection initialization with prefork demonstrates proper signal usage:

```python
from celery.signals import worker_init, worker_process_init, worker_process_shutdown

@worker_init.connect
def setup_logging(sender=None, **kwargs):
    """Main process: configure logging infrastructure"""
    import logging
    logging.basicConfig(level=logging.INFO)
    logging.info(f"Worker {sender} starting")

@worker_process_init.connect
def init_worker_process(sender=None, **kwargs):
    """Each child process: initialize database connections"""
    import os
    from database import celery_engine
    
    # Clear inherited connection pool from parent
    celery_engine.dispose(close=False)
    
    print(f"Worker process {os.getpid()} initialized")

@worker_process_shutdown.connect
def shutdown_worker_process(sender=None, **kwargs):
    """Each child process: cleanup on shutdown"""
    from database import celery_engine
    celery_engine.dispose()
```

For async infrastructure requiring an event loop per worker process, `worker_process_init` is the appropriate initialization point. Some production systems maintain a single event loop per worker process using a background thread running `loop.run_forever()`, initialized in this signal. Tasks then submit coroutines to this loop using `asyncio.run_coroutine_threadsafe()`. While not officially supported by Celery, this pattern solves problems with sharing async resources like SQLAlchemy async sessions that cannot be created repeatedly with `asyncio.run()`.

## Performance implications of asyncio.to_thread() for CPU-bound operations like xarray and GRIB parsing

The fundamental misunderstanding about `asyncio.to_thread()` for CPU-bound operations stems from confusion about Python's threading model and the Global Interpreter Lock. Threading in Python provides concurrency for I/O-bound operations but not parallelism for CPU-bound work. This distinction is crucial when dealing with data-intensive operations like xarray dataset manipulation and GRIB file parsing.

`asyncio.to_thread()` executes a function in a thread from the default ThreadPoolExecutor. For I/O-bound operations like network requests or file reads, this provides excellent performance by allowing the event loop to continue processing other tasks while blocking I/O occurs in the background thread. Benchmarks show 29× speedup for I/O-bound workloads compared to synchronous execution. However, for CPU-bound operations, the GIL ensures only one thread executes Python bytecode at any time, eliminating any parallelism benefits.

Concrete benchmarking data illustrates the performance impact. A CPU-intensive Fibonacci calculation taking 35 seconds synchronously takes 39 seconds with threading (slower due to context switching overhead) and 86 seconds with asyncio (much slower due to event loop management overhead). The same workload with multiprocessing using ProcessPoolExecutor completes in 10 seconds—3.5× faster than synchronous execution through true parallel execution across CPU cores.

For xarray and GRIB parsing specifically, the performance characteristics reveal why threading provides no benefits. The cfgrib library, which xarray uses for GRIB file access, exhibits severe performance issues for large files. A 2 MB GRIB file loads instantly, but a 20 MB file can take several minutes. Files around 100 MB require 5-10 minutes to load with approximately 40× memory overhead—a 100 MB GRIB file consumes 4 GB of RAM during loading. These operations are CPU-intensive: parsing binary formats, decompressing data, building coordinate systems, and constructing numpy arrays. None of this work benefits from threading due to the GIL.

The correct approach for GRIB parsing in Celery tasks uses ProcessPoolExecutor for true parallel processing across files:

```python
from concurrent.futures import ProcessPoolExecutor
import xarray as xr

def parse_grib_file(filepath):
    """CPU-intensive: should run in separate process"""
    ds = xr.open_dataset(filepath, engine="cfgrib")
    result = ds.compute()
    ds.close()
    return result.to_dict()

@celery_app.task
def process_grib_batch(file_paths):
    """Celery task: distribute across CPU cores"""
    import os
    cpu_count = os.cpu_count()
    
    with ProcessPoolExecutor(max_workers=cpu_count) as executor:
        results = list(executor.map(parse_grib_file, file_paths))
    
    return results
```

This pattern provides genuine parallelism since each subprocess has its own Python interpreter and GIL. Four files parsing simultaneously on a 4-core machine complete in roughly the same time as parsing one file, rather than taking 4× as long.

For large datasets requiring processing beyond simple parsing, xarray integrates with Dask for parallel computation. Dask can use either a threaded scheduler (default) or multiprocessing scheduler. For CPU-intensive operations, explicitly configuring the multiprocessing scheduler delivers substantially better performance:

```python
import dask
import dask.multiprocessing

dask.set_options(get=dask.multiprocessing.get)

# Now xarray operations use multiprocessing
ds = xr.open_dataset("large_file.grib", engine="cfgrib")
chunked_ds = ds.chunk({"time": 100})
result = chunked_ds.mean(dim="time").compute()  # Runs in parallel
```

An alternative optimization converts GRIB to NetCDF format in a one-time preprocessing step. Subsequent access is dramatically faster since NetCDF has better internal indexing and compression. This preprocessing approach makes sense when the same data will be accessed repeatedly by multiple tasks.

Memory management becomes critical for GRIB processing. The 40× memory overhead means a single 100 MB file requires 4 GB RAM. With multiple worker processes potentially loading files simultaneously, memory exhaustion occurs rapidly. Strategies include chunked processing with xarray's lazy loading, explicit cleanup and garbage collection after each file, and configuring Celery's `worker_max_tasks_per_child` and `worker_max_memory_per_child` settings to recycle worker processes before memory exhaustion.

## Choosing between NullPool and small connection pools for Celery workers

This decision balances performance against safety and operational complexity. NullPool represents the simplest, safest option, while small persistent pools offer performance benefits at the cost of correct initialization requirements. Understanding the tradeoffs helps make informed decisions for production deployments.

NullPool creates a new database connection for each operation and immediately closes it afterward. No connection state persists between operations. This eliminates all issues related to connection reuse, shared connections across processes, and connection pool exhaustion. The overhead of connection establishment appears in every query, but for modern databases on low-latency networks, this typically adds only 1-5 milliseconds per operation—negligible for background tasks that aren't latency-sensitive.

The compelling advantage of NullPool is operational simplicity. No initialization signals are required. No disposal calls are needed in worker startup. Forking behavior doesn't matter. The pattern works identically across all Celery pool types. When database access patterns are infrequent—tasks that make only a few queries or run sporadically—the connection overhead is insignificant compared to task processing time. Production systems processing nightly batch jobs or hourly data imports often use NullPool successfully because the connection overhead is dwarfed by actual processing time.

Small connection pools with 2-3 connections per worker provide connection reuse benefits while maintaining manageable total connection counts. With proper initialization using `worker_process_init` to call `engine.dispose(close=False)`, this approach works reliably in production. The performance benefit appears primarily in tasks making many sequential database queries. Instead of paying connection establishment overhead for each query, the task reuses an existing connection from the pool. For tasks executing hundreds or thousands of queries, this accumulated overhead reduction becomes significant.

The decision matrix considers several factors. Task frequency matters: tasks running continuously benefit from connection reuse, while sporadic tasks don't. Query patterns within tasks influence the choice—single queries per task gain little from pooling, while tasks with many queries benefit substantially. Database connection limits constrain choices—strict connection limits favor NullPool to minimize total connections. Operational complexity tolerance affects the decision—teams comfortable with Celery signals and connection pool management can use small pools, while teams preferring simplicity should choose NullPool.

A hybrid approach deploys different engines for different task types within the same application. Long-running data processing tasks that make continuous database queries use small pools for efficiency. Quick administrative tasks that make single queries use NullPool for simplicity. Celery's task routing functionality directs tasks to different queues served by workers configured with different engines and pool types.

For connection pool configuration with persistent pools, key parameters include `pool_size=2` for the number of persistent connections, `max_overflow=3` allowing temporary additional connections during spikes, `pool_pre_ping=True` to verify connection health before use, and `pool_recycle=3600` to close and recreate connections after one hour to prevent stale connection accumulation. These settings balance performance and reliability for production workloads.

Testing both approaches in staging environments with representative workloads provides empirical data for the decision. Monitor database connection counts, task execution times, and connection establishment overhead. Many production deployments successfully run NullPool for all Celery workers because the simplicity benefits outweigh the small performance cost for typical background task workloads.

## Handling async Redis managers in Celery workers

Redis serves multiple roles in typical FastAPI-plus-Celery architectures: message broker for Celery task queue, result backend for task status and return values, caching layer for application data, and coordination mechanism for distributed locks and pub/sub. Managing async Redis connections in Celery workers presents similar challenges to database connections, with additional complexity from event loop lifecycle issues.

The fundamental problem mirrors database connection management: async Redis connections and connection pools bind to specific event loops. When using `asyncio.run()` in Celery tasks, each invocation creates a new event loop, executes the coroutine, and closes the loop. Async Redis clients or connection pools created outside this context—such as at module level or in worker startup—bind to an event loop that no longer exists when the task executes. Attempting to use these connections raises errors like "Event loop is closed" or "Task got Future attached to a different loop."

The simplest pattern creates fresh Redis connections within each `asyncio.run()` context:

```python
import aioredis

@celery_app.task
def process_with_redis(data):
    async def task_impl():
        redis = await aioredis.create_redis_pool('redis://localhost')
        try:
            await redis.set('key', 'value')
            result = await redis.get('key')
            return result
        finally:
            redis.close()
            await redis.wait_closed()
    
    return asyncio.run(task_impl())
```

This approach guarantees the Redis connection exists in the same event loop context where it's used. The disadvantage is connection overhead—each task execution establishes a new Redis connection and closes it afterward. For Redis, this overhead is typically lower than database connections since Redis is single-threaded and optimized for rapid connection handling. However, for high-frequency tasks, the accumulated overhead becomes noticeable.

For Celery's internal use of Redis as broker and result backend, separate configuration controls connection pooling. Celery's Redis support includes its own connection pool management independent of application-level async Redis usage. Key configuration parameters include `broker_pool_limit` controlling the maximum number of connections in the broker pool, `redis_max_connections` setting the maximum connections per pool, and `broker_transport_options` allowing detailed Redis client configuration including timeouts and keepalive settings.

A common production issue involves connection pool multiplication. Celery creates approximately 8 connection pools at startup—separate pools for broker operations, result backend operations, and various internal subsystems. If each pool allows 30 connections, a single Celery worker can open 240 Redis connections. With multiple workers, this quickly exhausts Redis's connection limit (default 10,000 connections, but often configured lower).

The solution limits broker pooling explicitly:

```python
# celeryconfig.py
broker_pool_limit = 10  # Maximum connections in broker pool
redis_max_connections = 50  # Per-worker connection limit
broker_transport_options = {
    'max_connections': 10,
    'socket_keepalive': True,
    'socket_keepalive_options': {
        'TCP_KEEPIDLE': 30,
        'TCP_KEEPINTVL': 10,
        'TCP_KEEPCNT': 3,
    },
    'socket_timeout': 10.0,
    'retry_on_timeout': True
}
```

Some production deployments on platforms with strict connection limits (like Heroku Redis) disable connection pooling entirely by setting `broker_pool_limit = None`. This forces Celery to create new connections as needed and close them immediately after use—similar to the NullPool pattern for databases.

For application-level async Redis usage beyond Celery's internal needs, production systems implement distributed locking and coordination patterns. Redis locks ensure only one task processes a particular resource at a time. FastAPI endpoints use these locks to prevent concurrent task submission:

```python
from redis import Redis
from redis.lock import Lock as RedisLock
from fastapi import FastAPI, HTTPException

app = FastAPI()
redis_client = Redis.from_url("redis://localhost")

@app.post("/start-processing")
async def start_processing(data: dict):
    lock = RedisLock(redis_client, name="processing_lock", timeout=300)
    
    try:
        acquired = lock.acquire(blocking_timeout=4)
        if not acquired:
            raise HTTPException(status_code=503, detail="Another task is running")
        
        # Check if task is already running
        current_task_id = redis_client.get("current_task")
        if current_task_id:
            result = celery_app.AsyncResult(current_task_id)
            if not result.ready():
                raise HTTPException(status_code=400, detail="Task already running")
        
        # Submit new task
        task = process_data.delay(data)
        redis_client.set("current_task", task.id)
        
        return {"task_id": task.id}
    finally:
        lock.release()
```

This pattern uses synchronous Redis clients in FastAPI (though async clients work similarly) to coordinate Celery task submission. The lock acquisition happens in the API layer, preventing race conditions when multiple requests arrive simultaneously.

For advanced cases requiring persistent async Redis connections across multiple tasks, the single event loop pattern uses a background thread running an event loop continuously throughout the worker process lifetime. This thread is initialized in `worker_process_init`, and tasks submit coroutines to it using `asyncio.run_coroutine_threadsafe()`. While more complex, this approach enables sharing async resources like Redis connection pools across many task executions. However, the operational complexity typically outweighs benefits except for extremely high-frequency task execution with heavy Redis usage.

## Real-world production examples of async code sharing between FastAPI and Celery

Production architectures from companies deploying FastAPI with Celery reveal consistent patterns that balance framework capabilities with operational requirements. These systems maintain clear separation between FastAPI's async HTTP handling and Celery's synchronous task execution while enabling efficient code sharing for business logic.

TestDriven.io published a comprehensive production guide demonstrating Docker-based deployment with three services: FastAPI web application, Celery workers, and Redis for both message brokering and result storage. Their architecture uses async FastAPI endpoints to receive requests and immediately return task IDs, allowing Celery workers to process work asynchronously. The pattern includes Flower monitoring dashboard for production visibility into task execution, worker scaling via Docker Compose (`docker-compose up --scale worker=3`), and comprehensive testing infrastructure covering both unit tests for task logic and integration tests for the full request-to-completion cycle.

Their code structure separates concerns cleanly. FastAPI endpoints remain fully async, using async libraries like `aiohttp` for external API calls. Celery tasks are defined as synchronous functions but wrap async operations internally when needed:

```python
# FastAPI endpoint
@app.post("/process", status_code=201)
async def process_request(payload: dict):
    task = process_data.delay(payload)
    return {"task_id": task.id}

# Celery task
@celery_app.task
def process_data(payload: dict):
    # Synchronous wrapper for async logic
    return asyncio.run(async_processing(payload))

async def async_processing(payload: dict):
    # Actual business logic using async libraries
    async with aiohttp.ClientSession() as session:
        results = await fetch_data(session, payload)
    return results
```

TheLorry, a delivery logistics company, implemented FastAPI with Celery and RabbitMQ for email sending, image processing, ML model training, and route optimization. Their production architecture uses task routing to distribute different workload types across specialized worker pools. I/O-bound tasks like email sending route to gevent workers with high concurrency (500+ greenlets), while CPU-bound ML training routes to prefork workers matched to CPU core counts. This routing pattern emerged from production experience where mixing workload types on single worker pools caused performance degradation:

```python
# celeryconfig.py
task_routes = {
    'tasks.send_email': {'queue': 'io_bound'},
    'tasks.train_model': {'queue': 'cpu_bound'},
    'tasks.process_image': {'queue': 'cpu_bound'},
    'tasks.fetch_data': {'queue': 'io_bound'},
}

# Start specialized workers
# celery -A app worker -Q io_bound -P gevent -c 500
# celery -A app worker -Q cpu_bound -P prefork -c 4
```

Their implementation uses task retry logic with exponential backoff for external service failures, parallel task execution with Celery groups for splitting large batch operations, and Flower deployed alongside production workers for real-time monitoring of task queues, worker health, and execution times.

A common production challenge involves async Redis connection management. One engineering team documented encountering "Event loop is closed" errors when sharing async Redis connection pools created at worker startup. Their solution moved Redis client initialization inside the `asyncio.run()` context of each task. While this adds connection overhead, it eliminated the event loop lifecycle issues that caused frequent production failures. For high-frequency tasks, they implemented a custom solution with a persistent event loop running in a background thread, though they noted the complexity makes it suitable only for critical high-throughput paths.

Production-ready GitHub repositories demonstrate full implementations. The testdrivenio/fastapi-celery repository includes Docker Compose orchestration, environment-based configuration, volume mounting for development hot reload, worker scaling capabilities, and complete testing infrastructure. Their Dockerfile setup shows proper service dependencies, health checks, and graceful shutdown handling. The sumanentc/fastapi-celery-rabbitmq-application repository demonstrates RabbitMQ as broker with parallel task execution using Celery's `group` primitive for distributing work across workers.

Database connection patterns in production consistently use separate engines. FastAPI initializes an async engine once at application startup with substantial connection pooling. Celery workers create synchronous engines, typically using NullPool for simplicity or small persistent pools with proper initialization signals. The separation prevents multiprocessing connection sharing issues while optimizing each component for its workload characteristics. Production configurations always enable `pool_pre_ping=True` for connection health checks and set `pool_recycle=3600` to prevent stale connection accumulation from long-lived workers.

One production system handling Jupyter notebook execution via API implemented distributed locking with Redis to ensure only one notebook executes at a time. Their FastAPI endpoint acquires a Redis lock before checking whether a task is already running and submitting new tasks only when no execution is in progress. This pattern prevents resource exhaustion from concurrent notebook executions while providing clear HTTP error responses when submission fails due to existing execution.

Error handling and retry logic appear consistently in production systems. Tasks configure retry behavior with `@task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3, 'countdown': 5})` for automatic retry with exponential backoff. Dead letter queue patterns route repeatedly failing tasks to separate queues for investigation. Circuit breakers wrap external API calls to prevent cascade failures when dependencies experience outages.

Production monitoring extends beyond Flower to include database connection count monitoring, Redis connection tracking, task execution time percentiles, worker process memory usage, and queue length metrics. These metrics drive capacity planning and alert on anomalous conditions like growing queue backlogs or connection pool exhaustion. Successful deployments treat monitoring as first-class infrastructure rather than an afterthought.

The consistent lesson from production systems is maintaining architectural clarity: FastAPI owns HTTP request handling with full async capabilities, Celery owns background task execution with synchronous task definitions that internally wrap async code when beneficial, separate connection pools prevent resource sharing issues, explicit task routing matches workload types to appropriate worker configurations, and comprehensive monitoring provides visibility into the full request-to-completion lifecycle. Systems that blur these boundaries by attempting to force fully async Celery or sharing resources between FastAPI and Celery encounter reliability and performance issues in production.