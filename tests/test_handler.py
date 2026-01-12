import os
import sys
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# プロジェクトのルートディレクトリをPythonパスに追加
project_root = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'src'))

from src.handler import (
    _is_below_threshold,
    _calculate_daily_change,
    _calculate_weekly_change,
    _check_and_notify_all_tickers,
    _format_notification_message,
    _generate_vt_graph
)


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
        test_data = pd.DataFrame({
            'Close': [100.0, 105.0]  # 5%の上昇
        })

        result = _calculate_daily_change(test_data)
        assert result == 5.0

    def test_calculate_daily_change_negative(self):
        """前日比マイナスの場合のテスト"""
        test_data = pd.DataFrame({
            'Close': [100.0, 97.0]  # 3%の下落
        })

        result = _calculate_daily_change(test_data)
        assert result == -3.0

    def test_calculate_daily_change_no_change(self):
        """前日比変化なしの場合のテスト"""
        test_data = pd.DataFrame({
            'Close': [100.0, 100.0]  # 変化なし
        })

        result = _calculate_daily_change(test_data)
        assert result == 0.0


class TestCalculateWeeklyChange:
    """calculate_weekly_change関数のテストクラス"""

    def test_calculate_weekly_change_positive(self):
        """1週間前比プラスの場合のテスト"""
        test_data = pd.DataFrame({
            'Close': [100.0, 102.0, 104.0, 103.0, 110.0]  # 10%の上昇
        })

        result = _calculate_weekly_change(test_data)
        assert result == 10.0

    def test_calculate_weekly_change_negative(self):
        """1週間前比マイナスの場合のテスト"""
        test_data = pd.DataFrame({
            'Close': [100.0, 98.0, 96.0, 94.0, 90.0]  # 10%の下落
        })

        result = _calculate_weekly_change(test_data)
        assert result == -10.0

    def test_calculate_weekly_change_no_change(self):
        """1週間前比変化なしの場合のテスト"""
        test_data = pd.DataFrame({
            'Close': [100.0, 102.0, 98.0, 105.0, 100.0]  # 変化なし
        })

        result = _calculate_weekly_change(test_data)
        assert result == 0.0

class TestCheckAndNotifyAllTickers:
    """check_and_notify_all_tickers関数のテストクラス"""

    def test_check_and_notify_no_alert_needed(self):
        """アラートが不要な場合のテスト"""
        ticker_data = [
            {
                'name': 'VT',
                'daily_change': -1.0,  # 閾値内
                'weekly_change': -3.0,  # 閾値内
                'current_price': 100.0
            },
            {
                'name': 'VOO',
                'daily_change': 1.0,   # プラス
                'weekly_change': -2.0,  # 閾値内
                'current_price': 200.0
            }
        ]

        result = _check_and_notify_all_tickers(ticker_data, -2.0, -5.0)
        assert result is False

    def test_check_and_notify_daily_alert_needed(self):
        """日次アラートが必要な場合のテスト"""
        ticker_data = [
            {
                'name': 'VT',
                'daily_change': -3.0,  # 閾値を下回る
                'weekly_change': -1.0,  # 閾値内
                'current_price': 100.0
            }
        ]

        result = _check_and_notify_all_tickers(ticker_data, -2.0, -5.0)
        assert result is True

    def test_check_and_notify_weekly_alert_needed(self):
        """週次アラートが必要な場合のテスト"""
        ticker_data = [
            {
                'name': 'VOO',
                'daily_change': -1.0,  # 閾値内
                'weekly_change': -6.0,  # 閾値を下回る
                'current_price': 200.0
            }
        ]

        result = _check_and_notify_all_tickers(ticker_data, -2.0, -5.0)
        assert result is True

    def test_check_and_notify_both_alerts_needed(self):
        """両方のアラートが必要な場合のテスト"""
        ticker_data = [
            {
                'name': 'QQQ',
                'daily_change': -3.0,  # 閾値を下回る
                'weekly_change': -7.0,  # 閾値を下回る
                'current_price': 300.0
            }
        ]

        result = _check_and_notify_all_tickers(ticker_data, -2.0, -5.0)
        assert result is True

    def test_check_and_notify_mixed_tickers(self):
        """複数銘柄で一部がアラート対象の場合のテスト"""
        ticker_data = [
            {
                'name': 'VT',
                'daily_change': -1.0,  # 閾値内
                'weekly_change': -3.0,  # 閾値内
                'current_price': 100.0
            },
            {
                'name': 'VOO',
                'daily_change': -3.0,  # 閾値を下回る
                'weekly_change': -2.0,  # 閾値内
                'current_price': 200.0
            },
            {
                'name': 'QQQ',
                'daily_change': -1.0,  # 閾値内
                'weekly_change': -6.0,  # 閾値を下回る
                'current_price': 300.0
            }
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
            "📈ETF Price Tracker 2025-01-01\n\n"
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
            "【為替】\n"
            "USD/JPY: 150.25"
        )

        assert result == expected


class TestGenerateVtGraph:
    """_generate_vt_graph関数のテストクラス"""

    @patch("src.handler.plt")
    def test_generate_vt_graph(self, mock_plt):
        """グラフが正常に生成され、指定したパスに保存されることをテスト"""
        # モックの設定
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)

        # テストデータの作成
        vt_data = pd.DataFrame(
            {"Close": [100, 105, 102]},
            index=pd.to_datetime(["2023-01-01", "2023-01-02", "2023-01-03"]),
        )

        # テスト対象関数の実行
        file_path = _generate_vt_graph(vt_data)

        # アサーション
        mock_plt.style.use.assert_called_with("dark_background")
        mock_plt.subplots.assert_called_with(figsize=(10, 6))
        mock_ax.plot.assert_called_with(
            vt_data.index, vt_data["Close"], label="VT Close Price", color="cyan"
        )
        mock_ax.set_title.assert_called_with("VT 6-Month Price Trend", color="white")
        mock_fig.savefig.assert_called_once()
        assert file_path.startswith("/tmp/etf_graphs/vt_graph_")
        assert file_path.endswith(".png")


if __name__ == "__main__":
    pytest.main([__file__])
