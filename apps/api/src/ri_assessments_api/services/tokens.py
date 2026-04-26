"""Magic-link token plumbing (spec §13, §14.2).

Token = HS256 JWT carrying assignment_id + subject_id + exp.
Stored fingerprint = SHA256(jwt) hex digest. We index assignments by the
fingerprint so a leaked DB row cannot be replayed."""

import hashlib
from datetime import datetime

from ..auth import decode_candidate_token, issue_candidate_token

__all__ = [
    "decode_candidate_token",
    "hash_token",
    "issue_candidate_token",
]


def hash_token(token: str) -> str:
    """SHA256 hex digest of a magic-link token. Stored in assignments.token_hash."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def candidate_token_url(base_url: str, token: str) -> str:
    """Convenience: build the full /a/{token} URL for a candidate."""
    return f"{base_url.rstrip('/')}/a/{token}"


def is_expired(expires_at: datetime, now: datetime) -> bool:
    return expires_at <= now
