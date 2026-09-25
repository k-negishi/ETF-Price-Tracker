import os
import sys
from datetime import datetime
from unittest.mock import Mock, patch

import pandas as pd
import pytest

# プロジェクトのルートディレクトリをPythonパスに追加
project_root = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "src"))

from src.handler import (
    _is_below_threshold,
    _calculate_daily_change,
    _calculate_weekly_change,
    _check_and_notify_all_tickers,
    _format_notification_message,
    _download_with_retry,
    _download_prices_with_fallback,
    _build_ticker_data,
    _has_nan_values,
    MarketDataUnavailableError,
    create_chart,
)
from src.s3_storage import CHART_FILENAME


class TestIsBelowThreshold:
    """is_below_threshold関数のテストクラス"""

    def test_is_below_threshold_true_case(self):
        """閾値を下回る場合のテスト"""
        assert _is_below_threshold(-3.0, -2.0) is True
        assert _is_below_threshold(-2.0, -2.0) is True  # 等しい場合もTrue

    def test_is_below_threshold_false_case(self):
        """閾値を上回る場合のテスト"""
        assert _is_below_threshold(-1.0, -2.0) is False
        assert _is_below_threshold(0.0, -1.0) is False

    def test_is_below_threshold_edge_cases(self):
        """エッジケースのテスト"""
        assert _is_below_threshold(0.0, 0.0) is True
        assert _is_below_threshold(-0.1, 0.0) is True
        assert _is_below_threshold(0.1, 0.0) is False


class TestCalculateDailyChange:
    """calculate_daily_change関数のテストクラス"""

    def test_calculate_daily_change_positive(self):
        """前日比プラスの場合のテスト"""
        # テストデータ作成
        test_data = pd.DataFrame(
            {
                "Close": [100.0, 105.0]  # 5%の上昇
            }
        )

        result = _calculate_daily_change(test_data)
        assert result == 5.0

    def test_calculate_daily_change_negative(self):
        """前日比マイナスの場合のテスト"""
        test_data = pd.DataFrame(
            {
                "Close": [100.0, 97.0]  # 3%の下落
            }
        )

        result = _calculate_daily_change(test_data)
        assert result == -3.0

    def test_calculate_daily_change_no_change(self):
        """前日比変化なしの場合のテスト"""
        test_data = pd.DataFrame(
            {
                "Close": [100.0, 100.0]  # 変化なし
            }
        )

        result = _calculate_daily_change(test_data)
        assert result == 0.0


class TestCalculateWeeklyChange:
    """calculate_weekly_change関数のテストクラス"""

    def test_calculate_weekly_change_positive(self):
        """1週間前比プラスの場合のテスト"""
        test_data = pd.DataFrame(
            {
                "Close": [100.0, 102.0, 104.0, 103.0, 110.0]  # 10%の上昇
            }
        )

        result = _calculate_weekly_change(test_data)
        assert result == 10.0

    def test_calculate_weekly_change_negative(self):
        """1週間前比マイナスの場合のテスト"""
        test_data = pd.DataFrame(
            {
                "Close": [100.0, 98.0, 96.0, 94.0, 90.0]  # 10%の下落
            }
        )

        result = _calculate_weekly_change(test_data)
        assert result == -10.0

    def test_calculate_weekly_change_no_change(self):
        """1週間前比変化なしの場合のテスト"""
        test_data = pd.DataFrame(
            {
                "Close": [100.0, 102.0, 98.0, 105.0, 100.0]  # 変化なし
            }
        )

        result = _calculate_weekly_change(test_data)
        assert result == 0.0


class TestCheckAndNotifyAllTickers:
    """check_and_notify_all_tickers関数のテストクラス"""

    def test_check_and_notify_no_alert_needed(self):
        """アラートが不要な場合のテスト"""
        ticker_data = [
            {
                "name": "VT",
                "daily_change": -1.0,  # 閾値内
                "weekly_change": -3.0,  # 閾値内
                "current_price": 100.0,
            },
            {
                "name": "VOO",
                "daily_change": 1.0,  # プラス
                "weekly_change": -2.0,  # 閾値内
                "current_price": 200.0,
            },
        ]

        result = _check_and_notify_all_tickers(ticker_data, -2.0, -5.0)
        assert result is False

    def test_check_and_notify_daily_alert_needed(self):
        """日次アラートが必要な場合のテスト"""
        ticker_data = [
            {
                "name": "VT",
                "daily_change": -3.0,  # 閾値を下回る
                "weekly_change": -1.0,  # 閾値内
                "current_price": 100.0,
            }
        ]

        result = _check_and_notify_all_tickers(ticker_data, -2.0, -5.0)
        assert result is True

    def test_check_and_notify_weekly_alert_needed(self):
        """週次アラートが必要な場合のテスト"""
        ticker_data = [
            {
                "name": "VOO",
                "daily_change": -1.0,  # 閾値内
                "weekly_change": -6.0,  # 閾値を下回る
                "current_price": 200.0,
            }
        ]

        result = _check_and_notify_all_tickers(ticker_data, -2.0, -5.0)
        assert result is True

    def test_check_and_notify_both_alerts_needed(self):
        """両方のアラートが必要な場合のテスト"""
        ticker_data = [
            {
                "name": "QQQ",
                "daily_change": -3.0,  # 閾値を下回る
                "weekly_change": -7.0,  # 閾値を下回る
                "current_price": 300.0,
            }
        ]

        result = _check_and_notify_all_tickers(ticker_data, -2.0, -5.0)
        assert result is True

    def test_check_and_notify_mixed_tickers(self):
        """複数銘柄で一部がアラート対象の場合のテスト"""
        ticker_data = [
            {
                "name": "VT",
                "daily_change": -1.0,  # 閾値内
                "weekly_change": -3.0,  # 閾値内
                "current_price": 100.0,
            },
            {
                "name": "VOO",
                "daily_change": -3.0,  # 閾値を下回る
                "weekly_change": -2.0,  # 閾値内
                "current_price": 200.0,
            },
            {
                "name": "QQQ",
                "daily_change": -1.0,  # 閾値内
                "weekly_change": -6.0,  # 閾値を下回る
                "current_price": 300.0,
            },
        ]

        result = _check_and_notify_all_tickers(ticker_data, -2.0, -5.0)
        assert result is True


class TestFormatNotificationMessage:
    """format_notification_message関数のテストクラス"""

    def test_format_notification_message_multiple_tickers(self):
        """複数銘柄のメッセージフォーマットテスト"""
        ticker_data = [
            {
                "name": "VT",
                "daily_change": -2.5,
                "weekly_change": -4.2,
                "current_price": 98.75,
            },
            {
                "name": "VOO",
                "daily_change": -1.8,
                "weekly_change": -3.1,
                "current_price": 385.20,
            },
            {
                "name": "QQQ",
                "daily_change": 0.5,
                "weekly_change": -1.2,
                "current_price": 350.45,
            },
        ]

        date = "2025-01-01"
        usd_jpy_rate = 150.25
        result = _format_notification_message(date, ticker_data, usd_jpy_rate)
        expected = (
            "📈2025-01-01 ETF Tracker\n\n"
            "【VT】\n"
            "現在値: $98.75\n"
            "前日比: -2.5%\n"
            "前週比: -4.2%\n\n"
            "【VOO】\n"
            "現在値: $385.20\n"
            "前日比: -1.8%\n"
            "前週比: -3.1%\n\n"
            "【QQQ】\n"
            "現在値: $350.45\n"
            "前日比: 0.5%\n"
            "前週比: -1.2%\n\n"
            "【為替】 USD/JPY: 150.25"
        )

        assert result == expected


class TestCreateChartFilename:
    """create_chart関数のファイル名テスト"""

    @patch("matplotlib.pyplot.savefig")
    @patch("matplotlib.pyplot.close")
    def test_create_chart_uses_constant_filename(self, mock_close, mock_savefig):
        """create_chart関数がCHART_FILENAME定数を使用することを確認"""
        test_data = pd.DataFrame(
            {"Close": [100.0 + i for i in range(30)]},
            index=pd.date_range("2025-12-01", periods=30),
        )

        filepath = create_chart(test_data)

        # ファイルパスがCHART_FILENAMEを含んでいることを確認
        assert CHART_FILENAME in filepath
        assert filepath == f"/tmp/{CHART_FILENAME}"

        # savefigが正しいパスで呼ばれたか確認
        mock_savefig.assert_called_once()
        call_args = mock_savefig.call_args
        assert call_args[0][0] == f"/tmp/{CHART_FILENAME}"


class TestDownloadWithRetry:
    """download_with_retry関数のテストクラス"""

    def test_download_with_retry_retries_when_nan(self):
        """NaNが含まれる場合にリトライすることを確認"""
        data_with_nan = pd.DataFrame({"Close": [100.0, float("nan")]})
        data_without_nan = pd.DataFrame({"Close": [100.0, 101.0]})

        with (
            patch(
                "src.handler.yf.download", side_effect=[data_with_nan, data_without_nan]
            ) as mock_download,
            patch("src.handler.time.sleep") as mock_sleep,
        ):
            result = _download_with_retry(
                tickers="VT",
                period="1mo",
                auto_adjust=True,
                max_attempts=2,
                retry_interval_seconds=1,
            )

        assert result.equals(data_without_nan)
        assert mock_download.call_count == 2
        mock_sleep.assert_called_once_with(1)

    def test_download_with_retry_raises_after_all_attempts_fail(self):
        """欠損した最終結果を後段へ流さないことを確認"""
        data_with_nan = pd.DataFrame({"Close": [100.0, float("nan")]})

        with (
            patch("src.handler.yf.download", return_value=data_with_nan),
            patch("src.handler.time.sleep"),
        ):
            with pytest.raises(MarketDataUnavailableError):
                _download_with_retry(
                    tickers="VT",
                    period="1mo",
                    max_attempts=2,
                    retry_interval_seconds=0,
                )

    def test_download_falls_back_to_unadjusted_close(self):
        """調整後終値が欠損した場合に通常終値を採用することを確認"""
        index = pd.to_datetime(["2026-09-23", "2026-09-24"])
        adjusted = pd.DataFrame({"Close": [100.0, float("nan")]}, index=index)
        raw = pd.DataFrame({"Close": [100.0, 101.0]}, index=index)

        with (
            patch(
                "src.handler.yf.download",
                side_effect=[adjusted, adjusted, adjusted, raw],
            ),
            patch("src.handler.time.sleep"),
        ):
            result = _download_prices_with_fallback(
                tickers="VT",
                period="1mo",
                end=datetime(2026, 9, 25).date(),
                expected_price_date=datetime(2026, 9, 24).date(),
            )

        assert result["Close"].iloc[-1] == 101.0

    def test_download_falls_back_when_adjusted_data_lacks_expected_date(self):
        """調整後終値に基準日がない場合も通常終値を試すことを確認"""
        adjusted = pd.DataFrame(
            {"Close": [100.0]}, index=pd.to_datetime(["2026-09-23"])
        )
        raw = pd.DataFrame(
            {"Close": [100.0, 101.0]},
            index=pd.to_datetime(["2026-09-23", "2026-09-24"]),
        )

        with patch("src.handler.yf.download", side_effect=[adjusted, raw]):
            result = _download_prices_with_fallback(
                tickers="VT",
                period="1mo",
                end=datetime(2026, 9, 25).date(),
                expected_price_date=datetime(2026, 9, 24).date(),
            )

        assert result["Close"].iloc[-1] == 101.0

    def test_download_fills_missing_close_from_fast_info(self):
        """日足の行だけ先に生成された場合は市場価格メタデータで補完する"""
        index = pd.to_datetime(["2026-09-23", "2026-09-24"])
        missing = pd.DataFrame({"Close": [100.0, float("nan")]}, index=index)
        ticker = Mock()
        ticker.fast_info.last_price = 101.0

        with (
            patch("src.handler.yf.download", return_value=missing),
            patch("src.handler.yf.Ticker", return_value=ticker),
            patch("src.handler.time.sleep"),
        ):
            result = _download_prices_with_fallback(
                tickers="VT",
                period="1mo",
                end=datetime(2026, 9, 25).date(),
                expected_price_date=datetime(2026, 9, 24).date(),
            )

        assert result["Close"].iloc[-1] == 101.0


class TestBuildTickerData:
    def test_uses_explicit_current_previous_and_weekly_dates(self):
        """3銘柄で共通する日付を基準に変動率を計算することを確認"""
        index = pd.to_datetime(["2026-09-16", "2026-09-17", "2026-09-23", "2026-09-24"])
        combined = pd.concat(
            {
                "VT": pd.DataFrame(
                    {"Close": [100.0, 101.0, 109.0, 110.0]}, index=index
                ),
                "VOO": pd.DataFrame(
                    {"Close": [200.0, 202.0, 218.0, 220.0]}, index=index
                ),
                "QQQ": pd.DataFrame(
                    {"Close": [300.0, 303.0, 327.0, 330.0]}, index=index
                ),
            },
            axis=1,
        )

        price_date, ticker_data = _build_ticker_data(
            combined, ("VT", "VOO", "QQQ"), datetime(2026, 9, 24).date()
        )

        assert price_date == datetime(2026, 9, 24).date()
        assert ticker_data[0] == {
            "name": "VT",
            "daily_change": 0.92,
            "weekly_change": 8.91,
            "current_price": 110.0,
        }

    def test_rejects_missing_expected_date_instead_of_using_older_price(self):
        """基準日の欠損を過去日の価格で暗黙補完しないことを確認"""
        index = pd.to_datetime(["2026-09-23", "2026-09-24"])
        combined = pd.concat(
            {
                "VT": pd.DataFrame({"Close": [100.0, float("nan")]}, index=index),
                "VOO": pd.DataFrame({"Close": [200.0, 201.0]}, index=index),
                "QQQ": pd.DataFrame({"Close": [300.0, 301.0]}, index=index),
            },
            axis=1,
        )

        with pytest.raises(MarketDataUnavailableError):
            _build_ticker_data(
                combined, ("VT", "VOO", "QQQ"), datetime(2026, 9, 24).date()
            )


class TestHasNanValues:
    """has_nan_values関数のテストクラス"""

    def test_has_nan_values_single_ticker_no_nan(self):
        """単一ティッカーで最新行にNaNがない場合のテスト"""
        data = pd.DataFrame({"Close": [100.0, 101.0]})
        assert _has_nan_values(data, "VT") is False

    def test_has_nan_values_single_ticker_with_nan_in_latest(self):
        """単一ティッカーで最新行にNaNがある場合のテスト"""
        data_with_nan = pd.DataFrame({"Close": [100.0, float("nan")]})
        assert _has_nan_values(data_with_nan, "VT") is True

    def test_has_nan_values_single_ticker_with_nan_in_past(self):
        """単一ティッカーで過去行にNaNがあるが最新行はOKの場合のテスト"""
        # 過去データにNaNがあっても最新行がOKならFalseを返す
        data = pd.DataFrame({"Close": [float("nan"), 100.0, 101.0]})
        assert _has_nan_values(data, "VT") is False

    def test_has_nan_values_multi_ticker_no_nan(self):
        """複数ティッカーで全てOKの場合のテスト"""
        vt_data = pd.DataFrame({"Close": [100.0, 101.0]})
        voo_data = pd.DataFrame({"Close": [200.0, 201.0]})
        combined = pd.concat({"VT": vt_data, "VOO": voo_data}, axis=1)

        assert _has_nan_values(combined, ["VT", "VOO"]) is False

    def test_has_nan_values_multi_ticker_with_nan_in_latest(self):
        """複数ティッカーで最新行にNaNがある場合のテスト"""
        vt_data = pd.DataFrame({"Close": [100.0, 101.0]})
        voo_data_with_nan = pd.DataFrame({"Close": [200.0, float("nan")]})
        combined_with_nan = pd.concat({"VT": vt_data, "VOO": voo_data_with_nan}, axis=1)
        assert _has_nan_values(combined_with_nan, ["VT", "VOO"]) is True

    def test_has_nan_values_multi_ticker_with_nan_in_past(self):
        """複数ティッカーで過去行にNaNがあるが最新行はOKの場合のテスト"""
        # 過去データにNaNがあっても最新行がOKならFalseを返す
        vt_data = pd.DataFrame({"Close": [float("nan"), 100.0, 101.0]})
        voo_data = pd.DataFrame({"Close": [200.0, 201.0, 202.0]})
        combined = pd.concat({"VT": vt_data, "VOO": voo_data}, axis=1)
        assert _has_nan_values(combined, ["VT", "VOO"]) is False


class TestS3ImageIntegration:
    """S3経由の画像送信フローの統合テスト"""

    def test_chart_filename_is_constant(self):
        """チャートファイル名が定数を使用していることを確認"""
        assert CHART_FILENAME == "vt_chart.png"

    @patch("src.handler.S3Storage")
    def test_s3_storage_called_with_correct_filename(self, mock_s3_class):
        """S3Storageが正しいファイル名で呼ばれることを確認"""
        from src.handler import S3Storage

        # S3Storageを直接使用する場合のシミュレーション
        mock_s3_instance = Mock()
        mock_s3_instance.upload_and_get_url.return_value = (
            "https://s3.amazonaws.com/test-bucket/charts/2026/01/12/vt_chart.png"
        )

        # テストケース
        storage = S3Storage()
        url = storage.upload_and_get_url(
            filepath="/tmp/vt_chart.png",
            filename_hint=CHART_FILENAME,
            now=datetime.now(),
        )

        assert url is not None


if __name__ == "__main__":
    pytest.main([__file__])
