import os
from datetime import datetime
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import pytest
from dotenv import load_dotenv

from src.line_notifier import LineMessagingNotifier

load_dotenv()


class TestLineNotifier:
    def test_line_notifier(self):
        # CI環境ではスキップ
        if os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true":
            return
        if not os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or not os.getenv("LINE_USER_ID"):
            pytest.skip("LINE環境変数が未設定のためスキップします。")

        line_notifier = LineMessagingNotifier()

        jst_timezone = ZoneInfo("Asia/Tokyo")
        datetime_format = "%Y/%m/%d %H:%M:%S"
        current_jst_time = datetime.now(jst_timezone).strftime(datetime_format)
        test_message = f"test{current_jst_time}"

        line_notifier.send_message(test_message)


class TestLineMessagingNotifierImageUrl:
    """send_image_url メソッドのテストクラス"""

    @patch("requests.post")
    @patch.dict(
        os.environ,
        {
            "LINE_CHANNEL_ACCESS_TOKEN": "test-token",
            "LINE_USER_ID": "test-user",
        },
    )
    def test_send_image_url_success(self, mock_post):
        """画像URL送信成功のテスト"""
        # モックレスポンス設定
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        notifier = LineMessagingNotifier()
        result = notifier.send_image_url("https://example.com/image.png")

        assert result == {"status": "success"}

        # 正しいペイロードで呼ばれたか確認
        call_args = mock_post.call_args
        payload = call_args[1]["json"]

        assert payload["to"] == "test-user"
        assert payload["messages"][0]["type"] == "image"
        assert (
            payload["messages"][0]["originalContentUrl"]
            == "https://example.com/image.png"
        )
        assert (
            payload["messages"][0]["previewImageUrl"] == "https://example.com/image.png"
        )

    @patch.dict(
        os.environ,
        {
            "LINE_CHANNEL_ACCESS_TOKEN": "test-token",
            "LINE_USER_ID": "test-user",
        },
    )
    def test_send_image_url_non_https_raises_error(self):
        """HTTPS以外のURLでエラー発生のテスト"""
        notifier = LineMessagingNotifier()

        with pytest.raises(ValueError, match="HTTPSである必要があります"):
            notifier.send_image_url("http://example.com/image.png")

    @patch("requests.post")
    @patch.dict(
        os.environ,
        {
            "LINE_CHANNEL_ACCESS_TOKEN": "test-token",
            "LINE_USER_ID": "test-user",
        },
    )
    def test_send_image_url_api_error(self, mock_post):
        """LINE APIエラー時のテスト"""
        # エラーレスポンス設定
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_post.return_value = mock_response

        notifier = LineMessagingNotifier()

        with pytest.raises(Exception, match="LINE API エラー"):
            notifier.send_image_url("https://example.com/image.png")
