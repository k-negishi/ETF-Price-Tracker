import os
import time
from functools import wraps
from typing import Any, Callable, Dict, TypeVar

import requests
from typing_extensions import ParamSpec

P = ParamSpec("P")
R = TypeVar("R")


def retry_notification(
    max_retries: int = 3, delay: int = 10
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    通知送信用リトライデコレータ

    Args:
        max_retries (int): 最大リトライ回数
        delay (int): リトライ間隔（秒）
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            last_exception: Exception | None = None

            for attempt in range(max_retries):
                try:
                    result = func(*args, **kwargs)
                    return result
                except Exception as e:
                    last_exception = e

                    if attempt < max_retries - 1:
                        time.sleep(delay)

            raise last_exception if last_exception else Exception("通知送信失敗")

        return wrapper

    return decorator


class LineMessagingNotifier:
    """
    LINE Messaging APIを使用した簡易通知サービス
    """

    def __init__(self) -> None:
        """
        初期化
        """
        # 環境変数から値を取得
        self.channel_access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
        self.user_id = os.getenv("LINE_USER_ID")

        if not self.channel_access_token or not self.user_id:
            raise ValueError("環境変数が設定されていません。")

        # API設定
        self.api_url = "https://api.line.me/v2/bot/message/push"
        self.timeout = 10  # タイムアウト設定（秒）

        # ヘッダー設定
        self.headers = {
            "Authorization": f"Bearer {self.channel_access_token}",
            "Content-Type": "application/json",
            "User-Agent": "StockAlertBot/2.0",
        }

    @retry_notification(max_retries=3, delay=10)
    def send_message(self, message: str) -> Dict[str, Any]:
        """
        LINE通知メッセージを送信（リトライ機能付き）

        Args:
            message (str): 送信するメッセージ

        Returns:
            dict: API レスポンス
        """
        # リクエストボディ作成
        payload = {"to": self.user_id, "messages": [{"type": "text", "text": message}]}

        # API リクエスト送信
        response = requests.post(
            self.api_url, headers=self.headers, json=payload, timeout=self.timeout
        )

        if response.status_code == 200:
            return {"status": "success"}
        else:
            raise Exception(
                f"LINE API エラー: HTTP {response.status_code}, Message: {response.text}"
            )

    @retry_notification(max_retries=3, delay=10)
    def send_image(self, image_url: str) -> Dict[str, Any]:
        """
        LINEに画像URLを送信（リトライ機能付き）

        Args:
            image_url (str): 送信する画像のURL

        Returns:
            dict: API レスポンス
        """
        # リクエストボディ作成
        payload = {
            "to": self.user_id,
            "messages": [
                {
                    "type": "image",
                    "originalContentUrl": image_url,
                    "previewImageUrl": image_url,
                }
            ],
        }

        # API リクエスト送信
        response = requests.post(
            self.api_url, headers=self.headers, json=payload, timeout=self.timeout
        )

        if response.status_code == 200:
            return {"status": "success"}
        else:
            raise Exception(
                f"LINE API エラー: HTTP {response.status_code}, Message: {response.text}"
            )
