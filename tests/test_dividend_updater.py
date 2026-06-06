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
