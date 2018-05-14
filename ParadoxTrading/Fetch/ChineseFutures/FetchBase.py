import json
import typing

import psycopg2
import psycopg2.extensions
import pymongo
import pymongo.collection
import pymongo.database
from diskcache import Cache
from pymongo import MongoClient

from ParadoxTrading.Fetch import FetchAbstract, RegisterAbstract
from ParadoxTrading.Utils import DataStruct


class RegisterInstrument(RegisterAbstract):
    DOMINANT = 1
    SUB_DOMINANT = 2
    BEFORE_DOMINANT = 3
    AFTER_DOMINANT = 4
    MOST_OPENINTEREST = 5
    SECOND_OPENINTEREST = 6
    MOST_VOLUME = 7
    SECOND_VOLUME = 8

    def __init__(
            self, _product: str = None, _type: int = 1
    ):
        """
        Market Register is used to store market sub information,
        pre-processed data and strategies used it

        :param _product: reg which product, if not None, ignore instrument
        :param _type: type to register, default dominant
        """
        super().__init__()
        assert _product is not None
        assert _type in [1, 2, 3, 4, 5, 6]

        # market register info
        self.product = _product
        self.type = _type

    def toJson(self) -> str:
        """
        encode register info into json str

        :return: json str
        """
        return json.dumps((
            ('product', self.product),
            ('type', self.type),
        ))

    def toKwargs(self) -> dict:
        """
        turn self to dict, used by fetchSymbol()

        :return:
        """
        return {
            '_product': self.product,
            '_type': self.type,
        }

    @staticmethod
    def fromJson(_json_str: str) -> 'RegisterInstrument':
        """
        create object from a json str

        :param _json_str: json str stores register info
        :return: market register object
        """
        data = dict(json.loads(_json_str))
        return RegisterInstrument(
            data['product'],
            data['type'],
        )


class RegisterIndex(RegisterAbstract):
    def __init__(self, _product: str):
        """
        because it is index, there is only product as parameter

        :param _product:
        """
        super().__init__()

        self.product = _product

    def toJson(self) -> str:
        return json.dumps((
            ('product', self.product),
        ))

    def toKwargs(self) -> dict:
        return {
            '_product': self.product
        }

    @staticmethod
    def fromJson(_json_str: str) -> 'RegisterIndex':
        data: typing.Dict[str, typing.Any] = dict(json.loads(_json_str))
        return RegisterIndex(
            data['product']
        )


class FetchBase(FetchAbstract):
    def __init__(
            self, _mongo_host='localhost', _psql_host='localhost',
            _psql_user='', _psql_password='', _cache_path='cache'
    ):
        super().__init__()
        self.register_type = RegisterInstrument

        self.mongo_host: str = _mongo_host
        self.mongo_dbname: str = 'ChineseFutures'

        self.psql_host: str = _psql_host
        self.psql_dbname: str = None
        self.psql_user: str = _psql_user
        self.psql_password: str = _psql_password

        self.cache: Cache = Cache(_cache_path)
        self.market_key: str = None
        self.tradingday_key: str = 'ChineseFuturesTradingDay_{}'
        self.prod_key: str = 'ChineseFuturesProduct_{}_{}'
        self.inst_key: str = 'ChineseFuturesInstrument_{}_{}'

        self._mongo_client: MongoClient = None
        self._mongo_db: pymongo.database.Database = None
        self._psql_con: psycopg2.extensions.connection = None
        self._psql_cur: psycopg2.extensions.cursor = None

        self.columns: typing.List = []

    def _get_mongo_db(self) -> pymongo.database.Database:
        if not self._mongo_db:
            if not self._mongo_client:
                self._mongo_client: MongoClient = MongoClient(
                    host=self.mongo_host
                )
            self._mongo_db: pymongo.database.Database = \
                self._mongo_client[self.mongo_dbname]
        return self._mongo_db

    def _get_psql_con_cur(self) -> typing.Tuple[
        psycopg2.extensions.connection, psycopg2.extensions.cursor
    ]:
        if not self._psql_con:
            self._psql_con: psycopg2.extensions.connection = \
                psycopg2.connect(
                    dbname=self.psql_dbname,
                    host=self.psql_host,
                    user=self.psql_user,
                    password=self.psql_password,
                )
        if not self._psql_cur:
            self._psql_cur: psycopg2.extensions.cursor = \
                self._psql_con.cursor()

        return self._psql_con, self._psql_cur

    def isTradingDay(self, _tradingday: str) -> bool:
        """
        check whether _tradingday is a tradingday,
        return True if any product available

        :param _tradingday:
        :return:
        """
        return self.fetchTradingDayInfo(
            _tradingday
        ) is not None

    def fetchAvailableProduct(self, _tradingday: str) -> list:
        """
        fetch all available product on pointed tradingday
        """
        data = self.fetchTradingDayInfo(_tradingday)
        ret = []
        if data is not None:
            ret = data['ProductList']
        return ret

    def productIsAvailable(
            self, _product: str, _tradingday: str
    ) -> bool:
        """
        check whether product is traded on tradingday
        """
        return self.fetchProductInfo(
            _product, _tradingday
        ) is not None

    def productLastTradingDay(
            self, _product: str, _tradingday: str
    ) -> typing.Union[None, str]:
        """
        get the first day less then _tradingday of _product
        """
        db = self._get_mongo_db()
        coll = db.product
        d = coll.find_one(
            filter={
                'TradingDay': {'$lt': _tradingday},
                'Product': _product,
            },
            sort=[('TradingDay', pymongo.DESCENDING)]
        )

        return d['TradingDay'] if d is not None else None

    def productNextTradingDay(
            self, _product: str, _tradingday: str
    ) -> typing.Union[None, str]:
        """
        get the first day greater then _tradingday of _product
        """
        db = self._get_mongo_db()
        coll = db.product
        d = coll.find_one(
            filter={
                'TradingDay': {'$gt': _tradingday},
                'Product': _product,
            },
            sort=[('TradingDay', pymongo.ASCENDING)]
        )

        return d['TradingDay'] if d is not None else None

    def fetchDominant(
            self, _product: str, _tradingday: str
    ) -> typing.Union[None, str]:
        """
        fetch dominant instrument of one product on tradingday
        """
        data = self.fetchProductInfo(_product, _tradingday)
        ret = None
        if data is not None:
            ret = data['Dominant']

        return ret

    def fetchSubDominant(
            self, _product: str, _tradingday: str
    ) -> typing.Union[None, str]:
        """
        fetch sub dominant instrument of one product on tradingday
        """
        data = self.fetchProductInfo(_product, _tradingday)
        ret = None
        if data is not None:
            ret = data['SubDominant']

        return ret

    def fetchAvailableInstrument(
            self, _product: str, _tradingday: str
    ) -> typing.List[str]:
        """
        fetch all traded instruments of pointed product on tradingday
        """
        data = self.fetchProductInfo(_product, _tradingday)
        ret = []
        if data is not None:
            ret = data['InstrumentList']
        return ret

    def instrumentIsAvailable(
            self, _instrument: str, _tradingday: str
    ) -> bool:
        """
        check whether instrument is traded on tradingday
        """
        return self.fetchInstrumentInfo(
            _instrument, _tradingday
        ) is not None

    def instrumentDeliveryMonth(
            self, _instrument: str, _tradingday: str
    ) -> typing.Union[None, str]:
        data = self.fetchInstrumentInfo(_instrument, _tradingday)
        if data is not None:
            return data['DeliveryMonth']
        return None

    def instrumentLastTradingDay(
            self, _instrument: str, _tradingday: str
    ) -> typing.Union[None, str]:
        """
        get the first day less then _tradingday of _instrument
        """
        db = self._get_mongo_db()
        coll = db.instrument
        d = coll.find_one(
            filter={
                'TradingDay': {'$lt': _tradingday},
                'Instrument': _instrument,
            },
            sort=[('TradingDay', pymongo.DESCENDING)]
        )

        return d['TradingDay'] if d is not None else None

    def instrumentNextTradingDay(
            self, _instrument: str, _tradingday: str
    ) -> typing.Union[None, str]:
        """
        get the first day greater then _tradingday of _instrument
        """
        db = self._get_mongo_db()
        coll = db.instrument
        d = coll.find_one(
            filter={
                'TradingDay': {'$gt': _tradingday},
                'Instrument': _instrument,
            },
            sort=[('TradingDay', pymongo.ASCENDING)]
        )

        return d['TradingDay'] if d is not None else None

    def fetchTradingDayInfo(
            self, _tradingday: str
    ) -> typing.Union[None, typing.Dict]:
        """
        get the whole tradingday record in mongo
        """
        key = self.tradingday_key.format(_tradingday)
        try:
            return self.cache[key]
        except KeyError:
            db = self._get_mongo_db()
            coll = db.tradingday
            data = coll.find_one({'TradingDay': _tradingday})
            self.cache[key] = data
            return data

    def fetchProductInfo(
            self, _product: str, _tradingday: str
    ) -> typing.Union[None, typing.Dict]:
        """
        get the whole product record in mongo
        """
        product = _product.lower()
        key = self.prod_key.format(product, _tradingday)
        try:
            return self.cache[key]
        except KeyError:
            db = self._get_mongo_db()
            coll = db.product
            data = coll.find_one({
                'TradingDay': _tradingday,
                'Product': _product,
            })
            self.cache[key] = data
            return data

    def fetchInstrumentInfo(
            self, _instrument: str, _tradingday: str
    ) -> typing.Union[None, typing.Dict]:
        """
        get the whole instrument record in mongo
        """
        instrument = _instrument.lower()
        key = self.inst_key.format(instrument, _tradingday)
        try:
            return self.cache[key]
        except KeyError:
            db = self._get_mongo_db()
            coll = db.instrument
            data = coll.find_one({
                'TradingDay': _tradingday,
                'Instrument': _instrument,
            })
            self.cache[key] = data
            return data

    def _get_sorted_list(
            self, _product: str, _tradingday: str, _key: str
    ):
        instrument_list = self.fetchAvailableInstrument(
            _product, _tradingday
        )
        if not instrument_list:
            return None
        tmp = [(
            k, self.fetchData(_tradingday, k)[_key][0]
        ) for k in instrument_list]
        tmp.sort(key=lambda x: x[1])

        return tmp

    def fetchSymbol(
            self, _tradingday: str, _product: str = None,
            _type: int = RegisterInstrument.DOMINANT,
    ) -> typing.Union[None, str]:
        """
        get symbol from database

        :param _tradingday: the tradingday
        :param _product: the product to fetch
        :param _type:
        :return:
        """

        assert _product is not None

        product = _product.lower()

        if _type == RegisterInstrument.DOMINANT:
            return self.fetchDominant(product, _tradingday)
        elif _type == RegisterInstrument.SUB_DOMINANT:
            return self.fetchSubDominant(product, _tradingday)
        elif _type == RegisterInstrument.BEFORE_DOMINANT:
            dominant = self.fetchDominant(product, _tradingday)
            if dominant is None:
                return None
            tmp = self.fetchAvailableInstrument(product, _tradingday)
            if not tmp:
                return None
            tmp.sort()
            tmp_index = tmp.index(dominant)
            tmp_index -= 1
            if tmp_index < 0:
                return None
            return tmp[tmp_index]
        elif _type == RegisterInstrument.AFTER_DOMINANT:
            dominant = self.fetchDominant(product, _tradingday)
            if dominant is None:
                return None
            tmp = self.fetchAvailableInstrument(product, _tradingday)
            if not tmp:
                return None
            tmp.sort()
            tmp_index = tmp.index(dominant)
            tmp_index += 1
            if tmp_index >= len(tmp):
                return None
            return tmp[tmp_index]
        elif _type == RegisterInstrument.MOST_OPENINTEREST:
            ret = self._get_sorted_list(
                product, _tradingday, 'openinterest'
            )
            return None if ret is None else ret[-1][0]
        elif _type == RegisterInstrument.SECOND_OPENINTEREST:
            ret = self._get_sorted_list(
                product, _tradingday, 'openinterest'
            )
            return None if ret is None else ret[-2][0]
        elif _type == RegisterInstrument.MOST_VOLUME:
            ret = self._get_sorted_list(
                product, _tradingday, 'volume'
            )
            return None if ret is None else ret[-1][0]
        elif _type == RegisterInstrument.SECOND_VOLUME:
            ret = self._get_sorted_list(
                product, _tradingday, 'volume'
            )
            return None if ret is None else ret[-2][0]
        else:
            raise Exception('unknown type')

    def fetchData(
            self, _tradingday: str, _symbol: str,
            _cache=True, _index='HappenTime'
    ) -> typing.Union[None, DataStruct]:
        """

        :param _tradingday:
        :param _symbol:
        :param _cache: whether to cache by hdf5
        :param _index: use which column to index
        :return:
        """
        assert isinstance(_symbol, str)
        symbol = _symbol.lower()

        key = self.market_key.format(symbol, _tradingday)
        if _cache:
            try:
                return self.cache[key]
            except KeyError:
                pass

        # fetch from database
        con, cur = self._get_psql_con_cur()

        # get all ticks
        cur.execute(
            "SELECT * FROM {} WHERE TradingDay='{}' "
            "ORDER BY {}".format(
                symbol, _tradingday, _index.lower())
        )
        data = list(cur.fetchall())
        if len(data):
            data = DataStruct(self.columns, _index.lower(), data)
        else:
            data = None

        if _cache:
            self.cache[key] = data
        return data

    def fetchDayData(
            self, _begin_day: str, _end_day: str,
            _symbol: str, _index: str = 'HappenTime'
    ) -> DataStruct:
        """
        get the data from _begin_day to _end_day(excluded)
        """
        begin_day = _begin_day
        end_day = _end_day
        if _end_day is None:
            end_day = begin_day

        con, cur = self._get_psql_con_cur()

        query = "SELECT * FROM {} " \
                "WHERE tradingday >= '{}' AND tradingday < '{}' " \
                "ORDER BY {}".format(
            _symbol.lower(), begin_day, end_day, _index.lower()
        )
        cur.execute(query)
        data = list(cur.fetchall())

        return DataStruct(self.columns, _index.lower(), data)
