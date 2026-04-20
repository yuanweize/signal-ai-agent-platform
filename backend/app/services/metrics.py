"""Runtime metrics and simple alert evaluation."""

from __future__ import annotations

import time
from collections import defaultdict

from app.config import settings


class RuntimeMetrics:
    def __init__(self) -> None:
        self.counters: dict[str, int] = defaultdict(int)
        self.latency_sum: dict[str, float] = defaultdict(float)
        self.latency_count: dict[str, int] = defaultdict(int)
        self.started_at = time.time()

    def inc(self, key: str, amount: int = 1) -> None:
        self.counters[key] += amount

    def observe_latency(self, key: str, value_seconds: float) -> None:
        self.latency_sum[key] += value_seconds
        self.latency_count[key] += 1

    def snapshot(self) -> dict:
        uptime = int(time.time() - self.started_at)

        pull_total = self.counters.get("signal.pull.total", 0)
        pull_fail = self.counters.get("signal.pull.fail", 0)
        pull_401 = self.counters.get("signal.pull.401", 0)
        pull_5xx = self.counters.get("signal.pull.5xx", 0)

        api_total = self.counters.get("api.requests.total", 0)
        api_401 = self.counters.get("api.requests.401", 0)
        api_5xx = self.counters.get("api.requests.5xx", 0)

        proc_count = self.latency_count.get("message.processing", 0)
        proc_avg = (
            self.latency_sum.get("message.processing", 0.0) / proc_count if proc_count else 0.0
        )

        pull_fail_rate = (pull_fail / pull_total) if pull_total else 0.0
        api_5xx_rate = (api_5xx / api_total) if api_total else 0.0

        alerts: list[dict] = []
        if pull_fail_rate > settings.alert_signal_pull_fail_rate:
            alerts.append(
                {
                    "level": "warning",
                    "code": "signal_pull_fail_rate_high",
                    "message": f"Signal pull fail rate is {pull_fail_rate:.2%}",
                }
            )
        if api_5xx_rate > settings.alert_api_5xx_rate:
            alerts.append(
                {
                    "level": "warning",
                    "code": "api_5xx_rate_high",
                    "message": f"API 5xx rate is {api_5xx_rate:.2%}",
                }
            )

        return {
            "uptime_seconds": uptime,
            "signal": {
                "pull_total": pull_total,
                "pull_fail": pull_fail,
                "pull_401": pull_401,
                "pull_5xx": pull_5xx,
                "pull_fail_rate": pull_fail_rate,
            },
            "api": {
                "requests_total": api_total,
                "status_401": api_401,
                "status_5xx": api_5xx,
                "status_5xx_rate": api_5xx_rate,
            },
            "message": {
                "processing_count": proc_count,
                "processing_avg_seconds": proc_avg,
            },
            "alerts": alerts,
        }


runtime_metrics = RuntimeMetrics()
