import datetime
import os
from typing import Any, Dict, List, TypedDict

import matplotlib.pyplot as plt
import pandas as pd
import yfinance as yf
from aws_lambda_powertools.utilities.typing import LambdaContext

from src.line_notifier import LineMessagingNotifier


class TickerData(TypedDict):
    name: str
    daily_change: float
    weekly_change: float
    current_price: float


from src.s3_uploader import S3Uploader


def lambda_handler(event: Dict[str, Any], context: LambdaContext) -> Dict[str, Any]:
    # グラフ描画用にVTの6ヶ月分のデータを取得
    vt_daily_data_6mo = yf.download("VT", period="6mo", auto_adjust=True)

    targets = ["VT", "VOO", "QQQ", "JPY=X"]
    all_data = yf.download(targets, period="1mo", group_by="ticker", auto_adjust=True)

    # 直近の日付が現在日付-1ではない場合は、処理をスキップ(米国市場の休場日を判定)
    if all_data.index[-1].date() != datetime.datetime.now().date() - datetime.timedelta(
        days=1
    ):
        return {
            "statusCode": 200,
            "body": {
                "notification_sent": False,
                "ticker_count": 0,
                "message": "Market is closed today",
            },
        }

    # 各ティッカーのデータを個別の変数に格納
    vt_data: pd.DataFrame = all_data["VT"]
    voo_data: pd.DataFrame = all_data["VOO"]
    qqq_data: pd.DataFrame = all_data["QQQ"]

    # 前日との計算
    vt_daily_change = _calculate_daily_change(vt_data)
    voo_daily_change = _calculate_daily_change(voo_data)
    qqq_daily_change = _calculate_daily_change(qqq_data)

    # 1週間前との計算
    vt_1wk_change = _calculate_weekly_change(vt_data)
    voo_1wk_change = _calculate_weekly_change(voo_data)
    qqq_1wk_change = _calculate_weekly_change(qqq_data)

    # 閾値の設定
    # TODO パイロット用にコメントアウトしたが、もうこのままでいいかも
    # DAILY_THRESHOLD = -2.0
    # WEEKLY_THRESHOLD = -5.0

    ticker_data_for_check: List[TickerData] = [
        {
            "name": "VT",
            "daily_change": vt_daily_change,
            "weekly_change": vt_1wk_change,
            "current_price": vt_data["Close"].iloc[-1],
        },
        {
            "name": "VOO",
            "daily_change": voo_daily_change,
            "weekly_change": voo_1wk_change,
            "current_price": voo_data["Close"].iloc[-1],
        },
        {
            "name": "QQQ",
            "daily_change": qqq_daily_change,
            "weekly_change": qqq_1wk_change,
            "current_price": qqq_data["Close"].iloc[-1],
        },
    ]

    # TODO パイロット用にコメントアウトしたけど、便利だしこのままでいいかも。
    # notification_needed = check_and_notify_all_tickers(ticker_data_for_check, DAILY_THRESHOLD, WEEKLY_THRESHOLD)
    notification_needed = True

    # 閾値を下回るETFが1つでも存在する場合、LINE通知を送信
    if notification_needed:
        line_notifier = LineMessagingNotifier()

        # vt のデータを使って日付を取得
        latest_date = vt_data.index[-1].date()

        # JPY=X のデータを取得
        jpy_data: pd.DataFrame = all_data["JPY=X"]
        usd_jpy_rate = jpy_data["Close"].iloc[-1]

        # グラフを生成
        vt_graph_path = _generate_vt_graph(vt_daily_data_6mo)

        # S3にアップロード
        s3_bucket_name = os.getenv("S3_BUCKET_NAME")
        if not s3_bucket_name:
            raise ValueError("S3_BUCKET_NAME environment variable is not set.")
        s3_uploader = S3Uploader(bucket_name=s3_bucket_name)
        s3_key = f"vt_graph_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        image_url = s3_uploader.upload_file(vt_graph_path, s3_key)

        # LINEに画像を送信
        line_notifier.send_image(image_url)

        message = _format_notification_message(
            latest_date, ticker_data_for_check, usd_jpy_rate
        )
        line_notifier.send_message(message)

    # Lambda用のレスポンス
    return {
        "statusCode": 200,
        "body": {
            "notification_sent": notification_needed,
            "ticker_count": len(ticker_data_for_check),
            "message": "Stock monitoring completed successfully",
        },
    }


def _is_below_threshold(change: float, threshold: float) -> bool:
    return change <= threshold


def _calculate_daily_change(stock_data: pd.DataFrame) -> float:
    """
    前日比の変動率を計算

    Args:
        stock_data (pd.DataFrame): 株価データ

    Returns:
        float: 前日比変動率（%、小数点以下2桁）
    """
    latest = stock_data["Close"].iloc[-1]
    previous = stock_data["Close"].iloc[-2]
    change: float = ((latest - previous) / previous) * 100
    return round(change, 2)


def _calculate_weekly_change(stock_data: pd.DataFrame) -> float:
    """
    1週間前比の変動率を計算

    Args:
        stock_data (pd.DataFrame): 株価データ

    Returns:
        float: 変動率（%）
    """
    oldest_price = stock_data["Close"].iloc[-5]
    current_price = stock_data["Close"].iloc[-1]
    change_pct: float = ((current_price - oldest_price) / oldest_price) * 100
    return round(change_pct, 2)


def _check_and_notify_all_tickers(
    ticker_data_list: List[TickerData],
    daily_threshold: float,
    weekly_threshold: float,
) -> bool:
    """
    Args:
        ticker_data_list (list): ティッカーデータのリスト
            [{'name': str, 'daily_change': float, 'weekly_change': float, 'current_price': float}, ...]
        daily_threshold (float): 日次変動の閾値
        weekly_threshold (float): 週次変動の閾値

    Returns:
        bool: 通知が必要かどうか（1つでも閾値を下回っていればTrue）
    """
    # 各ティッカーの閾値判定
    return any(
        _is_below_threshold(ticker["daily_change"], daily_threshold)
        or _is_below_threshold(ticker["weekly_change"], weekly_threshold)
        for ticker in ticker_data_list
    )


def _format_notification_message(
    latest_date: datetime.date,
    ticker_data_list: List[TickerData],
    usd_jpy_rate: float,
) -> str:
    """
    LINE通知用のメッセージを整形

    Args:
        latest_date: 最新の日付
        ticker_data_list (List[Dict[str, float]]): ティッカーデータのリスト
            [{'name': str, 'daily_change': float, 'weekly_change': float, 'current_price': float}, ...]
        usd_jpy_rate (float): USD/JPY為替レート

      Returns:
        str: 整形されたメッセージ文字列
    """

    alert_message = "📈ETF Price Tracker " + f"{latest_date}\n\n"
    for ticker in ticker_data_list:
        alert_message += f"【{ticker['name']}】\n"
        alert_message += f"現在値: ${ticker['current_price']:.2f}\n"
        alert_message += f"前日比: {ticker['daily_change']}%\n"
        alert_message += f"前週比: {ticker['weekly_change']}%\n\n"

    alert_message += f"【為替】\n"
    alert_message += f"USD/JPY: {usd_jpy_rate:.2f}\n"
    return alert_message.strip()


def _generate_vt_graph(vt_data: pd.DataFrame) -> str:
    """
    VTの6ヶ月間の株価推移グラフを生成し、一時ファイルに保存

    Args:
        vt_data (pd.DataFrame): VTの6ヶ月間の日次株価データ

    Returns:
        str: 生成されたグラフ画像のファイルパス
    """
    plt.style.use("dark_background")
    fig, ax = plt.subplots(figsize=(10, 6))

    # メインの株価チャート
    ax.plot(vt_data.index, vt_data["Close"], label="VT Close Price", color="cyan")
    ax.set_title("VT 6-Month Price Trend", color="white")
    ax.set_xlabel("Date", color="white")
    ax.set_ylabel("Price (USD)", color="white")
    ax.legend()
    ax.grid(True, linestyle="--", alpha=0.3)

    # X軸とY軸の目盛りを白に設定
    ax.tick_params(axis="x", colors="white")
    ax.tick_params(axis="y", colors="white")

    # グラフの枠線を白に設定
    for spine in ax.spines.values():
        spine.set_edgecolor("white")

    # 一時ファイルに保存
    save_dir = "/tmp/etf_graphs"
    os.makedirs(save_dir, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = os.path.join(save_dir, f"vt_graph_{timestamp}.png")
    fig.savefig(file_path, bbox_inches="tight", pad_inches=0.1, facecolor="black")
    plt.close(fig)

    return file_path


# スクリプトとして実行された場合のみメイン処理を実行
if __name__ == "__main__":
    lambda_handler({}, LambdaContext())
