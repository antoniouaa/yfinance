#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# yfinance - market data downloader
# https://github.com/ranaroussi/yfinance
#
# Copyright 2017-2019 Ran Aroussi
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

from __future__ import print_function

import time as _time
import datetime as _datetime
from typing import Optional

import pandas as _pd
import numpy as _np
import pandas as pd

from .data import TickerData

from urllib.parse import quote as urlencode

from . import utils

from . import shared
from .scrapers.analysis import Analysis
from .scrapers.fundamentals import Fundamentals
from .scrapers.holders import Holders
from .scrapers.quote import Quote
import json as _json

_BASE_URL_ = 'https://query2.finance.yahoo.com'
_SCRAPE_URL_ = 'https://finance.yahoo.com/quote'
_ROOT_URL_ = 'https://finance.yahoo.com'


class BasicInfo:
    # Contain small subset of info[] items that can be fetched faster elsewhere.
    # Imitates a dict.
    def __init__(self, tickerBaseObject):
        self._tkr = tickerBaseObject

        self._prices_1y = None
        self._md = None

        self._currency = None
        self._exchange = None
        self._timezone = None

        self._shares = None
        self._mcap = None

        self._last_price = None
        self._last_volume = None
        self._50d_day_average = None
        self._200d_day_average = None
        self._year_high = None
        self._year_low = None
        self._year_change = None
        self._10d_avg_vol = None
        self._3mo_avg_vol = None

    # dict imitation:
    def keys(self):
        attrs = utils.attributes(self)
        return attrs.keys()
    def items(self):
        return [(k,self[k]) for k in self.keys()]
    def __getitem__(self, k):
        if not isinstance(k, str):
            raise KeyError(f"key must be a string")
        if not k in self.keys():
            raise KeyError(f"'{k}' not valid key. Examine 'BasicInfo.keys()'")
        return getattr(self, k)
    def __contains__(self, k):
        return k in self.keys()
    def __iter__(self):
        return iter(self.keys())

    def __str__(self):
        return "lazy-loading dict with keys = " + str(self.keys())
    def __repr__(self):
        return self.__str__()

    def _get_1y_prices(self, fullDaysOnly=False):
        if self._prices_1y is None:
            self._prices_1y = self._tkr.history(period="380d", auto_adjust=False)
            self._md = self._tkr.get_history_metadata()
            try:
                ctp = self._md["currentTradingPeriod"]
                self._today_open = pd.to_datetime(ctp["regular"]["start"], unit='s', utc=True).tz_convert(self.timezone)
                self._today_close = pd.to_datetime(ctp["regular"]["end"], unit='s', utc=True).tz_convert(self.timezone)
                self._today_midnight = self._today_close.ceil("D")
            except:
                self._today_open = None
                self._today_close = None
                self._today_midnight = None
                raise

        if self._prices_1y.empty:
            return self.self._prices_1y

        dt1 = self._prices_1y.index[-1]
        if fullDaysOnly and self._exchange_open_now():
            # Exclude today
            dt1 -= utils._interval_to_timedelta("1h")
        dt0 = dt1 - utils._interval_to_timedelta("1y") + utils._interval_to_timedelta("1d")
        return self._prices_1y.loc[dt0:dt1]

    def _get_exchange_metadata(self):
        if self._md is not None:
            return self._md

        self._get_1y_prices()
        self._md = self._tkr.get_history_metadata()
        return self._md

    def _exchange_open_now(self):
        t = pd.Timestamp.utcnow()
        self._get_exchange_metadata()

        # if self._today_open is None and self._today_close is None:
        #     r = False
        # else:
        #     r = self._today_open <= t and t < self._today_close

        # if self._today_midnight is None:
        #     r = False
        # elif self._today_midnight.date() > t.tz_convert(self.timezone).date():
        #     r = False
        # else:
        #     r = t < self._today_midnight

        last_day_cutoff = self._get_1y_prices().index[-1] + _datetime.timedelta(days=1)
        last_day_cutoff += _datetime.timedelta(minutes=20)
        r = t < last_day_cutoff

        # print("_exchange_open_now() returning", r)
        return r
    
    @property
    def currency(self):
        if self._currency is not None:
            return self._currency

        if self._tkr._history_metadata is None:
            self._get_1y_prices()
        md = self._tkr.get_history_metadata()
        self._currency = md["currency"]
        return self._currency

    def _currency_is_cents(self):
        return self.currency in ["GBp"]

    @property
    def exchange(self):
        if self._exchange is not None:
            return self._exchange

        self._exchange = self._get_exchange_metadata()["exchangeName"]
        return self._exchange

    @property
    def timezone(self):
        if self._timezone is not None:
            return self._timezone

        self._timezone = self._get_exchange_metadata()["exchangeTimezoneName"]
        return self._timezone

    @property
    def shares(self):
        if self._shares is not None:
            return self._shares

        shares = self._tkr.get_shares_full(start=pd.Timestamp.utcnow().date()-pd.Timedelta(days=548))
        if shares is None:
            # Requesting 18 months failed, so fallback to shares which should include last year
            shares = self._tkr.get_shares()
        if shares is None:
            raise Exception(f"{self._tkr.ticker}: Cannot retrieve share count for calculating market cap")
        if isinstance(shares, pd.DataFrame):
            shares = shares[shares.columns[0]]
        self._shares = shares.iloc[-1]
        return self._shares

    @property
    def last_price(self):
        if self._last_price is not None:
            return self._last_price

        self._last_price = self._get_exchange_metadata()["regularMarketPrice"]
        return self._last_price

    @property
    def last_volume(self):
        if self._last_volume is not None:
            return self._last_volume

        prices = self._get_1y_prices()
        if prices.empty:
            self._last_volume = 0
        else:
            self._last_volume = prices["Volume"].iloc[-1]

        return self._last_volume

    @property
    def fifty_day_average(self):
        if self._50d_day_average is not None:
            return self._50d_day_average

        prices = self._get_1y_prices(fullDaysOnly=True)
        if prices.empty:
            self._50d_day_average = _np.nan
        else:
            n = prices.shape[0]
            a = n-50
            b = n
            if a < 0:
                a = 0
            self._50d_day_average = prices["Close"].iloc[a:b].mean()

        return self._50d_day_average

    @property
    def two_hundred_day_average(self):
        if self._200d_day_average is not None:
            return self._200d_day_average

        prices = self._get_1y_prices(fullDaysOnly=True)
        if prices.empty:
            self._200d_day_average = _np.nan
        else:
            n = prices.shape[0]
            a = n-200
            b = n
            if a < 0:
                a = 0

            self._200d_day_average = prices["Close"].iloc[a:b].mean()

        return self._200d_day_average

    @property
    def ten_day_average_volume(self):
        if self._10d_avg_vol is not None:
            return self._10d_avg_vol

        prices = self._get_1y_prices(fullDaysOnly=True)
        if prices.empty:
            self._10d_avg_vol = 0
        else:
            n = prices.shape[0]
            a = n-10
            b = n
            if a < 0:
                a = 0
            self._10d_avg_vol = prices["Volume"].iloc[a:b].mean()

        return self._10d_avg_vol

    @property
    def three_month_average_volume(self):
        if self._3mo_avg_vol is not None:
            return self._3mo_avg_vol

        prices = self._get_1y_prices(fullDaysOnly=True)
        if prices.empty:
            self._3mo_avg_vol = 0
        else:
            dt1 = prices.index[-1]
            dt0 = dt1 - utils._interval_to_timedelta("3mo") + utils._interval_to_timedelta("1d")
            self._3mo_avg_vol = prices.loc[dt0:dt1, "Volume"].mean()

        return self._3mo_avg_vol

    @property
    def year_high(self):
        if self._year_high is not None:
            return self._year_high

        prices = self._get_1y_prices(fullDaysOnly=True)
        self._year_high = prices["High"].max()
        return self._year_high

    @property
    def year_low(self):
        if self._year_low is not None:
            return self._year_low

        prices = self._get_1y_prices(fullDaysOnly=True)
        self._year_low = prices["Low"].min()
        return self._year_low

    @property
    def year_change(self):
        if self._year_change is not None:
            return self._year_change

        prices = self._get_1y_prices(fullDaysOnly=True)
        self._year_change = (prices["Close"].iloc[-1] - prices["Close"].iloc[0]) / prices["Close"].iloc[0]
        return self._year_change

    @property
    def market_cap(self):
        if self._mcap is not None:
            return self._mcap

        self._mcap = self.shares * self.last_price
        if self._currency_is_cents():
            self._mcap *= 0.01
        return self._mcap


class TickerBase:
    def __init__(self, ticker, session=None):
        self.ticker = ticker.upper()
        self.session = session
        self._history = None
        self._history_metadata = None
        self._base_url = _BASE_URL_
        self._scrape_url = _SCRAPE_URL_
        self._tz = None

        self._isin = None
        self._news = []
        self._shares = None

        self._earnings_dates = {}

        self._earnings = None
        self._financials = None

        # accept isin as ticker
        if utils.is_isin(self.ticker):
            self.ticker = utils.get_ticker_by_isin(self.ticker, None, session)

        self._data: TickerData = TickerData(self.ticker, session=session)

        self._analysis = Analysis(self._data)
        self._holders = Holders(self._data)
        self._quote = Quote(self._data)
        self._fundamentals = Fundamentals(self._data)

        self._basic_info = BasicInfo(self)

    def stats(self, proxy=None):
        ticker_url = "{}/{}".format(self._scrape_url, self.ticker)

        # get info and sustainability
        data = self._data.get_json_data_stores(proxy=proxy)["QuoteSummaryStore"]
        return data

    def history(self, period="1mo", interval="1d",
                start=None, end=None, prepost=False, actions=True,
                auto_adjust=True, back_adjust=False, repair=False, keepna=False,
                proxy=None, rounding=False, timeout=10,
                debug=True, raise_errors=False) -> pd.DataFrame:
        """
        :Parameters:
            period : str
                Valid periods: 1d,5d,1mo,3mo,6mo,1y,2y,5y,10y,ytd,max
                Either Use period parameter or use start and end
            interval : str
                Valid intervals: 1m,2m,5m,15m,30m,60m,90m,1h,1d,5d,1wk,1mo,3mo
                Intraday data cannot extend last 60 days
            start: str
                Download start date string (YYYY-MM-DD) or _datetime.
                Default is 1900-01-01
            end: str
                Download end date string (YYYY-MM-DD) or _datetime.
                Default is now
            prepost : bool
                Include Pre and Post market data in results?
                Default is False
            auto_adjust: bool
                Adjust all OHLC automatically? Default is True
            back_adjust: bool
                Back-adjusted data to mimic true historical prices
            repair: bool
                Detect currency unit 100x mixups and attempt repair
                Default is False
            keepna: bool
                Keep NaN rows returned by Yahoo?
                Default is False
            proxy: str
                Optional. Proxy server URL scheme. Default is None
            rounding: bool
                Round values to 2 decimal places?
                Optional. Default is False = precision suggested by Yahoo!
            timeout: None or float
                If not None stops waiting for a response after given number of
                seconds. (Can also be a fraction of a second e.g. 0.01)
                Default is 10 seconds.
            debug: bool
                If passed as False, will suppress
                error message printing to console.
            raise_errors: bool
                If True, then raise errors as
                exceptions instead of printing to console.
        """

        if start or period is None or period.lower() == "max":
            # Check can get TZ. Fail => probably delisted
            tz = self._get_ticker_tz(debug, proxy, timeout)
            if tz is None:
                # Every valid ticker has a timezone. Missing = problem
                err_msg = "No timezone found, symbol may be delisted"
                shared._DFS[self.ticker] = utils.empty_df()
                shared._ERRORS[self.ticker] = err_msg
                if debug:
                    if raise_errors:
                        raise Exception('%s: %s' % (self.ticker, err_msg))
                    else:
                        print('- %s: %s' % (self.ticker, err_msg))
                return utils.empty_df()

            if end is None:
                end = int(_time.time())
            else:
                end = utils._parse_user_dt(end, tz)
            if start is None:
                if interval == "1m":
                    start = end - 604800  # Subtract 7 days
                else:
                    _UNIX_TIMESTAMP_1900 = -2208994789
                    start = _UNIX_TIMESTAMP_1900
            else:
                start = utils._parse_user_dt(start, tz)
            params = {"period1": start, "period2": end}
        else:
            period = period.lower()
            params = {"range": period}

        params["interval"] = interval.lower()
        params["includePrePost"] = prepost

        # 1) fix weired bug with Yahoo! - returning 60m for 30m bars
        if params["interval"] == "30m":
            params["interval"] = "15m"

        # setup proxy in requests format
        if proxy is not None:
            if isinstance(proxy, dict) and "https" in proxy:
                proxy = proxy["https"]
            proxy = {"https": proxy}

        #if the ticker is MUTUALFUND or ETF, then get capitalGains events
        params["events"] = "div,splits,capitalGains"

        # Getting data from json
        url = "{}/v8/finance/chart/{}".format(self._base_url, self.ticker)

        data = None

        try:
            get_fn = self._data.get
            if end is not None:
                end_dt = _pd.Timestamp(end, unit='s').tz_localize("UTC")
                dt_now = end_dt.tzinfo.localize(_datetime.datetime.utcnow())
                data_delay = _datetime.timedelta(minutes=30)
                if end_dt+data_delay <= dt_now:
                    # Date range in past so safe to fetch through cache:
                    get_fn = self._data.cache_get
            data = get_fn(
                url=url,
                params=params,
                timeout=timeout
            )
            if "Will be right back" in data.text or data is None:
                raise RuntimeError("*** YAHOO! FINANCE IS CURRENTLY DOWN! ***\n"
                                   "Our engineers are working quickly to resolve "
                                   "the issue. Thank you for your patience.")

            data = data.json()
        except Exception:
            pass

        # Store the meta data that gets retrieved simultaneously
        try:
            self._history_metadata = data["chart"]["result"][0]["meta"]
        except Exception:
            self._history_metadata = {}

        err_msg = "No data found for this date range, symbol may be delisted"
        fail = False
        if data is None or not type(data) is dict:
            fail = True
        elif type(data) is dict and 'status_code' in data:
            err_msg += "(Yahoo status_code = {})".format(data["status_code"])
            fail = True
        elif "chart" in data and data["chart"]["error"]:
            err_msg = data["chart"]["error"]["description"]
            fail = True
        elif "chart" not in data or data["chart"]["result"] is None or not data["chart"]["result"]:
            fail = True
        elif period is not None and "timestamp" not in data["chart"]["result"][0] and period not in \
                self._history_metadata["validRanges"]:
            # User provided a bad period. The minimum should be '1d', but sometimes Yahoo accepts '1h'.
            err_msg = "Period '{}' is invalid, must be one of {}".format(period, self._history_metadata[
                "validRanges"])
            fail = True
        if fail:
            shared._DFS[self.ticker] = utils.empty_df()
            shared._ERRORS[self.ticker] = err_msg
            if debug:
                if raise_errors:
                    raise Exception('%s: %s' % (self.ticker, err_msg))
                else:
                    print('%s: %s' % (self.ticker, err_msg))
            return utils.empty_df()
        
        # parse quotes
        try:
            quotes = utils.parse_quotes(data["chart"]["result"][0])
            # Yahoo bug fix - it often appends latest price even if after end date
            if end and not quotes.empty:
                endDt = _pd.to_datetime(_datetime.datetime.utcfromtimestamp(end))
                if quotes.index[quotes.shape[0] - 1] >= endDt:
                    quotes = quotes.iloc[0:quotes.shape[0] - 1]
        except Exception:
            shared._DFS[self.ticker] = utils.empty_df()
            shared._ERRORS[self.ticker] = err_msg
            if debug:
                if raise_errors:
                    raise Exception('%s: %s' % (self.ticker, err_msg))
                else:
                    print('%s: %s' % (self.ticker, err_msg))
            return shared._DFS[self.ticker]

        # 2) fix weired bug with Yahoo! - returning 60m for 30m bars
        if interval.lower() == "30m":
            quotes2 = quotes.resample('30T')
            quotes = _pd.DataFrame(index=quotes2.last().index, data={
                'Open': quotes2['Open'].first(),
                'High': quotes2['High'].max(),
                'Low': quotes2['Low'].min(),
                'Close': quotes2['Close'].last(),
                'Adj Close': quotes2['Adj Close'].last(),
                'Volume': quotes2['Volume'].sum()
            })
            try:
                quotes['Dividends'] = quotes2['Dividends'].max()
            except Exception:
                pass
            try:
                quotes['Stock Splits'] = quotes2['Dividends'].max()
            except Exception:
                pass

        # Select useful info from metadata
        quote_type = self._history_metadata["instrumentType"]
        expect_capital_gains = quote_type in ('MUTUALFUND', 'ETF')
        tz_exchange = self._history_metadata["exchangeTimezoneName"]

        # Note: ordering is important. If you change order, run the tests!
        quotes = utils.set_df_tz(quotes, params["interval"], tz_exchange)
        quotes = utils.fix_Yahoo_dst_issue(quotes, params["interval"])
        quotes = utils.fix_Yahoo_returning_live_separate(quotes, params["interval"], tz_exchange)

        # actions
        dividends, splits, capital_gains = utils.parse_actions(data["chart"]["result"][0])
        if not expect_capital_gains:
            capital_gains = None

        if start is not None:
            # Note: use pandas Timestamp as datetime.utcfromtimestamp has bugs on windows
            # https://github.com/python/cpython/issues/81708
            startDt = _pd.Timestamp(start, unit='s')
            if dividends is not None:
                dividends = dividends[dividends.index>=startDt]
            if capital_gains is not None:
                capital_gains = capital_gains[capital_gains.index>=startDt]
            if splits is not None:
                splits = splits[splits.index >= startDt]
        if end is not None:
            endDt = _pd.Timestamp(end, unit='s')
            if dividends is not None:
                dividends = dividends[dividends.index<endDt]
            if capital_gains is not None:
                capital_gains = capital_gains[capital_gains.index<endDt]
            if splits is not None:
                splits = splits[splits.index < endDt]
        if splits is not None:
            splits = utils.set_df_tz(splits, interval, tz_exchange)
        if dividends is not None:
            dividends = utils.set_df_tz(dividends, interval, tz_exchange)
        if capital_gains is not None:
            capital_gains = utils.set_df_tz(capital_gains, interval, tz_exchange)

        # Prepare for combine
        intraday = params["interval"][-1] in ("m", 'h')
        if not intraday:
            # If localizing a midnight during DST transition hour when clocks roll back,
            # meaning clock hits midnight twice, then use the 2nd (ambiguous=True)
            quotes.index = _pd.to_datetime(quotes.index.date).tz_localize(tz_exchange, ambiguous=True, nonexistent='shift_forward')
            if dividends.shape[0] > 0:
                dividends.index = _pd.to_datetime(dividends.index.date).tz_localize(tz_exchange, ambiguous=True, nonexistent='shift_forward')
            if splits.shape[0] > 0:
                splits.index = _pd.to_datetime(splits.index.date).tz_localize(tz_exchange, ambiguous=True, nonexistent='shift_forward')

        # Combine
        df = quotes.sort_index()
        if dividends.shape[0] > 0:
            df = utils.safe_merge_dfs(df, dividends, interval)
        if "Dividends" in df.columns:
            df.loc[df["Dividends"].isna(), "Dividends"] = 0
        else:
            df["Dividends"] = 0.0
        if splits.shape[0] > 0:
            df = utils.safe_merge_dfs(df, splits, interval)
        if "Stock Splits" in df.columns:
            df.loc[df["Stock Splits"].isna(), "Stock Splits"] = 0
        else:
            df["Stock Splits"] = 0.0
        if expect_capital_gains:
            if capital_gains.shape[0] > 0:
                df = utils.safe_merge_dfs(df, capital_gains, interval)
            if "Capital Gains" in df.columns:
                df.loc[df["Capital Gains"].isna(),"Capital Gains"] = 0
            else:
                df["Capital Gains"] = 0.0

        if repair:
            # Do this before auto/back adjust
            df = self._fix_zeroes(df, interval, tz_exchange)
            df = self._fix_unit_mixups(df, interval, tz_exchange)

        # Auto/back adjust
        try:
            if auto_adjust:
                df = utils.auto_adjust(df)
            elif back_adjust:
                df = utils.back_adjust(df)
        except Exception as e:
            if auto_adjust:
                err_msg = "auto_adjust failed with %s" % e
            else:
                err_msg = "back_adjust failed with %s" % e
            shared._DFS[self.ticker] = utils.empty_df()
            shared._ERRORS[self.ticker] = err_msg
            if debug:
                if raise_errors:
                    raise Exception('%s: %s' % (self.ticker, err_msg))
                else:
                    print('%s: %s' % (self.ticker, err_msg))

        if rounding:
            df = _np.round(df, data[
                "chart"]["result"][0]["meta"]["priceHint"])
        df['Volume'] = df['Volume'].fillna(0).astype(_np.int64)

        if intraday:
            df.index.name = "Datetime"
        else:
            df.index.name = "Date"

        # duplicates and missing rows cleanup
        df = df[~df.index.duplicated(keep='first')]
        self._history = df.copy()
        if not actions:
            df = df.drop(columns=["Dividends", "Stock Splits", "Capital Gains"], errors='ignore')
        if not keepna:
            mask_nan_or_zero = (df.isna() | (df == 0)).all(axis=1)
            df = df.drop(mask_nan_or_zero.index[mask_nan_or_zero])

        return df

    # ------------------------

    def _reconstruct_intervals_batch(self, df, interval, tag=-1):
        if not isinstance(df, _pd.DataFrame):
            raise Exception("'df' must be a Pandas DataFrame not", type(df))

        # Reconstruct values in df using finer-grained price data. Delimiter marks what to reconstruct

        price_cols = [c for c in ["Open", "High", "Low", "Close", "Adj Close"] if c in df]
        data_cols = price_cols + ["Volume"]

        # If interval is weekly then can construct with daily. But if smaller intervals then
        # restricted to recent times:
        # - daily = hourly restricted to last 730 days
        sub_interval = None
        td_range = None
        if interval == "1wk":
            # Correct by fetching week of daily data
            sub_interval = "1d"
            td_range = _datetime.timedelta(days=7)
        elif interval == "1d":
            # Correct by fetching day of hourly data
            sub_interval = "1h"
            td_range = _datetime.timedelta(days=1)
        elif interval == "1h":
            sub_interval = "30m"
            td_range = _datetime.timedelta(hours=1)
        else:
            print("WARNING: Have not implemented repair for '{}' interval. Contact developers".format(interval))
            raise Exception("why here")
            return df

        df = df.sort_index()

        f_repair = df[data_cols].to_numpy()==tag
        f_repair_rows = f_repair.any(axis=1)

        # Ignore old intervals for which Yahoo won't return finer data:
        if sub_interval == "1h":
            f_recent = _datetime.date.today() - df.index.date < _datetime.timedelta(days=730)
            f_repair_rows = f_repair_rows & f_recent
        elif sub_interval in ["30m", "15m"]:
            f_recent = _datetime.date.today() - df.index.date < _datetime.timedelta(days=60)
            f_repair_rows = f_repair_rows & f_recent
        if not f_repair_rows.any():
            print("data too old to fix")
            return df

        dts_to_repair = df.index[f_repair_rows]
        indices_to_repair = _np.where(f_repair_rows)[0]

        if len(dts_to_repair) == 0:
            return df

        df_v2 = df.copy()
        df_noNa = df[~df[price_cols].isna().any(axis=1)]

        # Group nearby NaN-intervals together to reduce number of Yahoo fetches
        dts_groups = [[dts_to_repair[0]]]
        last_dt = dts_to_repair[0]
        last_ind = indices_to_repair[0]
        td = utils._interval_to_timedelta(interval)
        if interval == "1mo":
            grp_td_threshold = _datetime.timedelta(days=28)
        elif interval == "1wk":
            grp_td_threshold = _datetime.timedelta(days=28)
        elif interval == "1d":
            grp_td_threshold = _datetime.timedelta(days=14)
        elif interval == "1h":
            grp_td_threshold = _datetime.timedelta(days=7)
        else:
            grp_td_threshold = _datetime.timedelta(days=2)
            # grp_td_threshold = _datetime.timedelta(days=7)
        for i in range(1, len(dts_to_repair)):
            ind = indices_to_repair[i]
            dt = dts_to_repair[i]
            if (dt-dts_groups[-1][-1]) < grp_td_threshold:
                dts_groups[-1].append(dt)
            elif ind - last_ind <= 3:
                dts_groups[-1].append(dt)
            else:
                dts_groups.append([dt])
            last_dt = dt
            last_ind = ind

        # Add some good data to each group, so can calibrate later:
        for i in range(len(dts_groups)):
            g = dts_groups[i]
            g0 = g[0]
            i0 = df_noNa.index.get_loc(g0)
            if i0 > 0:
                dts_groups[i].insert(0, df_noNa.index[i0-1])
            gl = g[-1]
            il = df_noNa.index.get_loc(gl)
            if il < len(df_noNa)-1:
                dts_groups[i].append(df_noNa.index[il+1])

        n_fixed = 0
        for g in dts_groups:
            df_block = df[df.index.isin(g)]

            start_dt = g[0]
            start_d = start_dt.date()
            if sub_interval == "1h" and (_datetime.date.today() - start_d) > _datetime.timedelta(days=729):
                # Don't bother requesting more price data, Yahoo will reject
                continue
            elif sub_interval in ["30m", "15m"] and (_datetime.date.today() - start_d) > _datetime.timedelta(days=59):
                # Don't bother requesting more price data, Yahoo will reject
                continue

            td_1d = _datetime.timedelta(days=1)
            if interval in "1wk":
                fetch_start = start_d - td_range  # need previous week too
                fetch_end = g[-1].date() + td_range
            elif interval == "1d":
                fetch_start = start_d
                fetch_end = g[-1].date() + td_range
            else:
                fetch_start = g[0]
                fetch_end = g[-1] + td_range

            prepost = interval == "1d"
            df_fine = self.history(start=fetch_start, end=fetch_end, interval=sub_interval, auto_adjust=False, prepost=prepost, repair=False, keepna=True)
            if df_fine is None or df_fine.empty:
                print("YF: WARNING: Cannot reconstruct because Yahoo not returning data in interval")
                continue

            df_fine["ctr"] = 0
            if interval == "1wk":
                # df_fine["Week Start"] = df_fine.index.tz_localize(None).to_period("W-SUN").start_time
                weekdays = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
                week_end_day = weekdays[(df_block.index[0].weekday()+7-1)%7]
                df_fine["Week Start"] = df_fine.index.tz_localize(None).to_period("W-"+week_end_day).start_time
                grp_col = "Week Start"
            elif interval == "1d":
                df_fine["Day Start"] = pd.to_datetime(df_fine.index.date)
                grp_col = "Day Start"
            else:
                df_fine.loc[df_fine.index.isin(df_block.index), "ctr"] = 1
                df_fine["intervalID"] = df_fine["ctr"].cumsum()
                df_fine = df_fine.drop("ctr", axis=1)
                grp_col = "intervalID"
            df_fine = df_fine[~df_fine[price_cols].isna().all(axis=1)]

            df_new = df_fine.groupby(grp_col).agg(
                Open=("Open", "first"),
                Close=("Close", "last"),
                AdjClose=("Adj Close", "last"),
                Low=("Low", "min"),
                High=("High", "max"),
                Volume=("Volume", "sum")).rename(columns={"AdjClose":"Adj Close"})
            if grp_col in ["Week Start", "Day Start"]:
                df_new.index = df_new.index.tz_localize(df_fine.index.tz)
            else:
                df_fine["diff"] = df_fine["intervalID"].diff()
                new_index = _np.append([df_fine.index[0]], df_fine.index[df_fine["intervalID"].diff()>0])
                df_new.index = new_index

            # Calibrate! Check whether 'df_fine' has different split-adjustment.
            # If different, then adjust to match 'df'
            df_block_calib = df_block[price_cols]
            common_index = df_block_calib.index[df_block_calib.index.isin(df_new.index)]
            if len(common_index) == 0:
                # Can't calibrate so don't attempt repair
                continue
            df_new_calib = df_new[df_new.index.isin(common_index)][price_cols]
            df_block_calib = df_block_calib[df_block_calib.index.isin(common_index)]
            calib_filter = (df_block_calib != tag).to_numpy()
            if not calib_filter.any():
                # Can't calibrate so don't attempt repair
                continue
            # Avoid divide-by-zero warnings printing:
            df_new_calib = df_new_calib.to_numpy()
            df_block_calib = df_block_calib.to_numpy()
            for j in range(len(price_cols)):
                c = price_cols[j]
                f = ~calib_filter[:,j]
                if f.any():
                    df_block_calib[f,j] = 1
                    df_new_calib[f,j] = 1
            ratios = (df_block_calib / df_new_calib)[calib_filter]
            ratio = _np.mean(ratios)
            #
            ratio_rcp = round(1.0 / ratio, 1)
            ratio = round(ratio, 1)
            if ratio == 1 and ratio_rcp == 1:
                # Good!
                pass
            else:
                if ratio > 1:
                    # data has different split-adjustment than fine-grained data
                    # Adjust fine-grained to match
                    df_new[price_cols] *= ratio
                    df_new["Volume"] /= ratio
                elif ratio_rcp > 1:
                    # data has different split-adjustment than fine-grained data
                    # Adjust fine-grained to match
                    df_new[price_cols] *= 1.0 / ratio_rcp
                    df_new["Volume"] *= ratio_rcp

            # Repair!
            bad_dts = df_block.index[(df_block[price_cols]==tag).any(axis=1)]

            for idx in bad_dts:
                if not idx in df_new.index:
                    # Yahoo didn't return finer-grain data for this interval, 
                    # so probably no trading happened.
                    # print("no fine data")
                    continue
                df_new_row = df_new.loc[idx]

                if interval == "1wk":
                    df_last_week = df_new.iloc[df_new.index.get_loc(idx)-1]
                    df_fine = df_fine.loc[idx:]

                df_bad_row = df.loc[idx]
                bad_fields = df_bad_row.index[df_bad_row==tag].values
                if "High" in bad_fields:
                    df_v2.loc[idx, "High"] = df_new_row["High"]
                if "Low" in bad_fields:
                    df_v2.loc[idx, "Low"] = df_new_row["Low"]
                if "Open" in bad_fields:
                    if interval == "1wk" and idx != df_fine.index[0]:
                        # Exchange closed Monday. In this case, Yahoo sets Open to last week close
                        df_v2.loc[idx, "Open"] = df_last_week["Close"]
                        df_v2.loc[idx, "Low"] = min(df_v2.loc[idx, "Open"], df_v2.loc[idx, "Low"])
                    else:
                        df_v2.loc[idx, "Open"] = df_new_row["Open"]
                if "Close" in bad_fields:
                    df_v2.loc[idx, "Close"] = df_new_row["Close"]
                    # Assume 'Adj Close' also corrupted, easier than detecting whether true
                    df_v2.loc[idx, "Adj Close"] = df_new_row["Adj Close"]
                if "Volume" in bad_fields:
                    df_v2.loc[idx, "Volume"] = df_new_row["Volume"]
                n_fixed += 1

        return df_v2

    def _fix_unit_mixups(self, df, interval, tz_exchange):
        # Sometimes Yahoo returns few prices in cents/pence instead of $/£
        # I.e. 100x bigger
        # Easy to detect and fix, just look for outliers = ~100x local median

        if df.shape[0] == 0:
            return df
        if df.shape[0] == 1:
            # Need multiple rows to confidently identify outliers
            return df

        df2 = df.copy()

        if df.index.tz is None:
            df2.index = df2.index.tz_localize(tz_exchange)
        else:
            df2.index = df2.index.tz_convert(tz_exchange)

        # Only import scipy if users actually want function. To avoid
        # adding it to dependencies.
        from scipy import ndimage as _ndimage

        data_cols = ["High", "Open", "Low", "Close"]  # Order important, separate High from Low
        data_cols = [c for c in data_cols if c in df2.columns]
        f_zeroes = (df2[data_cols]==0).any(axis=1)
        if f_zeroes.any():
            df2_zeroes = df2[f_zeroes]
            df2 = df2[~f_zeroes]
        else:
            df2_zeroes = None
        if df2.shape[0] <= 1:
            return df
        median = _ndimage.median_filter(df2[data_cols].values, size=(3, 3), mode="wrap")
        ratio = df2[data_cols].values / median
        ratio_rounded = (ratio / 20).round() * 20  # round ratio to nearest 20
        f = ratio_rounded == 100
        if not f.any():
            return df

        # Mark values to send for repair
        tag = -1.0
        for i in range(len(data_cols)):
            fi = f[:,i]
            c = data_cols[i]
            df2.loc[fi, c] = tag

        n_before = (df2[data_cols].to_numpy()==tag).sum()
        df2 = self._reconstruct_intervals_batch(df2, interval, tag=tag)
        n_after = (df2[data_cols].to_numpy()==tag).sum()

        if n_after > 0:
            # This second pass will *crudely* "fix" any remaining errors in High/Low
            # simply by ensuring they don't contradict e.g. Low = 100x High.
            f = df2[data_cols].to_numpy()==tag
            for i in range(f.shape[0]):
                fi = f[i,:]
                if not fi.any():
                    continue
                idx = df2.index[i]

                c = "Open"
                j = data_cols.index(c)
                if fi[j]:
                    df2.loc[idx, c] = df.loc[idx, c] * 0.01
                #
                c = "Close"
                j = data_cols.index(c)
                if fi[j]:
                    df2.loc[idx, c] = df.loc[idx, c] * 0.01
                #
                c = "High"
                j = data_cols.index(c)
                if fi[j]:
                    df2.loc[idx, c] = df2.loc[idx, ["Open", "Close"]].max()
                #
                c = "Low"
                j = data_cols.index(c)
                if fi[j]:
                    df2.loc[idx, c] = df2.loc[idx, ["Open", "Close"]].min()

        n_after_crude = (df2[data_cols].to_numpy()==tag).sum()

        n_fixed = n_before - n_after_crude
        n_fixed_crudely = n_after - n_after_crude
        if n_fixed > 0:
            report_msg = f"{self.ticker}: fixed {n_fixed}/{n_before} currency unit mixups "
            if n_fixed_crudely > 0:
                report_msg += f"({n_fixed_crudely} crudely) "
            report_msg += f"in {interval} price data"
            print(report_msg)

        # Restore original values where repair failed
        f = df2[data_cols].values==tag
        for j in range(len(data_cols)):
            fj = f[:,j]
            if fj.any():
                c = data_cols[j]
                df2.loc[fj, c] = df.loc[fj, c]
        if df2_zeroes is not None:
            df2 = _pd.concat([df2, df2_zeroes]).sort_index()
            df2.index = _pd.to_datetime()

        return df2

    def _fix_zeroes(self, df, interval, tz_exchange):
        # Sometimes Yahoo returns prices=0 or NaN when trades occurred.
        # But most times when prices=0 or NaN returned is because no trades.
        # Impossible to distinguish, so only attempt repair if few or rare.

        if df.shape[0] == 0:
            return df

        df2 = df.copy()

        if df2.index.tz is None:
            df2.index = df2.index.tz_localize(tz_exchange)
        else:
            df2.index = df2.index.tz_convert(tz_exchange)

        price_cols = [c for c in ["Open", "High", "Low", "Close", "Adj Close"] if c in df2.columns]
        f_zero_or_nan = (df2[price_cols] == 0.0).values | df2[price_cols].isna().values
        # Check whether worth attempting repair
        if f_zero_or_nan.any(axis=1).sum() == 0:
            return df
        if f_zero_or_nan.sum() == len(price_cols)*len(df2):
            # Need some good data to calibrate
            return df
        # - avoid repair if many zeroes/NaNs
        pct_zero_or_nan = f_zero_or_nan.sum() / (len(price_cols)*len(df2))
        if f_zero_or_nan.any(axis=1).sum()>2 and pct_zero_or_nan > 0.05:
            return df

        data_cols = price_cols + ["Volume"]

        # Mark values to send for repair
        tag = -1.0
        for i in range(len(price_cols)):
            c = price_cols[i]
            df2.loc[f_zero_or_nan[:,i], c] = tag
        # If volume=0 or NaN for bad prices, then tag volume for repair
        df2.loc[f_zero_or_nan.any(axis=1) & (df2["Volume"]==0), "Volume"] = tag
        df2.loc[f_zero_or_nan.any(axis=1) & (df2["Volume"].isna()), "Volume"] = tag

        n_before = (df2[data_cols].to_numpy()==tag).sum()
        df2 = self._reconstruct_intervals_batch(df2, interval, tag=tag)
        n_after = (df2[data_cols].to_numpy()==tag).sum()
        n_fixed = n_before - n_after
        if n_fixed > 0:
            print("{}: fixed {} price=0.0 errors in {} price data".format(self.ticker, n_fixed, interval))

        # Restore original values where repair failed (i.e. remove tag values)
        f = df2[data_cols].values==tag
        for j in range(len(data_cols)):
            fj = f[:,j]
            if fj.any():
                c = data_cols[j]
                df2.loc[fj, c] = df.loc[fj, c]

        return df2

    def _get_ticker_tz(self, debug_mode, proxy, timeout):
        if self._tz is not None:
            return self._tz
        cache = utils.get_tz_cache()
        tz = cache.lookup(self.ticker)

        if tz and not utils.is_valid_timezone(tz):
            # Clear from cache and force re-fetch
            cache.store(self.ticker, None)
            tz = None

        if tz is None:
            tz = self._fetch_ticker_tz(debug_mode, proxy, timeout)

            if utils.is_valid_timezone(tz):
                # info fetch is relatively slow so cache timezone
                cache.store(self.ticker, tz)
            else:
                tz = None

        self._tz = tz
        return tz

    def _fetch_ticker_tz(self, debug_mode, proxy, timeout):
        # Query Yahoo for basic price data just to get returned timezone

        params = {"range": "1d", "interval": "1d"}

        # Getting data from json
        url = "{}/v8/finance/chart/{}".format(self._base_url, self.ticker)

        try:
            data = self._data.cache_get(url=url, params=params, proxy=proxy, timeout=timeout)
            data = data.json()
        except Exception as e:
            if debug_mode:
                print("Failed to get ticker '{}' reason: {}".format(self.ticker, e))
            return None
        else:
            error = data.get('chart', {}).get('error', None)
            if error:
                # explicit error from yahoo API
                if debug_mode:
                    print("Got error from yahoo api for ticker {}, Error: {}".format(self.ticker, error))
            else:
                try:
                    return data["chart"]["result"][0]["meta"]["exchangeTimezoneName"]
                except Exception as err:
                    if debug_mode:
                        print("Could not get exchangeTimezoneName for ticker '{}' reason: {}".format(self.ticker, err))
                        print("Got response: ")
                        print("-------------")
                        print(" {}".format(data))
                        print("-------------")
        return None

    def get_recommendations(self, proxy=None, as_dict=False):
        self._quote.proxy = proxy
        data = self._quote.recommendations
        if as_dict:
            return data.to_dict()
        return data

    def get_calendar(self, proxy=None, as_dict=False):
        self._quote.proxy = proxy
        data = self._quote.calendar
        if as_dict:
            return data.to_dict()
        return data

    def get_major_holders(self, proxy=None, as_dict=False):
        self._holders.proxy = proxy
        data = self._holders.major
        if as_dict:
            return data.to_dict()
        return data

    def get_institutional_holders(self, proxy=None, as_dict=False):
        self._holders.proxy = proxy
        data = self._holders.institutional
        if data is not None:
            if as_dict:
                return data.to_dict()
            return data

    def get_mutualfund_holders(self, proxy=None, as_dict=False):
        self._holders.proxy = proxy
        data = self._holders.mutualfund
        if data is not None:
            if as_dict:
                return data.to_dict()
            return data

    def get_info(self, proxy=None) -> dict:
        self._quote.proxy = proxy
        data = self._quote.info
        return data

    @property
    def basic_info(self):
        return self._basic_info

    def get_sustainability(self, proxy=None, as_dict=False):
        self._quote.proxy = proxy
        data = self._quote.sustainability
        if as_dict:
            return data.to_dict()
        return data

    def get_recommendations_summary(self, proxy=None, as_dict=False):
        self._quote.proxy = proxy
        data = self._quote.recommendations
        if as_dict:
            return data.to_dict()
        return data

    def get_analyst_price_target(self, proxy=None, as_dict=False):
        self._analysis.proxy = proxy
        data = self._analysis.analyst_price_target
        if as_dict:
            return data.to_dict()
        return data

    def get_rev_forecast(self, proxy=None, as_dict=False):
        self._analysis.proxy = proxy
        data = self._analysis.rev_est
        if as_dict:
            return data.to_dict()
        return data

    def get_earnings_forecast(self, proxy=None, as_dict=False):
        self._analysis.proxy = proxy
        data = self._analysis.eps_est
        if as_dict:
            return data.to_dict()
        return data

    def get_trend_details(self, proxy=None, as_dict=False):
        self._analysis.proxy = proxy
        data = self._analysis.analyst_trend_details
        if as_dict:
            return data.to_dict()
        return data

    def get_earnings_trend(self, proxy=None, as_dict=False):
        self._analysis.proxy = proxy
        data = self._analysis.earnings_trend
        if as_dict:
            return data.to_dict()
        return data

    def get_earnings(self, proxy=None, as_dict=False, freq="yearly"):
        """
        :Parameters:
            as_dict: bool
                Return table as Python dict
                Default is False
            freq: str
                "yearly" or "quarterly"
                Default is "yearly"
            proxy: str
                Optional. Proxy server URL scheme
                Default is None
        """
        self._fundamentals.proxy = proxy
        data = self._fundamentals.earnings[freq]
        if as_dict:
            dict_data = data.to_dict()
            dict_data['financialCurrency'] = 'USD' if 'financialCurrency' not in self._earnings else self._earnings[
                'financialCurrency']
            return dict_data
        return data

    def get_income_stmt(self, proxy=None, as_dict=False, pretty=False, freq="yearly", legacy=False):
        """
        :Parameters:
            as_dict: bool
                Return table as Python dict
                Default is False
            pretty: bool
                Format row names nicely for readability
                Default is False
            freq: str
                "yearly" or "quarterly"
                Default is "yearly"
            legacy: bool
                Return old financials tables. Useful for when new tables not available
                Default is False
            proxy: str
                Optional. Proxy server URL scheme
                Default is None
        """
        self._fundamentals.proxy = proxy

        if legacy:
            data = self._fundamentals.financials.get_income_scrape(freq=freq, proxy=proxy)
        else:
            data = self._fundamentals.financials.get_income_time_series(freq=freq, proxy=proxy)
            
        if pretty:
            data = data.copy()
            data.index = utils.camel2title(data.index, sep=' ', acronyms=["EBIT", "EBITDA", "EPS", "NI"])
        if as_dict:
            return data.to_dict()
        return data

    def get_incomestmt(self, proxy=None, as_dict=False, pretty=False, freq="yearly", legacy=False):
        return self.get_income_stmt(proxy, as_dict, pretty, freq, legacy)

    def get_financials(self, proxy=None, as_dict=False, pretty=False, freq="yearly", legacy=False):
        return self.get_income_stmt(proxy, as_dict, pretty, freq, legacy)

    def get_balance_sheet(self, proxy=None, as_dict=False, pretty=False, freq="yearly", legacy=False):
        """
        :Parameters:
            as_dict: bool
                Return table as Python dict
                Default is False
            pretty: bool
                Format row names nicely for readability
                Default is False
            freq: str
                "yearly" or "quarterly"
                Default is "yearly"
            legacy: bool
                Return old financials tables. Useful for when new tables not available
                Default is False
            proxy: str
                Optional. Proxy server URL scheme
                Default is None
        """
        self._fundamentals.proxy = proxy

        if legacy:
            data = self._fundamentals.financials.get_balance_sheet_scrape(freq=freq, proxy=proxy)
        else:
            data = self._fundamentals.financials.get_balance_sheet_time_series(freq=freq, proxy=proxy)

        if pretty:
            data = data.copy()
            data.index = utils.camel2title(data.index, sep=' ', acronyms=["PPE"])
        if as_dict:
            return data.to_dict()
        return data

    def get_balancesheet(self, proxy=None, as_dict=False, pretty=False, freq="yearly", legacy=False):
        return self.get_balance_sheet(proxy, as_dict, pretty, freq, legacy)

    def get_cash_flow(self, proxy=None, as_dict=False, pretty=False, freq="yearly", legacy=False):
        """
        :Parameters:
            as_dict: bool
                Return table as Python dict
                Default is False
            pretty: bool
                Format row names nicely for readability
                Default is False
            freq: str
                "yearly" or "quarterly"
                Default is "yearly"
            legacy: bool
                Return old financials tables. Useful for when new tables not available
                Default is False
            proxy: str
                Optional. Proxy server URL scheme
                Default is None
        """
        self._fundamentals.proxy = proxy

        if legacy:
            data = self._fundamentals.financials.get_cash_flow_scrape(freq=freq, proxy=proxy)
        else:
            data = self._fundamentals.financials.get_cash_flow_time_series(freq=freq, proxy=proxy)

        if pretty:
            data = data.copy()
            data.index = utils.camel2title(data.index, sep=' ', acronyms=["PPE"])
        if as_dict:
            return data.to_dict()
        return data

    def get_cashflow(self, proxy=None, as_dict=False, pretty=False, freq="yearly", legacy=False):
        return self.get_cash_flow(proxy, as_dict, pretty, freq, legacy)

    def get_dividends(self, proxy=None):
        if self._history is None:
            self.history(period="max", proxy=proxy)
        if self._history is not None and "Dividends" in self._history:
            dividends = self._history["Dividends"]
            return dividends[dividends != 0]
        return []

    def get_capital_gains(self, proxy=None):
        if self._history is None:
            self.history(period="max", proxy=proxy)
        if self._history is not None and "Capital Gains" in self._history:
            capital_gains = self._history["Capital Gains"]
            return capital_gains[capital_gains != 0]
        return []

    def get_splits(self, proxy=None):
        if self._history is None:
            self.history(period="max", proxy=proxy)
        if self._history is not None and "Stock Splits" in self._history:
            splits = self._history["Stock Splits"]
            return splits[splits != 0]
        return []

    def get_actions(self, proxy=None):
        if self._history is None:
            self.history(period="max", proxy=proxy)
        if self._history is not None and "Dividends" in self._history and "Stock Splits" in self._history:
            action_columns = ["Dividends", "Stock Splits"]
            if "Capital Gains" in self._history:
                action_columns.append("Capital Gains")
            actions = self._history[action_columns]
            return actions[actions != 0].dropna(how='all').fillna(0)
        return []

    def get_shares(self, proxy=None, as_dict=False):
        self._fundamentals.proxy = proxy
        data = self._fundamentals.shares
        if as_dict:
            return data.to_dict()
        return data

    def get_shares_full(self, start=None, end=None, proxy=None):
        # Process dates
        tz = self._get_ticker_tz(debug_mode=False, proxy=None, timeout=10)
        dt_now = _pd.Timestamp.utcnow().tz_convert(tz)
        if start is not None:
            start_ts = utils._parse_user_dt(start, tz)
            start = _pd.Timestamp.fromtimestamp(start_ts).tz_localize("UTC").tz_convert(tz)
            start_d = start.date()
        if end is not None:
            end_ts = utils._parse_user_dt(end, tz)
            end = _pd.Timestamp.fromtimestamp(end_ts).tz_localize("UTC").tz_convert(tz)
            end_d = end.date()
        if end is None:
            end = dt_now
        if start is None:
            start = end - _pd.Timedelta(days=548)  # 18 months
        if start >= end:
            print("ERROR: start date must be before end")
            return None
        start = start.floor("D")
        end = end.ceil("D")
        
        # Fetch
        ts_url_base = "https://query2.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/{0}?symbol={0}".format(self.ticker)
        shares_url = ts_url_base + "&period1={}&period2={}".format(int(start.timestamp()), int(end.timestamp()))
        try:
            json_str = self._data.cache_get(shares_url).text
            json_data = _json.loads(json_str)
        except:
            print(f"{self.ticker}: Yahoo web request for share count failed")
            return None
        try:
            fail = json_data["finance"]["error"]["code"] == "Bad Request"
        except:
            fail = False
        if fail:
            print(f"{self.ticker}: Yahoo web request for share count failed")
            return None

        shares_data = json_data["timeseries"]["result"]
        if not "shares_out" in shares_data[0]:
            print(f"{self.ticker}: Yahoo did not return share count in date range {start} -> {end}")
            return None
        try:
            df = _pd.Series(shares_data[0]["shares_out"], index=_pd.to_datetime(shares_data[0]["timestamp"], unit="s"))
        except Exception as e:
            print(f"{self.ticker}: Failed to parse shares count data: "+str(e))
            return None

        df.index = df.index.tz_localize(tz)
        df = df.sort_index()
        return df

    def get_isin(self, proxy=None) -> Optional[str]:
        # *** experimental ***
        if self._isin is not None:
            return self._isin

        ticker = self.ticker.upper()

        if "-" in ticker or "^" in ticker:
            self._isin = '-'
            return self._isin

        q = ticker

        self._quote.proxy = proxy
        if self._quote.info is None:
            # Don't print error message cause self._quote.info will print one
            return None
        if "shortName" in self._quote.info:
            q = self._quote.info['shortName']

        url = 'https://markets.businessinsider.com/ajax/' \
              'SearchController_Suggest?max_results=25&query=%s' \
              % urlencode(q)
        data = self._data.cache_get(url=url, proxy=proxy).text

        search_str = '"{}|'.format(ticker)
        if search_str not in data:
            if q.lower() in data.lower():
                search_str = '"|'
                if search_str not in data:
                    self._isin = '-'
                    return self._isin
            else:
                self._isin = '-'
                return self._isin

        self._isin = data.split(search_str)[1].split('"')[0].split('|')[0]
        return self._isin

    def get_news(self, proxy=None):
        if self._news:
            return self._news

        # Getting data from json
        url = "{}/v1/finance/search?q={}".format(self._base_url, self.ticker)
        data = self._data.cache_get(url=url, proxy=proxy)
        if "Will be right back" in data.text:
            raise RuntimeError("*** YAHOO! FINANCE IS CURRENTLY DOWN! ***\n"
                               "Our engineers are working quickly to resolve "
                               "the issue. Thank you for your patience.")
        data = data.json()

        # parse news
        self._news = data.get("news", [])
        return self._news

    def get_earnings_dates(self, limit=12, proxy=None) -> Optional[pd.DataFrame]:
        """
        Get earning dates (future and historic)
        :param limit: max amount of upcoming and recent earnings dates to return.
                      Default value 12 should return next 4 quarters and last 8 quarters.
                      Increase if more history is needed.

        :param proxy: requests proxy to use.
        :return: pandas dataframe
        """
        if self._earnings_dates and limit in self._earnings_dates:
            return self._earnings_dates[limit]

        page_size = min(limit, 100)  # YF caps at 100, don't go higher
        page_offset = 0
        dates = None
        while True:
            url = "{}/calendar/earnings?symbol={}&offset={}&size={}".format(
                _ROOT_URL_, self.ticker, page_offset, page_size)

            data = self._data.cache_get(url=url, proxy=proxy).text

            if "Will be right back" in data:
                raise RuntimeError("*** YAHOO! FINANCE IS CURRENTLY DOWN! ***\n"
                                   "Our engineers are working quickly to resolve "
                                   "the issue. Thank you for your patience.")

            try:
                data = _pd.read_html(data)[0]
            except ValueError:
                if page_offset == 0:
                    # Should not fail on first page
                    if "Showing Earnings for:" in data:
                        # Actually YF was successful, problem is company doesn't have earnings history
                        dates = utils.empty_earnings_dates_df()
                break
            if dates is None:
                dates = data
            else:
                dates = _pd.concat([dates, data], axis=0)

            page_offset += page_size
            # got less data then we asked for or already fetched all we requested, no need to fetch more pages
            if len(data) < page_size or len(dates) >= limit:
                dates = dates.iloc[:limit]
                break
            else:
                # do not fetch more than needed next time
                page_size = min(limit - len(dates), page_size)

        if dates is None or dates.shape[0] == 0:
            err_msg = "No earnings dates found, symbol may be delisted"
            print('- %s: %s' % (self.ticker, err_msg))
            return None
        dates = dates.reset_index(drop=True)

        # Drop redundant columns
        dates = dates.drop(["Symbol", "Company"], axis=1)

        # Convert types
        for cn in ["EPS Estimate", "Reported EPS", "Surprise(%)"]:
            dates.loc[dates[cn] == '-', cn] = "NaN"
            dates[cn] = dates[cn].astype(float)

        # Convert % to range 0->1:
        dates["Surprise(%)"] *= 0.01

        # Parse earnings date string
        cn = "Earnings Date"
        # - remove AM/PM and timezone from date string
        tzinfo = dates[cn].str.extract('([AP]M[a-zA-Z]*)$')
        dates[cn] = dates[cn].replace(' [AP]M[a-zA-Z]*$', '', regex=True)
        # - split AM/PM from timezone
        tzinfo = tzinfo[0].str.extract('([AP]M)([a-zA-Z]*)', expand=True)
        tzinfo.columns = ["AM/PM", "TZ"]
        # - combine and parse
        dates[cn] = dates[cn] + ' ' + tzinfo["AM/PM"]
        dates[cn] = _pd.to_datetime(dates[cn], format="%b %d, %Y, %I %p")
        # - instead of attempting decoding of ambiguous timezone abbreviation, just use 'info':
        self._quote.proxy = proxy
        tz = self._get_ticker_tz(debug_mode=False, proxy=proxy, timeout=30)
        dates[cn] = dates[cn].dt.tz_localize(tz)

        dates = dates.set_index("Earnings Date")

        self._earnings_dates[limit] = dates

        return dates

    def get_history_metadata(self) -> dict:
        if self._history_metadata is None:
            raise RuntimeError("Metadata was never retrieved so far, "
                               "call history() to retrieve it")
        return self._history_metadata
