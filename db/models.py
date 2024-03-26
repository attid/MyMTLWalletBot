import enum
from datetime import datetime

from sqlalchemy import String, func, SmallInteger, Float, ForeignKey, Enum, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, BigInteger, DateTime
from sqlalchemy.sql.ddl import CreateTable

Base = declarative_base()
metadata = Base.metadata


class TOperations(Base):
    __tablename__ = 'T_OPERATIONS'
    id = Column(String(32), primary_key=True)
    dt = Column(DateTime)
    operation = Column(String(32))
    amount1 = Column(String(32))
    code1 = Column(String(32))
    amount2 = Column(String(32))
    code2 = Column(String(32))
    from_account = Column(String(64))
    for_account = Column(String(64))
    memo = Column(String(64))
    transaction_hash = Column(String(64))
    ledger = Column(Integer)
    arhived = Column(Integer)


class MyMtlWalletBot(Base):
    __tablename__ = 'MYMTLWALLETBOT'

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False)
    public_key = Column(String(60))
    secret_key = Column(String(160))
    seed_key = Column(String(400))
    credit = Column(Integer)
    last_use_day = Column(DateTime)
    use_pin = Column(SmallInteger, default=0)
    free_wallet = Column(SmallInteger, default=1)
    default_wallet = Column(SmallInteger, default=0)
    need_delete = Column(SmallInteger, default=0)
    last_event_id = Column(String(32), default='0')
    balances = Column(Text)  # Now using Text for the balances field
    balances_event_id = Column(String(32), default='0')


# @event.listens_for(Session, 'before_flush')
# def receive_before_flush(session, flush_context, instances):
#    for instance in session.dirty:
#        if isinstance(instance, MyMtlWalletBot):
#            instance.last_use_day = datetime.now()  # Update the last_use_day to now
#            if instance.default_wallet == 1:
#                # If default_wallet is 1, set default_wallet to 0 for all other records of the same user
#                session.query(MyMtlWalletBot).filter(
#                    MyMtlWalletBot.user_id == instance.user_id,
#                    MyMtlWalletBot.public_key != instance.public_key
#                ).update({MyMtlWalletBot.default_wallet: 0})


class MyMtlWalletBotLog(Base):
    __tablename__ = 'MYMTLWALLETBOT_LOG'

    log_id = Column('LOG_ID', Integer, primary_key=True)
    user_id = Column('USER_ID', BigInteger)
    log_dt = Column('LOG_DT', DateTime)
    log_operation = Column('LOG_OPERATION', String(32))
    log_operation_info = Column('LOG_OPERATION_INFO', String(32))


class MyMtlWalletBotBook(Base):
    __tablename__ = 'MYMTLWALLETBOT_BOOK'

    id = Column(Integer, primary_key=True)
    address = Column(String(64))
    name = Column(String(64))
    user_id = Column(BigInteger)


class ChequeStatus(enum.Enum):
    CHEQUE = 0
    CANCELED = 1
    INVOICE = 2


class MyMtlWalletBotCheque(Base):
    __tablename__ = 'MYMTLWALLETBOT_CHEQUE'

    cheque_id = Column(Integer, primary_key=True)
    cheque_uuid = Column(String(32))
    cheque_amount = Column(String(32))
    cheque_count = Column(Integer)
    user_id = Column(BigInteger)
    #cheque_status = Column(Enum(ChequeStatus), default=ChequeStatus.CHEQUE.value)
    cheque_status = Column(Integer, default=ChequeStatus.CHEQUE.value)
    cheque_comment = Column(String(255))
    cheque_asset = Column(String(255))


class MyMtlWalletBotChequeHistory(Base):
    __tablename__ = 'MYMTLWALLETBOT_CHEQUE_HISTORY'

    cheque_history_id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger)
    dt_block = Column(DateTime)
    dt_receive = Column(DateTime)
    cheque_id = Column(Integer, ForeignKey('MYMTLWALLETBOT_CHEQUE.cheque_id'))


class MyMtlWalletBotMessages(Base):
    __tablename__ = 'MYMTLWALLETBOT_MESSAGES'

    message_id = Column(Integer, primary_key=True)
    user_message = Column(String(5000), nullable=False)
    keyboard = Column(Integer, default=0, nullable=False)
    user_id = Column(BigInteger, ForeignKey('MYMTLWALLETBOT_USERS.user_id'), nullable=False)
    was_send = Column(Integer, default=0, nullable=False)


class TransactionState(enum.Enum):
    CREATED = 0
    AT_WORK = 1
    SENT = 2
    ERROR = 3
    CANCELED = 4


class MyMtlWalletBotTransactions(Base):
    __tablename__ = 'MYMTLWALLETBOT_TRANSACTIONS'

    user_transaction_id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('MYMTLWALLETBOT_USERS.user_id'), nullable=False)
    user_transaction = Column(Text)
    transaction_state = Column(Enum(TransactionState), default=TransactionState.CREATED)
    transaction_date = Column(DateTime, default=func.current_timestamp())
    transaction_response = Column(Text)


class MyMtlWalletBotUsers(Base):
    __tablename__ = 'MYMTLWALLETBOT_USERS'

    user_id = Column(BigInteger, primary_key=True)
    user_name = Column(String(60))
    lang = Column(String(2), default='en')
    message_id = Column(BigInteger, default=0)
    donate_sum = Column(Float, default=0, nullable=False)
    default_address = Column(String(60), default='', nullable=False)
    usdt = Column(String(64))
    usdt_amount = Column(Integer, default=0)
    btc = Column(String(64))
    btc_date = Column(DateTime)
    can_5000 = Column(SmallInteger, default=0)


class TMessage(Base):
    __tablename__ = 'T_MESSAGE'
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger)
    text = Column(String(4000))
    was_send = Column(Integer, default=0)
    dt_add = Column(DateTime, default=datetime.now)
    use_alarm = Column(Integer, default=0)
    update_id = Column(BigInteger, default=0)
    button_json = Column(String(4000))


def update_db():
    Base.metadata.create_all()
    #metadata.create_all(engine)


if __name__ == "__main__":
    pass
    #from quik_pool import engine
    #print(CreateTable(MyMtlWalletBotCheque.__table__).compile(engine))
