"""
03 · 匹配引擎 · API schema
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class MatchpointResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category: str
    match_type: str
    similarity: float
    weight: float


class MatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_a_id: int
    user_b_id: int
    overall_score: float
    is_wildcard: bool
    status: str
    created_at: datetime
    matchpoints: Optional[list[MatchpointResponse]] = None


class MatchRunResponse(BaseModel):
    """POST /api/match/run 响应"""
    user_id: int
    new_matches: int
    matches: list[MatchResponse]
