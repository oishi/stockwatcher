# .devcontainer/Dockerfile
FROM python:3.12.6

# OS パッケージのアップデートと必要なパッケージのインストール
RUN apt-get update && apt-get install -y \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# 作業ディレクトリの設定
WORKDIR /workspace

# （必要に応じて、その他の環境設定を追加）
