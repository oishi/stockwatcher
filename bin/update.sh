#!/bin/bash

# 使用方法を表示する関数
usage() {
    echo "使用方法: $0 [銘柄コード1,銘柄コード2,...] [--period 期間]"
    echo "例: $0 8058,9984 --period 30d"
    echo "引数なしで実行すると、GASから銘柄リストを取得します"
    exit 1
}

# 引数があれば、そのまま price_updater.py に渡す
if [ $# -eq 0 ]; then
    # 引数がない場合は、引数なしで実行
    echo "GASから銘柄リストを取得して実行します..."
    python src/python/price_updater.py
else
    # 引数がある場合は、そのまま渡す
    python src/python/price_updater.py "$@"
fi
