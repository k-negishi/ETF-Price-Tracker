from unittest.mock import MagicMock, patch

from src.line_notifier import LineMessagingNotifier


class TestLineNotifier:
    @patch("requests.post")
    @patch("os.getenv")
    def test_send_message_success(self, mock_getenv, mock_post):
        # Arrange
        mock_getenv.side_effect = lambda key: {
            "LINE_CHANNEL_ACCESS_TOKEN": "dummy_token",
            "LINE_USER_ID": "dummy_user",
        }.get(key)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        line_notifier = LineMessagingNotifier()
        test_message = "test message"

        # Act
        result = line_notifier.send_message(test_message)

        # Assert
        assert result == {"status": "success"}
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args.kwargs["json"]["to"] == "dummy_user"
        assert call_args.kwargs["json"]["messages"][0]["text"] == test_message

    @patch("requests.post")
    @patch("os.getenv")
    @patch("builtins.open")
    def test_send_image_file_success(self, mock_open, mock_getenv, mock_post):
        # Arrange
        mock_getenv.side_effect = lambda key: {
            "LINE_CHANNEL_ACCESS_TOKEN": "dummy_token",
            "LINE_USER_ID": "dummy_user",
        }.get(key)

        mock_upload_response = MagicMock()
        mock_upload_response.raise_for_status.return_value = None
        mock_upload_response.json.return_value = {"contentId": "dummy_content_id"}

        mock_push_response = MagicMock()
        mock_push_response.raise_for_status.return_value = None
        mock_post.side_effect = [mock_upload_response, mock_push_response]

        line_notifier = LineMessagingNotifier()
        test_filepath = "/tmp/test.png"

        # Act
        result = line_notifier.send_image_file(test_filepath)

        # Assert
        assert result == {"status": "success"}
        assert mock_post.call_count == 2
        mock_open.assert_called_once_with(test_filepath, "rb")

        # 1. Upload call
        upload_call = mock_post.call_args_list[0]
        assert upload_call.args[0] == "https://api-data.line.me/v2/bot/message/upload"
        assert upload_call.kwargs["headers"]["Content-Type"] == "image/png"

        # 2. Push call
        push_call = mock_post.call_args_list[1]
        assert push_call.args[0] == "https://api.line.me/v2/bot/message/push"
        push_payload = push_call.kwargs["json"]
        assert push_payload["to"] == "dummy_user"
        assert (
            push_payload["messages"][0]["originalContentUrl"]
            == "content://dummy_content_id"
        )
