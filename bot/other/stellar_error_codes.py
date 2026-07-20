# Mapping of Stellar Horizon error codes to human-readable English messages

TRANSACTION_ERROR_CODES = {
    "tx_failed": "Transaction failed (error in one of the operations)",
    "tx_bad_auth": "Too few valid signatures or wrong network",
    "tx_bad_seq": "Bad transaction sequence number",
    "tx_insufficient_balance": "Insufficient balance to pay fee",
    "tx_no_source_account": "Source account not found",
    "tx_bad_auth_extra": "Unused signatures attached to transaction",
    "tx_internal_error": "Internal Horizon error",
    "tx_too_late": "Transaction is too late (time bounds)",
    "tx_too_early": "Transaction is not yet valid (time bounds)",
    "tx_missing_operation": "No operations in transaction",
}

OPERATION_ERROR_CODES = {
    "op_underfunded": "Insufficient funds for the operation",
    "op_no_destination": "Destination account not found",
    "op_no_source_account": "Source account not found",
    "op_not_authorized": "Operation not authorized",
    "op_line_full": "Trustline limit exceeded for destination",
    "op_no_trust": "No trustline for this asset",
    "op_bad_auth": "Too few valid signatures or wrong network",
    "op_bad_auth_extra": "Unused signatures attached to operation",
    "op_account_merge_seqnum_needed": "Account merge needs a valid sequence number",
    "op_low_reserve": "Not enough XLM to meet the minimum reserve",
    "op_offer_not_found": "Offer not found",
    "op_cross_self": "Cannot cross own offer",
    "op_malformed": "Malformed operation",
    "op_already_exists": "Object already exists",
    "op_no_issuer": "Asset issuer not found",
    "op_invalid_amount": "Invalid amount",
    "op_src_no_trust": "Source account has no trustline",
    "op_src_not_authorized": "Source account not authorized",
}


def get_stellar_error_message(result_codes: dict) -> str:
    """
    Returns a human-readable error message for result_codes from Horizon.
    """
    # First, check transaction-level error
    tx_code = result_codes.get("transaction")
    if tx_code and tx_code in TRANSACTION_ERROR_CODES:
        tx_msg = TRANSACTION_ERROR_CODES[tx_code]
    elif tx_code:
        tx_msg = f"Transaction code: {tx_code}"
    else:
        tx_msg = None

    # Successful operations can precede the operation that failed.
    op_codes = result_codes.get("operations")
    for operation_number, op_code in enumerate(op_codes or (), start=1):
        if op_code == "op_success":
            continue

        if op_code in OPERATION_ERROR_CODES:
            return (
                f"Operation {operation_number}: {op_code} — "
                f"{OPERATION_ERROR_CODES[op_code]}"
            )

        return f"Operation {operation_number}: {op_code}"

    # If only transaction error
    if tx_msg:
        return tx_msg

    # If nothing found
    return "Unknown Stellar error"
