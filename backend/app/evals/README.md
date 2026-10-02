# Retrieval evals

Scores the Code Analysis retrieval path: given a finding, does it name the
right file and line range?

## Why this exists

The retrieval path was changed four times — three anchor iterations, then
DOM extraction — and each change was judged by running one real site and
reading the output. That can't answer "did this improve accuracy, or just
move it?", and it can't catch a change that helps one codebase by hurting
another.

It paid for itself on the first run: 5/7, with three real ranking bugs
behind the two failures, none of which the unit tests could see because
each component was behaving exactly as written.

- **Line regions ignored anchor weight.** `_best_region` counted anchors
  per line, so a line matching one weak anchor tied with a line matching
  one strong one, and the earliest line won. A finding about a button
  labelled "Links" located at the line mentioning "Register Now".
- **The same string counted twice.** Anchors deduplicated on
  `(kind, value)`, so a quoted `"Register Now"` also extracted as a
  title-case phrase survived as two anchors and outweighed a single, equally
  real `Links`.
- **Stylesheets outranked markup on a tie.** Equal scores broke
  alphabetically, which put `index.css` ahead of `index.html` for every
  finding whose class appears once in each.

After those three: 7/7 on `--search-only`.

## Running

```bash
# deterministic half only - no LLM, no API key, no cost. Safe in CI.
uv run python -m app.evals.retrieval --search-only

# whole path including the LLM. Costs real calls.
uv run python -m app.evals.retrieval

# machine-readable, for diffing two runs
uv run python -m app.evals.retrieval --search-only --json
```

## Reading the two numbers

Neither is "the" score, and **the gap between them is the interesting
part**. Some cases the deterministic search cannot be expected to win
alone: asked which of two files causes a contrast bug, it ranks the
component mentioning the class three times above the stylesheet that sets
the colour, because counting anchor weight is all it does. Knowing that
colour lives in CSS is judgment, and that's the LLM's job
(docs/principles.md #2).

So `component-app`'s `color-contrast` case is expected to **fail**
`--search-only` and **pass** the full run. Both failing means retrieval
never surfaced the file at all, which is a real bug.

## Scoring

Deterministic, no LLM judge — a location is right or wrong against a
hand-verified answer, which is a fact (docs/principles.md #2). That also
keeps the harness free of the thing it measures.

Outcomes are deliberately finer than pass/fail, because they call for
different fixes and cost a developer differently:

| Outcome | Meaning |
|---|---|
| `located` | Right file, range overlaps the expected one |
| `wrong_lines` | Right file, unrelated part of it — the model misread a snippet |
| `wrong_file` | Named a different file — a ranking problem in the search |
| `missed` | Said `no_match` where a real location existed — an honest miss |
| `false_positive` | Invented a location where there was nothing — the expensive one |
| `correct_no_match` | Correctly said there was nothing to find |

Ranges are scored by **overlap, not equality**. The expected range is one
person's bracketing of "the responsible code"; a model returning the
opening tag where the answer says the whole block has found the right
thing, and grading that as a miss would make the harness punish correct
answers and reward matching one person's judgement.

## Adding a case

A directory under `cases/`:

```
cases/my-case/
  source/           the checkout, copied verbatim from something real
  case.json         findings, hand-verified answers, axe + DOM evidence
```

Every expected line number must be checked against the committed `source/`,
not against a remembered earlier version of the file — `cns-anniversary`
has an `<h1>` that the live page didn't have when the Fix Agent first ran
on it.

Two things a good case set needs:

- **At least one `file_path: null` case per codebase shape.** Without one, a
  system that always guesses scores as well as one that knows when to stop.
  Both current cases have one.
- **Different codebase shapes.** `cns-anniversary` is one hand-written HTML
  file; `component-app` is `.tsx` components plus a stylesheet. The second
  caught a problem the first couldn't on the run it was added.
