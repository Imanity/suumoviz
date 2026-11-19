"""Rate-limited HTTP fetching with stop rules.

- one connection, at least ``interval`` seconds between request starts;
- no cookies, no redirects followed, gzip accepted;
- 401/403/429 and challenge pages raise :class:`Blocked` (the run must stop and cool down);
- 5xx and network errors are retried a bounded number of times, then :class:`PageError`;
- request-count and wall-clock budgets raise :class:`BudgetExceeded`.
"""

from __future__ import annotations

import gzip
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime

from suumoviz import __version__

CHALLENGE_MARKERS = (
    "captcha",
    "recaptcha",
    "access denied",
    "unusual traffic",
    "ロボットではない",
    "アクセスが集中",
)
BLOCK_STATUSES = frozenset({401, 403, 429})


class CrawlError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class Blocked(CrawlError):
    """The source refused us; stop immediately and cool down."""

    def __init__(self, reason: str, retry_after: int | None = None) -> None:
        super().__init__(reason)
        self.retry_after = retry_after


class BudgetExceeded(CrawlError):
    """The run's request or time budget is used up."""


class PageError(CrawlError):
    """This page could not be fetched; the run may continue."""


@dataclass(frozen=True)
class Response:
    url: str
    status: int
    body: bytes
    headers: dict[str, str] = field(default_factory=dict)

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


class TransportError(Exception):
    """Network-level failure (DNS, timeout, connection reset)."""


Transport = Callable[[str, dict[str, str], float], Response]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def urllib_transport(url: str, headers: dict[str, str], timeout: float) -> Response:
    opener = urllib.request.build_opener(_NoRedirect)
    request = urllib.request.Request(url, headers=headers)
    try:
        with opener.open(request, timeout=timeout) as resp:
            status, raw, resp_headers = resp.status, resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        status, raw, resp_headers = exc.code, exc.read() or b"", dict(exc.headers or {})
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise TransportError(str(exc)) from exc
    if resp_headers.get("Content-Encoding", "").lower() == "gzip":
        raw = gzip.decompress(raw)
    return Response(url=url, status=status, body=raw, headers=resp_headers)


USER_AGENT = f"Mozilla/5.0 (compatible; SuumoViz/{__version__})"


def looks_like_challenge(body: bytes) -> bool:
    text = body.decode("utf-8", errors="ignore").lower()
    return any(marker in text for marker in CHALLENGE_MARKERS)


def _retry_after(headers: dict[str, str]) -> int | None:
    value = next((v for k, v in headers.items() if k.lower() == "retry-after"), None)
    if value is None:
        return None
    value = value.strip()
    if value.isdigit():
        return int(value)
    try:
        return max(0, int(parsedate_to_datetime(value).timestamp() - time.time()))
    except (TypeError, ValueError):
        return None


class Fetcher:
    def __init__(
        self,
        *,
        interval: float = 5.0,
        timeout: float = 30.0,
        max_requests: int = 150,
        max_seconds: float = 30 * 60,
        retry_delays: tuple[float, ...] = (30.0, 60.0),
        transport: Transport = urllib_transport,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,text/plain;q=0.9,*/*;q=0.1",
            "Accept-Language": "ja",
            "Accept-Encoding": "gzip",
        }
        self.interval = interval
        self.timeout = timeout
        self.max_requests = max_requests
        self.max_seconds = max_seconds
        self.retry_delays = retry_delays
        self.transport = transport
        self.clock = clock
        self.sleep = sleep
        self.requests = 0
        self.started = clock()
        self._last_start: float | None = None

    def _wait_turn(self) -> None:
        if self._last_start is not None:
            remaining = self._last_start + self.interval - self.clock()
            if remaining > 0:
                self.sleep(remaining)
        self._last_start = self.clock()

    def get(self, url: str) -> Response:
        error = "unknown"
        for attempt in range(len(self.retry_delays) + 1):
            if self.requests >= self.max_requests:
                raise BudgetExceeded("request_budget")
            self._wait_turn()
            if self.clock() - self.started >= self.max_seconds:
                raise BudgetExceeded("time_budget")
            self.requests += 1
            try:
                response = self.transport(url, self.headers, self.timeout)
            except TransportError as exc:
                error = f"network:{exc}"
            else:
                if response.status in BLOCK_STATUSES:
                    raise Blocked(f"http_{response.status}", _retry_after(response.headers))
                if response.status == 200:
                    if looks_like_challenge(response.body):
                        raise Blocked("challenge_page")
                    return response
                if response.status < 500:
                    raise PageError(f"http_{response.status}")
                error = f"http_{response.status}"
            if attempt < len(self.retry_delays):
                self.sleep(self.retry_delays[attempt])
        raise PageError(error)
