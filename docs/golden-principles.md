# Golden Principles

## 1) Parse, Do Not Guess

Never assume data shape or architecture intent. Use explicit contracts,
validated inputs, and documented boundaries.

## 2) Mechanical Enforcement Over Memory

Anything important should be checked by tools (linters, tests, CI), not only by
human conventions.

## 3) Minimal, Verifiable Diffs

Prefer small changes with clear verification evidence over broad rewrites.

## 4) Preserve Existing Guarantees

Do not weaken tests, lint gates, or CI checks to make changes pass.

## 5) Commit Discipline for DB Writes

Write operations in bot code must include `await session.commit()` within the
same session block.

## 6) Improve Touched Areas

When touching a file, leave it clearer or safer than before (naming, structure,
tests, docs).
