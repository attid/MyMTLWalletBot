#!/usr/bin/python3
from datetime import datetime, timedelta
from typing import Union

import fdb
from loguru import logger
from config_reader import config


# logger.add("check_stellar", rotation="1 MB")


# https://fdb.readthedocs.io/en/v2.0/ from datetime import timedelta, datetime
def connect_db():
    return fdb.connect(dsn=config.db_dns, user=config.db_user, password=config.db_password.get_secret_value(),
                       charset='UTF8')


@logger.catch
def execsql0(con, sql, param=None):
    cur = con.cursor()
    if param is None:
        cur.execute(sql)
    else:
        cur.execute(sql, param)
    try:
        return cur.fetchall()
    except:
        return []


@logger.catch
def free_db(con):
    con.close()
    del (con)


@logger.catch
def execsql(sql, param=None):
    con = connect_db()
    result = execsql0(con, sql, param)
    con.commit()
    free_db(con)
    return result


@logger.catch
def execsql1(sql, param=None, default: Union[str, None] = ''):
    result = execsql(sql, param)
    if len(result) > 0:
        return result[0][0]
    else:
        return default


@logger.catch
def many_insert(sql, param):
    con = connect_db()
    cur = con.cursor()
    cur.executemany(sql, param)
    con.commit()
    free_db(con)
    return


def send_admin_message(msg):
    execsql('insert into t_message (user_id, text, use_alarm) values (?,?,?)', (84131737, 'MMWB', 0))
    # add text to file error.txt
    with open('error.txt', 'a') as f:
        f.write(msg)
        f.write('\n')


def get_default_address(user_id: int):
    return execsql1('select default_address from mymtlwalletbot_users where user_id = ?', (user_id,))


def set_default_address(user_id: int, address: str):
    execsql('update mymtlwalletbot_users u set u.default_address = ? where u.user_id = ?', (address, user_id))


def get_user_account_by_username(username: str):
    public_key, user_id, default_address = execsql(
        f"select w.public_key, w.user_id, u.default_address from MyMTLWalletBot w "
        f"join MyMTLWalletBot_users u on u.user_id = w.user_id " +
        f"where u.user_name = ? and w.default_wallet = 1",
        (username.lower()[1:],))[0]

    if len(default_address) == 56:
        return default_address, user_id
    else:
        return public_key, user_id


def get_usdt_private_key(user_id: int, create_trc_private_key=None):
    addr = execsql1('select u.usdt from mymtlwalletbot_users u where u.user_id = ?', (user_id,))
    if addr and len(addr) == 64:
        return addr
    else:
        addr = create_trc_private_key()
        execsql('update mymtlwalletbot_users u set u.usdt = ? where u.user_id = ?', (addr, user_id,))
        return addr


def get_btc_uuid(user_id: int):
    btc_uuid = execsql1('select u.btc from mymtlwalletbot_users u where u.user_id = ?', (user_id,), default=None)
    btc_date = execsql1('select u.btc_date from mymtlwalletbot_users u where u.user_id = ?', (user_id,), default=None)
    if btc_uuid and btc_date and len(btc_uuid) > 10:
        return btc_uuid, btc_date
    else:
        return None, None


def set_btc_uuid(user_id: int, btc_uuid: Union[str, None]):
    execsql('update mymtlwalletbot_users u set u.btc = ?, u.btc_date = ? where u.user_id = ?',
            (btc_uuid, datetime.now() + timedelta(minutes=30), user_id,))


logger.add(send_admin_message, level='WARNING')

# if __name__ == "__main__":
#    memo = 'test'
