import datetime
from typing import Any, Dict, List, TypedDict

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
import yfinance as yf
from aws_lambda_powertools.utilities.typing import LambdaContext

from src.line_notifier import LineMessagingNotifier
from src.s3_storage import CHART_FILENAME, S3Storage, S3StorageError


class TickerData(TypedDict):
    name: str
    daily_change: float
    weekly_change: float
    current_price: float


def lambda_handler(event: Dict[str, Any], context: LambdaContext) -> Dict[str, Any]:
    targets = ["VT", "VOO", "QQQ", "JPY=X"]
    # 基準日
    base_date = datetime.datetime.now().date()

    all_data = yf.download(
        tickers=targets,
        period="1mo",
        group_by="ticker",
        end=base_date,
        auto_adjust=True,
    )
    print(all_data)

    # 直近の日付が現在日付-1ではない場合は、処理をスキップ(米国市場の休場日を判定)
    if _is_market_closed(all_data):
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

    # 通知が必要ない場合は処理をスキップ
    if not notification_needed:
        return {
            "statusCode": 200,
            "body": {
                "notification_sent": False,
                "ticker_count": len(ticker_data_for_check),
                "message": "Stock monitoring completed successfully",
            },
        }

    # 閾値を下回るETFが1つでも存在する場合、LINE通知を送信
    line_notifier = LineMessagingNotifier()

    latest_date = base_date

    # JPY=X のデータを取得
    jpy_data: pd.DataFrame = all_data["JPY=X"]
    usd_jpy_rate = jpy_data["Close"].iloc[-1]

    message = _format_notification_message(
        latest_date=latest_date,
        ticker_data_list=ticker_data_for_check,
        usd_jpy_rate=usd_jpy_rate,
    )
    line_notifier.send_message(message)

    # VTの3ヶ月グラフを生成してS3経由で送信
    try:
        vt_df_6mo = yf.download(tickers="VT", period="6mo", auto_adjust=True)
        chart_filepath = create_chart(vt_df_6mo)

        s3_storage = S3Storage()
        now = datetime.datetime.now()
        presigned_url = s3_storage.upload_and_get_url(
            filepath=chart_filepath, filename_hint=CHART_FILENAME, now=now
        )
        line_notifier.send_image_url(presigned_url)
    except S3StorageError as e:
        # S3エラーはログに記録するが、テキスト通知は既に送信済みなので処理は継続
        print(f"S3アップロードエラー: {e}")
    except ValueError as e:
        # S3_BUCKET未設定などの設定不備はログのみ残して通知処理は継続
        print(f"S3設定エラー: {e}")
    except Exception as e:
        # 画像生成/送信時の予期しないエラーで再試行されないようにログのみ残す
        print(f"画像通知の送信に失敗しました: {e}")

    # Lambda用のレスポンス
    return {
        "statusCode": 200,
        "body": {
            "notification_sent": True,
            "ticker_count": len(ticker_data_for_check),
            "message": "Stock monitoring completed successfully",
        },
    }


def _is_market_closed(all_data: pd.DataFrame) -> bool:
    """
    米国市場が休場していたかどうかを判定

    Args:
        all_data (pd.DataFrame): ダウンロードした株価データ

    Returns:
        bool: 市場が休場していたからTrue、そうでなければFalse
    """
    latest_date = all_data.index[-1].date()
    expected_date = datetime.datetime.now().date() - datetime.timedelta(days=1)
    return latest_date != expected_date


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

    alert_message += "【為替】\n"
    alert_message += f"USD/JPY: {usd_jpy_rate:.2f}\n"
    return alert_message.strip()


def create_chart(df: pd.DataFrame) -> str:
    """
    株価チャートを生成してファイルに保存

    Args:
        df (pd.DataFrame): VTの株価データ

    Returns:
        str: 保存された画像ファイルのパス
    """
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(df.index, df["Close"], color="#ff9900", linewidth=2)

    # グラフのスタイル設定
    ax.set_title("VT - Last 6 Months", fontsize=16)
    ax.set_facecolor("white")
    fig.set_facecolor("white")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))  # type: ignore[no-untyped-call]
    plt.xticks(rotation=45)
    plt.grid(True, linestyle="--", alpha=0.6)

    # ファイルに保存（ファイル名は定数CHART_FILENAMEを使用）
    filepath = f"/tmp/{CHART_FILENAME}"
    plt.savefig(filepath, bbox_inches="tight")
    plt.close(fig)

    return filepath


# スクリプトとして実行された場合のみメイン処理を実行
if __name__ == "__main__":
    lambda_handler({}, LambdaContext())
