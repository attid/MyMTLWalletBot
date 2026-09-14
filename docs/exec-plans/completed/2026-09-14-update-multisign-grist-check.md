# update-multisign-grist-check: MTLToolsUpdateMulti: switch reserv-registry check from dead Mongo to Grist

## Context

The `MTLToolsUpdateMulti` button (Update MultiSign) imports
`check_account_id_from_grist` from `bot/db/mongo.py` and silently checks
MongoDB `mtl_tables.accounts` instead of Grist. Mongo was retired long ago:
the prod bot has no `MONGODB_URL`, so `accounts_collection` stays `None` and
the check always returns `False` with zero logging ("address not found in
registry" for every user). The working Grist implementation exists in
`bot/other/grist_tools.py` but no production code calls it.

## Files/Directories To Change

- `bot/routers/mtltools.py`
- `bot/tests/routers/test_mtltools.py`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> User confirmed the proposed scope ("++") for `bot/routers/mtltools.py` and
> `bot/tests/routers/test_mtltools.py` after the plan summary was presented.

## Change Plan

1. [x] In `bot/routers/mtltools.py` replace `from db.mongo import check_account_id_from_grist`
   with `from other.grist_tools import check_account_id_from_grist`.
2. [x] In `bot/tests/routers/test_mtltools.py` add a regression guard that the router
   module is wired to the Grist implementation (not `db.mongo`)
   (`test_update_multi_registry_check_wired_to_grist`).
3. [x] Run `just check-fast`: 451 passed; `just test-e2e-smoke` not run (not part of the fast gate).

## Risks / Open Questions

- Grist check is an exact match on `signers_type == "reserv"` and `account_id`;
  users whose Grist row has another type value will still get the alert (data issue, not code).
- Dead Mongo code removal (`bot/db/mongo.py`, `mongodb_url` setting, motor dependency,
  docker-compose/CI mongo entries) is deliberately out of scope until user approves.

## Verification

- `just test-fast` (router test `test_cmd_tools_update_multi` must stay green).
- `just lint` / `just arch-test`.
