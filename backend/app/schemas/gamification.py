from datetime import datetime
from pydantic import BaseModel


class BadgeItem(BaseModel):
    code: str
    title: str
    description: str
    earned: bool
    awarded_at: datetime | None = None


class DailyProgressPoint(BaseModel):
    day: str
    xp: int
    sessions: int


class GamificationSummaryResponse(BaseModel):
    xp: int
    level: int
    xp_to_next_level: int
    streak_days: int
    weekly_goal_target: int
    weekly_progress: int
    badges: list[BadgeItem]
    recent_days: list[DailyProgressPoint]


class LeaderboardEntry(BaseModel):
    rank: int
    full_name: str
    level: int
    xp: int
    streak_days: int
