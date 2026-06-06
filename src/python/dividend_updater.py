"""配当履歴の取得と年間配当の集計。

yfinance の ex-date 付き配当(`Ticker.dividends`)を、決算月基準の会計年度で
合算して「年間配当」を算出する。決算月と最新の確定会計年度は
`Ticker.info['lastFiscalYearEnd']` から得る。

このモジュールの中核（会計年度ラベル付け・合算・年次系列化）は外部 I/O を
持たない純粋関数として実装し、単体テストで検証する。yfinance アクセスを伴う
取得関数はモック前提で薄く保つ。
"""

import argparse
import json
import logging
import os
import sys
from time import sleep
from typing import Dict, List, Optional

import requests
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


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


def dividend_metrics(annual_series) -> Dict[str, int]:
    """配当系列から派生指標 連増(V)/維持(W)/減配(X) を算出する。

    ``annual_series`` は build_annual_series と同じ「配当0(最新)〜配当N(古)」の
    並び。None は欠損として除外し、残った有効値を古い順に並べて前年比を評価する。

    - V 連増 = 最新側から遡り「減配していない(同一 or 増配)」が連続する年数
    - W 維持 = 前年比が同一だった年数（通算）
    - X 減配 = 前年比が減配だった年数（通算）

    GAS 側（シート上のマージ後配当列で計算する本番実装）の参照仕様であり、
    ロジックの正しさをこの Python 実装＋テストで担保する。
    """
    # 配当0..N(新→古) を 古→新 に並べ替え、欠損を除外
    values = [v for v in reversed(list(annual_series)) if v is not None]

    transitions = []  # 'up' / 'flat' / 'down'（古→新の順）
    for i in range(1, len(values)):
        prev, cur = values[i - 1], values[i]
        if cur > prev:
            transitions.append("up")
        elif cur == prev:
            transitions.append("flat")
        else:
            transitions.append("down")

    w = transitions.count("flat")
    x = transitions.count("down")

    # V: 最新(末尾)から遡って down でない限り連続加算
    v = 0
    for t in reversed(transitions):
        if t == "down":
            break
        v += 1

    return {"V": v, "W": w, "X": x}


def collect_dividends(
    tickers: List[str],
    years: int = 11,
    sleep_seconds: float = 2.0,
    ticker_factory=None,
) -> Dict[str, List[Optional[float]]]:
    """複数銘柄の年間配当系列を取得し ``{"6539.T": [配当0..10], ...}`` を返す。

    各銘柄で yfinance(info + dividends)へアクセスするため、レート制限を考慮して
    銘柄間に ``sleep_seconds`` の待機を入れる。取得に失敗した銘柄はスキップする
    （配当は3ヶ月に1回程度の低頻度更新のため、全件成功を必須とはしない）。
    """
    result: Dict[str, List[Optional[float]]] = {}
    total = len(tickers)
    for i, code in enumerate(tickers, 1):
        try:
            series = fetch_annual_dividends(code, years=years, ticker_factory=ticker_factory)
            result[_format_code(code)] = series
            logger.info(f"[{i}/{total}] {code}: 取得成功 {series}")
        except Exception as e:  # noqa: BLE001 - 1銘柄の失敗で全体を止めない
            logger.error(f"[{i}/{total}] {code}: 取得失敗 ({e})")
        if i < total and sleep_seconds:
            sleep(sleep_seconds)
    return result


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def post_dividends_to_gas(
    dividends_by_code: Dict[str, List[Optional[float]]], gas_url: str
) -> dict:
    """配当データを GAS へ送信する。

    payload は ``{"type": "dividend", "data": {"6539.T": [配当0..10], ...}}``。
    GAS 側は ``type=="dividend"`` を配当処理へ振り分ける（株価 payload とは後方互換）。
    """
    if not dividends_by_code:
        logger.warning("送信する配当データがありません")
        return {}
    payload = {"type": "dividend", "data": dividends_by_code}
    response = requests.post(gas_url, json=payload)
    response.raise_for_status()
    result = response.json()
    logger.info(
        f"配当データ送信完了: {len(dividends_by_code)}銘柄, "
        f"Response: {json.dumps(result, ensure_ascii=False)}"
    )
    return result


def main():
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    parser = argparse.ArgumentParser(description="配当履歴を取得して GAS に送信します")
    parser.add_argument("tickers", nargs="?", default="", help="カンマ区切りの銘柄コード")
    parser.add_argument("--years", type=int, default=11, help="取得する年数 (default: 11)")
    parser.add_argument(
        "--sleep", type=float, default=2.0, help="銘柄間の待機秒 (default: 2.0)"
    )
    args = parser.parse_args()

    gas_url = os.getenv("GAS_ENDPOINT_URL")
    if not gas_url:
        logger.error("環境変数 GAS_ENDPOINT_URL が設定されていません")
        sys.exit(1)

    if args.tickers:
        tickers = args.tickers.split(",")
    else:
        # 銘柄リスト取得は株価側の実装を再利用する
        import price_updater

        tickers = price_updater.fetch_tickers_from_gas(gas_url)

    if not tickers:
        logger.error("処理する銘柄がありません")
        sys.exit(1)

    logger.info(f"配当取得対象: {len(tickers)}銘柄")
    dividends = collect_dividends(tickers, years=args.years, sleep_seconds=args.sleep)
    if not dividends:
        logger.error("配当データを取得できませんでした")
        sys.exit(1)

    post_dividends_to_gas(dividends, gas_url)
    logger.info("配当の更新処理が完了しました")


if __name__ == "__main__":
    main()
