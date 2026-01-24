import os
import time
from typing import Any, Dict

import requests
from dotenv import find_dotenv, load_dotenv


class LineMessagingRetryableError(Exception):
    """リトライ対象のLINE送信エラー"""

    pass


class LineMessagingNotifier:
    """
    LINE Messaging APIを使用した簡易通知サービス
    """

    def __init__(self) -> None:
        """
        初期化
        """
        # ローカル実行時のみ .env を読む（本番は環境変数注入）
        if not os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or not os.getenv("LINE_USER_ID"):
            load_dotenv(find_dotenv())

        # 環境変数から値を取得
        self.channel_access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
        self.user_id = os.getenv("LINE_USER_ID")

        if not self.channel_access_token or not self.user_id:
            raise ValueError("環境変数が設定されていません。")

        # API設定
        self.api_url = "https://api.line.me/v2/bot/message/push"
        self.timeout = 10  # タイムアウト設定（秒）
        self.max_retries = 3
        self.retry_delay = 10

        # ヘッダー設定
        self.headers = {
            "Authorization": f"Bearer {self.channel_access_token}",
            "Content-Type": "application/json",
            "User-Agent": "StockAlertBot/2.0",
        }

    def send_messages(
        self, messages: list[Dict[str, Any]], retry_key: str | None = None
    ) -> Dict[str, Any]:
        """
        LINE通知メッセージを送信

        Args:
            messages (list[dict]): 送信するメッセージ配列
            retry_key (str | None): 冪等性確保用のリトライキー（オプション）

        Returns:
            dict: API レスポンス
        """
        for message in messages:
            if message.get("type") == "image":
                image_url = message.get("originalContentUrl", "")
                if not isinstance(image_url, str) or not image_url.startswith(
                    "https://"
                ):
                    raise ValueError(f"画像URLはHTTPSである必要があります: {image_url}")

        payload = {"to": self.user_id, "messages": messages}
        headers = dict(self.headers)
        if retry_key:
            headers["X-Line-Retry-Key"] = retry_key
        last_exception: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    self.api_url, headers=headers, json=payload, timeout=self.timeout
                )

                if response.status_code == 200:
                    return {"status": "success"}

                error = Exception(
                    "LINE API エラー: "
                    f"HTTP {response.status_code}, Message: {response.text}"
                )
                if 400 <= response.status_code < 500 and response.status_code != 429:
                    raise error
                raise LineMessagingRetryableError(str(error))
            except LineMessagingRetryableError as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                    continue
                raise
            except requests.RequestException as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                    continue
                raise

        raise last_exception if last_exception else Exception("通知送信失敗")

    def send_message(
        self, message: str, retry_key: str | None = None
    ) -> Dict[str, Any]:
        """
        テキストメッセージを送信

        Args:
            message (str): 送信するテキスト
            retry_key (str | None): 冪等性確保用のリトライキー

        Returns:
            dict: API レスポンス
        """
        return self.send_messages([{"type": "text", "text": message}], retry_key)

    def send_image_url(
        self, image_url: str, retry_key: str | None = None
    ) -> Dict[str, Any]:
        """
        画像URLメッセージを送信

        Args:
            image_url (str): 送信する画像URL（HTTPS必須）
            retry_key (str | None): 冪等性確保用のリトライキー

        Returns:
            dict: API レスポンス
        """
        return self.send_messages(
            [
                {
                    "type": "image",
                    "originalContentUrl": image_url,
                    "previewImageUrl": image_url,
                }
            ],
            retry_key,
        )
