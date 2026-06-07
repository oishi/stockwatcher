"""dividend_updater.py の単体テスト。

会計年度ラベル付け・年間配当の合算・年次系列化という純粋ロジックを、
ネットワーク非依存で検証する（yfinance は呼ばない）。
"""

import pandas as pd
import pytest

import dividend_updater as du


def _series(pairs):
    """[(date_str, amount), ...] から ex-date を index に持つ Series を作る。"""
    idx = pd.to_datetime([d for d, _ in pairs])
    return pd.Series([v for _, v in pairs], index=idx)


# --- fiscal_year_of -----------------------------------------------------

def test_fiscal_year_of_may_settlement():
    # 5月決算: 決算月以前はその年、超えると翌年
    assert du.fiscal_year_of(pd.Timestamp("2025-05-29"), 5) == 2025  # 期末
    assert du.fiscal_year_of(pd.Timestamp("2024-11-28"), 5) == 2025  # 中間
    assert du.fiscal_year_of(pd.Timestamp("2025-06-01"), 5) == 2026  # 翌年度入り


def test_fiscal_year_of_december_settlement():
    # 12月決算(JT等)は会計年度＝暦年
    assert du.fiscal_year_of(pd.Timestamp("2025-06-27"), 12) == 2025
    assert du.fiscal_year_of(pd.Timestamp("2025-12-29"), 12) == 2025


def test_fiscal_year_of_march_settlement():
    # 3月決算(レンゴー等)
    assert du.fiscal_year_of(pd.Timestamp("2025-03-28"), 3) == 2025  # 期末
    assert du.fiscal_year_of(pd.Timestamp("2024-09-27"), 3) == 2025  # 中間


# --- aggregate_annual_dividends ----------------------------------------

def test_aggregate_groups_interim_and_final_into_same_fy():
    # 5月決算: 2024-11(中間40) + 2025-05(期末55) は同じ FY2025 に合算される
    s = _series([("2024-11-28", 40.0), ("2025-05-29", 55.0)])
    annual = du.aggregate_annual_dividends(s, fy_end_month=5)
    assert annual == {2025: 95.0}


def test_aggregate_multiple_years():
    # 12月決算: 各暦年に合算
    s = _series(
        [
            ("2023-06-29", 94.0),
            ("2023-12-28", 100.0),
            ("2024-06-27", 97.0),
            ("2024-12-27", 97.0),
        ]
    )
    annual = du.aggregate_annual_dividends(s, fy_end_month=12)
    assert annual[2023] == pytest.approx(194.0)
    assert annual[2024] == pytest.approx(194.0)


def test_aggregate_handles_fractional_amounts():
    # 端数(5.5円半期)も正しく合算
    s = _series([("2025-03-28", 5.5), ("2024-09-27", 5.5)])
    annual = du.aggregate_annual_dividends(s, fy_end_month=3)
    assert annual[2025] == pytest.approx(11.0)


# --- build_annual_series -----------------------------------------------

def test_build_annual_series_orders_from_latest():
    annual = {2025: 195.0, 2024: 190.0, 2023: 180.0}
    series = du.build_annual_series(annual, latest_fy=2025, years=3)
    # 配当0=最新, 配当1, 配当2 の順
    assert series == [195.0, 190.0, 180.0]


def test_build_annual_series_fills_missing_with_none():
    annual = {2025: 195.0, 2023: 180.0}  # 2024 が欠損
    series = du.build_annual_series(annual, latest_fy=2025, years=3)
    assert series == [195.0, None, 180.0]


def test_build_annual_series_default_11_years():
    annual = {y: float(y) for y in range(2015, 2026)}
    series = du.build_annual_series(annual, latest_fy=2025)
    assert len(series) == 11
    assert series[0] == 2025.0   # 配当0
    assert series[10] == 2015.0  # 配当10


# --- fetch_annual_dividends (yfinance はモック) -------------------------

class _FakeTicker:
    """yfinance.Ticker の差し替え用。info と dividends だけ提供する。"""

    def __init__(self, code, lfy_dt, dividends):
        self.ticker = code
        self._lfy_dt = lfy_dt
        self._dividends = dividends

    @property
    def info(self):
        return {"lastFiscalYearEnd": int(self._lfy_dt.timestamp())}

    @property
    def dividends(self):
        return self._dividends


def test_fetch_annual_dividends_with_mock():
    from datetime import datetime, timezone

    # 5月決算・最新確定 FY2025。中間(2024-11)+期末(2025-05)=95、前年度(2024-05)=190
    lfy = datetime(2025, 5, 31, tzinfo=timezone.utc)
    div = _series([
        ("2024-05-29", 190.0),
        ("2024-11-28", 40.0),
        ("2025-05-29", 55.0),
    ])

    def factory(code):
        assert code == "1419.T"  # .T が付与されること
        return _FakeTicker(code, lfy, div)

    result = du.fetch_annual_dividends("1419", years=3, ticker_factory=factory)
    # 配当0=FY2025(40+55=95), 配当1=FY2024(190), 配当2=FY2023(無し→None)
    assert result == [95.0, 190.0, None]


def test_fetch_annual_dividends_rounds_fractional(monkeypatch):
    from datetime import datetime, timezone

    lfy = datetime(2025, 5, 31, tzinfo=timezone.utc)
    # 分割調整由来の端数(58.333332)と半期端数(52.5)を四捨五入する
    div = _series([("2024-05-29", 52.5), ("2025-05-29", 58.333332)])

    def factory(code):
        return _FakeTicker(code, lfy, div)

    result = du.fetch_annual_dividends("x", years=2, ticker_factory=factory)
    # FY2025=58.333→58, FY2024=52.5→53(四捨五入)
    assert result == [58, 53]


def test_fetch_annual_dividends_raises_without_fiscal_year():
    from datetime import datetime, timezone

    class _NoFYTicker(_FakeTicker):
        @property
        def info(self):
            return {}

    def factory(code):
        return _NoFYTicker(code, datetime(2025, 5, 31, tzinfo=timezone.utc), _series([]))

    with pytest.raises(ValueError):
        du.fetch_annual_dividends("1419", ticker_factory=factory)


# --- dividend_metrics (V/W/X) ------------------------------------------

def test_metrics_ms_japan_6539():
    # 配当0..10(新→古)。末尾2年は欠損。ユーザー確認値: V=8, W=4, X=0
    series = [56, 56, 49, 15, 15, 15, 15, 11, 9, None, None]
    assert du.dividend_metrics(series) == {"V": 8, "W": 4, "X": 0}


def test_metrics_tamahome_1419():
    # ユーザー確認値: V=10, W=1, X=0
    series = [195, 185, 180, 125, 100, 70, 53, 30, 15, 10, 10]
    assert du.dividend_metrics(series) == {"V": 10, "W": 1, "X": 0}


def test_metrics_with_recent_decline_breaks_streak():
    # 古→新: 10,20,15,15,30 → 直近は 15→15(維持)→30(増)。途中 20→15 で減配1回
    # 新→古入力: [30,15,15,20,10]
    # transitions(古→新): up, down, flat, up
    #   W(flat)=1, X(down)=1, V=末尾から up,flat,(down で停止)=2
    series = [30, 15, 15, 20, 10]
    assert du.dividend_metrics(series) == {"V": 2, "W": 1, "X": 1}


def test_metrics_all_declining():
    # 古→新: 50,40,30 (新→古入力 [30,40,50]) → 全減配
    # transitions: down, down → V=0, W=0, X=2
    series = [30, 40, 50]
    assert du.dividend_metrics(series) == {"V": 0, "W": 0, "X": 2}


def test_metrics_ignores_none_gaps():
    # 欠損を除外して評価する（先頭・途中の None）
    series = [56, 56, None, 15, 15]  # 新→古, 古→新有効: 15,15,56,56
    # transitions: flat, up, flat → W=2, X=0, V=3
    assert du.dividend_metrics(series) == {"V": 3, "W": 2, "X": 0}


# --- collect_dividends -------------------------------------------------

def test_collect_dividends_aggregates_and_skips_failures():
    from datetime import datetime, timezone

    lfy = datetime(2025, 5, 31, tzinfo=timezone.utc)

    def factory(code):
        if code == "1419.T":
            return _FakeTicker(
                code, lfy, _series([("2024-05-29", 190.0), ("2025-05-29", 195.0)])
            )
        raise RuntimeError("no data")  # 9999.T は取得失敗

    result = du.collect_dividends(
        ["1419", "9999"], years=3, sleep_seconds=0, ticker_factory=factory
    )
    # 成功銘柄のみ .T 付きキーで入り、失敗銘柄はスキップされる
    assert set(result.keys()) == {"1419.T"}
    assert result["1419.T"] == [195.0, 190.0, None]


# --- post_dividends_to_gas ---------------------------------------------

class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_post_dividends_payload_shape(monkeypatch):
    captured = {}

    def fake_post(url, json=None):
        captured["url"] = url
        captured["json"] = json
        return _FakeResp({"updateDividends": {"status": "success"}})

    monkeypatch.setattr(du.requests, "post", fake_post)

    res = du.post_dividends_to_gas({"6539.T": [56, 56, 49]}, "https://example.test/gas")

    # type 分岐用の type と data を持つ payload になっている
    assert captured["json"] == {"type": "dividend", "data": {"6539.T": [56, 56, 49]}}
    assert res["updateDividends"]["status"] == "success"


def test_post_dividends_empty_skips_request(monkeypatch):
    called = {"posted": False}

    def fake_post(url, json=None):
        called["posted"] = True
        return _FakeResp({})

    monkeypatch.setattr(du.requests, "post", fake_post)

    assert du.post_dividends_to_gas({}, "https://example.test/gas") == {}
    assert called["posted"] is False
