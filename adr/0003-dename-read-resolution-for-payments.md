# ADR-0003: Resolve DeName recipients through indexed public API

- Status: Accepted
- Date: 2026-09-29
- Deciders: DeName integration implementation

## Context

The bot already sends Stellar payments to account IDs, Telegram users, and
SEP-2 federation addresses. DeName stores forward addresses in Soroban
contracts, while `dens-api` exposes a read-only index of contract events.
Paying an outdated or substituted address would be costly to reverse.

## Decision

Use a dedicated `DeNameService` injected through `AppContext`. It reads only
the configured HTTPS mainnet `/api/v1` endpoint. It validates the name, record,
forward Stellar account ID, active expiration, and the health and recency of
the root and TLD indexer streams. The router looks up the name on entry and
again immediately before constructing the transaction. Any error or changed
address stops the flow. The user sees the name and full resolved account ID in
the existing payment confirmation.

## Consequences

- Positive: No new package or signing protocol is needed. Existing `G…`,
  federation, and Telegram username flows keep their behavior.
- Negative: DeName payments depend on a healthy indexer and API. The API has
  no network identity endpoint, so operations must configure a mainnet service.
- Follow-ups: If stronger settlement guarantees are required, add an on-chain
  read or explicit user confirmation tied to a recent ledger. The signed
  transaction still contains the concrete account ID, not the name.

## Alternatives Considered

1. Call Soroban RPC directly on every lookup. This avoids indexer lag but adds
   contract routing, network, and RPC failure handling to the bot.
2. Treat `owner` as the payment destination. Ownership and forward resolution
   differ, so this would send to the wrong account for some names.
