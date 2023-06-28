from datetime import timedelta
from sys import argv
from typing import Union, List, Optional

from sqlalchemy import update, select
from sqlalchemy.orm import Session
from db.models import *


def cmd_add_message(session: Session, user_id: int, text: str, use_alarm: int = 0, update_id: int = None,
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


def send_admin_message(session: Session, msg: str):
    cmd_add_message(session, 84131737, msg)
    # add text to file error.txt
    with open('error.txt', 'a') as f:
        f.write(f"{argv} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        f.write(msg)
        f.write('\n')
        f.write('******************************************************************************\n')


def get_default_address(session: Session, user_id: int):
    user = session.query(MyMtlWalletBotUsers).filter(MyMtlWalletBotUsers.user_id == user_id).one_or_none()
    if user is not None:
        return user.default_address
    else:
        return None


def set_default_address(session: Session, user_id: int, address: str):
    user = session.query(MyMtlWalletBotUsers).filter(MyMtlWalletBotUsers.user_id == user_id).one()
    if user is not None:
        user.default_address = address
        session.commit()
    else:
        raise ValueError(f"No user found with id {user_id}")


def get_user_account_by_username(session: Session, username: str):
    result = session.query(MyMtlWalletBot.public_key, MyMtlWalletBot.user_id, MyMtlWalletBotUsers.default_address). \
        join(MyMtlWalletBotUsers, MyMtlWalletBotUsers.user_id == MyMtlWalletBot.user_id). \
        filter(MyMtlWalletBotUsers.user_name == username.lower()[1:], MyMtlWalletBot.default_wallet == 1). \
        one_or_none()

    if result is not None:
        public_key, user_id, default_address = result
        if len(default_address) == 56:
            return default_address, user_id
        else:
            return public_key, user_id
    else:
        return None


def get_usdt_private_key(session: Session, user_id: int, create_trc_private_key=None):
    user = session.query(MyMtlWalletBotUsers).filter(MyMtlWalletBotUsers.user_id == user_id).one_or_none()
    if user and user.usdt and len(user.usdt) == 64:
        return user.usdt
    else:
        addr = create_trc_private_key()
        user.usdt = addr
        session.commit()
        return addr


def get_btc_uuid(session: Session, user_id: int):
    user = session.query(MyMtlWalletBotUsers).filter(MyMtlWalletBotUsers.user_id == user_id).one_or_none()
    if user and user.btc and user.btc_date and len(user.btc) > 10:
        return user.btc, user.btc_date
    else:
        return None, None


def set_btc_uuid(session: Session, user_id: int, btc_uuid: Union[str, None]):
    user = session.query(MyMtlWalletBotUsers).filter(MyMtlWalletBotUsers.user_id == user_id).one_or_none()
    if user is not None:
        user.btc = btc_uuid
        user.btc_date = datetime.now() + timedelta(minutes=30)
        session.commit()


def reset_balance(session: Session, user_id: int):
    user = session.query(MyMtlWalletBot).filter(MyMtlWalletBot.user_id == user_id,
                                                MyMtlWalletBot.default_wallet == 1).one_or_none()
    if user is not None:
        user.balances_event_id = '0'
        session.commit()


def get_book_data(session: Session, user_id: int) -> List[MyMtlWalletBotBook]:
    data = session.query(MyMtlWalletBotBook).filter(MyMtlWalletBotBook.user_id == user_id).all()
    return data


def get_address_book_by_id(session: Session, idx: int, user_id: int) -> Optional[MyMtlWalletBotBook]:
    book = session.query(MyMtlWalletBotBook).filter_by(id=idx, user_id=user_id).one_or_none()
    return book


def delete_address_book_by_id(session: Session, idx: int, user_id: int) -> None:
    book = session.query(MyMtlWalletBotBook).filter_by(id=idx, user_id=user_id).one()
    session.delete(book)
    session.commit()


def insert_into_address_book(session: Session, address: str, name: str, user_id: int) -> None:
    new_book = MyMtlWalletBotBook(address=address[:64], name=name[:64], user_id=user_id)
    session.add(new_book)
    session.commit()


def get_wallet_data(session: Session, user_id: int) -> list[MyMtlWalletBot]:
    wallet_data = session.query(MyMtlWalletBot).filter(MyMtlWalletBot.user_id == user_id,
                                                       MyMtlWalletBot.need_delete == 0).all()
    return wallet_data


def get_user_data(session: Session, inline_query: str) -> list[MyMtlWalletBotUsers]:
    user_data = session.query(MyMtlWalletBotUsers.user_name) \
        .filter(MyMtlWalletBotUsers.user_name.isnot(None),
                MyMtlWalletBotUsers.user_name.ilike(f"%{inline_query}%")).all()
    return user_data


def add_user_if_not_exists(session: Session, user_id: int, user_name: str):
    user_count = session.query(func.count(MyMtlWalletBotUsers.user_id)).filter(
        MyMtlWalletBotUsers.user_id == user_id).scalar()
    if user_count == 0:
        new_user = MyMtlWalletBotUsers(user_id=user_id, user_name=user_name)
        session.add(new_user)
        session.commit()


def add_user(session: Session, user_id: int, public_key, secret_key: str, i_free_wallet: int):
    # Get the maximum `last_event_id`
    last_event_id = session.query(func.max(MyMtlWalletBot.last_event_id)).scalar()

    # Create a new user
    new_user = MyMtlWalletBot(
        user_id=user_id,
        public_key=public_key,
        secret_key=secret_key,
        credit=5,
        default_wallet=1,
        free_wallet=i_free_wallet,
        last_event_id=last_event_id
    )
    session.add(new_user)
    session.commit()


def get_default_wallet(session: Session, user_id: int) -> MyMtlWalletBot:
    wallet = session.query(MyMtlWalletBot).filter(
        MyMtlWalletBot.user_id == user_id, MyMtlWalletBot.default_wallet == 1).first()
    return wallet


def update_username(session: Session, user_id: int, username):
    username = username.lower() if username else username
    user = session.query(MyMtlWalletBotUsers).filter(MyMtlWalletBotUsers.user_id == user_id).one_or_none()
    if user is not None:
        user.user_name = username
        session.commit()


def get_user_wallet(session: Session, user_id: int) -> MyMtlWalletBot:
    user = session.query(MyMtlWalletBot).filter(
        MyMtlWalletBot.user_id == user_id, MyMtlWalletBot.default_wallet == 1).one_or_none()
    return user


def is_new_user(session: Session, user_id: int):
    user_exists_in_users = session.query(MyMtlWalletBotUsers).filter(
        MyMtlWalletBotUsers.user_id == user_id).count() != 0
    if not user_exists_in_users:
        return True
    user_exists_in_wallet = session.query(MyMtlWalletBot).filter(MyMtlWalletBot.user_id == user_id).count() != 0
    return not user_exists_in_wallet


def user_can_new_free(session: Session, user_id: int):
    result = session.query(func.count(MyMtlWalletBot.user_id)).filter(
        MyMtlWalletBot.user_id == user_id,
        MyMtlWalletBot.free_wallet == 1
    ).scalar()

    if result > 2:
        return False
    else:
        return True


def unfree_wallet(session: Session, user_id: int, account_id: str):
    stmt = update(MyMtlWalletBot).where(
        (MyMtlWalletBot.user_id == user_id) &
        (MyMtlWalletBot.public_key == account_id)
    ).values(free_wallet=0)
    session.execute(stmt)
    session.commit()


def update_mymtlwalletbot_balances(session: Session, balances: str, user_id: int):
    user_wallet = session.query(MyMtlWalletBot).filter(
        MyMtlWalletBot.user_id == user_id,
        MyMtlWalletBot.default_wallet == 1).one_or_none()

    if user_wallet is not None:
        user_wallet.balances = balances
        user_wallet.balances_event_id = user_wallet.last_event_id
        session.commit()
    else:
        print(f"No wallet found for user_id {user_id} with default_wallet set to 1")


def delete_all_by_user(session: Session, user_id: int):
    session.query(MyMtlWalletBot).filter(MyMtlWalletBot.user_id == user_id).update(
        {MyMtlWalletBot.user_id: -1 * user_id})
    session.query(MyMtlWalletBotMessages).filter(MyMtlWalletBotMessages.user_id == user_id).delete()
    session.query(MyMtlWalletBotUsers).filter(MyMtlWalletBotUsers.user_id == user_id).delete()
    session.commit()


def delete_wallet(session: Session, user_id: int, public_key: str):
    session.query(MyMtlWalletBot).filter(MyMtlWalletBot.user_id == user_id,
                                         MyMtlWalletBot.public_key == public_key
                                         ).update({MyMtlWalletBot.user_id: -1 * user_id,
                                                   MyMtlWalletBot.need_delete: 1
                                                   },
                                                  synchronize_session=False)  # Added this for better performance during updates.

    session.commit()


def update_secret_key(session: Session, user_id: int, new_secret_key: str, password_type: int):
    session.query(MyMtlWalletBot).filter(MyMtlWalletBot.user_id == user_id,
                                         MyMtlWalletBot.default_wallet == 1
                                         ).update({MyMtlWalletBot.secret_key: new_secret_key,
                                                   MyMtlWalletBot.use_pin: password_type},
                                                  synchronize_session=False)  # Added this for better performance during updates.

    session.commit()


def add_donate(session: Session, user_id: int, donate_sum: float):
    user = session.query(MyMtlWalletBotUsers).filter(MyMtlWalletBotUsers.user_id == user_id).one()
    if user is not None:
        user.donate_sum += donate_sum
        session.commit()


def stellar_get_wallets_list(session: Session, user_id: int):
    wallets = session.query(MyMtlWalletBot.public_key, MyMtlWalletBot.default_wallet,
                            MyMtlWalletBot.free_wallet).filter(MyMtlWalletBot.user_id == user_id).all()
    return wallets


def stellar_set_default_wallets(session: Session, user_id: int, public_key: str):
    # Set all other wallets of this user to not default
    session.query(MyMtlWalletBot).filter(
        MyMtlWalletBot.user_id == user_id,
        MyMtlWalletBot.public_key != public_key
    ).update({MyMtlWalletBot.default_wallet: 0}, synchronize_session=False)

    # Set the specified wallet of this user to default
    user = session.query(MyMtlWalletBot).filter_by(user_id=user_id, public_key=public_key).first()
    if user:
        user.default_wallet = 1
        session.commit()
        return True
    else:
        return False


def insert_into_mtlwalletbot_cheque(session: Session, send_uuid: str, send_sum: str, send_count: int, user_id: int,
                                    send_comment: str):
    new_cheque = MyMtlWalletBotCheque(
        cheque_uuid=send_uuid,
        cheque_amount=send_sum,
        cheque_count=send_count,
        user_id=user_id,
        cheque_comment=send_comment
    )
    session.add(new_cheque)
    session.commit()


def get_cheque(session: Session, cheque_uuid: str, user_id: int = None) -> MyMtlWalletBotCheque:
    query = session.query(MyMtlWalletBotCheque).filter(MyMtlWalletBotCheque.cheque_uuid == cheque_uuid)

    if user_id is not None:
        query = query.filter(MyMtlWalletBotCheque.user_id == user_id)

    cheque = query.one_or_none()
    return cheque


def get_cheque_receive_count(session: Session, cheque_uuid: str, user_id: int = None):
    query = session.query(func.count('*')). \
        select_from(MyMtlWalletBotCheque). \
        join(MyMtlWalletBotChequeHistory, MyMtlWalletBotCheque.cheque_id == MyMtlWalletBotChequeHistory.cheque_id). \
        filter(MyMtlWalletBotCheque.cheque_uuid == cheque_uuid)

    if user_id is not None:
        query = query.filter(MyMtlWalletBotChequeHistory.user_id == user_id)

    receive_count = query.scalar()

    return receive_count


def get_available_cheques(session: Session, user_id: int) -> List[MyMtlWalletBotCheque]:
    cheque_subquery = session.query(
        func.count(MyMtlWalletBotChequeHistory.cheque_id).label("cheque_history_count")
    ).filter(
        MyMtlWalletBotChequeHistory.cheque_id == MyMtlWalletBotCheque.cheque_id
    ).subquery()

    cheques = session.query(
        MyMtlWalletBotCheque
    ).filter(
        MyMtlWalletBotCheque.cheque_count > select([cheque_subquery]),
        MyMtlWalletBotCheque.user_id == user_id,
        MyMtlWalletBotCheque.cheque_status == 0
    ).all()

    return cheques


def insert_into_cheque_history(session: Session, user_id: int, cheque_id: int):
    new_cheque_history = MyMtlWalletBotChequeHistory(
        user_id=user_id,
        dt_block=datetime.now(),
        cheque_id=cheque_id
    )
    session.add(new_cheque_history)
    session.commit()


if __name__ == '__main__':
    pass
    # from quik_pool import quik_pool
