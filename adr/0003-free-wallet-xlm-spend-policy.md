# ADR-0003: Free-wallet native XLM spending policy

- Status: Accepted
- Date: 2026-10-24
- Deciders: MMWB maintainers

## Context

A free wallet (`wallet.is_free=True`) must not spend its own native XLM through
operations the bot allows it to sign. The previous XDR check used a flat
operation allowlist: `PathPaymentStrictSend`, `PathPaymentStrictReceive`, and
`CreateClaimableBalance` were rejected wholesale. That blocked safe donations
(MTLCROWD, Docker3 #99) where the free wallet spends a non-native asset or where
another account is the effective operation source.

Stellar separates several concepts that must not be conflated:

- a signature (including a free wallet co-signing),
- the transaction fee source,
- the transaction source,
- the operation source,
- the asset an operation actually spends.

For `PathPaymentStrictSend` and `PathPaymentStrictReceive` the spent asset is
`send_asset`, regardless of `dest_asset` or the intermediate `path`. For
`CreateClaimableBalance` it is `asset`.

## Decision

1. Effective operation source is `operation.source` when set, otherwise
   `transaction.source`. Muxed accounts are compared by their underlying `G...`
   account.
2. `PathPaymentStrictSend`, `PathPaymentStrictReceive`, and
   `CreateClaimableBalance` are allowed for a free wallet when the spent asset
   is non-native. They are rejected only when the spent asset is native XLM and
   the effective source is the free wallet itself.
3. The existing `Payment` XLM guard and the Soroban `InvokeHostFunction` guard
   stay unchanged and are not relaxed.
4. If the free-wallet address, effective source, or spent asset cannot be
   determined, the check fails closed. Fee-bump transactions remain
   unsupported and are rejected for free wallets.
5. A dedicated `FreeWalletPolicyError` reaches the router, which shows a
   localized free-wallet explanation instead of the generic `bad_xdr` message
   and does not echo raw XDR. Other invalid-XDR causes keep the generic path.

The free-wallet policy applies to assets spent by operations only. Transaction
fees and Stellar base reserves are still paid in XLM by the transaction source.
Those are separate product constraints and are not changed by this ADR.

## Consequences

- Positive: safe non-native path payments and claimable balances can be signed
  by free wallets; native-XLM spending and co-signer confusion are blocked;
  users get an actionable rejection reason.
- Negative: fee and reserve XLM consumption by a free wallet is still possible
  through transaction fees; sponsored reserves and fee-bump flows remain
  unsupported.
- Follow-ups: decide the product boundary for free-wallet transaction fees and
  reserves in a separate task; consider richer rejection details (operation
  type, asset) if support needs them.

## Alternatives Considered

1. Keep the flat allowlist and reject all path/claimable-balance operations.
   Rejected: blocks legitimate non-native donations and contradicts the
   "do not spend own XLM" invariant.
2. Check `dest_asset` or transaction source instead of `send_asset` and
   effective operation source. Rejected: incorrect semantics; allows native
   XLM spending or blocks safe co-signed operations.
3. Rely on signatures to identify the spending account. Rejected: a signature
   does not imply source, and a free wallet may only co-sign.
