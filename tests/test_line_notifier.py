import unittest
from unittest.mock import MagicMock, patch

from dotenv import load_dotenv

from src.line_notifier import LineMessagingNotifier

load_dotenv()


class TestLineNotifier(unittest.TestCase):
    @patch("src.line_notifier.requests.post")
    @patch("src.line_notifier.os.getenv")
    def test_send_message_success(self, mock_getenv: MagicMock, mock_post: MagicMock) -> None:
        # Arrange
        mock_getenv.side_effect = lambda key: {
            "LINE_CHANNEL_ACCESS_TOKEN": "dummy_token",
            "LINE_USER_ID": "dummy_user",
        }.get(key)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        notifier = LineMessagingNotifier()
        message = "Test message"

        # Act
        result = notifier.send_message(message)

        # Assert
        expected_headers = {
            "Authorization": "Bearer dummy_token",
            "Content-Type": "application/json",
            "User-Agent": "StockAlertBot/2.0",
        }
        expected_payload = {
            "to": "dummy_user",
            "messages": [{"type": "text", "text": message}],
        }
        mock_post.assert_called_once_with(
            "https://api.line.me/v2/bot/message/push",
            headers=expected_headers,
            json=expected_payload,
            timeout=10,
        )
        self.assertEqual(result, {"status": "success"})

    @patch("src.line_notifier.requests.post")
    @patch("src.line_notifier.os.getenv")
    def test_send_message_failure(self, mock_getenv: MagicMock, mock_post: MagicMock) -> None:
        # Arrange
        mock_getenv.side_effect = lambda key: {
            "LINE_CHANNEL_ACCESS_TOKEN": "dummy_token",
            "LINE_USER_ID": "dummy_user",
        }.get(key)

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_post.return_value = mock_response

        notifier = LineMessagingNotifier()
        message = "Test message"

        # Act & Assert
        with self.assertRaisesRegex(
            Exception, "LINE API エラー: HTTP 400, Message: Bad Request"
        ):
            notifier.send_message(message)

    @patch("src.line_notifier.os.getenv")
    def test_init_raises_error_if_env_vars_missing(self, mock_getenv: MagicMock) -> None:
        # Arrange
        mock_getenv.return_value = None

        # Act & Assert
        with self.assertRaisesRegex(ValueError, "環境変数が設定されていません。"):
            LineMessagingNotifier()