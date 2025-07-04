import json
import requests
import sys
import os
import argparse
from dotenv import load_dotenv
from time import sleep
from typing import Dict, List
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import logging
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv()

# ロギングの設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def format_ticker_symbol(ticker: str) -> str:
    """
    ティッカーシンボルを適切な形式に変換する
    例: 8098 -> 8098.T
    """
    formatted_ticker = f"{ticker}.T" if not ticker.endswith('.T') else ticker
    logger.debug(f"ティッカー変換: {ticker} -> {formatted_ticker}")
    return formatted_ticker

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def fetch_single_stock_data(ticker: str, period: str) -> pd.DataFrame:
    """
    単一銘柄のデータを取得する関数（リトライロジック付き）
    """
    formatted_ticker = format_ticker_symbol(ticker)
    logger.info(f"データ取得開始: {formatted_ticker}")
    try:
        stock = yf.Ticker(formatted_ticker)
        data = stock.history(period=period)
        
        if data.empty:
            raise ValueError(f"データが空です: {formatted_ticker}")
            
        # カラム名を標準化
        data = data[['Open', 'High', 'Low', 'Close', 'Volume']]
        data.columns = ['open', 'high', 'low', 'close', 'volume']
        return data
        
    except Exception as e:
        logger.error(f"銘柄 {formatted_ticker} のデータ取得中にエラーが発生: {str(e)}")
        raise

def fetch_stock_data(tickers: List[str], period: str) -> Dict[str, pd.DataFrame]:
    """
    複数銘柄のデータを取得する関数
    """
    stock_data = {}
    total = len(tickers)
    failed_tickers = []
    
    logger.info(f"開始: 全{total}銘柄のデータを取得します")
    
    for i, ticker in enumerate(tickers, 1):
        try:
            data = fetch_single_stock_data(ticker, period)
            stock_data[ticker] = data
            logger.info(f"[{i}/{total}] {ticker}: 成功")
            
        except Exception as e:
            logger.error(f"[{i}/{total}] {ticker}: 失敗 ({str(e)})")
            failed_tickers.append(ticker)
            continue
        
        # APIレート制限を考慮して短い待機を入れる
        sleep(0.5)
    
    success_count = len(stock_data)
    logger.info(f"\n取得完了: {success_count}/{total}銘柄のデータを取得しました")
    
    if failed_tickers:
        logger.warning(f"取得に失敗した銘柄: {', '.join(failed_tickers)}")
    
    return stock_data

def convert_to_json(stock_data: Dict[str, pd.DataFrame]) -> Dict[str, List[Dict]]:
    """
    DataFrameをJSON形式に変換する関数
    """
    json_data = {}
    failed_conversions = []
    
    for ticker, data in stock_data.items():
        try:
            json_data[ticker] = [
                {
                    "date": index.strftime("%Y-%m-%d"),
                    "open": float(row.open),
                    "high": float(row.high),
                    "low": float(row.low),
                    "close": float(row.close)
                }
                for index, row in data.iterrows()
                if not (pd.isna(row.open) or pd.isna(row.high) or pd.isna(row.low) or pd.isna(row.close))
            ]
            
            if not json_data[ticker]:  # 有効なデータがない場合
                raise ValueError("有効なデータポイントがありません")
                
        except Exception as e:
            logger.error(f"{ticker}: データの変換中にエラーが発生しました ({str(e)})")
            failed_conversions.append(ticker)
            if ticker in json_data:
                del json_data[ticker]
            continue
    
    if failed_conversions:
        logger.warning(f"JSON変換に失敗した銘柄: {', '.join(failed_conversions)}")
    
    return json_data

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def post_to_gas(json_data: Dict[str, List[Dict]], gas_url: str) -> None:
    """
    データをGoogle Apps Scriptに送信する関数（リトライロジック付き）
    """
    if not json_data:
        logger.warning("送信するデータがありません")
        return
        
    failed_posts = []
    for ticker, data in json_data.items():
        try:
            response = requests.post(gas_url, json={ticker: data})
            response.raise_for_status()
            response_json = response.json()
            logger.info(f"Processed ticker: {ticker}, Response: {json.dumps(response_json, indent=4)}")
        except requests.exceptions.RequestException as e:
            logger.error(f"GASへのデータ送信中にエラーが発生: {str(e)}")
            failed_posts.append(ticker)
            continue
    
    if failed_posts:
        logger.warning(f"GASへの送信に失敗した銘柄: {', '.join(failed_posts)}")
        raise Exception("一部の銘柄でGASへの送信に失敗しました")

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def fetch_tickers_from_gas(gas_url: str) -> List[str]:
    """
    GASから銘柄リストを取得する関数（リトライロジック付き）
    """
    try:
        logger.info(f"GASから銘柄リストの取得を開始します: {gas_url}")
        response = requests.get(gas_url)
        response.raise_for_status()
        tickers = json.loads(response.text)
        
        if not tickers:
            raise ValueError("銘柄リストが空です")
            
        return tickers
        
    except requests.exceptions.RequestException as e:
        logger.error(f"銘柄リストの取得中にエラーが発生: {str(e)}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"銘柄リストのJSONデコードに失敗: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"予期せぬエラーが発生: {str(e)}")
        raise

def main():
    parser = argparse.ArgumentParser(description="株価データを取得して更新します")
    parser.add_argument("tickers", nargs="?", default="", help="カンマ区切りの銘柄コード")
    parser.add_argument("--period", default="10d", help="データ期間 (default: 10d)")

    args = parser.parse_args()

    gas_url = os.getenv("GAS_ENDPOINT_URL")
    if not gas_url:
        logger.error("環境変数 GAS_ENDPOINT_URL が設定されていません")
        sys.exit(1)

    try:
        tickers = args.tickers.split(',') if args.tickers else fetch_tickers_from_gas(gas_url)
        if not tickers:
            logger.error("処理する銘柄がありません")
            sys.exit(1)
            
        logger.info(f"取得した銘柄: {', '.join(tickers)}")

        stock_data = fetch_stock_data(tickers, args.period)
        if not stock_data:
            logger.error("株価データの取得に失敗しました")
            sys.exit(1)
            
        json_data = convert_to_json(stock_data)
        if not json_data:
            logger.error("JSONデータの変換に完全に失敗しました")
            sys.exit(1)
            
        post_to_gas(json_data, gas_url)
        logger.info("処理が正常に完了しました")
        
    except Exception as e:
        logger.error(f"予期せぬエラーが発生しました: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
