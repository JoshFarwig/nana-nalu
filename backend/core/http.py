import logging
import asyncio
import httpx
from functools import wraps

from core.configs.http_config import HTTPConfig

logger = logging.getLogger(__name__)


def retry_on_failure(func):
    """Decorator to add retry logic to async HTTP operations"""

    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        operation_name = func.__name__
        last_exception = None

        for attempt in range(self._max_retries):
            try:
                return await func(self, *args, **kwargs)

            except (httpx.NetworkError, httpx.TimeoutException) as e:
                last_exception = e
                if attempt < self._max_retries - 1:
                    delay = self._calculate_retry_delay(attempt)
                    logger.warning(
                        "Network error, retrying",
                        extra={
                            "method": operation_name,
                            "attempt": attempt + 1,
                            "max_retries": self._max_retries,
                            "error": str(e),
                            "retry_delay": delay,
                        },
                    )
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(
                        "Failed after retries",
                        extra={
                            "method": operation_name,
                            "max_retries": self._max_retries,
                            "error": str(e),
                        },
                    )
                    raise

            except httpx.HTTPStatusError as e:
                if e.response.status_code >= 500 or e.response.status_code == 429:
                    if attempt < self._max_retries - 1:
                        delay = self._calculate_retry_delay(attempt)
                        logger.warning(
                            f"HTTP {e.response.status_code}, retrying",
                            extra={
                                "method": operation_name,
                                "status_code": e.response.status_code,
                                "attempt": attempt + 1,
                                "max_retries": self._max_retries,
                                "retry_delay": delay,
                            },
                        )
                        await asyncio.sleep(delay)
                        continue
                    else:
                        logger.error(
                            "HTTP error",
                            extra={
                                "method": operation_name,
                                "status_code": e.response.status_code,
                                "error": str(e),
                            },
                        )
                        raise

        if last_exception:
            raise last_exception

    return wrapper


class AsyncHTTPManager:
    def __init__(self, config: HTTPConfig) -> None:
        self._max_retries = config.max_retries
        self._retry_base_delay = config.retry_base_delay
        self._retry_max_delay = config.retry_max_delay
        self._retry_backoff_factor = config.retry_backoff_factor

        limits = httpx.Limits(
            max_connections=config.max_connections,
            max_keepalive_connections=config.max_keepalive_connections,
        )

        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(config.timeout),
            limits=limits,
            headers={"user-agent": config.user_agent},
            follow_redirects=True,
        )

        logger.info(
            "AsyncHTTPManager initialized",
            extra={
                "timeout": config.timeout,
                "max_connections": config.max_connections,
                "max_retries": config.max_retries,
                "retry_base_delay": config.retry_base_delay,
                "retry_backoff_factor": config.retry_backoff_factor,
            },
        )

    def _calculate_retry_delay(self, attempt: int) -> float:
        """Calculate exponential backoff delay with max cap"""
        delay = self._retry_base_delay * (self._retry_backoff_factor**attempt)
        return min(delay, self._retry_max_delay)

    async def get(self, url: str, **kwargs) -> httpx.Response:
        return await self._request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> httpx.Response:
        return await self._request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs) -> httpx.Response:
        return await self._request("PUT", url, **kwargs)

    async def delete(self, url: str, **kwargs) -> httpx.Response:
        return await self._request("DELETE", url, **kwargs)

    @retry_on_failure
    async def download_stream(
        self,
        url: str,
        file_path: str,
        chunk_size: int = 8192,
        **kwargs,
    ) -> int:
        """
        Stream download a file to disk.

        Args:
            url: URL to download from
            file_path: Local file path to save to
            chunk_size: Bytes to read per iteration (default: 8KB)
            **kwargs: Additional arguments passed to httpx request

        Returns:
            Total bytes downloaded

        Raises:
            httpx.HTTPStatusError: On HTTP errors
            httpx.NetworkError: On network failures
            IOError: On file write errors
        """
        logger.debug(
            "Starting stream download",
            extra={"url": url, "file_path": file_path, "chunk_size": chunk_size},
        )

        async with self._client.stream("GET", url, **kwargs) as response:
            response.raise_for_status()

            total_bytes = 0
            with open(file_path, "wb") as f:
                # stream bytes into memory w/ aiter_bytes to lower memory pressure
                async for chunk in response.aiter_bytes(chunk_size=chunk_size):
                    f.write(chunk)
                    total_bytes += len(chunk)

            logger.info(
                "Downloaded file successfully",
                extra={
                    "url": url,
                    "file_path": file_path,
                    "total_bytes": total_bytes,
                },
            )
            return total_bytes

    @retry_on_failure
    async def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        logger.debug(
            f"Making {method} request",
            extra={"method": method, "url": url},
        )

        response = await self._client.request(method, url, **kwargs)
        response.raise_for_status()

        logger.debug(
            f"{method} request successful",
            extra={"method": method, "url": url, "status_code": response.status_code},
        )

        return response

    async def close(self) -> None:
        await self._client.aclose()
        logger.info("AsyncHTTPManager closed")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
