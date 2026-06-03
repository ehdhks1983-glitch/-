from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class VerifyResult:
    valid: bool
    reason: Optional[str] = None
    status: Optional[str] = None
    plan_type: Optional[str] = None
    expires_at: Optional[str] = None
    days_remaining: Optional[int] = None
    max_hwid_count: Optional[int] = None
    offline: bool = False
