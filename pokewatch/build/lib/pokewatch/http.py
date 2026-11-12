"""Polite, defensive HTTP client used by every connector.

* Per-retailer token-bucket request budget
* robots.txt enforcement for non-API web endpoints
* Exponential backoff with jitter for timeouts / 5xx / 429 (honours Retry-After)
* CAPTCHA / bot-wall detection -> BlockedError (never retried around, never parsed)
"""

from __future__ import annotations

import logging
import random
import threading
import time
from urllib import robotparser
from urllib.parse import urlsplit

import httpx

from .domain import CheckStatus

log = logging.getLogger(__name__)

BLOCK_MARKERS = (
    "captcha", "px-captcha", "are you a robot", "verify you are human", "access denied",
    "cf-chl", "challenge-platform", "_incapsula_resource", "request unsuccessful. incapsula",
    "pardon our interruption", "akamai", "bot detection",
)


class FetchError(Exception):
    status: CheckStatus = CheckStatus.ERROR

    def __init__(self, message: str, status: CheckStatus | None = None, http_status: int | None = None):
        super().__init__(message)
        if status is not None:
            self.status = status
        self.http_status = http_status


class BlockedError(FetchError):
    status = CheckStatus.BLOCKED


class RateLimitedError(FetchError):
    status = CheckStatus.RATE_LIMITED


class DisallowedError(FetchError):
    status = CheckStatus.DISALLOWED


class TimeoutFetchError(FetchError):
    status = CheckStatus.TIMEOUT


class TokenBucket:
    def __init__(self, per_minute: int, sleep=time.sleep, clock=time.monotonic):
        self.capacity = max(1, per_minute)
        self.tokens = float(self.capacity)
        self.rate = self.capacity / 60.0
        self._sleep, self._clock = sleep, clock
        self.last = clock()
        self.lock = threading.Lock()

    def acquire(self) -> None:
        with self.lock:
            while True:
                now = self._clock()
                self.tokens = min(self.capacity, self.tokens + (now - self.last) * self.rate)
                self.last = now
                if self.tokens >= 1:
                    self.tokens -= 1
                    return
                self._sleep((1 - self.tokens) / self.rate)


def looks_blocked(resp: httpx.Response) -> bool:
    ctype = resp.headers.get("content-type", "")
    if resp.status_code in (403, 429, 503) and "json" not in ctype:
        return True
    if "html" in ctype:
        head = resp.text[:20000].lower()
        return any(m in head for m in BLOCK_MARKERS)
    return False


class PoliteClient:
    def __init__(
        self,
        retailer: str,
        user_agent: str,
        requests_per_minute: int = 30,
        timeout_s: float = 15.0,
        max_retries: int = 3,
        backoff_base_s: float = 1.5,
        respect_robots: bool = True,
        transport: httpx.BaseTransport | None = None,
        sleep=time.sleep,
    ):
        self.retailer = retailer
        self.respect_robots = respect_robots
        self.max_retries = max_retries
        self.backoff_base_s = backoff_base_s
        self._sleep = sleep
        self.bucket = TokenBucket(requests_per_minute, sleep=sleep)
        self.requests_made = 0
        self._robots: dict[str, robotparser.RobotFileParser | None] = {}
        self.client = httpx.Client(
            headers={"User-Agent": user_agent, "Accept": "application/json, text/html;q=0.8"},
            timeout=timeout_s,
            follow_redirects=True,
            transport=transport,
        )

    def close(self) -> None:
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # -- robots ---------------------------------------------------------
    def allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            rp = robotparser.RobotFileParser()
            try:
                self.bucket.acquire()
                self.requests_made += 1
                r = self.client.get(f"{origin}/robots.txt")
                if r.status_code >= 400 and r.status_code != 404:
                    # unknown policy (blocked / error): be conservative
                    self._robots[origin] = None
                else:
                    rp.parse(r.text.splitlines() if r.status_code == 200 else [])
                    self._robots[origin] = rp
            except httpx.HTTPError:
                self._robots[origin] = None
        rp = self._robots[origin]
        if rp is None:
            return False
        ua = self.client.headers.get("User-Agent", "*")
        return rp.can_fetch(ua, url)

    # -- requests -------------------------------------------------------
    def get(self, url: str, params: dict | None = None, headers: dict | None = None) -> httpx.Response:
        if not self.allowed(url):
            raise DisallowedError(f"robots.txt disallows (or could not be read for) {url}")
        attempt = 0
        while True:
            attempt += 1
            self.bucket.acquire()
            self.requests_made += 1
            try:
                resp = self.client.get(url, params=params, headers=headers)
            except httpx.TimeoutException as e:
                if attempt > self.max_retries:
                    raise TimeoutFetchError(f"timeout after {attempt} attempts: {e}") from e
                self._backoff(attempt)
                continue
            except httpx.TransportError as e:
                if attempt > self.max_retries:
                    raise FetchError(f"network error after {attempt} attempts: {e}") from e
                self._backoff(attempt)
                continue

            if looks_blocked(resp):
                # Never retry or try to get around a bot wall.
                raise BlockedError(f"blocked/captcha response (HTTP {resp.status_code})", http_status=resp.status_code)
            if resp.status_code == 429:
                if attempt > self.max_retries:
                    raise RateLimitedError("HTTP 429 rate limited", http_status=429)
                self._backoff(attempt, retry_after=resp.headers.get("Retry-After"))
                continue
            if resp.status_code >= 500:
                if attempt > self.max_retries:
                    raise FetchError(f"HTTP {resp.status_code} after {attempt} attempts", http_status=resp.status_code)
                self._backoff(attempt)
                continue
            return resp

    def _backoff(self, attempt: int, retry_after: str | None = None) -> None:
        delay = self.backoff_base_s * (2 ** (attempt - 1))
        if retry_after:
            try:
                delay = max(delay, float(retry_after))
            except ValueError:
                pass
        delay = min(delay, 120) * random.uniform(0.8, 1.2)
        log.info("backing off", extra={"retailer": self.retailer, "attempt": attempt, "delay_s": round(delay, 2)})
        self._sleep(delay)
