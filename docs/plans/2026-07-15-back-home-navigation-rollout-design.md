# Back/Home Navigation Rollout Design

## Context

Send and Swap already establish the navigation contract for the bot:

- `FlowBack` is a flow-local action that returns to the semantic previous step;
- `Return` is the global Home action;
- Back preserves the active flow and counts as user activity;
- Home clears FSM state, renders the main balance screen, completes the
  notification flow, and releases pending blockchain notifications;
- leaving a transaction confirmation through Back invalidates stale signing
  data immediately;
- a successful or otherwise irreversible terminal screen does not offer Back;
- notification-message keyboards remain Home-only and are not converted into
  flow navigation.

This rollout applies that existing contract to the rest of the bot. It does not
introduce browser-style navigation history, a generic screen stack, or a new
navigation framework.

## Screen Classification

Every user-facing screen in scope is classified before it is changed.

| Screen type | Back behavior | Home behavior |
| --- | --- | --- |
| Intermediate FSM step | `FlowBack` rerenders the semantic previous step and preserves still-valid data | Existing `Return` handler clears the flow and completes notification delivery |
| Transaction confirmation before submit | `FlowBack` returns to the last editable step and removes pending XDR/signature fields | Existing `Return` behavior |
| Nested callback menu without FSM | Existing parent-menu callback is shown with the localized Back label; Home remains a separate `Return` button | Existing `Return` behavior |
| Entry screen with no parent inside the function | No synthetic Back target is invented | Home only |
| Successful, submitted, destructive, or externally completed terminal screen | Back is omitted so an irreversible action cannot be re-entered | Home only |
| Notification message | Unchanged | Existing Settings + Home keyboard |

Invalid input and recoverable build errors remain in the current state and show
the same navigation controls as the corresponding prompt. Back handlers must
reuse existing render functions where possible, not duplicate screen markup.

## State and Data Safety

Back is a state transition, not merely a keyboard change. Each functional slice
must document a state-transition table before implementation. The table names
the current state, previous state or parent renderer, data retained, and data
invalidated.

The Send/Swap safety rules remain mandatory everywhere:

- preserve global UI data such as `last_message_id` and unrelated FSM keys;
- preserve user input that is still valid for the previous step;
- clear data owned by the abandoned step and all later steps;
- clear `PENDING_SIGNATURE_REQUEST_KEY`, `xdr`, `operation`, `sign_msg`,
  `success_msg`, and flow-specific signing callbacks when leaving a built
  confirmation;
- never allow Back to reopen a transaction after successful submission;
- stale `FlowBack` callbacks without an active FSM must remain inert and must
  not extend the notification hold.

The shared primitives in `bot/keyboards/common_keyboards.py` and the activity
classification in `bot/middleware/notification_activity.py` are already the
baseline. A slice should extend them only when a real keyboard shape cannot be
expressed with the current helpers.

## Rollout Strategy

Three rollout shapes were considered:

1. One repository-wide patch. It is mechanically direct but creates a very
   large review surface and mixes unrelated transaction/state risks.
2. One patch per router. It is easy to locate, but large routers such as
   `inout.py`, `wallet_setting.py`, and `sign.py` contain several independent
   functions and would still produce risky changes.
3. Functional slices with a master plan and a small execution plan per slice.
   This follows the existing Send/Swap work, keeps each transition graph and
   regression suite reviewable, and permits stopping safely after any slice.

The rollout uses option 3. Each slice starts with a mini-plan under
`docs/exec-plans/active/`, follows TDD, passes its focused router tests, then
passes `just check-fast`. Higher-risk signing slices also run E2E/external
checks before completion.

## Functional Slices

### 1. Trade and order management

Cover new-order asset selection, amount, receive amount, transaction
confirmation, and existing-order amount/price editing in
`bot/routers/trade.py`. Back from a built order must invalidate its pending
signature payload. Market and order-list/detail screens use their existing
parent callbacks and gain a separate Home only where both actions are
semantically available.

### 2. Wallet settings and assets

Cover expert asset code/issuer entry, address-book editing, wallet selection,
asset visibility, add/delete asset menus, data management, and security
submenus in `bot/routers/wallet_setting.py` and `bot/keyboards/assets.py`.
Stateful entry fields use `FlowBack`; nested menus reuse explicit callbacks to
their immediate existing parent. Successful trustline/security operations stay
Home-only.

### 3. MTL tools and MTLAP tools

Cover delegate, donation-address/name/percent, BIM-address/name, and MTLAP
recommend/delegate flows in `bot/routers/mtltools.py` and
`bot/routers/mtlap.py`. Back from confirmation clears the tool signing payload;
Back within form entry returns one field at a time. Tool lists and detail menus
use their existing parent callbacks plus Home.

### 4. Wallet onboarding and signing credentials

Cover private/public key entry in `bot/routers/add_wallet.py` and PIN/password
setup or retry screens in `bot/routers/sign.py`. Back must never expose secrets,
restore an already consumed signing request, or turn WebApp cancellation into a
transaction replay. This slice follows Trade, Assets, and Tools because signing
is shared infrastructure and has the broadest regression surface.

### 5. Used-function navigation audit

After the four priority slices, audit the remaining actively used stateful and
nested-menu flows. Candidate files identified by the initial inventory include
`bot/routers/inout.py`, `bot/routers/common_start.py`, `bot/routers/fest.py`,
`bot/routers/bsn.py`, `bot/routers/common_setting.py`,
`bot/routers/notification_settings.py`, `bot/routers/start_msg.py`,
`bot/routers/uri.py`, and `bot/keyboards/webapp.py`. The audit first confirms
that a function is still used, then creates a separate mini-plan for each
material function that needs changes. It must not pull legacy or explicitly
deferred functions back into scope.

### 6. Repository-wide regression

Re-run the inline-keyboard inventory after all approved slices, verify every
changed transition and signing boundary, and execute the full repository,
E2E, external, architecture, and secret-scan gates.

## Explicitly Deferred or Excluded

- `bot/routers/ton.py` is legacy and must not be modified by this rollout.
- `bot/routers/cheque.py` is low-use and deferred to a future separately
  approved task.
- Admin-only restart confirmation is not an inline user-navigation flow and is
  excluded.
- Notification-message keyboards remain Home-only under the existing delivery
  contract.

## Testing Contract

Each slice adds router tests using `mock_telegram` and real local keyboard
builders. At minimum, tests verify:

- every intermediate prompt contains both the expected Back action and
  `Return` Home;
- Back moves to the correct prior state and renders the correct prompt/menu;
- valid earlier data and global FSM data survive;
- later-step and signing data are removed immediately;
- invalid input keeps the current state and the same navigation controls;
- Home clears state and calls notification-flow completion;
- Back extends notification hold only while FSM is active;
- successful/irreversible terminal screens contain no Back;
- a stale Back callback cannot reopen or resubmit a transaction.

Focused tests run first, followed by `just check-fast`. Transaction/signing and
external-payment slices additionally run `just test-e2e-smoke`, and any slice
touching Redis/notifier integration runs `just test-external`. Every completed
slice runs `just secret-scan` before commit.

## Completion Criteria

The rollout is complete when every user-facing inline keyboard is accounted for
in one of the classifications above, every intermediate state has a tested
semantic Back transition, Home consistently completes the flow, no terminal
screen permits replay through Back, and all repository gates pass.
