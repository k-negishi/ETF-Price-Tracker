import datetime
import math
import os
import time
from typing import Any, Dict, List, Sequence, TypedDict

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
import yfinance as yf
from aws_lambda_powertools.utilities.typing import LambdaContext

from src.line_notifier import LineMessagingNotifier
from src.s3_storage import CHART_FILENAME, S3Storage, S3StorageError

ETF_TICKERS = ("VT", "VOO", "QQQ")


class MarketDataUnavailableError(RuntimeError):
    """通知に利用できる価格をyfinanceから取得できなかった。"""

    def __init__(self, message: str, data: pd.DataFrame | None = None) -> None:
        super().__init__(message)
        self.data = data if data is not None else pd.DataFrame()


class TickerData(TypedDict):
    name: str
    daily_change: float
    weekly_change: float
    current_price: float


def lambda_handler(event: Dict[str, Any], context: LambdaContext) -> Dict[str, Any]:
    # 基準日
    base_date = datetime.datetime.now().date()
    expected_price_date = base_date - datetime.timedelta(days=1)

    try:
        all_data = _download_prices_with_fallback(
            tickers=ETF_TICKERS,
            period="1mo",
            group_by="ticker",
            end=base_date,
            expected_price_date=expected_price_date,
        )
    except MarketDataUnavailableError as e:
        print(f"ETF価格取得失敗: {e}")
        return {
            "statusCode": 503,
            "body": {
                "notification_sent": False,
                "ticker_count": 0,
                "message": "ETF prices are not available",
            },
        }

    try:
        price_date, ticker_data_for_check = _build_ticker_data(
            all_data, ETF_TICKERS, expected_price_date
        )
    except MarketDataUnavailableError as e:
        print(f"ETF価格検証失敗: {e}")
        return {
            "statusCode": 503,
            "body": {
                "notification_sent": False,
                "ticker_count": 0,
                "message": "ETF prices failed validation",
            },
        }

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

    # LINE通知の送信
    line_notifier = LineMessagingNotifier()

    # ETFと取引時間が異なる為替は別に取得する
    try:
        jpy_data = _download_prices_with_fallback(
            tickers="JPY=X",
            period="1mo",
            end=base_date,
            expected_price_date=expected_price_date,
        )
        usd_jpy_rate = _price_on_date(jpy_data, expected_price_date)
    except MarketDataUnavailableError as e:
        print(f"為替取得失敗: {e}")
        return {
            "statusCode": 503,
            "body": {
                "notification_sent": False,
                "ticker_count": len(ticker_data_for_check),
                "message": "USD/JPY rate is not available",
            },
        }

    message = _format_notification_message(
        latest_date=price_date,
        ticker_data_list=ticker_data_for_check,
        usd_jpy_rate=usd_jpy_rate,
    )
    image_url: str | None = None
    # VTの3ヶ月グラフを生成してS3経由で送信
    try:
        vt_df_6mo = _download_prices_with_fallback(
            tickers="VT",
            period="6mo",
            end=base_date,
            expected_price_date=expected_price_date,
        )
        chart_filepath = create_chart(vt_df_6mo)

        # ファイルサイズを確認してログ出力
        file_size_bytes = os.path.getsize(chart_filepath)
        file_size_mb = file_size_bytes / (1024 * 1024)
        print(
            f"チャート画像生成完了: {chart_filepath}, "
            f"サイズ: {file_size_bytes} bytes ({file_size_mb:.2f} MB)"
        )

        # LINE API画像サイズ制限チェック (10MB)
        if file_size_bytes > 10 * 1024 * 1024:
            print("警告: 画像サイズがLINE API制限 (10MB) を超えています")

        s3_storage = S3Storage()
        now = datetime.datetime.now()
        # presigned URL有効期限を24時間 (86400秒) に設定
        image_url = s3_storage.upload_and_get_url(
            filepath=chart_filepath,
            filename_hint=CHART_FILENAME,
            now=now,
            expires_in=86400,
        )
        print(
            f"presigned URL生成成功: {image_url[:100]}..."
        )  # URLの先頭100文字のみログ出力
    except S3StorageError as e:
        # S3エラーはログに記録するが、テキスト通知はこの後送信するため処理は継続
        print(f"S3アップロードエラー: {e}")
    except ValueError as e:
        # S3_BUCKET未設定などの設定不備はログのみ残して通知処理は継続
        print(f"S3設定エラー: {e}")
    except Exception as e:
        # 画像生成/送信時の予期しないエラーで再試行されないようにログのみ残す
        print(f"画像通知の送信に失敗しました: {e}")

    line_notifier.send_messages([{"type": "text", "text": message}])

    if image_url:
        try:
            line_notifier.send_messages(
                [
                    {
                        "type": "image",
                        "originalContentUrl": image_url,
                        "previewImageUrl": image_url,
                    }
                ]
            )
            print("LINE画像送信成功")
        except Exception as e:
            # エラーの詳細情報をログ出力
            print(
                f"LINE画像送信失敗: エラータイプ={type(e).__name__}, "
                f"メッセージ={str(e)}, "
                f"URL={image_url[:100]}..."
            )

    # Lambda用のレスポンス
    return {
        "statusCode": 200,
        "body": {
            "notification_sent": True,
            "ticker_count": len(ticker_data_for_check),
            "message": "Stock monitoring completed successfully",
        },
    }


def _download_with_retry(
    *,
    tickers: str | Sequence[str],
    period: str,
    group_by: str | None = None,
    end: datetime.date | None = None,
    auto_adjust: bool = True,
    max_attempts: int = 3,
    retry_interval_seconds: int = 2,
) -> pd.DataFrame:
    """
    yfinanceでNaNまたは取得例外が発生するケースに備えてリトライする

    Args:
        tickers: 取得対象のティッカー
        period: 取得期間
        group_by: グループ化方法
        end: 終了日
        auto_adjust: 自動調整フラグ
        max_attempts: 最大リトライ回数
        retry_interval_seconds: リトライ間隔（秒）

    Raises:
        MarketDataUnavailableError: 最大試行後も最新終値が利用できない場合
    """
    download_kwargs: Dict[str, Any] = {
        "tickers": tickers,
        "period": period,
        "auto_adjust": auto_adjust,
    }
    if group_by:
        download_kwargs["group_by"] = group_by
    if end:
        download_kwargs["end"] = end

    last_data: pd.DataFrame | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            last_data = yf.download(**download_kwargs, progress=False)
        except Exception as error:
            print(
                "yfinance一括取得例外: "
                f"tickers={tickers}, auto_adjust={auto_adjust}, "
                f"attempt={attempt}/{max_attempts}, "
                f"error_type={type(error).__name__}, error={error}"
            )
            if attempt < max_attempts:
                print(
                    "yfinance一括取得再試行: "
                    f"wait_seconds={retry_interval_seconds}, "
                    f"attempt={attempt}/{max_attempts}"
                )
                time.sleep(retry_interval_seconds)
                continue
            raise MarketDataUnavailableError(
                f"{tickers}: {max_attempts}回試行後も取得処理が失敗しました "
                f"(auto_adjust={auto_adjust}, error={error})",
                last_data,
            ) from error

        _log_latest_prices(last_data, tickers, attempt, auto_adjust)
        if not _has_nan_values(last_data, tickers):
            return last_data
        if attempt < max_attempts:
            print(
                "yfinanceからNaNが返却されたため、"
                f"{retry_interval_seconds}秒後に再試行します。({attempt}/{max_attempts})"
            )
            time.sleep(retry_interval_seconds)

    raise MarketDataUnavailableError(
        f"{tickers}: {max_attempts}回試行後も最新終値を取得できませんでした "
        f"(auto_adjust={auto_adjust})",
        last_data,
    )


def _download_prices_with_fallback(
    *,
    tickers: str | Sequence[str],
    period: str,
    expected_price_date: datetime.date,
    group_by: str | None = None,
    end: datetime.date | None = None,
) -> pd.DataFrame:
    """基準日付きの日足だけを、取得方式を切り替えながら取得する。"""
    symbols = [tickers] if isinstance(tickers, str) else list(tickers)
    print(
        "市場データ取得開始: "
        f"tickers={symbols}, expected_date={expected_price_date}, "
        f"period={period}, end={end}"
    )

    try:
        adjusted_data = _download_with_retry(
            tickers=tickers,
            period=period,
            group_by=group_by,
            end=end,
            auto_adjust=True,
        )
        if _has_prices_on_date(adjusted_data, tickers, expected_price_date):
            _log_price_date_result(
                adjusted_data,
                tickers,
                expected_price_date,
                source="batch_adjusted",
                accepted=True,
            )
            return adjusted_data
        _log_price_date_result(
            adjusted_data,
            tickers,
            expected_price_date,
            source="batch_adjusted",
            accepted=False,
        )
        print(
            "市場データ取得方式切替: "
            "from=batch_adjusted, to=batch_raw, "
            "reason=expected_date_missing_or_invalid"
        )
    except MarketDataUnavailableError as adjusted_error:
        print(
            "市場データ取得方式切替: "
            f"from=batch_adjusted, to=batch_raw, reason={adjusted_error}"
        )

    try:
        raw_data = _download_with_retry(
            tickers=tickers,
            period=period,
            group_by=group_by,
            end=end,
            auto_adjust=False,
        )
        if _has_prices_on_date(raw_data, tickers, expected_price_date):
            _log_price_date_result(
                raw_data,
                tickers,
                expected_price_date,
                source="batch_raw",
                accepted=True,
            )
            return raw_data
        _log_price_date_result(
            raw_data,
            tickers,
            expected_price_date,
            source="batch_raw",
            accepted=False,
        )
        print(
            "市場データ取得方式切替: "
            "from=batch_raw, to=individual_raw, "
            "reason=expected_date_missing_or_invalid"
        )
    except MarketDataUnavailableError as raw_error:
        print(
            "市場データ取得方式切替: "
            f"from=batch_raw, to=individual_raw, reason={raw_error}"
        )

    try:
        individual_data = _download_individual_histories(
            tickers=symbols,
            period=period,
            end=end,
            expected_price_date=expected_price_date,
        )
    except MarketDataUnavailableError as individual_error:
        print(
            "市場データ取得失敗: "
            f"tickers={symbols}, expected_date={expected_price_date}, "
            f"reason={individual_error}"
        )
        raise

    _log_price_date_result(
        individual_data,
        tickers,
        expected_price_date,
        source="individual_raw",
        accepted=True,
    )
    return individual_data


def _has_prices_on_date(
    data: pd.DataFrame,
    tickers: str | Sequence[str],
    price_date: datetime.date,
) -> bool:
    """全銘柄について、指定日の有効な終値が揃っているかを判定する。"""
    if data.empty:
        return False
    symbols = [tickers] if isinstance(tickers, str) else list(tickers)
    for ticker in symbols:
        try:
            close = _close_series(data, ticker if len(symbols) > 1 else None)
        except KeyError:
            return False
        matching_indexes = [
            index for index in close.index if index.date() == price_date
        ]
        if not matching_indexes or not _is_valid_price(close.loc[matching_indexes[-1]]):
            return False
    return True


def _download_individual_histories(
    *,
    tickers: Sequence[str],
    period: str,
    end: datetime.date | None,
    expected_price_date: datetime.date,
    max_attempts: int = 3,
    retry_interval_seconds: int = 2,
) -> pd.DataFrame:
    """銘柄ごとに通常日足を取得し、全銘柄の基準日価格が揃った場合だけ返す。"""
    histories: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        last_data = pd.DataFrame()
        for attempt in range(1, max_attempts + 1):
            try:
                last_data = yf.Ticker(ticker).history(
                    period=period,
                    end=end,
                    auto_adjust=False,
                    actions=False,
                    raise_errors=True,
                )
                valid = _has_prices_on_date(last_data, ticker, expected_price_date)
                _log_price_date_result(
                    last_data,
                    ticker,
                    expected_price_date,
                    source="individual_raw",
                    accepted=valid,
                    attempt=attempt,
                )
                if valid:
                    histories[ticker] = last_data
                    break
            except Exception as error:
                print(
                    "個別日足取得例外: "
                    f"ticker={ticker}, expected_date={expected_price_date}, "
                    f"attempt={attempt}/{max_attempts}, "
                    f"error_type={type(error).__name__}, error={error}"
                )

            if attempt < max_attempts:
                print(
                    "個別日足再試行: "
                    f"ticker={ticker}, wait_seconds={retry_interval_seconds}, "
                    f"attempt={attempt}/{max_attempts}"
                )
                time.sleep(retry_interval_seconds)
        else:
            raise MarketDataUnavailableError(
                f"{ticker}: {expected_price_date}の通常日足を"
                f"{max_attempts}回試行しても取得できませんでした",
                last_data,
            )

    if len(tickers) == 1:
        return histories[tickers[0]]
    return pd.concat(histories, axis=1)


def _log_price_date_result(
    data: pd.DataFrame,
    tickers: str | Sequence[str],
    price_date: datetime.date,
    *,
    source: str,
    accepted: bool,
    attempt: int | None = None,
) -> None:
    """基準日価格の採否と銘柄別の値を診断可能な形で記録する。"""
    symbols = [tickers] if isinstance(tickers, str) else list(tickers)
    values: list[str] = []
    for ticker in symbols:
        try:
            close = _close_series(data, ticker if len(symbols) > 1 else None)
            matching_indexes = [
                index for index in close.index if index.date() == price_date
            ]
            value: object = (
                close.loc[matching_indexes[-1]] if matching_indexes else "missing_date"
            )
            values.append(f"{ticker}={value!r}")
        except (AttributeError, KeyError, IndexError):
            values.append(f"{ticker}='missing_close'")

    latest_date: object = "none"
    if not data.empty:
        latest_index = data.index[-1]
        latest_date = (
            latest_index.date() if hasattr(latest_index, "date") else latest_index
        )
    attempt_text = f", attempt={attempt}" if attempt is not None else ""
    print(
        f"市場データ{'採用' if accepted else '不採用'}: "
        f"source={source}{attempt_text}, expected_date={price_date}, "
        f"latest_date={latest_date}, close=[{', '.join(values)}]"
    )


def _log_latest_prices(
    data: pd.DataFrame,
    tickers: str | Sequence[str],
    attempt: int,
    auto_adjust: bool,
) -> None:
    """欠損原因を追跡できる範囲で、最新日と終値を記録する。"""
    if data.empty:
        print(
            f"yfinance取得結果: attempt={attempt}, auto_adjust={auto_adjust}, empty=True"
        )
        return
    symbols = [tickers] if isinstance(tickers, str) else list(tickers)
    values: list[str] = []
    for ticker in symbols:
        try:
            close = _close_series(data, ticker if len(symbols) > 1 else None)
            values.append(f"{ticker}={close.iloc[-1]!r}")
        except (KeyError, IndexError):
            values.append(f"{ticker}=missing")
    latest_index = data.index[-1]
    latest_date = latest_index.date() if hasattr(latest_index, "date") else latest_index
    print(
        "yfinance取得結果: "
        f"attempt={attempt}, auto_adjust={auto_adjust}, "
        f"latest_date={latest_date}, close=[{', '.join(values)}]"
    )


def _has_nan_values(data: pd.DataFrame, tickers: str | Sequence[str]) -> bool:
    """
    yfinance取得データの最新日付（前日）にNaNが含まれるか判定

    Args:
        data: 取得した株価データ
        tickers: 対象ティッカー

    Returns:
        bool: NaNが含まれる場合True
    """
    if data.empty:
        return True

    if isinstance(tickers, str):
        try:
            close_series = data["Close"]
        except KeyError:
            return True
        # MultiIndex columnsの場合、DataFrameが返されるため、最初の列を取得
        if isinstance(close_series, pd.DataFrame):
            close_series = close_series.iloc[:, 0]
        close_value = close_series.iloc[-1]
        return bool(close_value is pd.NA or pd.isna(close_value))

    for ticker in tickers:
        try:
            ticker_data = data[ticker]
        except KeyError:
            return True
        # MultiIndex columnsの場合、DataFrameが返される
        if isinstance(ticker_data, pd.DataFrame):
            if "Close" not in ticker_data.columns:
                return True
            close_price = ticker_data["Close"].iloc[-1]
        else:
            # 単一SeriesのClose列の場合
            close_price = ticker_data.iloc[-1]
        if pd.isna(close_price):
            return True

    return False


def _close_series(data: pd.DataFrame, ticker: str | None = None) -> pd.Series:
    """単一・複数銘柄のDataFrameからClose列を統一的に取り出す。"""
    ticker_data = data[ticker] if ticker is not None else data
    close = ticker_data["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    return close


def _is_valid_price(value: object) -> bool:
    try:
        price = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    return math.isfinite(price) and price > 0


def _price_on_date(data: pd.DataFrame, price_date: datetime.date) -> float:
    """指定日の有効なCloseを返す。暗黙に別日へフォールバックしない。"""
    close = _close_series(data)
    matching_indexes = [index for index in close.index if index.date() == price_date]
    if not matching_indexes:
        raise MarketDataUnavailableError(f"{price_date}の終値がありません", data)
    value = close.loc[matching_indexes[-1]]
    if not _is_valid_price(value):
        raise MarketDataUnavailableError(
            f"{price_date}の終値が不正です: {value!r}", data
        )
    return float(value)


def _build_ticker_data(
    data: pd.DataFrame,
    tickers: Sequence[str],
    expected_price_date: datetime.date,
) -> tuple[datetime.date, List[TickerData]]:
    """基準日、直前取引日、1週間前の取引日を明示して通知値を作る。"""
    close_by_ticker = {
        ticker: pd.to_numeric(_close_series(data, ticker), errors="coerce")
        for ticker in tickers
    }
    closes = pd.DataFrame(close_by_ticker).sort_index()
    closes = closes.replace([float("inf"), float("-inf")], pd.NA)
    valid_rows = closes.dropna(how="any")
    valid_rows = valid_rows[(valid_rows > 0).all(axis=1)]

    current_indexes = [
        index for index in valid_rows.index if index.date() == expected_price_date
    ]
    if not current_indexes:
        raise MarketDataUnavailableError(
            f"3銘柄が揃った{expected_price_date}の終値がありません", data
        )
    current_index = current_indexes[-1]

    previous_rows = valid_rows[valid_rows.index < current_index]
    if previous_rows.empty:
        raise MarketDataUnavailableError("前日比の比較日がありません", data)
    previous_index = previous_rows.index[-1]

    weekly_target = expected_price_date - datetime.timedelta(days=7)
    weekly_rows = previous_rows[
        pd.Index([index.date() <= weekly_target for index in previous_rows.index])
    ]
    if weekly_rows.empty:
        raise MarketDataUnavailableError("前週比の比較日がありません", data)
    weekly_index = weekly_rows.index[-1]

    print(
        "ETF価格採用日: "
        f"current={current_index.date()}, previous={previous_index.date()}, "
        f"weekly={weekly_index.date()}"
    )
    ticker_data: List[TickerData] = []
    for ticker in tickers:
        current = float(valid_rows.loc[current_index, ticker])
        previous = float(valid_rows.loc[previous_index, ticker])
        weekly = float(valid_rows.loc[weekly_index, ticker])
        ticker_data.append(
            {
                "name": ticker,
                "daily_change": round(((current - previous) / previous) * 100, 2),
                "weekly_change": round(((current - weekly) / weekly) * 100, 2),
                "current_price": current,
            }
        )
    return current_index.date(), ticker_data


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
    close_col = stock_data["Close"]
    # MultiIndex columnsの場合、DataFrameが返されるため、最初の列を取得
    if isinstance(close_col, pd.DataFrame):
        close_col = close_col.iloc[:, 0]
    # NaN値を除いた最新2営業日のデータを使用
    valid_data = close_col.dropna()
    if len(valid_data) < 2:
        return 0.0
    latest = valid_data.iloc[-1]
    previous = valid_data.iloc[-2]
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
    close_col = stock_data["Close"]
    # MultiIndex columnsの場合、DataFrameが返されるため、最初の列を取得
    if isinstance(close_col, pd.DataFrame):
        close_col = close_col.iloc[:, 0]
    # NaN値を除いた最新5営業日のデータを使用
    valid_data = close_col.dropna()
    if len(valid_data) < 2:
        return 0.0
    oldest_price = valid_data.iloc[-5] if len(valid_data) >= 5 else valid_data.iloc[0]
    current_price = valid_data.iloc[-1]
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

    alert_message = f"📈{latest_date} ETF Tracker\n\n"
    for ticker in ticker_data_list:
        alert_message += f"【{ticker['name']}】\n"
        alert_message += f"現在値: ${ticker['current_price']:.2f}\n"
        alert_message += f"前日比: {ticker['daily_change']}%\n"
        alert_message += f"前週比: {ticker['weekly_change']}%\n\n"
    alert_message += "【為替】 " + f"USD/JPY: {usd_jpy_rate:.2f}"
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
    # MultiIndex columnsの場合と通常columnsの場合の両方に対応
    if isinstance(df.columns, pd.MultiIndex):
        close_data = (
            df[("Close", "VT")]
            if ("Close", "VT") in df.columns
            else df.iloc[:, df.columns.get_level_values(0) == "Close"].iloc[:, 0]
        )
    else:
        close_data = df["Close"]
    ax.plot(df.index, close_data, color="#ff9900", linewidth=2)

    # グラフのスタイル設定
    ax.set_title("VT - Last 6 Months", fontsize=16)
    ax.set_facecolor("white")
    fig.set_facecolor("white")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))  # type: ignore[no-untyped-call]
    plt.xticks(rotation=45)
    plt.grid(True, linestyle="--", alpha=0.6)

    # ファイルに保存（ファイル名は定数CHART_FILENAMEを使用）
    # dpi=80に設定して画像サイズを最適化 (LINE推奨1MB以下、最大10MB)
    filepath = f"/tmp/{CHART_FILENAME}"
    plt.savefig(filepath, bbox_inches="tight", dpi=80)
    plt.close(fig)

    return filepath


# スクリプトとして実行された場合のみメイン処理を実行
if __name__ == "__main__":
    lambda_handler({}, LambdaContext())
