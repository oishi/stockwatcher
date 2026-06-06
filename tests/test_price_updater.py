"""price_updater.py の単体テスト。

外部 I/O（yfinance / requests）はモックし、ネットワークに依存しない
純粋ロジックを対象にする。実ネットワーク・実 GAS・実 yfinance は叩かない。
"""

import pandas as pd
import pytest

import price_updater


# --- format_ticker_symbol ---------------------------------------------------

def test_format_ticker_symbol_appends_suffix():
    assert price_updater.format_ticker_symbol("8098") == "8098.T"


def test_format_ticker_symbol_keeps_existing_suffix():
    assert price_updater.format_ticker_symbol("8098.T") == "8098.T"


# --- convert_to_json --------------------------------------------------------

@pytest.fixture
def sample_df():
    idx = pd.to_datetime(["2026-06-01", "2026-06-02"])
    return pd.DataFrame(
        {
            "open": [100.0, 110.0],
            "high": [105.0, 115.0],
            "low": [95.0, 108.0],
            "close": [102.0, 112.0],
            "volume": [1000, 2000],
        },
        index=idx,
    )


def test_convert_to_json_basic(sample_df):
    result = price_updater.convert_to_json({"2914.T": sample_df})

    assert "2914.T" in result
    rows = result["2914.T"]
    assert len(rows) == 2
    assert rows[0] == {
        "date": "2026-06-01",
        "open": 100.0,
        "high": 105.0,
        "low": 95.0,
        "close": 102.0,
    }
    # volume は送信ペイロードに含めない仕様であることを担保する
    assert "volume" not in rows[0]


def test_convert_to_json_drops_nan_rows(sample_df):
    df = sample_df.copy()
    df.loc[df.index[1], "close"] = float("nan")  # 2行目を欠損にする

    rows = price_updater.convert_to_json({"2914.T": df})["2914.T"]

    assert len(rows) == 1
    assert rows[0]["date"] == "2026-06-01"


def test_convert_to_json_excludes_ticker_with_no_valid_rows(sample_df):
    df = sample_df.copy()
    df[["open", "high", "low", "close"]] = float("nan")  # 全行欠損

    result = price_updater.convert_to_json({"2914.T": df})

    # 有効データが 1 件も無い銘柄は結果に含まれない
    assert "2914.T" not in result


# --- fetch_single_stock_data ------------------------------------------------

class _FakeTicker:
    def __init__(self, df):
        self._df = df

    def history(self, period):
        return self._df


def test_fetch_single_stock_data_standardizes_columns(monkeypatch):
    raw = pd.DataFrame(
        {
            "Open": [100.0],
            "High": [105.0],
            "Low": [95.0],
            "Close": [102.0],
            "Volume": [1000],
            "Dividends": [0.0],
            "Stock Splits": [0.0],
        },
        index=pd.to_datetime(["2026-06-01"]),
    )
    monkeypatch.setattr(price_updater.yf, "Ticker", lambda symbol: _FakeTicker(raw))

    df = price_updater.fetch_single_stock_data("2914", period="5d")

    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert df.iloc[0]["close"] == 102.0


def test_fetch_single_stock_data_raises_on_empty(monkeypatch):
    empty = pd.DataFrame()
    monkeypatch.setattr(price_updater.yf, "Ticker", lambda symbol: _FakeTicker(empty))

    # @retry でラップされているため、最終的に元例外が送出されることを確認する
    with pytest.raises(Exception):
        price_updater.fetch_single_stock_data("2914", period="5d")


# --- fetch_tickers_from_gas -------------------------------------------------

class _FakeResponse:
    def __init__(self, text, status_ok=True):
        self.text = text
        self._status_ok = status_ok

    def raise_for_status(self):
        if not self._status_ok:
            import requests
            raise requests.exceptions.HTTPError("error")

    def json(self):
        import json
        return json.loads(self.text)


def test_fetch_tickers_from_gas_parses_list(monkeypatch):
    monkeypatch.setattr(
        price_updater.requests,
        "get",
        lambda url: _FakeResponse('["2914.T", "8058.T"]'),
    )

    tickers = price_updater.fetch_tickers_from_gas("https://example.test/gas")

    assert tickers == ["2914.T", "8058.T"]


def test_fetch_tickers_from_gas_raises_on_empty(monkeypatch):
    monkeypatch.setattr(
        price_updater.requests,
        "get",
        lambda url: _FakeResponse("[]"),
    )

    with pytest.raises(Exception):
        price_updater.fetch_tickers_from_gas("https://example.test/gas")


# --- post_to_gas ------------------------------------------------------------

def test_post_to_gas_skips_when_empty(monkeypatch):
    called = {"posted": False}

    def _fake_post(url, json=None):
        called["posted"] = True
        return _FakeResponse("{}")

    monkeypatch.setattr(price_updater.requests, "post", _fake_post)

    # 空データなら POST せずに早期 return する
    price_updater.post_to_gas({}, "https://example.test/gas")

    assert called["posted"] is False


def test_post_to_gas_sends_each_ticker(monkeypatch):
    posted = []

    def _fake_post(url, json=None):
        posted.append(json)
        return _FakeResponse('{"result": "success"}')

    monkeypatch.setattr(price_updater.requests, "post", _fake_post)

    payload = {"2914.T": [{"date": "2026-06-01", "open": 1, "high": 2, "low": 1, "close": 2}]}
    price_updater.post_to_gas(payload, "https://example.test/gas")

    assert posted == [payload]
