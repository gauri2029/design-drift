"""API tests for the human-review pause:
PUT /api/v1/projects/{project_id}/design-analysis/{id}/fix-review.

Rows are seeded straight into the database rather than produced by a real
graph run (test_design_analysis_api.py already covers that path end to
end): what's under test here is the review gate itself, and a full run per
case would be minutes of Playwright and mocked LLM traffic to set up state
this file can state directly.
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

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


async def _seed(fix_proposal: dict | None) -> tuple[str, str]:
    project = Project(
        id=uuid.uuid4(),
        name="Marketing homepage",
        figma_file_key="abc123",
        figma_node_id="1:23",
        target_url="http://example.test/",
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
