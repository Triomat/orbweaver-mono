"""JSON-on-disk persistence for review sessions."""

from __future__ import annotations

import logging
from pathlib import Path

from orbweaver.review.models import ReviewSession

logger = logging.getLogger(__name__)


class ReviewStore:
    """Stores ReviewSession objects as individual JSON files in a directory."""

    def __init__(self, data_dir: str | Path = "reviews") -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def create(self, policy_name: str, defaults: dict | None = None) -> ReviewSession:
        session = ReviewSession(
            policy_name=policy_name,
            defaults=defaults or {},
        )
        self._write(session)
        return session

    def get(self, review_id: str) -> ReviewSession | None:
        path = self.data_dir / f"{review_id}.json"
        if not path.exists():
            return None
        try:
            return ReviewSession.model_validate_json(path.read_text())
        except Exception as e:
            logger.error("Failed to load review %s: %s", review_id, e)
            return None

    def list_all(self) -> list[ReviewSession]:
        sessions: list[ReviewSession] = []
        for path in sorted(
            self.data_dir.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        ):
            try:
                sessions.append(ReviewSession.model_validate_json(path.read_text()))
            except Exception as e:
                logger.warning("Skipping malformed review file %s: %s", path.name, e)
        return sessions

    def save(self, session: ReviewSession) -> None:
        session.touch()
        self._write(session)

    def delete(self, review_id: str) -> bool:
        path = self.data_dir / f"{review_id}.json"
        if path.exists():
            path.unlink()
            return True
        return False

    def _write(self, session: ReviewSession) -> None:
        path = self.data_dir / f"{session.id}.json"
        path.write_text(session.model_dump_json(indent=2))
