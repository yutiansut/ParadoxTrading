from datetime import datetime

from ParadoxTrading.Fetch import FetchGuoJinTick
from ParadoxTrading.Indicator import CloseBar, HighBar, LowBar, OpenBar, SumBar, Diff, MA, OHLC
from ParadoxTrading.Utils import SplitIntoMinute

fetcher = FetchGuoJinTick()
fetcher.psql_host = '192.168.4.102'
fetcher.mongo_host = '192.168.4.102'
fetcher.psql_user = 'ubuntu'

instrument = fetcher.fetchDominant('rb', '20160104')
data = fetcher.fetchData('20160104', instrument)
data = data.loc[:datetime(2016, 1, 4, 10)]
print(data)

spliter = SplitIntoMinute(5)
spliter.addMany(data)

ohlc = OHLC('lastprice')
ohlc.addMany(spliter.getBarList(), spliter.getBarBeginTimeList())
print(ohlc.getAllData())

open_bar = OpenBar('lastprice')
open_bar.addMany(spliter.getBarList(), spliter.getBarBeginTimeList())
bar_data = open_bar.getAllData()

close_bar = CloseBar('lastprice')
close_bar.addMany(spliter.getBarList(), spliter.getBarBeginTimeList())
bar_data.expand(close_bar.getAllData())

high_bar = HighBar('lastprice')
high_bar.addMany(spliter.getBarList(), spliter.getBarBeginTimeList())
bar_data.expand(high_bar.getAllData())

low_bar = LowBar('lastprice')
low_bar.addMany(spliter.getBarList(), spliter.getBarBeginTimeList())
bar_data.expand(low_bar.getAllData())

sum_bar = SumBar('askvolume', _ret_key='askvolume')
sum_bar.addMany(spliter.getBarList(), spliter.getBarBeginTimeList())
bar_data.expand(sum_bar.getAllData())

diff = Diff('close')
diff.addMany(bar_data)
bar_data.expand(diff.getAllData())

ma = MA(5, 'close')
ma.addMany(bar_data)
bar_data.expand(ma.getAllData())

print(bar_data)