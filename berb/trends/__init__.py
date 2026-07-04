"""Research trend tracking and automatic topic generation."""

from berb.trends.auto_topic import AutoTopicGenerator
from berb.trends.daily_digest import DailyDigest
from berb.trends.feeds import FeedManager
from berb.trends.opportunity_finder import OpportunityFinder
from berb.trends.trend_analyzer import TrendAnalyzer

__all__ = [
    "AutoTopicGenerator",
    "DailyDigest",
    "FeedManager",
    "OpportunityFinder",
    "TrendAnalyzer",
]
