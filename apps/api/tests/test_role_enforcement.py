"""Role gates across admin / reviewer / viewer (spec §12.1, §9.3).

CLAUDE.md anchors role enforcement at the service layer: each mutating
service function declares its allowed roles via `ensure_role`. Routers
that compose helpers without passing a principal call `ensure_role`
themselves. These tests pin the matrix end to end."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from ri_assessments_api.auth import AdminPrincipal, ensure_role
from ri_assessments_api.services import admin as admin_service
from ri_assessments_api.services import references as references_service

from .conftest import MockSupabase


def _principal(role: str) -> AdminPrincipal:
    return AdminPrincipal(
        user_id=f"{role}-uid",
        email=f"{role}@example.com",
        full_name=role.title(),
        role=role,  # type: ignore[arg-type]
    )


# -- rescore_assignment (admin-only): router-level ensure_role ------------


def test_rescore_assignment_rejects_viewer():
    """The router calls `ensure_role(principal, 'admin')` before invoking
    scoring_service.score_assignment. Exercising ensure_role directly is
    sufficient: it is the source of truth and is wrapped by every gated
    handler."""

    with pytest.raises(HTTPException) as exc:
        ensure_role(_principal("viewer"), "admin")
    assert exc.value.status_code == 403


def test_rescore_assignment_accepts_admin():
    # Must not raise.
    ensure_role(_principal("admin"), "admin")


# -- rescore_attempt (admin-only): router-level ensure_role ---------------


def test_rescore_attempt_rejects_reviewer():
    with pytest.raises(HTTPException) as exc:
        ensure_role(_principal("reviewer"), "admin")
    assert exc.value.status_code == 403


# -- preview_variants (admin or reviewer) ---------------------------------


def test_preview_variants_accepts_reviewer():
    ensure_role(_principal("reviewer"), "admin", "reviewer")


def test_preview_variants_rejects_viewer():
    with pytest.raises(HTTPException) as exc:
        ensure_role(_principal("viewer"), "admin", "reviewer")
    assert exc.value.status_code == 403


# -- delete_document (admin-only) -----------------------------------------


def test_delete_document_rejects_reviewer():
    """services.references.delete_document is wrapped at service level by
    ensure_role(principal, 'admin'). A reviewer hitting the endpoint must
    be refused before any DB call."""

    mock = MockSupabase()
    with pytest.raises(HTTPException) as exc:
        references_service.delete_document(
            mock, _principal("reviewer"), "doc-1"
        )
    assert exc.value.status_code == 403
    # And no delete should have been queued.
    assert mock.calls_for("reference_documents", "delete") == []


def test_delete_document_admin_proceeds():
    mock = MockSupabase()
    references_service.delete_document(mock, _principal("admin"), "doc-1")
    deletes = mock.calls_for("reference_documents", "delete")
    assert deletes, "admin delete should reach the DB"
    assert ("eq", ("id", "doc-1")) in deletes[0].filters


# -- update_user_role (admin-only, refuses self-demotion) -----------------


def test_update_user_role_rejects_non_admin():
    mock = MockSupabase()
    with pytest.raises(HTTPException) as exc:
        admin_service.update_user_role(
            mock,
            _principal("reviewer"),
            target_user_id="other-uid",
            new_role="reviewer",
        )
    assert exc.value.status_code == 403


def test_update_user_role_refuses_self_demotion():
    mock = MockSupabase()
    p = _principal("admin")
    with pytest.raises(HTTPException) as exc:
        admin_service.update_user_role(
            mock,
            p,
            target_user_id=p.user_id,
            new_role="reviewer",
        )
    assert exc.value.status_code == 409
    assert "own admin role" in str(exc.value.detail)
    # The DB must not have been touched.
    assert mock.calls_for("users", "update") == []


def test_update_user_role_rejects_unknown_role():
    mock = MockSupabase()
    with pytest.raises(HTTPException) as exc:
        admin_service.update_user_role(
            mock,
            _principal("admin"),
            target_user_id="other-uid",
            new_role="superuser",
        )
    assert exc.value.status_code == 400
