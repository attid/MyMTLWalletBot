from typing import Any
from other.lang_tools import my_gettext
from infrastructure.utils.common_utils import float2str
from core.models.notification import NotificationOperation
from infrastructure.services.app_context import AppContext

def decode_db_effect(
    operation: NotificationOperation,
    decode_for: str,
    user_id: int,
    app_context: AppContext = None,
    localization_service: Any = None,
    force_perspective: str = None,
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
        # Trade: Bought (amount/asset_code), Sold (amount2/asset2_code)
        amount_bought = float2str(operation.trade_bought_amount)
        asset_bought = str(operation.trade_bought_asset)
        amount_sold = float2str(operation.trade_sold_amount)
        asset_sold = str(operation.trade_sold_asset)

        return my_gettext(
            user_id,
            "info_trade",
            (
                account_link,
                amount_bought,
                asset_bought,
                amount_sold,
                asset_sold,
                op_link,
            ),
            localization_service=loc_service,
        )
    elif operation.operation == "account_debited":
        return my_gettext(
            user_id,
            "info_debit",
            (account_link, float2str(operation.payment_amount), str(operation.payment_asset), op_link),
            localization_service=loc_service,
        )
    elif operation.operation == "create_account":
        return my_gettext(
            user_id,
            "info_create_account",
            (
                account_link,
                float2str(operation.payment_amount),
                str(operation.payment_asset),
                op_link,
            ),
            localization_service=loc_service,
        )
    elif operation.operation == "account_credited":
        return my_gettext(
            user_id,
            "info_credit",
            (account_link, float2str(operation.payment_amount), str(operation.payment_asset), op_link),
            localization_service=loc_service,
        )
    elif operation.operation in (
        "path_payment_strict_send",
        "path_payment_strict_receive",
    ):
        # Path Payment: Sent (amount2/asset2_code) -> Received (amount/asset_code)
        amount_sent = float2str(operation.amount2)
        asset_sent = str(operation.asset2_code)
        amount_received = float2str(operation.amount)
        asset_received = str(operation.asset_code)

        return my_gettext(
            user_id,
            "info_trade",
            (
                account_link,
                amount_sent,
                asset_sent,
                amount_received,
                asset_received,
                op_link,
            ),
            localization_service=loc_service,
        )
    elif operation.operation == "manage_data":
        if operation.asset2_code is None:
            # Data Removed
            return my_gettext(
                user_id,
                "info_data_removed",
                (
                    str(operation.asset_code),
                    account_link,
                    op_link,
                ),
                localization_service=loc_service,
            )
        elif operation.asset2_code == decode_for:
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
                    str(operation.asset_code)
                ),
                localization_service=loc_service,
             )
        else:
             # Data Set / Updated
             data_name = str(operation.asset_code)
             data_value = str(operation.asset2_code)
             return my_gettext(
                user_id,
                "info_data_set",
                (
                    account_link,
                    op_link,
                    data_name,
                    data_value
                ),
                localization_service=loc_service,
             )
    elif operation.operation == "payment":
        # Handle payment operations specifically
        memo_text = ""
        if operation.memo:
            memo_text = f"\nMemo: {operation.memo}"

        is_incoming = (decode_for == operation.for_account)
        if force_perspective == 'debit':
            is_incoming = False
        elif force_perspective == 'credit':
            is_incoming = True

        if is_incoming:
            # This is an incoming payment
            return (
                my_gettext(
                    user_id,
                    "info_credit",
                    (
                        account_link,
                        float2str(operation.payment_amount),
                        str(operation.payment_asset),
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
                        float2str(operation.payment_amount),
                        str(operation.payment_asset),
                        op_link,
                    ),
                    localization_service=loc_service,
                )
                + memo_text
            )
    elif operation.operation == "manage_sell_offer":
        # Handle sell offer operations
        # Format: account_link is creating/updating sell offer of amount(1) code1 for code2 at price amount2
        offer_id = ""
        if operation.transaction_hash:
            offer_id = f" (ID: {operation.transaction_hash})"

        # Adjust price formatting - if price is a number, format it nicely
        price_str = str(operation.offer_price)
        try:
            price_val = float(operation.offer_price or 0)
            price_str = float2str(price_val)
        except Exception:
            pass

        # Format larger amounts for better readability (like 2480 EURMTL)
        amount_str = float2str(operation.offer_amount)
        if operation.offer_amount and float(operation.offer_amount) > 1000:
            # Add spaces for large numbers: 2480.2366399 -> 2 480.24
            try:
                amt_val = float(operation.offer_amount)
                amount_str = f"{amt_val:,.2f}".replace(",", " ").replace(".", ",")
            except Exception:
                pass

        # Use localization for sell offer message
        # Manage Sell Offer: 
        # Selling: asset2_code (Amount: operation.amount)
        # Buying: asset_code (Price: operation.amount2)
        
        selling_asset = str(operation.offer_selling_asset)
        buying_asset = str(operation.offer_buying_asset)
        
        return my_gettext(
            user_id,
            "info_sell_offer",
            (
                account_link,
                amount_str, # Amount being sold
                selling_asset,
                buying_asset,
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
        # Buy Offer:
        # Buying: asset_code (Amount: operation.amount)
        # Selling: asset2_code (Price: operation.amount2)
        
        buying_asset = str(operation.offer_buying_asset)
        amount_buying = float2str(operation.offer_amount)
        selling_asset = str(operation.offer_selling_asset)
        price_unit = float2str(operation.offer_price)

        return my_gettext(
            user_id,
            "info_buy_offer",
            (
                account_link,
                buying_asset,
                amount_buying,
                selling_asset,
                price_unit,
                offer_id,
                op_link,
            ),
            localization_service=loc_service,
        )
    else:
        return f"new operation for {account_link} \n\n{op_link}"
