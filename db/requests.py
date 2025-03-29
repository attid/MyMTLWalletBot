import asyncio
from datetime import timedelta
from sys import argv
from typing import Union, List, Optional, Tuple

from loguru import logger
from sqlalchemy import update, select
from sqlalchemy.orm import Session, Query
from db.models import *


def db_add_message(session: Session, user_id: int, text: str, use_alarm: int = 0, update_id: int = None,
                   button_json: str = None) -> None:
    """
    Insert a new message into the t_message table.

    :param session: SQLAlchemy DB session
    :param user_id: The ID of the user
    :param text: The message text
    :param use_alarm: The alarm usage flag (default is 0)
    :param update_id:
    :param button_json:
    """
    new_message = TMessage(user_id=user_id, text=text, use_alarm=use_alarm, update_id=update_id,
                           button_json=button_json)
    session.add(new_message)
    session.commit()


# def db_send_admin_message(session: Session, msg: str):
#     db_add_message(session, 84131737, msg)
#     # add text to file error.txt
#     with open('error.txt', 'a') as f:
#         f.write(f"{argv} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
#         f.write(msg)
#         f.write('\n')
#         f.write('******************************************************************************\n')


def db_get_default_address(session: Session, user_id: int):
    user = session.query(MyMtlWalletBotUsers).filter(MyMtlWalletBotUsers.user_id == user_id).one_or_none()
    if user is not None:
        return user.default_address
    else:
        return None


def db_set_default_address(session: Session, user_id: int, address: str):
    user = session.query(MyMtlWalletBotUsers).filter(MyMtlWalletBotUsers.user_id == user_id).one()
    if user is not None:
        user.default_address = address
        session.commit()
    else:
        raise ValueError(f"No user found with id {user_id}")


def db_get_user_account_by_username(session: Session, username: str):
    # First query to check the default_address
    user = session.query(MyMtlWalletBotUsers.user_id, MyMtlWalletBotUsers.default_address) \
        .filter(MyMtlWalletBotUsers.user_name == username.lower()[1:]) \
        .one_or_none()

    if user is not None:
        user_id, default_address = user
        if len(default_address) == 56:
            return default_address, user_id
        else:
            # Second query if default_address is not available or invalid
            wallet = session.query(MyMtlWalletBot.public_key) \
                .filter(MyMtlWalletBot.user_id == user_id, MyMtlWalletBot.default_wallet == 1) \
                .one_or_none()
            if wallet is not None:
                return wallet.public_key, user_id

    return None, None


def db_get_usdt_private_key(session: Session, user_id: int, create_trc_private_key=None, user_name: str = None):
    if user_name:
        user = session.query(MyMtlWalletBotUsers).filter(MyMtlWalletBotUsers.user_name == user_name).one_or_none()
    else:
        user = session.query(MyMtlWalletBotUsers).filter(MyMtlWalletBotUsers.user_id == user_id).one_or_none()
    if user and user.usdt and len(user.usdt) == 64:
        return user.usdt, user.usdt_amount
    else:
        addr = create_trc_private_key()
        user.usdt = addr
        session.commit()
        return addr, 0


def db_update_usdt_sum(session: Session, user_id: int, update_summ: int, user_name: str = None):
    if user_name:
        user = session.query(MyMtlWalletBotUsers).filter(MyMtlWalletBotUsers.user_name == user_name).one_or_none()
    else:
        user = session.query(MyMtlWalletBotUsers).filter(MyMtlWalletBotUsers.user_id == user_id).one_or_none()

    if user and user.usdt and len(user.usdt) == 64:
        user.usdt_amount = user.usdt_amount + update_summ
        session.commit()
        return user.usdt
    else:
        raise ValueError(f"No user found with id {user_id}")


def db_get_usdt_balances(session: Session) -> List[Tuple[str, int, int]]:
    users = session.query(MyMtlWalletBotUsers.user_name, MyMtlWalletBotUsers.usdt_amount, MyMtlWalletBotUsers.user_id).filter(MyMtlWalletBotUsers.usdt_amount > 0).order_by(
        MyMtlWalletBotUsers.usdt_amount.desc()).all()
    return [(user_name, amount, user_id) for user_name, amount, user_id in users]


def db_get_btc_uuid(session: Session, user_id: int):
    user = session.query(MyMtlWalletBotUsers).filter(MyMtlWalletBotUsers.user_id == user_id).one_or_none()
    if user and user.btc and user.btc_date and len(user.btc) > 10:
        return user.btc, user.btc_date
    else:
        return None, None


def db_set_btc_uuid(session: Session, user_id: int, btc_uuid: Union[str, None]):
    user = session.query(MyMtlWalletBotUsers).filter(MyMtlWalletBotUsers.user_id == user_id).one_or_none()
    if user is not None:
        user.btc = btc_uuid
        user.btc_date = datetime.now() + timedelta(minutes=30)
        session.commit()


def db_reset_balance(session: Session, user_id: int):
    user = session.query(MyMtlWalletBot).filter(MyMtlWalletBot.user_id == user_id,
                                                MyMtlWalletBot.default_wallet == 1).one_or_none()
    if user is not None:
        user.balances_event_id = '0'
        session.commit()


def db_get_book_data(session: Session, user_id: int) -> List[MyMtlWalletBotBook]:
    data = session.query(MyMtlWalletBotBook).filter(MyMtlWalletBotBook.user_id == user_id).all()
    return data


def db_get_address_book_by_id(session: Session, idx: int, user_id: int) -> Optional[MyMtlWalletBotBook]:
    book = session.query(MyMtlWalletBotBook).filter_by(id=idx, user_id=user_id).one_or_none()
    return book


def db_delete_address_book_by_id(session: Session, idx: int, user_id: int) -> None:
    book = session.query(MyMtlWalletBotBook).filter_by(id=idx, user_id=user_id).first()
    session.delete(book)
    session.commit()


def db_insert_into_address_book(session: Session, address: str, name: str, user_id: int) -> None:
    new_book = MyMtlWalletBotBook(address=address[:64], name=name[:64], user_id=user_id)
    session.add(new_book)
    session.commit()


def db_get_user_data(session: Session, inline_query: str) -> list[MyMtlWalletBotUsers]:
    user_data = session.query(MyMtlWalletBotUsers.user_name) \
        .filter(MyMtlWalletBotUsers.user_name.isnot(None),
                MyMtlWalletBotUsers.user_name.ilike(f"%{inline_query}%")).all()
    return user_data


def db_add_user_if_not_exists(session: Session, user_id: int, user_name: str):
    user_count = session.query(func.count(MyMtlWalletBotUsers.user_id)).filter(
        MyMtlWalletBotUsers.user_id == user_id).scalar()
    user_name = user_name.lower() if user_name else None
    if user_count == 0:
        new_user = MyMtlWalletBotUsers(user_id=user_id, user_name=user_name)
        session.add(new_user)
        session.commit()


def db_add_wallet(session: Session, user_id: int, public_key, secret_key: str, i_free_wallet: int,
                  seed_key: str = None):
    # Get the maximum `last_event_id`
    last_event_id = session.query(func.max(MyMtlWalletBot.last_event_id)).scalar()

    # Create a new user
    new_wallet = MyMtlWalletBot(
        user_id=user_id,
        public_key=public_key,
        secret_key=secret_key,
        seed_key=seed_key,
        credit=5,
        default_wallet=0,
        free_wallet=i_free_wallet,
        last_event_id=last_event_id
    )
    session.add(new_wallet)
    session.commit()
    db_set_default_wallets(session, user_id, public_key)


def db_get_default_wallet(session: Session, user_id: int) -> MyMtlWalletBot:
    wallet = session.query(MyMtlWalletBot).filter(
        MyMtlWalletBot.user_id == user_id, MyMtlWalletBot.default_wallet == 1,
        MyMtlWalletBot.need_delete == 0).first()
    return wallet


def db_update_username(session: Session, user_id: int, username):
    username = username.lower() if username else username
    user = session.query(MyMtlWalletBotUsers).filter(MyMtlWalletBotUsers.user_id == user_id).one_or_none()
    if (user is not None) and (user.user_name != username):
        user.user_name = username
        session.commit()


def db_is_new_user(session: Session, user_id: int):
    user_exists_in_users = session.query(MyMtlWalletBotUsers).filter(
        MyMtlWalletBotUsers.user_id == user_id).count() != 0
    if not user_exists_in_users:
        return True
    user_exists_in_wallet = session.query(MyMtlWalletBot).filter(MyMtlWalletBot.user_id == user_id,
                                                                 MyMtlWalletBot.need_delete == 0).count() != 0
    return not user_exists_in_wallet


def db_user_can_new_free(session: Session, user_id: int):
    result = session.query(func.count(MyMtlWalletBot.user_id)).filter(
        MyMtlWalletBot.user_id == user_id,
        MyMtlWalletBot.free_wallet == 1,
        MyMtlWalletBot.need_delete == 0
    ).scalar()

    if result > 2:
        return False
    else:
        return True


def db_unfree_wallet(session: Session, user_id: int, account_id: str):
    stmt = update(MyMtlWalletBot).where(
        (MyMtlWalletBot.user_id == user_id) &
        (MyMtlWalletBot.public_key == account_id)
    ).values(free_wallet=0)
    session.execute(stmt)
    session.commit()


def db_update_mymtlwalletbot_balances(session: Session, balances: str, user_id: int):
    user_wallet = session.query(MyMtlWalletBot).filter(
        MyMtlWalletBot.user_id == user_id,
        MyMtlWalletBot.default_wallet == 1).one_or_none()

    if user_wallet is not None:
        user_wallet.balances = balances
        user_wallet.balances_event_id = user_wallet.last_event_id
        session.commit()
    else:
        logger.error(f"No wallet found for user_id {user_id} with default_wallet set to 1")


def db_delete_all_by_user(session: Session, user_id: int):
    if user_id < 1:
        return
    session.query(MyMtlWalletBot).filter(MyMtlWalletBot.user_id == user_id).update(
        {MyMtlWalletBot.need_delete: 1})
    session.query(MyMtlWalletBotMessages).filter(MyMtlWalletBotMessages.user_id == user_id).delete()
    session.query(MyMtlWalletBotUsers).filter(MyMtlWalletBotUsers.user_id == user_id).delete()
    session.commit()


def db_delete_wallet(session: Session, user_id: int, public_key: str, erase: bool = False, idx: int = None):
    if user_id < 1:
        return
    wallet = session.query(MyMtlWalletBot).filter(MyMtlWalletBot.user_id == user_id,
                                                  MyMtlWalletBot.public_key == public_key)
    if idx is not None:
        wallet = wallet.filter(MyMtlWalletBot.id == idx)

    wallet = wallet.first()

    if wallet is not None:
        if erase:
            session.delete(wallet)
        else:
            wallet.need_delete = 1
        session.commit()


async def db_delete_wallet_async(session: Session, user_id: int, public_key: str, erase: bool = False, idx: int = None):
    await asyncio.to_thread(db_delete_wallet, session, user_id, public_key, erase, idx)


def db_update_secret_key(session: Session, user_id: int, new_secret_key: str, password_type: int):
    session.query(MyMtlWalletBot).filter(MyMtlWalletBot.user_id == user_id,
                                         MyMtlWalletBot.default_wallet == 1
                                         ).update({MyMtlWalletBot.secret_key: new_secret_key,
                                                   MyMtlWalletBot.use_pin: password_type},
                                                  synchronize_session=False)  # Added this for better performance during updates.

    session.commit()


def db_add_donate(session: Session, user_id: int, donate_sum: float):
    user = session.query(MyMtlWalletBotUsers).filter(MyMtlWalletBotUsers.user_id == user_id).one()
    if user is not None:
        user.donate_sum += donate_sum
        session.commit()


def db_get_wallets_list(session: Session, user_id: int) -> List[MyMtlWalletBot]:
    wallets = session.query(MyMtlWalletBot).filter(MyMtlWalletBot.user_id == user_id,
                                                   MyMtlWalletBot.need_delete == 0).all()
    return wallets


def db_get_deleted_wallets_list(session: Session) -> List[MyMtlWalletBot]:
    wallets = session.query(MyMtlWalletBot).filter(MyMtlWalletBot.need_delete == 1).all()
    return wallets


def db_set_default_wallets(session: Session, user_id: int, public_key: str):
    # Set all routers wallets of this user to not default
    session.query(MyMtlWalletBot).filter(
        MyMtlWalletBot.user_id == user_id
    ).update({MyMtlWalletBot.default_wallet: 0}, synchronize_session=False)

    # Set the specified wallet of this user to default
    user = session.query(MyMtlWalletBot).filter_by(user_id=user_id, public_key=public_key, need_delete=0).first()
    if user:
        user.default_wallet = 1
        session.commit()
        return True
    else:
        return False


def db_add_cheque(session: Session, send_uuid: str, send_sum: str, send_count: int, user_id: int,
                  send_comment: str) -> MyMtlWalletBotCheque:
    new_cheque = MyMtlWalletBotCheque(
        cheque_uuid=send_uuid,
        cheque_amount=send_sum,
        cheque_count=send_count,
        user_id=user_id,
        cheque_comment=send_comment
    )
    session.add(new_cheque)
    session.commit()
    return new_cheque


def db_get_cheque(session: Session, cheque_uuid: str, user_id: int = None) -> MyMtlWalletBotCheque:
    query = session.query(MyMtlWalletBotCheque).filter(MyMtlWalletBotCheque.cheque_uuid == cheque_uuid)

    if user_id is not None:
        query = query.filter(MyMtlWalletBotCheque.user_id == user_id)

    cheque = query.one_or_none()
    return cheque


def db_get_cheque_receive_count(session: Session, cheque_uuid: str, user_id: int = None):
    query = session.query(func.count('*')). \
        select_from(MyMtlWalletBotCheque). \
        join(MyMtlWalletBotChequeHistory, MyMtlWalletBotCheque.cheque_id == MyMtlWalletBotChequeHistory.cheque_id). \
        filter(MyMtlWalletBotCheque.cheque_uuid == cheque_uuid)

    if user_id is not None:
        query = query.filter(MyMtlWalletBotChequeHistory.user_id == user_id)

    receive_count = query.scalar()

    return receive_count


def db_get_available_cheques(session: Session, user_id: int) -> List[MyMtlWalletBotCheque]:
    cheques = session.query(
        MyMtlWalletBotCheque
    ).outerjoin(
        MyMtlWalletBotChequeHistory,
        MyMtlWalletBotCheque.cheque_id == MyMtlWalletBotChequeHistory.cheque_id
    ).group_by(
        MyMtlWalletBotCheque
    ).having(
        func.count(MyMtlWalletBotChequeHistory.cheque_id) < MyMtlWalletBotCheque.cheque_count
    ).filter(
        MyMtlWalletBotCheque.user_id == user_id,
        MyMtlWalletBotCheque.cheque_status != ChequeStatus.CANCELED.value
    ).all()

    return cheques


def db_add_cheque_history(session: Session, user_id: int, cheque_id: int):
    new_cheque_history = MyMtlWalletBotChequeHistory(
        user_id=user_id,
        dt_block=datetime.now(),
        cheque_id=cheque_id
    )
    session.add(new_cheque_history)
    session.commit()


def db_get_user(session: Session, user_id: int) -> MyMtlWalletBotUsers:
    return session.query(MyMtlWalletBotUsers).filter(MyMtlWalletBotUsers.user_id == user_id).one_or_none()


def get_user_lang(session: Session, user_id: int):
    try:
        user = session.query(MyMtlWalletBotUsers).filter(MyMtlWalletBotUsers.user_id == user_id).first()
        if user is not None:
            return user.lang
        else:
            return 'en'
    except Exception as ex:
        # print(ex)  # Or handle the exception in some routers way
        return 'en'


def get_wallet_info(session: Session, user_id: int, public_key: str) -> str:
    wallet = session.query(MyMtlWalletBot).filter(MyMtlWalletBot.user_id == user_id,
                                                  MyMtlWalletBot.public_key == public_key,
                                                  MyMtlWalletBot.need_delete == 0).first()
    if wallet is None:
        return "(нет данных)"
    if wallet.free_wallet == 1:
        info_text = '(free)'
    elif wallet.use_pin == 0:
        info_text = '(no pin)'
    elif wallet.use_pin == 1:
        info_text = '(pin)'
    elif wallet.use_pin == 2:
        info_text = '(pass)'
    elif wallet.use_pin == 10:
        info_text = '(r/o)'
    else:
        info_text = '(0_0)'

    default_address = db_get_default_address(session, user_id)
    if default_address == wallet.public_key:
        info_text += ' 📩'
    return info_text


if __name__ == '__main__':
    pass
    print(db_get_usdt_private_key(quik_pool(), 1, user_name='itolstov'))
