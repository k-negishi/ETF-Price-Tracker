"""S3 storage module for uploading and managing chart images."""

import os
from datetime import datetime
from typing import Optional

import boto3
from botocore.exceptions import ClientError

# チャートファイル名定数
CHART_FILENAME = "vt_chart.png"


class S3StorageError(Exception):
    """S3ストレージ操作のカスタム例外"""

    pass


class S3Storage:
    """S3への画像アップロードとpresigned URL生成を管理するクラス"""

    def __init__(self, bucket_name: Optional[str] = None) -> None:
        """
        Initialize S3Storage.

        Args:
            bucket_name: S3バケット名（省略時は環境変数S3_BUCKETから取得）

        Raises:
            ValueError: S3_BUCKETが設定されていない場合
        """
        self.bucket_name = bucket_name or os.getenv("S3_BUCKET")

        if not self.bucket_name:
            raise ValueError("環境変数S3_BUCKETが設定されていません。")

        # boto3クライアントの初期化
        self.s3_client = boto3.client("s3")

    def build_s3_key(self, filename: str, now: datetime) -> str:
        """
        S3キーを生成（charts/YYYY/MM/DD/filename形式）

        Args:
            filename: ファイル名（例: vt_chart.png）
            now: 現在日時

        Returns:
            str: S3キー（例: charts/2026/01/12/vt_chart.png）
        """
        # YYYY/MM/DD形式で年月日を取得（ゼロパディング）
        year = now.strftime("%Y")
        month = now.strftime("%m")
        day = now.strftime("%d")

        return f"charts/{year}/{month}/{day}/{filename}"

    def upload_file(self, filepath: str, key: str) -> None:
        """
        ファイルをS3にアップロード

        Args:
            filepath: ローカルファイルパス
            key: S3キー

        Raises:
            S3StorageError: アップロード失敗時
        """
        try:
            self.s3_client.upload_file(
                Filename=filepath,
                Bucket=self.bucket_name,
                Key=key,
                ExtraArgs={"ContentType": "image/png"},
            )
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", "Unknown error")
            raise S3StorageError(
                f"S3アップロード失敗: {error_code} - {error_message}"
            ) from e
        except FileNotFoundError as e:
            raise S3StorageError(f"ファイルが見つかりません: {filepath}") from e
        except Exception as e:
            raise S3StorageError(f"予期しないエラーが発生しました: {str(e)}") from e

    def create_presigned_url(self, key: str, expires_in: int = 3600) -> str:
        """
        presigned URL（GET）を生成

        Args:
            key: S3キー
            expires_in: URL有効期限（秒）、デフォルト3600秒

        Returns:
            str: presigned URL（HTTPS）

        Raises:
            S3StorageError: URL生成失敗時
        """
        try:
            url: str = self.s3_client.generate_presigned_url(
                ClientMethod="get_object",
                Params={"Bucket": self.bucket_name, "Key": key},
                ExpiresIn=expires_in,
            )
            return url
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", "Unknown error")
            raise S3StorageError(
                f"presigned URL生成失敗: {error_code} - {error_message}"
            ) from e
        except Exception as e:
            raise S3StorageError(f"予期しないエラーが発生しました: {str(e)}") from e

    def upload_and_get_url(
        self, filepath: str, filename_hint: str, now: datetime
    ) -> str:
        """
        ファイルをS3にアップロードしてpresigned URLを返す

        Args:
            filepath: ローカルファイルパス
            filename_hint: ファイル名のヒント（S3キー生成に使用）
            now: 現在日時（S3キー生成に使用）

        Returns:
            str: presigned URL

        Raises:
            S3StorageError: アップロードまたはURL生成失敗時
        """
        # S3キーを生成
        s3_key = self.build_s3_key(filename_hint, now)

        # アップロード実行
        self.upload_file(filepath, s3_key)

        # presigned URLを生成して返す
        return self.create_presigned_url(s3_key)
