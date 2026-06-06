"""テスト共通設定。

price_updater の一部関数は tenacity の @retry でラップされており、
失敗系テストでは指数バックオフの実待機が走ってテストが極端に遅くなる。
テスト中はリトライ待機をゼロにして高速化する（リトライ回数自体は維持）。
"""

import pytest
from tenacity import wait_none

import dividend_updater
import price_updater


@pytest.fixture(autouse=True)
def _disable_retry_wait():
    for fn in (
        price_updater.fetch_single_stock_data,
        price_updater.post_to_gas,
        price_updater.fetch_tickers_from_gas,
        dividend_updater.post_dividends_to_gas,
    ):
        retry = getattr(fn, "retry", None)
        if retry is not None:
            retry.wait = wait_none()
    yield
