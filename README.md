# ETF Price Tracker

[![Python](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![AWS SAM](https://img.shields.io/badge/AWS-SAM-blueviolet.svg)](https://aws.amazon.com/serverless/sam/)
[![AWS EventBridge](https://img.shields.io/badge/AWS-EventBridge-blue.svg)](https://aws.amazon.com/eventbridge/)
[![AWS Lambda](https://img.shields.io/badge/AWS-Lambda-orange.svg)](https://aws.amazon.com/lambda/)

<table>
    <thead>
        <tr>
           <th style="text-align:center"><a href="#日本語版">日本語版</a></th>
           <th style="text-align:center"><a href="#english-version">English Version</a></th>     
        </tr>
    </thead>
</table>

---

## 日本語版

### 概要

VT、VOO、QQQの人気ETFの価格とUSD/JPY為替レートを監視し、日々の価格変動をテキストでLINEに通知します。  
さらに、VTの6ヶ月株価チャートを画像で送信する機能も備えています。

### アーキテクチャ

```

EventBridge スケジュール
↓
AWS Lambda
├─ yfinance（データ取得）
├─ matplotlib（チャート生成: /tmp/vt_chart.png）
├─ boto3（S3アップロード）
├─ S3 presigned URL生成
└─ LINE Messaging API（Push API）
├─ テキスト通知送信
└─ 画像通知送信（HTTPS URL）

```

### 処理フロー

1. **EventBridge スケジュール起動**

   毎週火〜土曜日の午前9時15分（JST）にLambda関数を実行（UTC 0:15、NY夏時間は前日20:15、NY冬時間は前日19:15）

2. **データ取得**

   yfinanceを使用し、3つのETFとUSD/JPY為替レートを別々に取得。ETFは一括の調整後日足、一括の通常日足、銘柄ごとの通常日足の順でフォールバック

3. **価格検証・変動率計算**

   VT・VOO・QQQの3銘柄すべてについて基準日の価格が揃った場合だけ、同じ取引日を使って現在値・前日比・前週比を計算。通知見出しにはETF価格の基準日を表示し、値が揃わない場合は`NaN`を通知せず処理を終了

4. **チャート生成**

   matplotlibでVTの6ヶ月チャートを生成し、`/tmp/vt_chart.png`に保存

5. **S3アップロード**

   boto3を使用してチャート画像をS3にアップロード

6. **Presigned URL生成**

   S3から有効期限付きのpresigned URL（GET）を取得

7. **LINE Push API送信**

   テキストと画像でETF価格とチャートを送信

### 使用技術

- AWS Lambda
- Python 3.13
- AWS EventBridge
- AWS S3
- AWS SAM
- yfinance 0.2.65
- matplotlib
- LINE Messaging API

### 監視対象ETF

| シンボル | 正式名称 | 説明 |
|----------|----------|------|
| VT | バンガード・トータルワールドストック | 世界株式市場全体を対象としたETF |
| VOO | バンガード・S&P500 | S&P500指数 |
| QQQ | インベスコQQQトラスト | NASDAQ100指数 |

### LINE 通知メッセージの例

#### テキスト通知

例1:
```

📈2025-04-03 ETF Tracker

【VT】
現在値: $100.20
前日比: -3.8%
前週比: -9.2%

【VOO】
現在値: $390.50
前日比: -3.1%
前週比: -10.0%

【QQQ】
現在値: $352.10
前日比: -5.97%
前週比: -8.5%

【為替】 USD/JPY: 150.25

```

例2:
```

📈2020-03-16 ETF Tracker

【VT】
現在値: $61.30
前日比: -12.0%
前週比: -17.4%

【VOO】
現在値: $220.00
前日比: -11.3%
前週比: -16.2%

【QQQ】
現在値: $170.40
前日比: -11.7%
前週比: -15.3%

【為替】 USD/JPY: 110.50

```

#### 画像通知

VTの6ヶ月株価チャートが画像として送信されます。

![vt_chart.png](docs/vt_chart.png)

### 環境構築手順

#### Python仮想環境の作成

```bash
python -m venv .venv
source .venv/bin/activate
````

#### 依存関係のインストール

```bash
pip install -r requirements.txt
```

#### 開発用依存関係のインストール

```bash
pip install -r requirements-dev.txt
```

### ローカル開発

#### ローカル実行

`.env` に `LINE_CHANNEL_ACCESS_TOKEN` と `LINE_USER_ID` を設定しておくと、ローカル実行時に自動で読み込みます。

#### 静的解析・フォーマット・型チェック

```bash
ruff check src --fix
ruff format src
mypy src
```

#### テスト実行

```bash
python -c "from src.handler import lambda_handler; from aws_lambda_powertools.utilities.typing import LambdaContext; print(lambda_handler({}, LambdaContext()))"
```

```bash
python -m pytest tests/
```

### CI/CD

GitHub Actions と AWS SAM を使用したサーバーレスアプリケーションの自動デプロイメントを実装しています。

---

## English Version

### Overview

This application monitors the prices of popular ETFs (VT, VOO, QQQ) and the USD/JPY exchange rate, and sends daily price change notifications to LINE in text format.
It also includes a feature to send a 6-month price chart for VT as an image.

### Architecture

```
EventBridge Schedule
↓
AWS Lambda
├─ yfinance (Data Retrieval)
├─ matplotlib (Chart Generation: /tmp/vt_chart.png)
├─ boto3 (S3 Upload)
├─ S3 Presigned URL Generation
└─ LINE Messaging API (Push API)
├─ Send Text Notification
└─ Send Image Notification (HTTPS URL)
```

### Processing Flow

1. **EventBridge Schedule Trigger**
   Executes the Lambda function every Tuesday through Saturday at 9:15 AM JST (00:15 UTC, 8:15 PM on the previous day in New York during daylight saving time, and 7:15 PM during standard time).

2. **Data Retrieval**
   Retrieves the three ETFs separately from the USD/JPY exchange rate using yfinance. ETF retrieval falls back from batch adjusted daily data to batch unadjusted daily data and then to per-symbol unadjusted daily data.

3. **Price Validation and Change Calculation**
   Calculates the current price, day-over-day change, and week-over-week change from common trading dates only when all three ETFs have a valid price for the target date. The notification heading shows the ETF price date; if the values are incomplete, the function exits without sending `NaN`.

4. **Chart Generation**
   Generates a 6-month price chart for VT using matplotlib and saves it to `/tmp/vt_chart.png`.

5. **S3 Upload**
   Uploads the chart image to Amazon S3 using boto3.

6. **Presigned URL Generation**
   Generates a presigned URL (GET) with an expiration time.

7. **LINE Push API Notification**
   Sends ETF price information and the chart via text and image messages using the LINE Messaging API.

### Technologies Used

* AWS Lambda
* Python 3.13
* AWS EventBridge
* AWS S3
* AWS SAM
* yfinance 0.2.65
* matplotlib
* LINE Messaging API

### Monitored ETFs

| Symbol | Official Name                  | Description                                  |
| ------ | ------------------------------ | -------------------------------------------- |
| VT     | Vanguard Total World Stock ETF | ETF covering the entire global equity market |
| VOO    | Vanguard S&P 500 ETF           | S&P 500 Index                                |
| QQQ    | Invesco QQQ Trust              | NASDAQ-100 Index                             |

### Example LINE Notification Messages

#### Text Notification

Example 1:

```
📈2025-04-03 ETF Tracker

【VT】
Current Price: $100.20
Day-over-Day Change: -3.8%
Week-over-Week Change: -9.2%

【VOO】
Current Price: $390.50
Day-over-Day Change: -3.1%
Week-over-Week Change: -10.0%

【QQQ】
Current Price: $352.10
Day-over-Day Change: -5.97%
Week-over-Week Change: -8.5%

【FX】 USD/JPY: 150.25
```

Example 2:

```
📈2020-03-16 ETF Tracker

【VT】
Current Price: $61.30
Day-over-Day Change: -12.0%
Week-over-Week Change: -17.4%

【VOO】
Current Price: $220.00
Day-over-Day Change: -11.3%
Week-over-Week Change: -16.2%

【QQQ】
Current Price: $170.40
Day-over-Day Change: -11.7%
Week-over-Week Change: -15.3%

【為替】 USD/JPY: 110.50
```

#### Image Notification

A 6-month price chart for VT is sent as an image.

![vt\_chart.png](docs/vt_chart.png)

### Environment Setup

#### Create Python Virtual Environment

```bash
python -m venv .venv
source .venv/bin/activate
```

#### Install Dependencies

```bash
pip install -r requirements.txt
```

#### Install Development Dependencies

```bash
pip install -r requirements-dev.txt
```

### Local Development

#### Local Execution

If `LINE_CHANNEL_ACCESS_TOKEN` and `LINE_USER_ID` are set in `.env`, they will be loaded automatically during local execution.

#### Static Analysis and Formatting

```bash
ruff check src --fix
ruff format src
mypy src
```

#### Run Tests

```bash
python -c "from src.handler import lambda_handler; from aws_lambda_powertools.utilities.typing import LambdaContext; print(lambda_handler({}, LambdaContext()))"
```

```bash
python -m pytest tests/
```

### CI/CD

Automated deployment of the serverless application using GitHub Actions and AWS SAM.
