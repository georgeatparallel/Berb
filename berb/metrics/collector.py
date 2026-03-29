"""P1 FIX: Metrics collector for Berb pipeline observability."""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MetricValue:
    """A single metric value with timestamp."""
    value: float
    timestamp: float = field(default_factory=time.time)


class MetricsCollector:
    """P1 FIX: Thread-safe metrics collector for Prometheus exposition.

    Collects metrics from pipeline stages, LLM calls, experiments, etc.
    Supports counters, gauges, and histograms.

    Usage:
        collector = get_metrics_collector()
        collector.increment("pipeline_stages_completed", labels={"stage": "TOPIC_INIT"})
        collector.set_gauge("llm_latency_seconds", 1.5, labels={"model": "gpt-4o"})
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # Metric storage: name -> labels -> values
        self._counters: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self._gauges: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self._histograms: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        # Metric metadata
        self._metric_types: dict[str, str] = {}  # name -> "counter"|"gauge"|"histogram"
        self._metric_descriptions: dict[str, str] = {}

    def register_metric(
        self,
        name: str,
        metric_type: str,
        description: str = "",
    ) -> None:
        """Register a metric with its type and description."""
        with self._lock:
            self._metric_types[name] = metric_type
            self._metric_descriptions[name] = description

    def increment(
        self,
        name: str,
        value: float = 1.0,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Increment a counter metric."""
        label_key = self._labels_to_key(labels or {})
        with self._lock:
            self._counters[name][label_key] += value
            if name not in self._metric_types:
                self._metric_types[name] = "counter"

    def set_gauge(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Set a gauge metric value."""
        label_key = self._labels_to_key(labels or {})
        with self._lock:
            self._gauges[name][label_key] = value
            if name not in self._metric_types:
                self._metric_types[name] = "gauge"

    def observe(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Add an observation to a histogram metric."""
        label_key = self._labels_to_key(labels or {})
        with self._lock:
            self._histograms[name][label_key].append(value)
            if name not in self._metric_types:
                self._metric_types[name] = "histogram"

    def get_counter(self, name: str, labels: dict[str, str] | None = None) -> float:
        """Get counter value."""
        label_key = self._labels_to_key(labels or {})
        with self._lock:
            return self._counters[name][label_key]

    def get_gauge(self, name: str, labels: dict[str, str] | None = None) -> float:
        """Get gauge value."""
        label_key = self._labels_to_key(labels or {})
        with self._lock:
            return self._gauges[name][label_key]

    def get_histogram_stats(
        self,
        name: str,
        labels: dict[str, str] | None = None,
    ) -> dict[str, float]:
        """Get histogram statistics (count, sum, min, max, avg)."""
        label_key = self._labels_to_key(labels or {})
        with self._lock:
            values = self._histograms[name][label_key]
            if not values:
                return {"count": 0, "sum": 0, "min": 0, "max": 0, "avg": 0}
            return {
                "count": len(values),
                "sum": sum(values),
                "min": min(values),
                "max": max(values),
                "avg": sum(values) / len(values),
            }

    def _labels_to_key(self, labels: dict[str, str]) -> str:
        """Convert labels dict to a sorted key string."""
        if not labels:
            return ""
        return ",".join(f"{k}={v}" for k, v in sorted(labels.items()))

    def _key_to_labels(self, key: str) -> dict[str, str]:
        """Convert key string back to labels dict."""
        if not key:
            return {}
        labels = {}
        for part in key.split(","):
            if "=" in part:
                k, v = part.split("=", 1)
                labels[k] = v
        return labels

    def get_all_metrics(self) -> dict[str, Any]:
        """Get all metrics as a dictionary."""
        with self._lock:
            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "histograms": {
                    name: {
                        label_key: self.get_histogram_stats(name, self._key_to_labels(label_key))
                        for label_key in values
                    }
                    for name, values in self._histograms.items()
                },
                "metadata": {
                    name: {
                        "type": self._metric_types.get(name, "unknown"),
                        "description": self._metric_descriptions.get(name, ""),
                    }
                    for name in set(
                        list(self._counters.keys())
                        + list(self._gauges.keys())
                        + list(self._histograms.keys())
                    )
                },
            }

    def reset(self) -> None:
        """Reset all metrics (useful for testing)."""
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()


# Global singleton
_COLLECTOR: MetricsCollector | None = None
_COLLECTOR_LOCK = threading.Lock()


def get_metrics_collector() -> MetricsCollector:
    """Get the global metrics collector singleton."""
    global _COLLECTOR
    with _COLLECTOR_LOCK:
        if _COLLECTOR is None:
            _COLLECTOR = MetricsCollector()
            # Register standard metrics
            _COLLECTOR.register_metric(
                "pipeline_stages_completed",
                "counter",
                "Number of pipeline stages completed successfully",
            )
            _COLLECTOR.register_metric(
                "pipeline_stages_failed",
                "counter",
                "Number of pipeline stages that failed",
            )
            _COLLECTOR.register_metric(
                "llm_requests_total",
                "counter",
                "Total number of LLM API requests",
            )
            _COLLECTOR.register_metric(
                "llm_requests_errors",
                "counter",
                "Number of LLM API request errors",
            )
            _COLLECTOR.register_metric(
                "llm_latency_seconds",
                "histogram",
                "LLM API request latency in seconds",
            )
            _COLLECTOR.register_metric(
                "llm_tokens_used",
                "counter",
                "Total tokens consumed from LLM API",
            )
            _COLLECTOR.register_metric(
                "experiment_runs_total",
                "counter",
                "Total number of experiment runs",
            )
            _COLLECTOR.register_metric(
                "experiment_runs_failed",
                "counter",
                "Number of failed experiment runs",
            )
            _COLLECTOR.register_metric(
                "experiment_duration_seconds",
                "histogram",
                "Experiment execution duration in seconds",
            )
        return _COLLECTOR