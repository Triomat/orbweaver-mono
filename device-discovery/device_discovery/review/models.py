"""Pydantic models for the review workflow."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class ReviewStatus(str, Enum):
    PENDING = "pending"    # Discovery in progress
    READY = "ready"        # Ready for user review
    INGESTED = "ingested"  # Sent to NetBox via Diode
    FAILED = "failed"      # Discovery or ingest failed


class ItemStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class ReviewItem(BaseModel):
    index: int
    status: ItemStatus = ItemStatus.PENDING
    data: dict  # Serialized NormalizedDevice (or VLAN / Prefix)


class ReviewSession(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    policy_name: str
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    status: ReviewStatus = ReviewStatus.PENDING
    # Policy defaults serialized so ingest can re-apply them
    defaults: dict = Field(default_factory=dict)
    devices: list[ReviewItem] = Field(default_factory=list)
    error: str | None = None

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc).isoformat()

    @property
    def summary(self) -> dict:
        """Lightweight dict for list views (no full device data)."""
        total = len(self.devices)
        accepted = sum(1 for d in self.devices if d.status == ItemStatus.ACCEPTED)
        rejected = sum(1 for d in self.devices if d.status == ItemStatus.REJECTED)
        return {
            "id": self.id,
            "policy_name": self.policy_name,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "status": self.status,
            "device_count": total,
            "accepted": accepted,
            "rejected": rejected,
            "pending": total - accepted - rejected,
            "error": self.error,
        }
