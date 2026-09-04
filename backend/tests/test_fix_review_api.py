"""API tests for the human-review pause and what follows it:
PUT .../design-analysis/{id}/fix-review and POST .../{id}/apply.

Rows are seeded straight into the database rather than produced by a real
graph run (test_design_analysis_api.py already covers that path end to
end): what's under test here is the review gate itself, and a full run per
case would be minutes of Playwright and mocked LLM traffic to set up state
this file can state directly.
"""

import uuid
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core.config import get_settings
from app.db.session import async_session_factory
from app.main import app
from app.models.design_analysis import DesignAnalysis
from app.models.project import Project


def _fix(title: str, *, no_fix: bool = False, original_code_found: bool = True) -> dict:
    return {
        "finding_title": title,
        "no_fix": no_fix,
        "patch": None
        if no_fix
        else {
            "file_path": "src/components/Button.tsx",
            "line_start": 12,
            "line_end": 12,
            "original_code": '<button className="bg-slate-200">',
            "replacement_code": '<button className="bg-slate-900">',
        },
        "explanation": "Raises the contrast.",
        "confidence": "high",
        "original_code_found": original_code_found,
    }


async def _seed(fix_proposal: dict | None, *, source_path: str | None = None) -> tuple[str, str]:
    project = Project(
        id=uuid.uuid4(),
        name="Marketing homepage",
        figma_file_key="abc123",
        figma_node_id="1:23",
        target_url="http://example.test/",
        source_path=source_path,
    )
    analysis = DesignAnalysis(
        id=uuid.uuid4(),
        project_id=project.id,
        model="test-model",
        result={
            "layout_summary": "",
            "design_intent": "",
            "key_components": [],
            "implementation_risks": [],
        },
        fix_proposal=fix_proposal,
    )
    async with async_session_factory() as session:
        session.add(project)
        await session.commit()
        session.add(analysis)
        await session.commit()
    return str(project.id), str(analysis.id)


@pytest.fixture(autouse=True)
async def _clean_up():
    yield
    async with async_session_factory() as session:
        await session.execute(delete(DesignAnalysis))
        await session.execute(delete(Project))
        await session.commit()


def _url(project_id: str, analysis_id: str) -> str:
    return f"/api/v1/projects/{project_id}/design-analysis/{analysis_id}/fix-review"


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_review_records_a_decision_per_proposed_fix() -> None:
    project_id, analysis_id = await _seed(
        {"summary": "Two patches.", "fixes": [_fix("color-contrast"), _fix("html-has-lang")]}
    )

    async with await _client() as client:
        # A run starts unreviewed — that's the pause.
        listed = await client.get(f"/api/v1/projects/{project_id}/design-analysis")
        assert listed.json()[0]["fix_review"] is None

        response = await client.put(
            _url(project_id, analysis_id),
            json={
                "decisions": [
                    {"finding_title": "color-contrast", "decision": "approved"},
                    {
                        "finding_title": "html-has-lang",
                        "decision": "rejected",
                        "note": "we set lang in the template, not here",
                    },
                ]
            },
        )

    assert response.status_code == 200, response.text
    review = response.json()["fix_review"]
    assert [d["decision"] for d in review["decisions"]] == ["approved", "rejected"]
    assert review["decisions"][1]["note"] == "we set lang in the template, not here"
    assert review["reviewed_at"]


async def test_review_is_replaced_not_appended_when_a_reviewer_changes_their_mind() -> None:
    project_id, analysis_id = await _seed(
        {"summary": "One patch.", "fixes": [_fix("color-contrast")]}
    )

    async with await _client() as client:
        await client.put(
            _url(project_id, analysis_id),
            json={"decisions": [{"finding_title": "color-contrast", "decision": "approved"}]},
        )
        response = await client.put(
            _url(project_id, analysis_id),
            json={"decisions": [{"finding_title": "color-contrast", "decision": "rejected"}]},
        )

    review = response.json()["fix_review"]
    assert len(review["decisions"]) == 1
    assert review["decisions"][0]["decision"] == "rejected"


async def test_a_patch_that_does_not_apply_cannot_be_approved() -> None:
    """The whole point of verifying original_code: a reviewer must not be
    able to sign off on a patch we already know doesn't match the file.
    """
    project_id, analysis_id = await _seed(
        {"summary": "Stale patch.", "fixes": [_fix("color-contrast", original_code_found=False)]}
    )

    async with await _client() as client:
        approve = await client.put(
            _url(project_id, analysis_id),
            json={"decisions": [{"finding_title": "color-contrast", "decision": "approved"}]},
        )
        # Rejecting it is exactly what a reviewer should be able to do.
        reject = await client.put(
            _url(project_id, analysis_id),
            json={"decisions": [{"finding_title": "color-contrast", "decision": "rejected"}]},
        )

    assert approve.status_code == 409
    assert "does not apply" in approve.json()["detail"]
    assert reject.status_code == 200


async def test_a_finding_the_run_declined_to_patch_is_not_reviewable() -> None:
    project_id, analysis_id = await _seed(
        {"summary": "Declined.", "fixes": [_fix("region", no_fix=True)]}
    )

    async with await _client() as client:
        response = await client.put(
            _url(project_id, analysis_id),
            json={"decisions": [{"finding_title": "region", "decision": "approved"}]},
        )

    assert response.status_code == 409
    assert "no patch" in response.json()["detail"]


async def test_reviewing_a_run_with_no_proposals_is_refused() -> None:
    project_id, analysis_id = await _seed(None)

    async with await _client() as client:
        response = await client.put(
            _url(project_id, analysis_id),
            json={"decisions": [{"finding_title": "anything", "decision": "approved"}]},
        )

    assert response.status_code == 409
    assert "nothing to review" in response.json()["detail"]


async def test_review_returns_404_for_an_unknown_run() -> None:
    project_id, _ = await _seed({"summary": "", "fixes": [_fix("color-contrast")]})

    async with await _client() as client:
        response = await client.put(
            _url(project_id, str(uuid.uuid4())),
            json={"decisions": [{"finding_title": "color-contrast", "decision": "approved"}]},
        )

    assert response.status_code == 404


async def test_review_rejects_an_empty_decision_list() -> None:
    project_id, analysis_id = await _seed({"summary": "", "fixes": [_fix("color-contrast")]})

    async with await _client() as client:
        response = await client.put(_url(project_id, analysis_id), json={"decisions": []})

    assert response.status_code == 422


# --- applying an approved review ------------------------------------------
#
# Splicing is unit-tested in test_apply_patch.py; what these cover is the
# gate around it — that a write only ever happens downstream of an
# approval, and happens once.


def _checkout(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setattr(get_settings(), "source_root", str(tmp_path / "sources"))
    checkout = tmp_path / "sources" / "marketing-site"
    checkout.mkdir(parents=True)
    (checkout / "index.html").write_text(
        '<!doctype html>\n<html lang="">\n<body>\n</body>\n', encoding="utf-8"
    )
    return checkout


def _lang_fix() -> dict:
    return {
        "finding_title": "html-has-lang",
        "no_fix": False,
        "patch": {
            "file_path": "index.html",
            "line_start": 2,
            "line_end": 2,
            "original_code": '<html lang="">',
            "replacement_code": '<html lang="en">',
        },
        "explanation": "Sets the document language.",
        "confidence": "high",
        "original_code_found": True,
    }


async def test_approved_patches_are_written_to_the_checkout(tmp_path, monkeypatch) -> None:
    checkout = _checkout(tmp_path, monkeypatch)
    project_id, analysis_id = await _seed(
        {"summary": "One patch.", "fixes": [_lang_fix()]}, source_path="marketing-site"
    )

    async with await _client() as client:
        await client.put(
            _url(project_id, analysis_id),
            json={"decisions": [{"finding_title": "html-has-lang", "decision": "approved"}]},
        )
        response = await client.post(
            f"/api/v1/projects/{project_id}/design-analysis/{analysis_id}/apply"
        )

    assert response.status_code == 200, response.text
    application = response.json()["fix_application"]
    assert application["fixes"] == [
        {
            "finding_title": "html-has-lang",
            "file_path": "index.html",
            "applied": True,
            "reason": None,
        }
    ]
    assert '<html lang="en">' in (checkout / "index.html").read_text()


async def test_a_rejected_patch_is_never_written(tmp_path, monkeypatch) -> None:
    checkout = _checkout(tmp_path, monkeypatch)
    before = (checkout / "index.html").read_text()
    project_id, analysis_id = await _seed(
        {"summary": "One patch.", "fixes": [_lang_fix()]}, source_path="marketing-site"
    )

    async with await _client() as client:
        await client.put(
            _url(project_id, analysis_id),
            json={"decisions": [{"finding_title": "html-has-lang", "decision": "rejected"}]},
        )
        response = await client.post(
            f"/api/v1/projects/{project_id}/design-analysis/{analysis_id}/apply"
        )

    assert response.status_code == 409
    assert "approved" in response.json()["detail"]
    assert (checkout / "index.html").read_text() == before


async def test_applying_before_any_review_is_refused(tmp_path, monkeypatch) -> None:
    checkout = _checkout(tmp_path, monkeypatch)
    before = (checkout / "index.html").read_text()
    project_id, analysis_id = await _seed(
        {"summary": "One patch.", "fixes": [_lang_fix()]}, source_path="marketing-site"
    )

    async with await _client() as client:
        response = await client.post(
            f"/api/v1/projects/{project_id}/design-analysis/{analysis_id}/apply"
        )

    assert response.status_code == 409
    assert (checkout / "index.html").read_text() == before


async def test_applying_twice_is_refused(tmp_path, monkeypatch) -> None:
    """The second call would act on a checkout that has already changed."""
    _checkout(tmp_path, monkeypatch)
    project_id, analysis_id = await _seed(
        {"summary": "One patch.", "fixes": [_lang_fix()]}, source_path="marketing-site"
    )

    async with await _client() as client:
        await client.put(
            _url(project_id, analysis_id),
            json={"decisions": [{"finding_title": "html-has-lang", "decision": "approved"}]},
        )
        first = await client.post(
            f"/api/v1/projects/{project_id}/design-analysis/{analysis_id}/apply"
        )
        second = await client.post(
            f"/api/v1/projects/{project_id}/design-analysis/{analysis_id}/apply"
        )

    assert first.status_code == 200
    assert second.status_code == 409
    assert "already been applied" in second.json()["detail"]


async def test_a_patch_that_no_longer_fits_is_reported_not_forced(tmp_path, monkeypatch) -> None:
    """Approval and application are separate moments, and the file is the
    user's in between."""
    checkout = _checkout(tmp_path, monkeypatch)
    project_id, analysis_id = await _seed(
        {"summary": "One patch.", "fixes": [_lang_fix()]}, source_path="marketing-site"
    )

    async with await _client() as client:
        await client.put(
            _url(project_id, analysis_id),
            json={"decisions": [{"finding_title": "html-has-lang", "decision": "approved"}]},
        )
        # The user edits the file themselves before applying.
        (checkout / "index.html").write_text(
            '<!doctype html>\n<html lang="fr">\n<body>\n</body>\n', encoding="utf-8"
        )
        response = await client.post(
            f"/api/v1/projects/{project_id}/design-analysis/{analysis_id}/apply"
        )

    assert response.status_code == 200
    fix = response.json()["fix_application"]["fixes"][0]
    assert fix["applied"] is False
    assert "no longer in the file" in fix["reason"]
    # Their edit survives.
    assert '<html lang="fr">' in (checkout / "index.html").read_text()


async def test_applying_without_a_source_checkout_is_refused(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "source_root", str(tmp_path / "sources"))
    project_id, analysis_id = await _seed(
        {"summary": "One patch.", "fixes": [_lang_fix()]}, source_path=None
    )

    async with await _client() as client:
        await client.put(
            _url(project_id, analysis_id),
            json={"decisions": [{"finding_title": "html-has-lang", "decision": "approved"}]},
        )
        response = await client.post(
            f"/api/v1/projects/{project_id}/design-analysis/{analysis_id}/apply"
        )

    assert response.status_code == 409
    assert "no source checkout" in response.json()["detail"]


# --- verifying an applied fix ---------------------------------------------
#
# The graph itself is covered in test_verification_graph.py. What's gated
# here is the precondition: verification only means something once a patch
# was actually written, and it needs the original run's own before-side.


async def _seed_applied(tmp_path, monkeypatch, *, applied: bool) -> tuple[str, str]:
    """A run whose patch was approved and applied (or attempted)."""
    _checkout(tmp_path, monkeypatch)
    project_id, analysis_id = await _seed(
        {"summary": "One patch.", "fixes": [_lang_fix()]}, source_path="marketing-site"
    )
    async with async_session_factory() as session:
        analysis = await session.get(DesignAnalysis, uuid.UUID(analysis_id))
        assert analysis is not None
        analysis.fix_application = {
            "applied_at": "2026-01-04T00:00:00Z",
            "fixes": [
                {
                    "finding_title": "html-has-lang",
                    "file_path": "index.html",
                    "applied": applied,
                    "reason": None if applied else "the code is no longer in the file",
                }
            ],
        }
        await session.commit()
    return project_id, analysis_id


async def test_verifying_before_applying_is_refused(tmp_path, monkeypatch) -> None:
    _checkout(tmp_path, monkeypatch)
    project_id, analysis_id = await _seed(
        {"summary": "One patch.", "fixes": [_lang_fix()]}, source_path="marketing-site"
    )

    async with await _client() as client:
        response = await client.post(
            f"/api/v1/projects/{project_id}/design-analysis/{analysis_id}/verify"
        )

    assert response.status_code == 409
    assert "haven't been applied" in response.json()["detail"]


async def test_verifying_when_nothing_was_written_is_refused(tmp_path, monkeypatch) -> None:
    """An apply where every patch was skipped changed no files, so there is
    nothing for verification to be about."""
    project_id, analysis_id = await _seed_applied(tmp_path, monkeypatch, applied=False)

    async with await _client() as client:
        response = await client.post(
            f"/api/v1/projects/{project_id}/design-analysis/{analysis_id}/verify"
        )

    assert response.status_code == 409
    assert "nothing to verify" in response.json()["detail"]


async def test_verifying_a_run_with_no_stored_before_capture_is_refused(
    tmp_path, monkeypatch
) -> None:
    """These rows predate the columns rather than being broken now, so the
    refusal names the missing piece instead of failing on an assert."""
    project_id, analysis_id = await _seed_applied(tmp_path, monkeypatch, applied=True)

    async with await _client() as client:
        response = await client.post(
            f"/api/v1/projects/{project_id}/design-analysis/{analysis_id}/verify"
        )

    assert response.status_code == 409
    assert "no stored production capture" in response.json()["detail"]


async def test_verify_rejects_a_non_http_target_url_override(tmp_path, monkeypatch) -> None:
    """The override exists so a local dev server can be checked; it is not
    a general-purpose fetch."""
    project_id, analysis_id = await _seed_applied(tmp_path, monkeypatch, applied=True)

    async with await _client() as client:
        response = await client.post(
            f"/api/v1/projects/{project_id}/design-analysis/{analysis_id}/verify",
            json={"target_url": "file:///etc/passwd"},
        )

    assert response.status_code == 422
