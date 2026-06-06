"""配当履歴の取得と年間配当の集計。

yfinance の ex-date 付き配当(`Ticker.dividends`)を、決算月基準の会計年度で
合算して「年間配当」を算出する。決算月と最新の確定会計年度は
`Ticker.info['lastFiscalYearEnd']` から得る。

このモジュールの中核（会計年度ラベル付け・合算・年次系列化）は外部 I/O を
持たない純粋関数として実装し、単体テストで検証する。yfinance アクセスを伴う
取得関数はモック前提で薄く保つ。
"""

from typing import Dict, List, Optional


def fiscal_year_of(ex_date, fy_end_month: int) -> int:
    """ex-date が属する会計年度ラベルを返す。

    決算月を ``fy_end_month`` とすると、決算月以前(<=)の月はその暦年を、
    決算月を超える月は翌暦年を会計年度ラベルとする。

    例: 5月決算(fy_end_month=5)の場合
        2024-11-28(中間) -> 2025
        2025-05-29(期末) -> 2025
        2025-06-01       -> 2026
    """
    return ex_date.year if ex_date.month <= fy_end_month else ex_date.year + 1


def aggregate_annual_dividends(dividends, fy_end_month: int) -> Dict[int, float]:
    """ex-date 付き配当(pandas.Series)を会計年度で合算する。

    戻り値は ``{会計年度ラベル: 年間配当合計}``。
    index は日付(tz 付きでも可)、値は 1 株あたり配当額を想定。
    """
    result: Dict[int, float] = {}
    for ex_date, amount in dividends.items():
        fy = fiscal_year_of(ex_date, fy_end_month)
        result[fy] = result.get(fy, 0.0) + float(amount)
    return result


def build_annual_series(
    annual: Dict[int, float], latest_fy: int, years: int = 11
) -> List[Optional[float]]:
    """年間配当を「配当0(最新確定年度)〜配当(years-1)」の順で並べて返す。

    ``latest_fy`` を配当0 とし、1 年ずつ遡る。該当年度のデータが無ければ None。
    list シートの配当0〜配当10(11列)に対応させるため既定は years=11。
    """
    return [annual.get(latest_fy - i) for i in range(years)]


def _format_code(code: str) -> str:
    """銘柄コードを yfinance 形式(末尾 .T)へ整える。"""
    code = str(code)
    return code if code.endswith(".T") else f"{code}.T"


def fetch_annual_dividends(code, years: int = 11, ticker_factory=None) -> List[Optional[float]]:
    """yfinance から配当を取得し、配当0〜配当(years-1) の年間配当リストを返す。

    決算月・最新確定会計年度は ``info['lastFiscalYearEnd']`` から得る。
    ``ticker_factory`` を渡すとテスト時に yfinance.Ticker を差し替えられる
    （省略時は yfinance.Ticker を遅延 import して使用）。
    """
    from datetime import datetime, timezone

    if ticker_factory is None:
        import yfinance as yf

        ticker_factory = yf.Ticker

    ticker = ticker_factory(_format_code(code))

    lfy_ts = ticker.info.get("lastFiscalYearEnd")
    if not lfy_ts:
        raise ValueError(f"lastFiscalYearEnd を取得できませんでした: {code}")
    last_fiscal_year_end = datetime.fromtimestamp(lfy_ts, tz=timezone.utc)
    fy_end_month = last_fiscal_year_end.month
    latest_fy = last_fiscal_year_end.year  # 決算日の暦年＝最新確定会計年度ラベル

    annual = aggregate_annual_dividends(ticker.dividends, fy_end_month)
    return build_annual_series(annual, latest_fy, years)
