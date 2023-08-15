import yfinance as yf
import pandas as pd
import json
import requests
import sys
from dotenv import load_dotenv
import os

load_dotenv()

def fetch_stock_data(tickers, period):
    stock_data = {ticker: yf.Ticker(ticker).history(period=period) for ticker in tickers}
    return stock_data

def convert_to_json(stock_data):
    json_data = {
        ticker: [
            {
                "date": row.Index.strftime("%Y-%m-%d"),
                "open": row.Open,
                "high": row.High,
                "low": row.Low,
                "close": row.Close
            }
            for row in data.itertuples()
        ]
        for ticker, data in stock_data.items()
    }
    return json_data

def post_to_gas(json_data, gas_url):
    for ticker, data in json_data.items():
        response = requests.post(gas_url, json={ticker: data})
        response_json = response.json()
        print(f"Processed ticker: {ticker}, Response: {json.dumps(response_json, indent=4)}")

def fetch_tickers_from_gas(gas_url):
    response = requests.get(gas_url)
    return json.loads(response.text)

if __name__ == "__main__":
    period_input = sys.argv[1] if len(sys.argv) > 1 else "10d"

    gas_url = os.getenv("GAS_ENDPOINT_URL")  # GASエンドポイントURLを環境変数から取得

    if not gas_url:
        print("Please set the GAS_ENDPOINT_URL in the .env file.")
        sys.exit(1)

    tickers = fetch_tickers_from_gas(gas_url) if len(sys.argv) <= 1 else sys.argv[1].split(',')
    print(f"Retrieved tickers: {', '.join(tickers)}")
    
    stock_data = fetch_stock_data(tickers, period_input)
    json_data = convert_to_json(stock_data)

    post_to_gas(json_data, gas_url)
