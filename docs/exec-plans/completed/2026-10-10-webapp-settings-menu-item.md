# webapp-settings-menu-item: Open /settings from the mini app three-dots menu

## Context

The `/settings` page (saved-key management, key deletion) exists since
e2cd02d but no page links to it — the only way in is typing the URL.
Users cannot delete a saved private key. Owner wants the entry in the
Telegram mini app three-dots menu (the menu shown on the owner's
screenshot), not an on-page button. Telegram exposes the fixed
"Settings" item via `Telegram.WebApp.SettingsButton` (Bot API 7.0+);
the label cannot be customized.

## Files/Directories To Change

- `webapp/templates/base.html`
- `webapp/templates/settings.html`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> Owner: «там должно было появиться меню ведущее на /settings возможно
> продолбали. проблема что я не могу удалить приватный ключ из вебаппа
> сейчас»; chose the three-dots menu variant: «нет не хочу кнопку я
> прислал скрин хочу в то меню»; approved with «на всех давай ++» and
> «Commit + push ++».

## Change Plan

1. [x] `base.html`: show `SettingsButton` on every page; onClick
       navigates to `/settings` preserving the `?lang=` param.
2. [x] `settings.html`: hide the SettingsButton on the settings page
       itself (self-navigation is a dead end).
3. [x] Run the full bot test suite.

## Risks / Open Questions

- Item label is fixed by Telegram («Настройки»/«Settings»), owner
  informed and accepted.

## Verification

- Full suite: 925 passed, 8 deselected.
- Webapp template tests: 14 passed.
