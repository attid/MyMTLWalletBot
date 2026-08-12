# Swap Path Propagation Design

## Problem

The swap flow currently separates quote selection from transaction
construction. Horizon returns a ranked path record containing both an amount
and a list of intermediate assets. The legacy quote helpers retain only the
amount, so the router calculates slippage from the best route while the
transaction builder receives its default empty path. For markets such as
USDM/MTL, this makes the transaction execute a weak direct market and fail
with `op_under_dest_min`.

## Design

Each strict-send or strict-receive quote helper will return the amount and the
intermediate asset list from the same first Horizon record. The router will
pass that list through the `SwapAssets` use case and the `IStellarService`
contract. `StellarService.swap_assets` already knows how to serialize a path,
so its existing path parameter remains the final construction boundary.

This avoids a second pathfinding request and guarantees that the amount used
for `dest_min` or `send_max` describes the route embedded in the XDR. Empty
paths remain valid when Horizon actually selects a direct market.

## Regression Coverage

Router tests will provide a Horizon response with a real intermediate asset
and use the real `SwapAssets`/`StellarService` construction path where
practical. The resulting XDR will be decoded and its strict-send or
strict-receive operation must contain the expected intermediate asset. Tests
will cover both command modes because both helpers currently discard path
data. Existing direct-route tests remain valid with an empty list.

No submission to Stellar is required: decoding the unsigned XDR is sufficient
to prove that quote selection and transaction construction agree.
