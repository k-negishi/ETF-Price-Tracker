import os
import sys
from unittest.mock import Mock, patch, MagicMock

import pandas as pd
import pytest

# プロジェクトのルートディレクトリをPythonパスに追加
project_root = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'src'))

from src.handler import (
    is_below_threshold,
    calculate_daily_change,
    calculate_weekly_change,
    check_and_notify_all_tickers,
    format_notification_message
)


class TestIsBelowThreshold:
    """is_below_threshold関数のテストクラス"""

    def test_is_below_threshold_true_case(self):
        """閾値を下回る場合のテスト"""
        assert is_below_threshold(-3.0, -2.0) is True
        assert is_below_threshold(-2.0, -2.0) is True  # 等しい場合もTrue

    def test_is_below_threshold_false_case(self):
        """閾値を上回る場合のテスト"""
        assert is_below_threshold(-1.0, -2.0) is False
        assert is_below_threshold(0.0, -1.0) is False

    def test_is_below_threshold_edge_cases(self):
        """エッジケースのテスト"""
        assert is_below_threshold(0.0, 0.0) is True
        assert is_below_threshold(-0.1, 0.0) is True
        assert is_below_threshold(0.1, 0.0) is False


class TestCalculateDailyChange:
    """calculate_daily_change関数のテストクラス"""

    def test_calculate_daily_change_positive(self):
        """前日比プラスの場合のテスト"""
        # テストデータ作成
        test_data = pd.DataFrame({
            'Close': [100.0, 105.0]  # 5%の上昇
        })

        result = calculate_daily_change(test_data)
        assert result == 5.0

    def test_calculate_daily_change_negative(self):
        """前日比マイナスの場合のテスト"""
        test_data = pd.DataFrame({
            'Close': [100.0, 97.0]  # 3%の下落
        })

        result = calculate_daily_change(test_data)
        assert result == -3.0

    def test_calculate_daily_change_no_change(self):
        """前日比変化なしの場合のテスト"""
        test_data = pd.DataFrame({
            'Close': [100.0, 100.0]  # 変化なし
        })

        result = calculate_daily_change(test_data)
        assert result == 0.0


class TestCalculateWeeklyChange:
    """calculate_weekly_change関数のテストクラス"""

    def test_calculate_weekly_change_positive(self):
        """1週間前比プラスの場合のテスト"""
        test_data = pd.DataFrame({
            'Close': [100.0, 102.0, 104.0, 103.0, 110.0]  # 10%の上昇
        })

        result = calculate_weekly_change(test_data)
        assert result == 10.0

    def test_calculate_weekly_change_negative(self):
        """1週間前比マイナスの場合のテスト"""
        test_data = pd.DataFrame({
            'Close': [100.0, 98.0, 96.0, 94.0, 90.0]  # 10%の下落
        })

        result = calculate_weekly_change(test_data)
        assert result == -10.0

    def test_calculate_weekly_change_no_change(self):
        """1週間前比変化なしの場合のテスト"""
        test_data = pd.DataFrame({
            'Close': [100.0, 102.0, 98.0, 105.0, 100.0]  # 変化なし
        })

        result = calculate_weekly_change(test_data)
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

        result = check_and_notify_all_tickers(ticker_data, -2.0, -5.0)
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

        result = check_and_notify_all_tickers(ticker_data, -2.0, -5.0)
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

        result = check_and_notify_all_tickers(ticker_data, -2.0, -5.0)
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

        result = check_and_notify_all_tickers(ticker_data, -2.0, -5.0)
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

        result = check_and_notify_all_tickers(ticker_data, -2.0, -5.0)
        assert result is True

class TestFormatNotificationMessage:
    """format_notification_message関数のテストクラス"""
    def test_format_notification_message_multiple_tickers(self):
        """複数銘柄のメッセージフォーマットテスト"""
        ticker_data = [
            {
                'name': 'VT',
                'daily_change': -2.5,
                'weekly_change': -4.2,
                'current_price': 98.75
            },
            {
                'name': 'VOO',
                'daily_change': -1.8,
                'weekly_change': -3.1,
                'current_price': 385.20
            },
            {
                'name': 'QQQ',
                'daily_change': 0.5,
                'weekly_change': -1.2,
                'current_price': 350.45
            }
        ]

        result = format_notification_message(ticker_data)

        expected = ("📊 株価下落アラート\n\n"
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
                    "前週比: -1.2%")

        assert result == expected

class TestIntegration:
    """統合テスト"""

    @patch('yfinance.download')
    @patch('handler.LineMessagingNotifier')
    def test_main_workflow_no_notification(self, mock_notifier, mock_yf_download):
        """通知が不要な場合の統合テスト"""
        # yfinanceのモックデータ設定
        mock_data = MagicMock()
        mock_data.index = [
            pd.Timestamp('2024-01-01'),
            pd.Timestamp('2024-01-02'),
            pd.Timestamp('2024-01-03'),
            pd.Timestamp('2024-01-04'),
            pd.Timestamp('2024-01-05')
        ]
        mock_data.__getitem__.return_value = pd.DataFrame({
            'Close': [100.0, 101.0, 102.0, 103.0, 104.0]
        })
        mock_yf_download.return_value = mock_data

        # 実際のworkflowをシミュレート
        targets = ['VT', 'VOO', 'QQQ']
        all_data = mock_yf_download(targets, period='1mo', group_by='ticker', auto_adjust=True)

        # 各ティッカーのデータを取得
        vt_data = all_data['VT']
        voo_data = all_data['VOO']
        qqq_data = all_data['QQQ']

        # 計算実行
        vt_daily_change = calculate_daily_change(vt_data)
        vt_weekly_change = calculate_weekly_change(vt_data)

        # 閾値チェック（通知不要な設定）
        ticker_data_for_check = [{
            'name': 'VT',
            'daily_change': vt_daily_change,
            'weekly_change': vt_weekly_change,
            'current_price': vt_data['Close'].iloc[-1]
        }]

        notification_needed = check_and_notify_all_tickers(
            ticker_data_for_check, -10.0, -15.0  # 厳しい閾値設定
        )

        # アサーション
        assert notification_needed is False
        mock_notifier.assert_not_called()

    @patch('yfinance.download')
    @patch('handler.LineMessagingNotifier')
    def test_main_workflow_with_notification(self, mock_notifier, mock_yf_download):
        """通知が必要な場合の統合テスト"""
        # yfinanceのモックデータ設定（下落パターン）
        mock_data = MagicMock()
        mock_data.index = [
            pd.Timestamp('2024-01-01'),
            pd.Timestamp('2024-01-02'),
            pd.Timestamp('2024-01-03'),
            pd.Timestamp('2024-01-04'),
            pd.Timestamp('2024-01-05')
        ]
        mock_data.__getitem__.return_value = pd.DataFrame({
            'Close': [100.0, 98.0, 96.0, 94.0, 90.0]  # 急落パターン
        })
        mock_yf_download.return_value = mock_data

        # モック通知インスタンス設定
        mock_notifier_instance = Mock()
        mock_notifier.return_value = mock_notifier_instance

        # 実際のworkflowをシミュレート
        targets = ['VT']
        all_data = mock_yf_download(targets, period='1mo', group_by='ticker', auto_adjust=True)

        vt_data = all_data['VT']
        vt_daily_change = calculate_daily_change(vt_data)
        vt_weekly_change = calculate_weekly_change(vt_data)

        ticker_data_for_check = [{
            'name': 'VT',
            'daily_change': vt_daily_change,
            'weekly_change': vt_weekly_change,
            'current_price': vt_data['Close'].iloc[-1]
        }]

        notification_needed = check_and_notify_all_tickers(
            ticker_data_for_check, -2.0, -5.0  # 通常の閾値設定
        )

        # 通知実行をシミュレート
        if notification_needed:
            line_notifier = mock_notifier()
            message = format_notification_message(ticker_data_for_check)
            line_notifier.send_message(message)

        # アサーション
        assert notification_needed is True
        mock_notifier.assert_called_once()
        mock_notifier_instance.send_message.assert_called_once()

if __name__ == '__main__':
    pytest.main([__file__])
