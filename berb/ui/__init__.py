"""UI module for Berb.

Terminal dashboard and progress visualization.

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from berb.ui.dashboard import (
    PipelineDashboard,
    StageProgress,
    get_dashboard,
    start_dashboard,
    stop_dashboard,
    update_progress,
    update_cost,
    update_papers,
)

__all__ = [
    "PipelineDashboard",
    "StageProgress",
    "get_dashboard",
    "start_dashboard",
    "stop_dashboard",
    "update_progress",
    "update_cost",
    "update_papers",
]
