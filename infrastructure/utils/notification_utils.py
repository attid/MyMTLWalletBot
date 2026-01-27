from typing import Any
from loguru import logger
from db.models import TOperations
from other.lang_tools import my_gettext
from infrastructure.utils.common_utils import float2str
from infrastructure.services.app_context import AppContext


def decode_db_effect(
    operation: TOperations,
    decode_for: str,
    user_id: int,
    app_context: AppContext = None,
    localization_service: Any = None,
):
    """Formats message about operation for sending to user

    Args:
        operation: Operation object from database
        decode_for: Public key of wallet for which message is formatted
        user_id: User ID for message localization
        app_context: Application context (legacy, optional)
        localization_service: Localization service (preferred)
    """
    assert operation.for_account is not None, "for_account must not be None"
    assert operation.id is not None, "id must not be None"
    simple_account = operation.for_account[:4] + ".." + operation.for_account[-4:]
    account_link = "https://viewer.eurmtl.me/account/" + operation.for_account
    account_link = f'<a href="{account_link}">{simple_account}</a>'

    # Resolve dependencies
    loc_service = localization_service
    if not loc_service and app_context:
        loc_service = app_context.localization_service

    op_id_clean = operation.id.split('_')[0] if operation.id else ""
    op_link = f'<a href="https://viewer.eurmtl.me/operation/{op_id_clean}">viewer</a>'
    if operation.operation == "trade":
        return my_gettext(
            user_id,
            "info_trade",
            (
                account_link,
                float2str(operation.amount1),
                str(operation.code1),
                float2str(operation.amount2),
                str(operation.code2),
                op_link,
            ),
            localization_service=loc_service,
        )
    elif operation.operation == "account_debited":
        return my_gettext(
            user_id,
            "info_debit",
            (account_link, float2str(operation.amount1), str(operation.code1), op_link),
            localization_service=loc_service,
        )
    elif operation.operation == "create_account":
        return my_gettext(
            user_id,
            "info_create_account",
            (
                account_link,
                float2str(operation.amount1),
                str(operation.code1),
                op_link,
            ),
            localization_service=loc_service,
        )
    elif operation.operation == "account_credited":
        return my_gettext(
            user_id,
            "info_credit",
            (account_link, float2str(operation.amount1), str(operation.code1), op_link),
            localization_service=loc_service,
        )
    elif operation.operation in (
        "path_payment_strict_send",
        "path_payment_strict_receive",
    ):
        return my_gettext(
            user_id,
            "info_trade",
            (
                account_link,
                float2str(operation.amount2),  # Sent amount (Source)
                str(operation.code2),  # Sent asset (Source)
                float2str(operation.amount1),  # Received amount (Dest)
                str(operation.code1),  # Received asset (Dest)
                op_link,
            ),
            localization_service=loc_service,
        )
    elif operation.operation == "manage_data":
        if operation.code2 is None:
            # Data Removed
            return my_gettext(
                user_id,
                "info_data_removed",
                (
                    str(operation.code1),
                    account_link,
                    op_link,
                ),
                localization_service=loc_service,
            )
        elif operation.code2 == decode_for:
             # User mentioned in Data
             simple_decode_for = decode_for[:4] + ".." + decode_for[-4:]
             decode_for_link = "https://viewer.eurmtl.me/account/" + decode_for
             decode_for_link = f'<a href="{decode_for_link}">{simple_decode_for}</a>'
             
             return my_gettext(
                user_id,
                "info_data_mention",
                (
                    account_link,
                    decode_for_link,
                    op_link,
                    str(operation.code1)
                ),
                localization_service=loc_service,
             )
        else:
             # Data Set / Updated
             return my_gettext(
                user_id,
                "info_data_set",
                (
                    account_link,
                    op_link,
                    str(operation.code1),
                    str(operation.code2)
                ),
                localization_service=loc_service,
             )
    elif operation.operation == "payment":
        # Handle payment operations specifically
        memo_text = ""
        if operation.memo:
            memo_text = f"\nMemo: {operation.memo}"

        if decode_for == operation.for_account:
            # This is an incoming payment
            return (
                my_gettext(
                    user_id,
                    "info_credit",
                    (
                        account_link,
                        float2str(operation.amount1),
                        str(operation.code1),
                        op_link,
                    ),
                    localization_service=loc_service,
                )
                + memo_text
            )
        else:
            # This is an outgoing payment or other account
            # Use source account for the message "From ... was debit" to be logically correct with "Source"
            simple_source = operation.from_account[:4] + ".." + operation.from_account[-4:]
            source_link = "https://viewer.eurmtl.me/account/" + operation.from_account
            source_link_html = f'<a href="{source_link}">{simple_source}</a>'

            return (
                my_gettext(
                    user_id,
                    "info_debit",
                    (
                        source_link_html,
                        float2str(operation.amount1),
                        str(operation.code1),
                        op_link,
                    ),
                    localization_service=loc_service,
                )
                + memo_text
            )
    elif operation.operation == "manage_sell_offer":
        # Handle sell offer operations
        # Format: account_link is creating/updating sell offer of amount1 code1 for code2 at price amount2
        offer_id = ""
        if operation.transaction_hash:
            offer_id = f" (ID: {operation.transaction_hash})"

        # Adjust price formatting - if price is a number, format it nicely
        price_str = operation.amount2
        try:
            price = float(operation.amount2 or 0)
            price_str = float2str(price)
        except:
            pass

        # Format larger amounts for better readability (like 2480 EURMTL)
        amount_str = float2str(operation.amount1)
        if operation.amount1 and float(operation.amount1) > 1000:
            # Add spaces for large numbers: 2480.2366399 -> 2 480.24
            try:
                amount = float(operation.amount1)
                amount_str = f"{amount:,.2f}".replace(",", " ").replace(".", ",")
            except:
                pass

        # Use localization for sell offer message
        return my_gettext(
            user_id,
            "info_sell_offer",
            (
                account_link,
                amount_str,
                str(operation.code1),
                str(operation.code2),
                price_str,
                offer_id,
                op_link,
            ),
            localization_service=loc_service,
        )
    elif operation.operation == "manage_buy_offer":
        # Handle buy offer operations
        offer_id = ""
        if operation.transaction_hash:
            offer_id = f" (Offer ID: {operation.transaction_hash})"

        # Use localization for buy offer message
        return my_gettext(
            user_id,
            "info_buy_offer",
            (
                account_link,
                str(operation.code1),
                float2str(operation.amount1),
                str(operation.code2),
                float2str(operation.amount2),
                offer_id,
                op_link,
            ),
            localization_service=loc_service,
        )
    else:
        return f"new operation for {account_link} \n\n{op_link}"
