# Telegram Rich Messages Evaluation

Status: evaluation paused for team review
Recorded: 2026-08-18
Suggested review date: 2026-08-25

## Purpose

Evaluate Telegram Rich Messages for selected MMWB screens. This is a research
note, not an implementation decision. Regular HTML messages remain the current
product behavior.

## Verified Platform Capabilities

Telegram introduced Rich Messages in Bot API 10.1 on 2026-06-11 and expanded
their input blocks and media handling in Bot API 10.2 on 2026-07-14.

Relevant official references:

- [Telegram product announcement](https://telegram.org/blog/watch-apps-and-more/kk?setln=en)
- [Bot API Rich Messages](https://core.telegram.org/bots/api#rich-messages)
- [Bot API `sendRichMessage`](https://core.telegram.org/bots/api#sendrichmessage)
- [aiogram `sendRichMessage`](https://docs.aiogram.dev/en/v3.30.0/api/methods/send_rich_message.html)

Verified limits and features:

- Up to 32,768 UTF-8 characters in one rich message.
- Up to 500 blocks and 16 nesting levels.
- Up to 50 photo, video, animation, audio, or voice-note attachments.
- Headings, lists, task lists, tables, quotes, collapsible details, footnotes,
  anchors, code blocks, formulas, maps, collages, and slideshows.
- Rich Markdown, Rich HTML, or explicit input blocks.
- Inline and reply keyboards can be attached.
- Rich messages can be edited with `editMessageText.rich_message`.
- Regular rich messages can be sent to private chats, groups, topics, and
  channels when the bot has the corresponding send permissions.
- Streaming with `sendRichMessageDraft` is separate and limited to private
  chats. A draft is a temporary preview and must be finalized with
  `sendRichMessage`.

The repository now resolves aiogram 3.30.0, which exposes
`InputRichMessage` and `Bot.send_rich_message()` for Bot API 10.2.

## Live Experiment

Two messages were sent through `@MyMTLWalletTestBot` on 2026-08-18:

1. Message `8951`: proposed wallet home screen with a four-column balance
   table, heading, link, expandable wallet details, date-time formatting, and
   an inline keyboard.
2. Message `8952`: decoded transaction preview with a summary table, operation
   list, nested details, footnote, inline keyboard, and a 6,232-character
   synthetic raw XDR block.

Telegram accepted both messages. The second experiment confirmed that a rich
message can carry the full synthetic XDR beyond the regular 4,096-character
message limit.

### Client observations

| Client | Observation |
| --- | --- |
| Mobile | The four-column balance table does not fit the viewport, but horizontal scrolling is convenient. |
| Desktop | Pending review. |
| Web | Pending review. |

The mobile result is acceptable for reports, but primary wallet information
should not require horizontal scrolling. A home-screen table should be tested
with three short columns, for example `Asset`, `Available`, and `Total`.
Locked amounts and technical details can be placed below the row or in a
collapsible details block. This is a design recommendation, not a product
validation limit.

## Candidate Uses in MMWB

### 1. Transaction decoding and signing

Highest-value candidate. The current signing path truncates decoded output to
approximately 4,000 characters and replaces oversized signing content with a
generic message. A rich signing screen could show:

- A compact summary of wallet, network, fees, and operation count.
- Human-readable payment, offer, and Soroban operations.
- Prominent warnings for unusual or destructive operations.
- Expandable technical details and complete raw XDR.
- Existing sign, reject, decode, PIN, and Web App controls.

This improves both readability and the user's ability to verify what is being
signed.

### 2. Send and swap confirmation

Use structured sections for amount, asset, destination, memo, fees, expected
balance, exchange path, and canceled offers. For swaps, replace the current
asterisk convention with explicit labels such as `estimated` and `minimum
received`.

### 3. Wallet home screen

Use a narrow balance table or structured list. Avoid placing essential values
outside the initial mobile viewport. Full issuers, liabilities, and network
details can remain expandable.

### 4. Orders and SEP-6/SEP-24 requests

Move long values out of button labels. Present orders or anchor requests as a
compact list or table, with each record's identifiers, timestamps, and links in
an expandable section.

### 5. Cheques and invoices in inline mode

`InputRichMessageContent` can make a shared cheque or invoice a structured
card in private chats, groups, or channels. This is a useful later experiment
because it exercises rich inline results rather than the bot's normal screen
flow.

### 6. Notification digest

Rich messages could combine queued blockchain notifications into one digest.
This should be evaluated separately because current notification delivery has
per-event history, cache invalidation, ordering, and at-least-once guarantees.

### 7. Receive QR and help screens

These are lower-priority candidates. The existing photo with caption already
handles the receive screen well. Rich messages become useful only if one card
needs multiple media items, memo guidance, or longer instructions.

## Proposed Integration Boundary

Do not replace every existing `send_message()` call. Short menus,
confirmations, and prompts remain simpler as regular messages.

If implementation proceeds, introduce a rich-message path alongside
`bot/infrastructure/utils/telegram_utils.py::send_message()`. It must preserve
the existing UI guarantees:

- Edit or replace the tracked screen consistently.
- Maintain `last_message_id`.
- Preserve notification badge decoration and its UI markup lease.
- Support existing inline keyboards.
- Keep Telegram failures inside the established UI operation wrapper.
- Store or reconstruct a regular-message fallback only if client testing shows
  that one is necessary.

Likely implementation and test boundaries:

- `bot/infrastructure/utils/telegram_utils.py`
- `bot/tests/infrastructure/test_telegram_utils.py`
- `bot/routers/sign.py` and `bot/tests/routers/test_sign.py` for the first pilot
- Localization resources for any new user-facing strings

The signing/decode pilot is preferable to a global migration because it solves
an existing truncation problem while keeping the change isolated.

## Open Questions for Review

1. How do the two live samples render in Telegram Desktop and Telegram Web?
2. Is horizontal table scrolling acceptable outside the home screen?
3. Should the first pilot cover only decoded XDR, or the complete signing
   confirmation screen?
4. Should rich content be generated with Rich Markdown or explicit blocks?
   Markdown is easier to author; explicit blocks provide stronger structure.
5. What behavior do supported clients show when a rich message is edited?
6. What happens on older or third-party Telegram clients, and is an application
   fallback required?
7. Should raw XDR be visible in a collapsed section by default or remain behind
   the existing decode action?

## Suggested Next Experiment

When review resumes:

1. Record Desktop and Web observations for messages `8951` and `8952`.
2. Send a mobile-focused home variant with no more than three short columns.
3. Send the same decoded transaction using explicit blocks and compare it with
   Rich Markdown.
4. Test editing a rich message while preserving its inline keyboard.
5. Decide whether to implement the signing/decode pilot.
6. If approved, create a new execution plan with explicit edit permission for
   the integration utility, signing router, localization resources, and tests.
