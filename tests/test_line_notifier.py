import os
import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from src.line_notifier import LineMessagingNotifier

load_dotenv()


class TestLineNotifier(unittest.TestCase):
    @patch.dict(
        os.environ,
        {
            "LINE_CHANNEL_ACCESS_TOKEN": "test_token",
            "LINE_USER_ID": "test_user",
        },
    )
    @patch("src.line_notifier.requests.post")
    def test_line_notifier(self, mock_post):
        # CI環境ではスキップ
        if os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true":
            return
        mock_post.return_value.status_code = 200

        line_notifier = LineMessagingNotifier()

        jst_timezone = ZoneInfo("Asia/Tokyo")
        datetime_format = "%Y/%m/%d %H:%M:%S"
        current_jst_time = datetime.now(jst_timezone).strftime(datetime_format)
        test_message = f"test{current_jst_time}"

        line_notifier.send_message(test_message)
        mock_post.assert_called_once()

    @patch.dict(
        os.environ,
        {
            "LINE_CHANNEL_ACCESS_TOKEN": "test_token",
            "LINE_USER_ID": "test_user",
        },
    )
    @patch("src.line_notifier.requests.post")
    def test_send_image(self, mock_post):
        mock_post.return_value.status_code = 200
        line_notifier = LineMessagingNotifier()
        image_url = "https://example.com/image.png"
        line_notifier.send_image(image_url)
        mock_post.assert_called_once()
        sent_payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(sent_payload["messages"][0]["type"], "image")
        self.assertEqual(
            sent_payload["messages"][0]["originalContentUrl"], image_url
        )
