# This code parses date/times, so please https://app.quicktype.io/
#
#     pip install python-dateutil
#
#
# To use this code, make sure you
#
#     import json
#
# and then, to convert JSON from a string, do
#
#     result = offer_from_dict(json.loads(json_string))
from dataclasses import dataclass
from typing import Optional, Any, List, TypeVar, Type, cast, Callable
from datetime import datetime
import dateutil.parser

T = TypeVar("T")


def from_bool(x: Any) -> bool:
    assert isinstance(x, bool)
    return x


def from_str(x: Any) -> str:
    assert isinstance(x, str)
    return x


def from_none(x: Any) -> Any:
    assert x is None
    return x


def from_union(fs, x):
    for f in fs:
        try:
            return f(x)
        except:
            pass
    assert False


def to_class(c: Type[T], x: Any) -> dict:
    assert isinstance(x, c)
    return cast(Any, x).to_dict()


def from_int(x: Any) -> int:
    assert isinstance(x, int) and not isinstance(x, bool)
    return x


def from_datetime(x: Any) -> datetime:
    return dateutil.parser.parse(x)


def is_type(t: Type[T], x: Any) -> T:
    assert isinstance(x, t)
    return x


def from_list(f: Callable[[Any], T], x: Any) -> List[T]:
    assert isinstance(x, list)
    return [f(y) for y in x]


@dataclass
class MyAsset:
    asset_type: Optional[str] = None
    asset_code: Optional[str] = None
    asset_issuer: Optional[str] = None

    @staticmethod
    def from_dict(obj: Any) -> 'MyAsset':
        assert isinstance(obj, dict)
        asset_type = from_union([from_str, from_none], obj.get("asset_type"))
        asset_code = from_union([from_str, from_none], obj.get("asset_code"))
        asset_issuer = from_union([from_str, from_none], obj.get("asset_issuer"))
        return MyAsset(asset_type, asset_code, asset_issuer)

    def to_dict(self) -> dict:
        result: dict = {}
        result["asset_type"] = from_union([from_str, from_none], self.asset_type)
        result["asset_code"] = from_union([from_str, from_none], self.asset_code)
        result["asset_issuer"] = from_union([from_str, from_none], self.asset_issuer)
        return result


@dataclass
class Next:
    href: Optional[str] = None

    @staticmethod
    def from_dict(obj: Any) -> 'Next':
        assert isinstance(obj, dict)
        href = from_union([from_str, from_none], obj.get("href"))
        return Next(href)

    def to_dict(self) -> dict:
        result: dict = {}
        result["href"] = from_union([from_str, from_none], self.href)
        return result


@dataclass
class RecordLinks:
    links_self: Optional[Next] = None
    offer_maker: Optional[Next] = None

    @staticmethod
    def from_dict(obj: Any) -> 'RecordLinks':
        assert isinstance(obj, dict)
        links_self = from_union([Next.from_dict, from_none], obj.get("self"))
        offer_maker = from_union([Next.from_dict, from_none], obj.get("offer_maker"))
        return RecordLinks(links_self, offer_maker)

    def to_dict(self) -> dict:
        result: dict = {}
        result["self"] = from_union([lambda x: to_class(Next, x), from_none], self.links_self)
        result["offer_maker"] = from_union([lambda x: to_class(Next, x), from_none], self.offer_maker)
        return result


@dataclass
class PriceR:
    n: Optional[int] = None
    d: Optional[int] = None

    @staticmethod
    def from_dict(obj: Any) -> 'PriceR':
        assert isinstance(obj, dict)
        n = from_union([from_int, from_none], obj.get("n"))
        d = from_union([from_int, from_none], obj.get("d"))
        return PriceR(n, d)

    def to_dict(self) -> dict:
        result: dict = {}
        result["n"] = from_union([from_int, from_none], self.n)
        result["d"] = from_union([from_int, from_none], self.d)
        return result


@dataclass
class MyOffer:
    id: Optional[int] = None
    paging_token: Optional[int] = None
    links: Optional[RecordLinks] = None
    seller: Optional[str] = None
    selling: Optional[MyAsset] = None
    buying: Optional[MyAsset] = None
    amount: Optional[str] = None
    price_r: Optional[PriceR] = None
    price: Optional[str] = None
    last_modified_ledger: Optional[int] = None
    last_modified_time: Optional[datetime] = None

    @staticmethod
    def from_dict(obj: Any) -> 'MyOffer':
        assert isinstance(obj, dict)
        id = from_union([from_none, lambda x: int(from_str(x))], obj.get("id"))
        paging_token = from_union([from_none, lambda x: int(from_str(x))], obj.get("paging_token"))
        links = from_union([RecordLinks.from_dict, from_none], obj.get("_links"))
        seller = from_union([from_str, from_none], obj.get("seller"))
        selling = from_union([MyAsset.from_dict, from_none], obj.get("selling"))
        buying = from_union([MyAsset.from_dict, from_none], obj.get("buying"))
        amount = from_union([from_str, from_none], obj.get("amount"))
        price_r = from_union([PriceR.from_dict, from_none], obj.get("price_r"))
        price = from_union([from_str, from_none], obj.get("price"))
        last_modified_ledger = from_union([from_int, from_none], obj.get("last_modified_ledger"))
        last_modified_time = from_union([from_datetime, from_none], obj.get("last_modified_time"))
        return MyOffer(id, paging_token, links, seller, selling, buying, amount, price_r, price, last_modified_ledger,
                       last_modified_time)

    def to_dict(self) -> dict:
        result: dict = {}
        result["id"] = from_union([lambda x: from_none((lambda x: is_type(type(None), x))(x)),
                                   lambda x: from_str((lambda x: str((lambda x: is_type(int, x))(x)))(x))], self.id)
        result["paging_token"] = from_union([lambda x: from_none((lambda x: is_type(type(None), x))(x)),
                                             lambda x: from_str((lambda x: str((lambda x: is_type(int, x))(x)))(x))],
                                            self.paging_token)
        result["_links"] = from_union([lambda x: to_class(RecordLinks, x), from_none], self.links)
        result["seller"] = from_union([from_str, from_none], self.seller)
        result["selling"] = from_union([lambda x: to_class(MyAsset, x), from_none], self.selling)
        result["buying"] = from_union([lambda x: to_class(MyAsset, x), from_none], self.buying)
        result["amount"] = from_union([from_str, from_none], self.amount)
        result["price_r"] = from_union([lambda x: to_class(PriceR, x), from_none], self.price_r)
        result["price"] = from_union([from_str, from_none], self.price)
        result["last_modified_ledger"] = from_union([from_int, from_none], self.last_modified_ledger)
        result["last_modified_time"] = from_union([lambda x: x.isoformat(), from_none], self.last_modified_time)
        return result


@dataclass
class Embedded:
    records: Optional[List[MyOffer]] = None

    @staticmethod
    def from_dict(obj: Any) -> 'Embedded':
        assert isinstance(obj, dict)
        records = from_union([lambda x: from_list(MyOffer.from_dict, x), from_none], obj.get("records"))
        return Embedded(records)

    def to_dict(self) -> dict:
        result: dict = {}
        result["records"] = from_union([lambda x: from_list(lambda x: to_class(MyOffer, x), x), from_none],
                                       self.records)
        return result


@dataclass
class OfferLinks:
    links_self: Optional[Next] = None
    next: Optional[Next] = None
    prev: Optional[Next] = None

    @staticmethod
    def from_dict(obj: Any) -> 'OfferLinks':
        assert isinstance(obj, dict)
        links_self = from_union([Next.from_dict, from_none], obj.get("self"))
        next = from_union([Next.from_dict, from_none], obj.get("next"))
        prev = from_union([Next.from_dict, from_none], obj.get("prev"))
        return OfferLinks(links_self, next, prev)

    def to_dict(self) -> dict:
        result: dict = {}
        result["self"] = from_union([lambda x: to_class(Next, x), from_none], self.links_self)
        result["next"] = from_union([lambda x: to_class(Next, x), from_none], self.next)
        result["prev"] = from_union([lambda x: to_class(Next, x), from_none], self.prev)
        return result


@dataclass
class MyOffers:
    links: Optional[OfferLinks] = None
    embedded: Optional[Embedded] = None

    @staticmethod
    def from_dict(obj: Any) -> 'MyOffers':
        assert isinstance(obj, dict)
        links = from_union([OfferLinks.from_dict, from_none], obj.get("_links"))
        embedded = from_union([Embedded.from_dict, from_none], obj.get("_embedded"))
        return MyOffers(links, embedded)

    def to_dict(self) -> dict:
        result: dict = {}
        result["_links"] = from_union([lambda x: to_class(OfferLinks, x), from_none], self.links)
        result["_embedded"] = from_union([lambda x: to_class(Embedded, x), from_none], self.embedded)
        return result


@dataclass
class Balance:
    balance: Optional[str] = None
    liquidity_pool_id: Optional[str] = None
    limit: Optional[str] = None
    last_modified_ledger: Optional[int] = None
    is_authorized: Optional[bool] = None
    is_authorized_to_maintain_liabilities: Optional[bool] = None
    asset_type: Optional[str] = None
    buying_liabilities: Optional[str] = None
    selling_liabilities: Optional[str] = None
    asset_code: Optional[str] = None
    asset_issuer: Optional[str] = None

    @staticmethod
    def from_dict(obj: Any) -> 'Balance':
        assert isinstance(obj, dict)
        balance = from_union([from_str, from_none], obj.get("balance"))
        liquidity_pool_id = from_union([from_str, from_none], obj.get("liquidity_pool_id"))
        limit = from_union([from_str, from_none], obj.get("limit"))
        last_modified_ledger = from_union([from_int, from_none], obj.get("last_modified_ledger"))
        is_authorized = from_union([from_bool, from_none], obj.get("is_authorized"))
        is_authorized_to_maintain_liabilities = from_union([from_bool, from_none],
                                                           obj.get("is_authorized_to_maintain_liabilities"))
        asset_type = from_union([from_str, from_none], obj.get("asset_type"))
        buying_liabilities = from_union([from_str, from_none], obj.get("buying_liabilities"))
        selling_liabilities = from_union([from_str, from_none], obj.get("selling_liabilities"))
        asset_code = from_union([from_str, from_none], obj.get("asset_code"))
        asset_issuer = from_union([from_str, from_none], obj.get("asset_issuer"))
        if asset_type == "native":
            asset_code = "XLM"
        return Balance(balance, liquidity_pool_id, limit, last_modified_ledger, is_authorized,
                       is_authorized_to_maintain_liabilities, asset_type, buying_liabilities, selling_liabilities,
                       asset_code, asset_issuer)

    def to_dict(self) -> dict:
        result: dict = {}
        result["balance"] = from_union([from_str, from_none], self.balance)
        result["liquidity_pool_id"] = from_union([from_str, from_none], self.liquidity_pool_id)
        result["limit"] = from_union([from_str, from_none], self.limit)
        result["last_modified_ledger"] = from_union([from_int, from_none], self.last_modified_ledger)
        result["is_authorized"] = from_union([from_bool, from_none], self.is_authorized)
        result["is_authorized_to_maintain_liabilities"] = from_union([from_bool, from_none],
                                                                     self.is_authorized_to_maintain_liabilities)
        result["asset_type"] = from_union([from_str, from_none], self.asset_type)
        result["buying_liabilities"] = from_union([from_str, from_none], self.buying_liabilities)
        result["selling_liabilities"] = from_union([from_str, from_none], self.selling_liabilities)
        result["asset_code"] = from_union([from_str, from_none], self.asset_code)
        result["asset_issuer"] = from_union([from_str, from_none], self.asset_issuer)
        return result


@dataclass
class Flags:
    auth_required: Optional[bool] = None
    auth_revocable: Optional[bool] = None
    auth_immutable: Optional[bool] = None
    auth_clawback_enabled: Optional[bool] = None

    @staticmethod
    def from_dict(obj: Any) -> 'Flags':
        assert isinstance(obj, dict)
        auth_required = from_union([from_bool, from_none], obj.get("auth_required"))
        auth_revocable = from_union([from_bool, from_none], obj.get("auth_revocable"))
        auth_immutable = from_union([from_bool, from_none], obj.get("auth_immutable"))
        auth_clawback_enabled = from_union([from_bool, from_none], obj.get("auth_clawback_enabled"))
        return Flags(auth_required, auth_revocable, auth_immutable, auth_clawback_enabled)

    def to_dict(self) -> dict:
        result: dict = {}
        result["auth_required"] = from_union([from_bool, from_none], self.auth_required)
        result["auth_revocable"] = from_union([from_bool, from_none], self.auth_revocable)
        result["auth_immutable"] = from_union([from_bool, from_none], self.auth_immutable)
        result["auth_clawback_enabled"] = from_union([from_bool, from_none], self.auth_clawback_enabled)
        return result


@dataclass
class EffectsClass:
    href: Optional[str] = None
    templated: Optional[bool] = None

    @staticmethod
    def from_dict(obj: Any) -> 'EffectsClass':
        assert isinstance(obj, dict)
        href = from_union([from_str, from_none], obj.get("href"))
        templated = from_union([from_bool, from_none], obj.get("templated"))
        return EffectsClass(href, templated)

    def to_dict(self) -> dict:
        result: dict = {}
        result["href"] = from_union([from_str, from_none], self.href)
        result["templated"] = from_union([from_bool, from_none], self.templated)
        return result


@dataclass
class Self:
    href: Optional[str] = None

    @staticmethod
    def from_dict(obj: Any) -> 'Self':
        assert isinstance(obj, dict)
        href = from_union([from_str, from_none], obj.get("href"))
        return Self(href)

    def to_dict(self) -> dict:
        result: dict = {}
        result["href"] = from_union([from_str, from_none], self.href)
        return result


@dataclass
class Links:
    links_self: Optional[Self] = None
    transactions: Optional[EffectsClass] = None
    operations: Optional[EffectsClass] = None
    payments: Optional[EffectsClass] = None
    effects: Optional[EffectsClass] = None
    offers: Optional[EffectsClass] = None
    trades: Optional[EffectsClass] = None
    data: Optional[EffectsClass] = None

    @staticmethod
    def from_dict(obj: Any) -> 'Links':
        assert isinstance(obj, dict)
        links_self = from_union([Self.from_dict, from_none], obj.get("self"))
        transactions = from_union([EffectsClass.from_dict, from_none], obj.get("transactions"))
        operations = from_union([EffectsClass.from_dict, from_none], obj.get("operations"))
        payments = from_union([EffectsClass.from_dict, from_none], obj.get("payments"))
        effects = from_union([EffectsClass.from_dict, from_none], obj.get("effects"))
        offers = from_union([EffectsClass.from_dict, from_none], obj.get("offers"))
        trades = from_union([EffectsClass.from_dict, from_none], obj.get("trades"))
        data = from_union([EffectsClass.from_dict, from_none], obj.get("data"))
        return Links(links_self, transactions, operations, payments, effects, offers, trades, data)

    def to_dict(self) -> dict:
        result: dict = {}
        result["self"] = from_union([lambda x: to_class(Self, x), from_none], self.links_self)
        result["transactions"] = from_union([lambda x: to_class(EffectsClass, x), from_none], self.transactions)
        result["operations"] = from_union([lambda x: to_class(EffectsClass, x), from_none], self.operations)
        result["payments"] = from_union([lambda x: to_class(EffectsClass, x), from_none], self.payments)
        result["effects"] = from_union([lambda x: to_class(EffectsClass, x), from_none], self.effects)
        result["offers"] = from_union([lambda x: to_class(EffectsClass, x), from_none], self.offers)
        result["trades"] = from_union([lambda x: to_class(EffectsClass, x), from_none], self.trades)
        result["data"] = from_union([lambda x: to_class(EffectsClass, x), from_none], self.data)
        return result


@dataclass
class Signer:
    weight: Optional[int] = None
    key: Optional[str] = None
    type: Optional[str] = None

    @staticmethod
    def from_dict(obj: Any) -> 'Signer':
        assert isinstance(obj, dict)
        weight = from_union([from_int, from_none], obj.get("weight"))
        key = from_union([from_str, from_none], obj.get("key"))
        type = from_union([from_str, from_none], obj.get("type"))
        return Signer(weight, key, type)

    def to_dict(self) -> dict:
        result: dict = {}
        result["weight"] = from_union([from_int, from_none], self.weight)
        result["key"] = from_union([from_str, from_none], self.key)
        result["type"] = from_union([from_str, from_none], self.type)
        return result


@dataclass
class Thresholds:
    low_threshold: Optional[int] = None
    med_threshold: Optional[int] = None
    high_threshold: Optional[int] = None

    @staticmethod
    def from_dict(obj: Any) -> 'Thresholds':
        assert isinstance(obj, dict)
        low_threshold = from_union([from_int, from_none], obj.get("low_threshold"))
        med_threshold = from_union([from_int, from_none], obj.get("med_threshold"))
        high_threshold = from_union([from_int, from_none], obj.get("high_threshold"))
        return Thresholds(low_threshold, med_threshold, high_threshold)

    def to_dict(self) -> dict:
        result: dict = {}
        result["low_threshold"] = from_union([from_int, from_none], self.low_threshold)
        result["med_threshold"] = from_union([from_int, from_none], self.med_threshold)
        result["high_threshold"] = from_union([from_int, from_none], self.high_threshold)
        return result


@dataclass
class MyAccount:
    sequence_time: Optional[int] = None
    links: Optional[Links] = None
    id: Optional[str] = None
    account_id: Optional[str] = None
    sequence: Optional[str] = None
    sequence_ledger: Optional[int] = None
    subentry_count: Optional[int] = None
    inflation_destination: Optional[str] = None
    home_domain: Optional[str] = None
    last_modified_ledger: Optional[int] = None
    last_modified_time: Optional[datetime] = None
    thresholds: Optional[Thresholds] = None
    flags: Optional[Flags] = None
    balances: Optional[List[Balance]] = None
    signers: Optional[List[Signer]] = None
    data: Optional[dict] = None
    num_sponsoring: Optional[int] = None
    num_sponsored: Optional[int] = None
    paging_token: Optional[str] = None

    @staticmethod
    def from_dict(obj: Any) -> 'MyAccount':
        assert isinstance(obj, dict)
        sequence_time = from_union([from_none, lambda x: int(from_str(x))], obj.get("sequence_time"))
        links = from_union([Links.from_dict, from_none], obj.get("_links"))
        id = from_union([from_str, from_none], obj.get("id"))
        account_id = from_union([from_str, from_none], obj.get("account_id"))
        sequence = from_union([from_str, from_none], obj.get("sequence"))
        sequence_ledger = from_union([from_int, from_none], obj.get("sequence_ledger"))
        subentry_count = from_union([from_int, from_none], obj.get("subentry_count"))
        inflation_destination = from_union([from_str, from_none], obj.get("inflation_destination"))
        home_domain = from_union([from_str, from_none], obj.get("home_domain"))
        last_modified_ledger = from_union([from_int, from_none], obj.get("last_modified_ledger"))
        last_modified_time = from_union([from_datetime, from_none], obj.get("last_modified_time"))
        thresholds = from_union([Thresholds.from_dict, from_none], obj.get("thresholds"))
        flags = from_union([Flags.from_dict, from_none], obj.get("flags"))
        balances = from_union([lambda x: from_list(Balance.from_dict, x), from_none], obj.get("balances"))
        signers = from_union([lambda x: from_list(Signer.from_dict, x), from_none], obj.get("signers"))
        data = obj.get("data")
        num_sponsoring = from_union([from_int, from_none], obj.get("num_sponsoring"))
        num_sponsored = from_union([from_int, from_none], obj.get("num_sponsored"))
        paging_token = from_union([from_str, from_none], obj.get("paging_token"))
        return MyAccount(sequence_time, links, id, account_id, sequence, sequence_ledger, subentry_count,
                         inflation_destination, home_domain, last_modified_ledger, last_modified_time, thresholds,
                         flags, balances, signers, data, num_sponsoring, num_sponsored, paging_token)

    def to_dict(self) -> dict:
        result: dict = {}
        result["sequence_time"] = from_union([lambda x: from_none((lambda x: is_type(type(None), x))(x)),
                                              lambda x: from_str((lambda x: str((lambda x: is_type(int, x))(x)))(x))],
                                             self.sequence_time)
        result["_links"] = from_union([lambda x: to_class(Links, x), from_none], self.links)
        result["id"] = from_union([from_str, from_none], self.id)
        result["account_id"] = from_union([from_str, from_none], self.account_id)
        result["sequence"] = from_union([from_str, from_none], self.sequence)
        result["sequence_ledger"] = from_union([from_int, from_none], self.sequence_ledger)
        result["subentry_count"] = from_union([from_int, from_none], self.subentry_count)
        result["inflation_destination"] = from_union([from_str, from_none], self.inflation_destination)
        result["home_domain"] = from_union([from_str, from_none], self.home_domain)
        result["last_modified_ledger"] = from_union([from_int, from_none], self.last_modified_ledger)
        result["last_modified_time"] = from_union([lambda x: x.isoformat(), from_none], self.last_modified_time)
        result["thresholds"] = from_union([lambda x: to_class(Thresholds, x), from_none], self.thresholds)
        result["flags"] = from_union([lambda x: to_class(Flags, x), from_none], self.flags)
        result["balances"] = from_union([lambda x: from_list(lambda x: to_class(Balance, x), x), from_none],
                                        self.balances)
        result["signers"] = from_union([lambda x: from_list(lambda x: to_class(Signer, x), x), from_none], self.signers)
        result["data"] = self.data
        result["num_sponsoring"] = from_union([from_int, from_none], self.num_sponsoring)
        result["num_sponsored"] = from_union([from_int, from_none], self.num_sponsored)
        result["paging_token"] = from_union([from_str, from_none], self.paging_token)
        return result


@dataclass
class Account:
    href: Optional[str] = None

    @staticmethod
    def from_dict(obj: Any) -> 'Account':
        assert isinstance(obj, dict)
        href = from_union([from_str, from_none], obj.get("href"))
        return Account(href)

    def to_dict(self) -> dict:
        result: dict = {}
        result["href"] = from_union([from_str, from_none], self.href)
        return result


@dataclass
class Effects:
    href: Optional[str] = None
    templated: Optional[bool] = None

    @staticmethod
    def from_dict(obj: Any) -> 'Effects':
        assert isinstance(obj, dict)
        href = from_union([from_str, from_none], obj.get("href"))
        templated = from_union([from_bool, from_none], obj.get("templated"))
        return Effects(href, templated)

    def to_dict(self) -> dict:
        result: dict = {}
        result["href"] = from_union([from_str, from_none], self.href)
        result["templated"] = from_union([from_bool, from_none], self.templated)
        return result


@dataclass
class Links:
    links_self: Optional[Account] = None
    account: Optional[Account] = None
    ledger: Optional[Account] = None
    operations: Optional[Effects] = None
    effects: Optional[Effects] = None
    precedes: Optional[Account] = None
    succeeds: Optional[Account] = None
    transaction: Optional[Account] = None

    @staticmethod
    def from_dict(obj: Any) -> 'Links':
        assert isinstance(obj, dict)
        links_self = from_union([Account.from_dict, from_none], obj.get("self"))
        account = from_union([Account.from_dict, from_none], obj.get("account"))
        ledger = from_union([Account.from_dict, from_none], obj.get("ledger"))
        operations = from_union([Effects.from_dict, from_none], obj.get("operations"))
        effects = from_union([Effects.from_dict, from_none], obj.get("effects"))
        precedes = from_union([Account.from_dict, from_none], obj.get("precedes"))
        succeeds = from_union([Account.from_dict, from_none], obj.get("succeeds"))
        transaction = from_union([Account.from_dict, from_none], obj.get("transaction"))
        return Links(links_self, account, ledger, operations, effects, precedes, succeeds, transaction)

    def to_dict(self) -> dict:
        result: dict = {}
        result["self"] = from_union([lambda x: to_class(Account, x), from_none], self.links_self)
        result["account"] = from_union([lambda x: to_class(Account, x), from_none], self.account)
        result["ledger"] = from_union([lambda x: to_class(Account, x), from_none], self.ledger)
        result["operations"] = from_union([lambda x: to_class(Effects, x), from_none], self.operations)
        result["effects"] = from_union([lambda x: to_class(Effects, x), from_none], self.effects)
        result["precedes"] = from_union([lambda x: to_class(Account, x), from_none], self.precedes)
        result["succeeds"] = from_union([lambda x: to_class(Account, x), from_none], self.succeeds)
        result["transaction"] = from_union([lambda x: to_class(Account, x), from_none], self.transaction)
        return result


@dataclass
class Timebounds:
    min_time: Optional[int] = None
    max_time: Optional[int] = None

    @staticmethod
    def from_dict(obj: Any) -> 'Timebounds':
        assert isinstance(obj, dict)
        min_time = from_union([from_none, lambda x: int(from_str(x))], obj.get("min_time"))
        max_time = from_union([from_none, lambda x: int(from_str(x))], obj.get("max_time"))
        return Timebounds(min_time, max_time)

    def to_dict(self) -> dict:
        result: dict = {}
        result["min_time"] = from_union([lambda x: from_none((lambda x: is_type(type(None), x))(x)),
                                         lambda x: from_str((lambda x: str((lambda x: is_type(int, x))(x)))(x))],
                                        self.min_time)
        result["max_time"] = from_union([lambda x: from_none((lambda x: is_type(type(None), x))(x)),
                                         lambda x: from_str((lambda x: str((lambda x: is_type(int, x))(x)))(x))],
                                        self.max_time)
        return result


@dataclass
class Preconditions:
    timebounds: Optional[Timebounds] = None

    @staticmethod
    def from_dict(obj: Any) -> 'Preconditions':
        assert isinstance(obj, dict)
        timebounds = from_union([Timebounds.from_dict, from_none], obj.get("timebounds"))
        return Preconditions(timebounds)

    def to_dict(self) -> dict:
        result: dict = {}
        result["timebounds"] = from_union([lambda x: to_class(Timebounds, x), from_none], self.timebounds)
        return result


@dataclass
class ResultCodes:
    transaction: Optional[str] = None

    @staticmethod
    def from_dict(obj: Any) -> 'ResultCodes':
        assert isinstance(obj, dict)
        transaction = from_union([from_str, from_none], obj.get("transaction"))
        return ResultCodes(transaction)

    def to_dict(self) -> dict:
        result: dict = {}
        result["transaction"] = from_union([from_str, from_none], self.transaction)
        return result


@dataclass
class Extras:
    envelope_xdr: Optional[str] = None
    result_codes: Optional[ResultCodes] = None
    result_xdr: Optional[str] = None

    @staticmethod
    def from_dict(obj: Any) -> 'Extras':
        assert isinstance(obj, dict)
        envelope_xdr = from_union([from_str, from_none], obj.get("envelope_xdr"))
        result_codes = from_union([ResultCodes.from_dict, from_none], obj.get("result_codes"))
        result_xdr = from_union([from_str, from_none], obj.get("result_xdr"))
        return Extras(envelope_xdr, result_codes, result_xdr)

    def to_dict(self) -> dict:
        result: dict = {}
        result["envelope_xdr"] = from_union([from_str, from_none], self.envelope_xdr)
        result["result_codes"] = from_union([lambda x: to_class(ResultCodes, x), from_none], self.result_codes)
        result["result_xdr"] = from_union([from_str, from_none], self.result_xdr)
        return result


@dataclass
class MyResponse:
    fee_charged: Optional[int] = None
    max_fee: Optional[int] = None
    memo: Optional[str] = None
    memo_bytes: Optional[str] = None
    links: Optional[Links] = None
    id: Optional[str] = None
    paging_token: Optional[str] = None
    successful: Optional[bool] = None
    hash: Optional[str] = None
    ledger: Optional[int] = None
    created_at: Optional[datetime] = None
    source_account: Optional[str] = None
    source_account_sequence: Optional[str] = None
    fee_account: Optional[str] = None
    type: Optional[str] = None
    title: Optional[str] = None
    status: Optional[int] = None
    detail: Optional[str] = None
    extras: Optional[Extras] = None
    operation_count: Optional[int] = None
    envelope_xdr: Optional[str] = None
    result_xdr: Optional[str] = None
    result_meta_xdr: Optional[str] = None
    fee_meta_xdr: Optional[str] = None
    memo_type: Optional[str] = None
    signatures: Optional[List[str]] = None
    valid_after: Optional[datetime] = None
    valid_before: Optional[datetime] = None
    preconditions: Optional[Preconditions] = None

    @staticmethod
    def from_dict(obj: Any) -> 'MyResponse':
        assert isinstance(obj, dict)
        fee_charged = from_union([from_none, lambda x: int(from_str(x))], obj.get("fee_charged"))
        max_fee = from_union([from_none, lambda x: int(from_str(x))], obj.get("max_fee"))
        memo = from_union([from_str, from_none], obj.get("memo"))
        memo_bytes = from_union([from_str, from_none], obj.get("memo_bytes"))
        links = from_union([Links.from_dict, from_none], obj.get("_links"))
        id = from_union([from_str, from_none], obj.get("id"))
        paging_token = from_union([from_str, from_none], obj.get("paging_token"))
        successful = from_union([from_bool, from_none], obj.get("successful"))
        hash = from_union([from_str, from_none], obj.get("hash"))
        ledger = from_union([from_int, from_none], obj.get("ledger"))
        created_at = from_union([from_datetime, from_none], obj.get("created_at"))
        source_account = from_union([from_str, from_none], obj.get("source_account"))
        source_account_sequence = from_union([from_str, from_none], obj.get("source_account_sequence"))
        fee_account = from_union([from_str, from_none], obj.get("fee_account"))
        type = from_union([from_str, from_none], obj.get("type"))
        title = from_union([from_str, from_none], obj.get("title"))
        status = from_union([from_int, from_none], obj.get("status"))
        detail = from_union([from_str, from_none], obj.get("detail"))
        extras = from_union([Extras.from_dict, from_none], obj.get("extras"))
        operation_count = from_union([from_int, from_none], obj.get("operation_count"))
        envelope_xdr = from_union([from_str, from_none], obj.get("envelope_xdr"))
        result_xdr = from_union([from_str, from_none], obj.get("result_xdr"))
        result_meta_xdr = from_union([from_str, from_none], obj.get("result_meta_xdr"))
        fee_meta_xdr = from_union([from_str, from_none], obj.get("fee_meta_xdr"))
        memo_type = from_union([from_str, from_none], obj.get("memo_type"))
        signatures = from_union([lambda x: from_list(from_str, x), from_none], obj.get("signatures"))
        valid_after = from_union([from_datetime, from_none], obj.get("valid_after"))
        valid_before = from_union([from_datetime, from_none], obj.get("valid_before"))
        preconditions = from_union([Preconditions.from_dict, from_none], obj.get("preconditions"))
        return MyResponse(fee_charged, max_fee, memo, memo_bytes, links, id, paging_token, successful, hash, ledger,
                          created_at, source_account, source_account_sequence, fee_account, type, title, status, detail,
                          extras, operation_count, envelope_xdr, result_xdr, result_meta_xdr, fee_meta_xdr, memo_type,
                          signatures, valid_after, valid_before, preconditions)

    def to_dict(self) -> dict:
        result: dict = {}
        result["fee_charged"] = from_union([lambda x: from_none((lambda x: is_type(type(None), x))(x)),
                                            lambda x: from_str((lambda x: str((lambda x: is_type(int, x))(x)))(x))],
                                           self.fee_charged)
        result["max_fee"] = from_union([lambda x: from_none((lambda x: is_type(type(None), x))(x)),
                                        lambda x: from_str((lambda x: str((lambda x: is_type(int, x))(x)))(x))],
                                       self.max_fee)
        result["memo"] = from_union([from_str, from_none], self.memo)
        result["memo_bytes"] = from_union([from_str, from_none], self.memo_bytes)
        result["_links"] = from_union([lambda x: to_class(Links, x), from_none], self.links)
        result["id"] = from_union([from_str, from_none], self.id)
        result["paging_token"] = from_union([from_str, from_none], self.paging_token)
        result["successful"] = from_union([from_bool, from_none], self.successful)
        result["hash"] = from_union([from_str, from_none], self.hash)
        result["ledger"] = from_union([from_int, from_none], self.ledger)
        result["created_at"] = from_union([lambda x: x.isoformat(), from_none], self.created_at)
        result["source_account"] = from_union([from_str, from_none], self.source_account)
        result["source_account_sequence"] = from_union([from_str, from_none], self.source_account_sequence)
        result["fee_account"] = from_union([from_str, from_none], self.fee_account)
        result["type"] = from_union([from_str, from_none], self.type)
        result["title"] = from_union([from_str, from_none], self.title)
        result["status"] = from_union([from_int, from_none], self.status)
        result["detail"] = from_union([from_str, from_none], self.detail)
        result["extras"] = from_union([lambda x: to_class(Extras, x), from_none], self.extras)
        result["operation_count"] = from_union([from_int, from_none], self.operation_count)
        result["envelope_xdr"] = from_union([from_str, from_none], self.envelope_xdr)
        result["result_xdr"] = from_union([from_str, from_none], self.result_xdr)
        result["result_meta_xdr"] = from_union([from_str, from_none], self.result_meta_xdr)
        result["fee_meta_xdr"] = from_union([from_str, from_none], self.fee_meta_xdr)
        result["memo_type"] = from_union([from_str, from_none], self.memo_type)
        result["signatures"] = from_union([lambda x: from_list(from_str, x), from_none], self.signatures)
        result["valid_after"] = from_union([lambda x: x.isoformat(), from_none], self.valid_after)
        result["valid_before"] = from_union([lambda x: x.isoformat(), from_none], self.valid_before)
        result["preconditions"] = from_union([lambda x: to_class(Preconditions, x), from_none], self.preconditions)
        return result


if __name__ == "__main__":
    pass
