# Demo fixtures

Exported runs that seed the public deployment's read-only showcase.

Each subdirectory is one fixture: a `fixture.json` plus the PNGs from that
run. They are produced by `app.tools.demo_export` from a real analysis in a
local database, and loaded by `app.tools.demo_seed` into a deployed one. See
[../docs/deployment.md](../docs/deployment.md) for the two commands.

## Why fixtures and not a live run

The public deployment serves stored output rather than executing the agents.
A run launches a Chromium and makes several model calls; on a public URL that
means anyone who finds it can spend the author's API budget. So the demo
shows what the agents really produced and refuses to produce more, enforced
in the API, not by hiding buttons. See `app/services/demo.py`.

## What a fixture contains

The agents' own output: the findings, the pixel-diff numbers, the axe-core
report, the files and line ranges the Code Analysis agent matched, the
patches the Fix agent drafted, the review decision, and the verification
verdict. Plus the five images: the Figma render, the page capture, the diff,
and the post-fix capture and diff.

## What a fixture must never contain

A checkout, whole source files, or a cloned workspace.

A located finding legitimately quotes the few lines of `code_evidence` the
agent used to justify the match: that *is* the finding, and without it the
demo shows a conclusion with no evidence. But that is the limit.

Run the export with `--check-only` first. It prints every path and every
quoted line the fixture would carry, so the decision to publish them is made
with the text in front of you:

```bash
cd backend
uv run python -m app.tools.demo_export --project-id <uuid> --check-only
```

Only export a project whose repository you own or are licensed to publish.
