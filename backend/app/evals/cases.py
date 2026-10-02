"""Loading eval cases off disk.

A case is a directory: a `source/` checkout, and a `case.json` listing the
findings to locate with their hand-verified answers. Fixtures are files
rather than Python so a case can be added by copying a real page and
writing down where things are — which is how the useful ones get written.
"""

import json
from pathlib import Path

from pydantic import BaseModel

from app.evals.types import EvalFinding, ExpectedLocation

CASES_ROOT = Path(__file__).parent / "cases"


class EvalCase(BaseModel):
    name: str
    source_root: Path
    # Findings and their answers, paired. One list rather than two keyed by
    # title, so a case can't half-specify an answer.
    findings: list[tuple[EvalFinding, ExpectedLocation]]
    # Verbatim axe output for this page, when the case covers accessibility
    # findings — they anchor on axe's per-violation DOM evidence, so
    # dropping it would measure a weaker pipeline than the real one.
    accessibility_report: dict[str, object] | None = None
    dom_snapshot: dict[str, object] | None = None
    target_selector: str | None = None


def load_cases(root: Path = CASES_ROOT) -> list[EvalCase]:
    cases = []
    for case_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        cases.append(load_case(case_dir))
    return cases


def load_case(case_dir: Path) -> EvalCase:
    spec = json.loads((case_dir / "case.json").read_text())
    return EvalCase(
        name=case_dir.name,
        source_root=case_dir / "source",
        findings=[
            (
                EvalFinding.model_validate(entry["finding"]),
                ExpectedLocation.model_validate(entry["expected"]),
            )
            for entry in spec["findings"]
        ],
        accessibility_report=spec.get("accessibility_report"),
        dom_snapshot=spec.get("dom_snapshot"),
        target_selector=spec.get("target_selector"),
    )
