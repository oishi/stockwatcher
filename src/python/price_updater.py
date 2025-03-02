import yfinance as yf
import json
import requests
import sys
import os
import argparse
from dotenv import load_dotenv
from time import sleep
from typing import Dict, List
import pandas as pd

load_dotenv()

def fetch_stock_data(tickers, period):
    stock_data = {}
    total = len(tickers)
    
    print(f"開始: 全{total}銘柄のデータを取得します")
    
    for i, ticker in enumerate(tickers, 1):
        try:
            data = yf.Ticker(ticker).history(period=period)
            if not data.empty:
                stock_data[ticker] = data
                print(f"[{i}/{total}] {ticker}: 成功")
            else:
                print(f"[{i}/{total}] {ticker}: スキップ (データなし)")
        except Exception as e:
            print(f"[{i}/{total}] {ticker}: エラー ({str(e)})")
        
        # Yahoo Financeのレート制限を考慮して少し待機
        sleep(0.1)
    
    print(f"\n取得完了: {len(stock_data)}/{total}銘柄のデータを取得しました")
    return stock_data

def convert_to_json(stock_data):
    json_data = {}
    for ticker, data in stock_data.items():
        try:
            json_data[ticker] = [
                {
                    "date": row.Index.strftime("%Y-%m-%d"),
                    "open": float(row.Open),
                    "high": float(row.High),
                    "low": float(row.Low),
                    "close": float(row.Close)
                }
                for row in data.itertuples()
                if not (pd.isna(row.Open) or pd.isna(row.High) or pd.isna(row.Low) or pd.isna(row.Close))
            ]
        except Exception as e:
            print(f"{ticker}: データの変換中にエラーが発生しました ({str(e)})")
            continue
    
    return json_data

def post_to_gas(json_data, gas_url):
    for ticker, data in json_data.items():
        response = requests.post(gas_url, json={ticker: data})
        print(response.text)  # レスポンス内容をプリント
        response_json = response.json()
        print(f"Processed ticker: {ticker}, Response: {json.dumps(response_json, indent=4)}")

def fetch_tickers_from_gas(gas_url):
    response = requests.get(gas_url)
    return json.loads(response.text)


def main():
    parser = argparse.ArgumentParser(description="Fetch and update stock data.")
    parser.add_argument("tickers", nargs="?", default="", help="Comma-separated list of tickers.")
    parser.add_argument("--period", default="10d", help="Data period (default: 3d).")

    args = parser.parse_args()

    gas_url = os.getenv("GAS_ENDPOINT_URL")  # GASエンドポイントURLを環境変数から取得

    if not gas_url:
        print("Please set the GAS_ENDPOINT_URL in the .env file.")
        sys.exit(1)

    tickers = args.tickers.split(',') if args.tickers else fetch_tickers_from_gas(gas_url)
    period_input = args.period

    print(f"Retrieved tickers: {', '.join(tickers)}")

    stock_data = fetch_stock_data(tickers, period_input)
    json_data = convert_to_json(stock_data)

    print(json_data)

    post_to_gas(json_data, gas_url)

if __name__ == "__main__":
    main()
