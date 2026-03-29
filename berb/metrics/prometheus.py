"""P1 FIX: Prometheus exposition format exporter."""

from __future__ import annotations

import logging
from typing import Any

from berb.metrics.collector import MetricsCollector, get_metrics_collector

logger = logging.getLogger(__name__)


class PrometheusExporter:
    """P1 FIX: Export metrics in Prometheus text exposition format.

    Usage:
        exporter = PrometheusExporter()
        prometheus_text = exporter.export()  # Ready for /metrics endpoint
    """

    def __init__(self, collector: MetricsCollector | None = None) -> None:
        self._collector = collector or get_metrics_collector()

    def export(self) -> str:
        """Export all metrics in Prometheus text format.

        Returns:
            Prometheus exposition format string suitable for /metrics endpoint.
        """
        metrics = self._collector.get_all_metrics()
        lines: list[str] = []

        # Export counters
        for name, label_values in metrics["counters"].items():
            metadata = metrics["metadata"].get(name, {})
            desc = metadata.get("description", "")
            if desc:
                lines.append(f"# HELP {name} {desc}")
            lines.append(f"# TYPE {name} counter")
            for label_key, value in label_values.items():
                if label_key:
                    lines.append(f'{name}{{{label_key}}} {value}')
                else:
                    lines.append(f'{name} {value}')
            lines.append("")

        # Export gauges
        for name, label_values in metrics["gauges"].items():
            metadata = metrics["metadata"].get(name, {})
            desc = metadata.get("description", "")
            if desc:
                lines.append(f"# HELP {name} {desc}")
            lines.append(f"# TYPE {name} gauge")
            for label_key, value in label_values.items():
                if label_key:
                    lines.append(f'{name}{{{label_key}}} {value}')
                else:
                    lines.append(f'{name} {value}')
            lines.append("")

        # Export histograms (simplified - just export summary stats)
        for name, label_stats in metrics["histograms"].items():
            metadata = metrics["metadata"].get(name, {})
            desc = metadata.get("description", "")
            if desc:
                lines.append(f"# HELP {name} {desc}")
            lines.append(f"# TYPE {name} gauge")  # Export as gauge for simplicity
            for label_key, stats in label_stats.items():
                stats_dict = stats if isinstance(stats, dict) else {}
                for stat_name, stat_value in stats_dict.items():
                    metric_name = f"{name}_{stat_name}"
                    if label_key:
                        lines.append(f'{metric_name}{{{label_key}}} {stat_value}')
                    else:
                        lines.append(f'{metric_name} {stat_value}')
            lines.append("")

        return "\n".join(lines)

    def export_for_http(self) -> bytes:
        """Export metrics as bytes for HTTP response."""
        return self.export().encode("utf-8")


def create_metrics_handler():
    """Create a simple HTTP handler for /metrics endpoint.

    Returns a function suitable for use with http.server or similar.
    """
    exporter = PrometheusExporter()

    def metrics_handler() -> tuple[int, dict[str, str], bytes]:
        """Return (status_code, headers, body) for /metrics endpoint."""
        return (
            200,
            {"Content-Type": "text/plain; charset=utf-8"},
            exporter.export_for_http(),
        )

    return metrics_handler