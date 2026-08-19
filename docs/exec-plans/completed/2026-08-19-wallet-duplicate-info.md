# wallet-duplicate-info: Handle duplicate wallet info rows

## Context

`SqlAlchemyWalletRepository.get_info()` raises `MultipleResultsFound` when
legacy data contains more than one active wallet row for the same user and
public key. Other wallet lookups already tolerate duplicate legacy rows by
selecting the newest row deterministically.

## Files/Directories To Change

- `bot/infrastructure/persistence/sqlalchemy_wallet_repository.py`
- `bot/tests/infrastructure/test_infrastructure_repositories.py`
- `docs/exec-plans/`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> "++"

## Change Plan

1. [x] Add a regression test proving duplicate active wallet rows do not make
   `get_info()` raise and that the newest row determines the result.
2. [x] Update `get_info()` to select the newest matching active row.
3. [x] Run the focused repository test.
4. [x] Run repository quality gates relevant to the change.
5. [x] Complete and archive this execution plan.

## Risks / Open Questions

- Duplicate rows may contain conflicting wallet modes; choosing the highest
  `id` matches the repository's existing legacy-duplicate policy.
- This change intentionally does not mutate or deduplicate production data.

## Verification

- `uv run pytest bot/tests/infrastructure/test_infrastructure_repositories.py -k get_info`
- `just check-fast`
- Expected: regression test and quality gates pass.
