from __future__ import annotations

import time
from abc import ABC, abstractmethod

import httpx

from ..config import Settings
from ..domain import CheckResult, ReleaseInfo, SupportLevel
from ..http import PoliteClient


class Connector(ABC):
    """A retailer connector. One instance == one retailer code."""

    code: str
    name: str
    tier: int = 1
    support_level: SupportLevel = SupportLevel.SUPPORTED
    respect_robots: bool = True  # official JSON APIs set False (robots.txt governs crawlers, not APIs)
    status_note: str = ""
    config_key: str | None = None  # key in runtime["connectors"]; defaults to code

    def __init__(self, settings: Settings, runtime: dict, transport: httpx.BaseTransport | None = None, sleep=time.sleep):
        self.settings = settings
        self.runtime = runtime
        self.transport = transport
        self.sleep = sleep

    @property
    def conf(self) -> dict:
        return self.runtime.get("connectors", {}).get(self.config_key or self.code, {})

    def configured(self) -> tuple[bool, str]:
        return True, "ok"

    def client(self) -> PoliteClient:
        return PoliteClient(
            retailer=self.code,
            user_agent=self.settings.user_agent,
            requests_per_minute=int(self.conf.get("requests_per_minute", 30)),
            timeout_s=self.settings.http_timeout_s,
            respect_robots=self.respect_robots,
            transport=self.transport,
            sleep=self.sleep,
        )

    @abstractmethod
    def discover(self, queries: list[str]) -> CheckResult: ...

    @abstractmethod
    def check(self, product_ids: list[str]) -> CheckResult: ...


class UnsupportedConnector(Connector):
    """Registered so it shows in the dashboard with the reason; makes no requests."""

    support_level = SupportLevel.UNSUPPORTED

    def configured(self) -> tuple[bool, str]:
        return False, self.status_note

    def discover(self, queries):  # pragma: no cover - never scheduled
        return CheckResult(self.code)

    def check(self, product_ids):  # pragma: no cover
        return CheckResult(self.code)


class ReleaseSource(ABC):
    code: str
    name: str

    def __init__(self, settings: Settings, runtime: dict, transport: httpx.BaseTransport | None = None, sleep=time.sleep):
        self.settings, self.runtime, self.transport, self.sleep = settings, runtime, transport, sleep

    @abstractmethod
    def fetch(self) -> list[ReleaseInfo]: ...
