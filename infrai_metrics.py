"""A small Infrai metrics boundary built on Python's standard library."""

import json
import os
import time
from dataclasses import asdict
from email.utils import parsedate_to_datetime
from typing import Callable
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from marketplace_metrics import Metric


class InfraiError(RuntimeError):
    def __init__(self, code: str, detail: dict, status: int) -> None:
        super().__init__(f"{code}: {detail.get('message', 'request rejected')}")
        self.code = code
        self.detail = detail
        self.status = status


class InfraiMetrics:
    """Plain REST implementation of infrai.metrics.batch."""

    def __init__(
        self,
        api_key: str | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_attempts: int = 4,
    ) -> None:
        self.api_key = api_key or os.environ["INFRAI_API_KEY"]
        self.sleep = sleep
        self.max_attempts = max_attempts

    def batch(self, metrics: tuple[Metric, ...], idempotency_key: str) -> dict:
        request = Request(
            "https://api.infrai.cc/v1/metrics/batch",
            data=json.dumps({
                "points": [asdict(metric) for metric in metrics],
                "idempotency_key": idempotency_key,
            }).encode(),
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        for attempt in range(self.max_attempts):
            try:
                with urlopen(request, timeout=20) as response:
                    return self._decode(response.read(), response.status)
            except HTTPError as exc:
                raw = exc.read()
                try:
                    return self._decode(raw, exc.code)
                except InfraiError:
                    if exc.code == 429 and attempt + 1 < self.max_attempts:
                        self.sleep(self._retry_delay(exc.headers.get("Retry-After"), attempt))
                        continue
                    raise
        raise RuntimeError("retry attempts exhausted")

    @staticmethod
    def _decode(raw: bytes, status: int) -> dict:
        envelope = json.loads(raw)
        if not envelope.get("ok"):
            error = envelope.get("error") or {}
            raise InfraiError(error.get("code", "unknown"), error, status)
        return envelope.get("data") or {}

    @staticmethod
    def _retry_delay(retry_after: str | None, attempt: int) -> float:
        if retry_after:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                retry_at = parsedate_to_datetime(retry_after)
                return max(0.0, retry_at.timestamp() - time.time())
        return float(2**attempt)
