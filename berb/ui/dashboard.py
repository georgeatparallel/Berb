"""Terminal progress dashboard for Berb pipeline.

Real-time terminal UI showing pipeline progress, costs,
quality metrics, and ETA using the rich library.

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class StageProgress(BaseModel):
    """Progress for a single stage.

    Attributes:
        stage_number: Stage number
        stage_name: Stage name
        status: Stage status
        progress: Progress percentage (0-100)
        message: Current message
        started_at: When stage started
        completed_at: When stage completed
        cost_usd: Cost for this stage
    """

    stage_number: int
    stage_name: str
    status: str = "pending"  # pending, running, completed, failed
    progress: float = Field(default=0.0, ge=0.0, le=100.0)
    message: str = ""
    started_at: str | None = None
    completed_at: str | None = None
    cost_usd: float = 0.0


class PipelineDashboard:
    """Rich terminal dashboard for pipeline progress.

    This dashboard provides real-time updates on:
    - Current stage and progress
    - Cost running total
    - Papers found/processed
    - Model usage breakdown
    - ETA

    Usage::

        dashboard = PipelineDashboard()
        dashboard.start()

        # Update during pipeline
        dashboard.update_stage_progress(8, 50, "Generating hypotheses...")
        dashboard.update_cost(0.25)
        dashboard.update_papers_found(45)

        # Complete stage
        dashboard.complete_stage(8)

        # Start next stage
        dashboard.start_stage(9, "EXPERIMENT_DESIGN")

        dashboard.stop()
    """

    def __init__(self, enabled: bool = True):
        """Initialize dashboard.

        Args:
            enabled: Whether dashboard is enabled
        """
        self.enabled = enabled
        self.console = None
        self.live = None
        self.start_time = None

        # State
        self.current_stage: StageProgress | None = None
        self.stages: dict[int, StageProgress] = {}
        self.total_cost_usd = 0.0
        self.papers_found = 0
        self.papers_screened = 0
        self.papers_included = 0
        self.model_usage: dict[str, float] = {}  # model -> token count
        self.quality_metrics: dict[str, float] = {}
        self.eta_minutes: float | None = None

        # Stage names
        self.stage_names = {
            1: "TOPIC_INIT",
            2: "PROBLEM_DECOMPOSE",
            3: "SEARCH_STRATEGY",
            4: "LITERATURE_COLLECT",
            5: "LITERATURE_SCREEN",
            6: "KNOWLEDGE_EXTRACT",
            7: "SYNTHESIS",
            8: "HYPOTHESIS_GEN",
            9: "EXPERIMENT_DESIGN",
            10: "CODE_GENERATION",
            11: "RESOURCE_PLANNING",
            12: "EXPERIMENT_RUN",
            13: "ITERATIVE_REFINE",
            14: "RESULT_ANALYSIS",
            15: "RESEARCH_DECISION",
            16: "PAPER_OUTLINE",
            17: "PAPER_DRAFT",
            18: "PEER_REVIEW",
            19: "PAPER_REVISION",
            20: "QUALITY_GATE",
            21: "KNOWLEDGE_ARCHIVE",
            22: "EXPORT_PUBLISH",
            23: "CITATION_VERIFY",
        }

    def start(self) -> None:
        """Start the dashboard."""
        if not self.enabled:
            return

        try:
            from rich.console import Console
            from rich.live import Live

            self.console = Console()
            self.live = Live(self._generate_table(), console=self.console, refresh_per_second=4)
            self.live.start()
            self.start_time = datetime.now(timezone.utc)

            self.console.print("[bold green]🚀 Berb Pipeline Started[/bold green]\n")

        except ImportError:
            logger.warning("rich library not installed - dashboard disabled")
            self.enabled = False

    def stop(self) -> None:
        """Stop the dashboard."""
        if not self.enabled or not self.live:
            return

        self.live.stop()

        # Print final summary
        self._print_summary()

    def start_stage(
        self,
        stage_number: int,
        stage_name: str | None = None,
    ) -> None:
        """Start a new stage.

        Args:
            stage_number: Stage number
            stage_name: Optional stage name
        """
        name = stage_name or self.stage_names.get(stage_number, f"Stage {stage_number}")

        self.current_stage = StageProgress(
            stage_number=stage_number,
            stage_name=name,
            status="running",
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        self.stages[stage_number] = self.current_stage

    def update_stage_progress(
        self,
        stage_number: int,
        progress: float,
        message: str = "",
    ) -> None:
        """Update stage progress.

        Args:
            stage_number: Stage number
            progress: Progress percentage (0-100)
            message: Status message
        """
        if stage_number in self.stages:
            self.stages[stage_number].progress = min(100.0, max(0.0, progress))
            self.stages[stage_number].message = message

    def complete_stage(
        self,
        stage_number: int,
        cost_usd: float = 0.0,
    ) -> None:
        """Complete a stage.

        Args:
            stage_number: Stage number
            cost_usd: Cost for this stage
        """
        if stage_number in self.stages:
            self.stages[stage_number].status = "completed"
            self.stages[stage_number].progress = 100.0
            self.stages[stage_number].completed_at = datetime.now(timezone.utc).isoformat()
            self.stages[stage_number].cost_usd = cost_usd
            self.total_cost_usd += cost_usd

    def update_cost(self, cost_usd: float) -> None:
        """Update total cost.

        Args:
            cost_usd: Additional cost
        """
        self.total_cost_usd += cost_usd

    def update_papers_found(self, count: int) -> None:
        """Update papers found count.

        Args:
            count: Number of papers found
        """
        self.papers_found = count

    def update_papers_screened(self, count: int) -> None:
        """Update papers screened count.

        Args:
            count: Number of papers screened
        """
        self.papers_screened = count

    def update_papers_included(self, count: int) -> None:
        """Update papers included count.

        Args:
            count: Number of papers included
        """
        self.papers_included = count

    def update_model_usage(
        self,
        model: str,
        tokens: int,
    ) -> None:
        """Update model usage.

        Args:
            model: Model name
            tokens: Token count
        """
        self.model_usage[model] = self.model_usage.get(model, 0) + tokens

    def update_quality_metric(
        self,
        metric: str,
        value: float,
    ) -> None:
        """Update quality metric.

        Args:
            metric: Metric name
            value: Metric value
        """
        self.quality_metrics[metric] = value

    def update_eta(self, minutes: float) -> None:
        """Update ETA.

        Args:
            minutes: ETA in minutes
        """
        self.eta_minutes = minutes

    def _generate_table(self) -> Any:
        """Generate rich table for display.

        Returns:
            Rich table object
        """
        from rich.table import Table
        from rich.panel import Panel
        from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn

        # Main layout
        from rich.layout import Layout
        layout = Layout()

        # Header
        header = Table(show_header=False, box=None, padding=(0, 1))
        header.add_column("Header", style="bold white")
        header.add_row("🧪 Berb Research Pipeline")
        header.add_row(f"Started: {self.start_time.strftime('%Y-%m-%d %H:%M:%S') if self.start_time else 'N/A'}")

        # Current stage panel
        if self.current_stage:
            stage_panel = self._create_stage_panel()
        else:
            stage_panel = Panel("Waiting to start...", title="Current Stage")

        # Stats panel
        stats_panel = self._create_stats_panel()

        # Progress panel
        progress_panel = self._create_progress_panel()

        # Assemble layout
        layout.split(
            Layout(header, name="header", size=3),
            Layout(stage_panel, name="stage", size=10),
            Layout(stats_panel, name="stats", size=12),
            Layout(progress_panel, name="progress", size=8),
        )

        return layout

    def _create_stage_panel(self) -> Panel:
        """Create current stage panel.

        Returns:
            Rich panel
        """
        from rich.panel import Panel
        from rich.progress import Progress, BarColumn, TextColumn

        if not self.current_stage:
            return Panel("Waiting...", title="Current Stage")

        stage = self.current_stage

        # Progress bar
        progress = Progress(
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        )

        task_id = progress.add_task(
            f"{stage.stage_name}",
            completed=stage.progress,
            total=100,
        )

        content = f"[white]{stage.message}[/white]\n\n"
        content += f"Status: [{self._status_color(stage.status)}]{stage.status.upper()}[/{self._status_color(stage.status)}]\n"
        content += f"Cost: ${stage.cost_usd:.3f}"

        return Panel(content, title="Current Stage", border_style="blue")

    def _create_stats_panel(self) -> Panel:
        """Create statistics panel.

        Returns:
            Rich panel
        """
        from rich.panel import Panel

        content = f"""[bold]📊 Literature:[/bold]
  Found: [cyan]{self.papers_found}[/cyan]
  Screened: [yellow]{self.papers_screened}[/yellow]
  Included: [green]{self.papers_included}[/green]

[bold]💰 Cost:[/bold]
  Total: [green]${self.total_cost_usd:.3f}[/green]

[bold]⏱️ ETA:[/bold]
  {f'{self.eta_minutes:.0f} min' if self.eta_minutes else 'Calculating...'}
"""

        return Panel(content, title="Statistics", border_style="green")

    def _create_progress_panel(self) -> Panel:
        """Create overall progress panel.

        Returns:
            Rich panel
        """
        from rich.panel import Panel

        # Count completed stages
        completed = sum(1 for s in self.stages.values() if s.status == "completed")
        total = 23

        # Stage status summary
        status_lines = []
        for i in range(1, 24):
            if i in self.stages:
                stage = self.stages[i]
                icon = self._status_icon(stage.status)
            else:
                icon = "⚪"
            status_lines.append(f"{icon} Stage {i}")

        content = f"[bold]Overall Progress:[/bold] {completed}/{total} stages\n\n"
        content += "\n".join(status_lines[:12])  # First 12 stages
        content += "\n..."

        return Panel(content, title="Pipeline Progress", border_style="yellow")

    def _status_color(self, status: str) -> str:
        """Get color for status.

        Args:
            status: Stage status

        Returns:
            Color name
        """
        colors = {
            "pending": "gray",
            "running": "yellow",
            "completed": "green",
            "failed": "red",
        }
        return colors.get(status, "white")

    def _status_icon(self, status: str) -> str:
        """Get icon for status.

        Args:
            status: Stage status

        Returns:
            Icon character
        """
        icons = {
            "pending": "⚪",
            "running": "🔄",
            "completed": "✅",
            "failed": "❌",
        }
        return icons.get(status, "⚪")

    def _print_summary(self) -> None:
        """Print final summary."""
        if not self.console:
            return

        from rich.panel import Panel

        # Calculate totals
        total_time = ""
        if self.start_time:
            end_time = datetime.now(timezone.utc)
            duration = (end_time - self.start_time).total_seconds() / 60
            total_time = f"{duration:.1f} minutes"

        content = f"""[bold]Pipeline Complete![/bold]

[bold]Duration:[/bold] {total_time}
[bold]Total Cost:[/bold] ${self.total_cost_usd:.3f}
[bold]Papers:[/bold] {self.papers_found} found, {self.papers_included} included

[bold]Quality Metrics:[/bold]
"""

        for metric, value in self.quality_metrics.items():
            content += f"  {metric}: {value:.2f}\n"

        self.console.print(Panel(content, title="Final Summary", border_style="green"))


# Global dashboard instance
_dashboard: PipelineDashboard | None = None


def get_dashboard(enabled: bool = True) -> PipelineDashboard:
    """Get or create dashboard.

    Args:
        enabled: Whether dashboard is enabled

    Returns:
        PipelineDashboard instance
    """
    global _dashboard
    if _dashboard is None:
        _dashboard = PipelineDashboard(enabled=enabled)
    return _dashboard


def start_dashboard() -> None:
    """Start the dashboard."""
    get_dashboard().start()


def stop_dashboard() -> None:
    """Stop the dashboard."""
    get_dashboard().stop()


# Convenience functions for pipeline integration
def update_progress(
    stage: int,
    progress: float,
    message: str = "",
) -> None:
    """Update stage progress."""
    get_dashboard().update_stage_progress(stage, progress, message)


def update_cost(cost: float) -> None:
    """Update cost."""
    get_dashboard().update_cost(cost)


def update_papers(count: int) -> None:
    """Update papers found."""
    get_dashboard().update_papers_found(count)
