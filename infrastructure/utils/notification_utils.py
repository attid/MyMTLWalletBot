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

    op_link = (
        f'<a href="https://viewer.eurmtl.me/operation/{operation.id}">expert link</a>'
    )
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
    elif operation.operation == "account_credited":
        return my_gettext(
            user_id,
            "info_credit",
            (account_link, float2str(operation.amount1), str(operation.code1), op_link),
            localization_service=loc_service,
        )
    elif operation.operation == "data_removed":
        return (
            f"You remove DATA: \n\n{operation.code1} \n\non {account_link}\n\n{op_link}"
        )
    elif operation.operation in ("data_created", "data_updated"):
        if operation.for_account == decode_for:
            return f"You added DATA on {account_link}\n\n{op_link}\n\nData:\n\n{operation.code1}\n{operation.code2}"
        if operation.code2 == decode_for:
            simple_decode_for = decode_for[:4] + ".." + decode_for[-4:]
            decode_for_link = "https://viewer.eurmtl.me/account/" + decode_for
            decode_for_link = f'<a href="{decode_for_link}">{simple_decode_for}</a>'
            return f"{account_link} set your account {decode_for_link} on his DATA \n\n{op_link}\n\nData Name:\n\n{operation.code1}"
        logger.info(
            f"op type: {operation.operation}, from: {operation.for_account}, {operation.code1}/{operation.code2}"
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
            return (
                my_gettext(
                    user_id,
                    "info_debit",
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
        return f"new operation for {account_link} \n\n{op_link}"
