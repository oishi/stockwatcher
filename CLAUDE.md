# CLAUDE.md

このファイルは、このリポジトリでClaude Code (claude.ai/code)が作業する際のガイダンスを提供します。

## 開発環境とコマンド

### 必要な設定
- Python 3.x と以下のライブラリが必要：
  ```bash
  pip install -r requirements.txt
  ```
- 環境変数 `GAS_ENDPOINT_URL` を設定（Google Apps ScriptのエンドポイントURL）

### 基本的な実行コマンド
```bash
# 引数なしで実行（GASから銘柄リストを取得）
python src/python/price_updater.py

# 特定の銘柄を指定して実行
python src/python/price_updater.py 2914.T,1419.T

# 期間を指定して実行
python src/python/price_updater.py --period 30d

# シェルスクリプトを使用した実行
./bin/update.sh
./bin/update.sh 8058,9984 --period 30d
```

### テストについて
- 現在、自動テストは実装されていません
- Google Apps Scriptの `debug.gs` に `testProcessStockData()` 関数があり、手動テストに使用できます

## システムアーキテクチャ

### 全体構成
このシステムは株価データの監視・更新を行う2つのコンポーネントで構成されています：

1. **Python コンポーネント** (`src/python/price_updater.py`)
   - yfinance APIを使用して株価データを取得
   - データをJSON形式でGoogle Apps Scriptに送信
   - リトライ機能とエラーハンドリングを実装

2. **Google Apps Script コンポーネント** (`src/gas/`)
   - `code.gs`: メインの処理ロジック（POST/GET ハンドラ）
   - `init.gs`: 銘柄シートの作成・削除機能
   - `debug.gs`: デバッグ・ログ機能、データクリア機能

### データフロー
1. Python側でyfinance APIから株価データを取得
2. 取得したデータをJSON形式でGASエンドポイントにPOST
3. GAS側で各銘柄専用シートにデータを保存
4. 営業日終値差分を計算してlistシートを更新
5. スパークライン（価格推移グラフ）を生成

### 主要な機能
- **銘柄データの自動取得**: 指定された銘柄または全銘柄の株価を取得
- **データ重複チェック**: 同一日付のデータは上書きされません
- **エラーハンドリング**: 各段階でのエラーを適切にログ記録
- **営業日差分計算**: 複数の期間での価格差分を自動計算
- **可視化**: スパークラインによる価格推移の可視化

### 重要なファイル構造
- `src/python/price_updater.py`: Pythonメインスクリプト
- `src/gas/code.gs`: GASメインロジック
- `src/gas/init.gs`: 銘柄シート管理
- `src/gas/debug.gs`: デバッグ・メンテナンス機能
- `bin/update.sh`: 実行用シェルスクリプト
- `requirements.txt`: Python依存関係

### Google Spreadsheet構造
- `list` シート: 銘柄リスト（A列：銘柄コード、B列：市場コード）
- `log` シート: エラーログ
- 各銘柄専用シート: 株価データ（日付、始値、高値、安値、終値）

## 開発時の注意事項

### Python開発
- `tenacity` ライブラリを使用したリトライ機能が実装済み
- ロギング設定が `price_updater.py` に組み込まれている
- APIレート制限を考慮して0.5秒の待機時間を設けている

### Google Apps Script開発
- メニューバーに「株価操作」メニューが追加される
- エラーは `log` シートに記録される
- 各銘柄は「銘柄コード.市場コード」の形式でシート名が決まる

### 環境設定
- `.env` ファイルで環境変数を管理
- `GAS_ENDPOINT_URL` は必須の環境変数
- 仮想環境の使用を推奨（venvディレクトリは.gitignoreに含まれる）