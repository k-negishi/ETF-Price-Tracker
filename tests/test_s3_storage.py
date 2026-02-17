"""Tests for S3Storage module."""

import os
from datetime import datetime
from unittest.mock import Mock, patch

import pytest
from botocore.exceptions import ClientError

from src.s3_storage import CHART_FILENAME, S3Storage, S3StorageError


class TestS3Storage:
    """S3Storageクラスのテストクラス"""

    def test_init_with_bucket_name(self):
        """バケット名を指定して初期化"""
        with patch("boto3.client"):
            storage = S3Storage(bucket_name="test-bucket")
            assert storage.bucket_name == "test-bucket"

    def test_init_from_env_variable(self):
        """環境変数からバケット名を取得"""
        with patch.dict(os.environ, {"S3_BUCKET": "env-bucket"}):
            with patch("boto3.client"):
                storage = S3Storage()
                assert storage.bucket_name == "env-bucket"

    def test_init_without_bucket_raises_error(self):
        """バケット名が未設定の場合エラー"""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(
                ValueError, match="環境変数S3_BUCKETが設定されていません"
            ):
                S3Storage()

    def test_build_s3_key(self):
        """S3キー生成のテスト"""
        with patch("boto3.client"):
            storage = S3Storage(bucket_name="test-bucket")
            test_date = datetime(2026, 1, 12, 10, 30, 0)

            key = storage.build_s3_key("vt_chart.png", test_date)

            assert key == "charts/2026/01/12/vt_chart.png"

    def test_build_s3_key_different_dates(self):
        """異なる日付でのS3キー生成"""
        with patch("boto3.client"):
            storage = S3Storage(bucket_name="test-bucket")

            # 12月31日
            key1 = storage.build_s3_key("chart.png", datetime(2025, 12, 31))
            assert key1 == "charts/2025/12/31/chart.png"

            # 1月1日
            key2 = storage.build_s3_key("chart.png", datetime(2026, 1, 1))
            assert key2 == "charts/2026/01/01/chart.png"

    @patch("boto3.client")
    def test_upload_file_success(self, mock_boto_client):
        """ファイルアップロード成功のテスト"""
        mock_s3 = Mock()
        mock_boto_client.return_value = mock_s3

        storage = S3Storage(bucket_name="test-bucket")

        # アップロード実行
        storage.upload_file("/tmp/test.png", "charts/2026/01/12/test.png")

        # boto3のupload_fileが正しく呼ばれたか確認
        mock_s3.upload_file.assert_called_once_with(
            Filename="/tmp/test.png",
            Bucket="test-bucket",
            Key="charts/2026/01/12/test.png",
            ExtraArgs={"ContentType": "image/png"},
        )

    @patch("boto3.client")
    def test_upload_file_client_error(self, mock_boto_client):
        """ClientError発生時のテスト"""
        mock_s3 = Mock()
        mock_s3.upload_file.side_effect = ClientError(
            {
                "Error": {
                    "Code": "NoSuchBucket",
                    "Message": "The specified bucket does not exist",
                }
            },
            "PutObject",
        )
        mock_boto_client.return_value = mock_s3

        storage = S3Storage(bucket_name="test-bucket")

        with pytest.raises(S3StorageError, match="S3アップロード失敗"):
            storage.upload_file("/tmp/test.png", "charts/2026/01/12/test.png")

    @patch("boto3.client")
    def test_upload_file_not_found(self, mock_boto_client):
        """ファイルが見つからない場合のテスト"""
        mock_s3 = Mock()
        mock_s3.upload_file.side_effect = FileNotFoundError()
        mock_boto_client.return_value = mock_s3

        storage = S3Storage(bucket_name="test-bucket")

        with pytest.raises(S3StorageError, match="ファイルが見つかりません"):
            storage.upload_file("/tmp/nonexistent.png", "charts/2026/01/12/test.png")

    @patch("boto3.client")
    def test_create_presigned_url_success(self, mock_boto_client):
        """presigned URL生成成功のテスト"""
        mock_s3 = Mock()
        mock_s3.generate_presigned_url.return_value = "https://s3.amazonaws.com/test-bucket/charts/2026/01/12/test.png?signature=xxx"
        mock_boto_client.return_value = mock_s3

        storage = S3Storage(bucket_name="test-bucket")

        url = storage.create_presigned_url("charts/2026/01/12/test.png")

        assert url.startswith("https://")
        mock_s3.generate_presigned_url.assert_called_once_with(
            ClientMethod="get_object",
            Params={"Bucket": "test-bucket", "Key": "charts/2026/01/12/test.png"},
            ExpiresIn=3600,
        )

    @patch("boto3.client")
    def test_create_presigned_url_custom_expiry(self, mock_boto_client):
        """カスタム有効期限でのpresigned URL生成"""
        mock_s3 = Mock()
        mock_s3.generate_presigned_url.return_value = "https://s3.amazonaws.com/test"
        mock_boto_client.return_value = mock_s3

        storage = S3Storage(bucket_name="test-bucket")

        storage.create_presigned_url("charts/2026/01/12/test.png", expires_in=7200)

        # 有効期限が7200秒で呼ばれたか確認
        call_args = mock_s3.generate_presigned_url.call_args
        assert call_args[1]["ExpiresIn"] == 7200

    @patch("boto3.client")
    def test_create_presigned_url_client_error(self, mock_boto_client):
        """presigned URL生成時のClientError"""
        mock_s3 = Mock()
        mock_s3.generate_presigned_url.side_effect = ClientError(
            {
                "Error": {
                    "Code": "NoSuchKey",
                    "Message": "The specified key does not exist",
                }
            },
            "GetObject",
        )
        mock_boto_client.return_value = mock_s3

        storage = S3Storage(bucket_name="test-bucket")

        with pytest.raises(S3StorageError, match="presigned URL生成失敗"):
            storage.create_presigned_url("charts/2026/01/12/test.png")

    @patch("boto3.client")
    def test_upload_and_get_url_success(self, mock_boto_client):
        """アップロードとURL取得の統合テスト"""
        mock_s3 = Mock()
        mock_s3.generate_presigned_url.return_value = "https://s3.amazonaws.com/test-bucket/charts/2026/01/12/vt_chart.png?sig=xxx"
        mock_boto_client.return_value = mock_s3

        storage = S3Storage(bucket_name="test-bucket")

        test_date = datetime(2026, 1, 12)
        url = storage.upload_and_get_url(
            filepath="/tmp/vt_chart.png", filename_hint="vt_chart.png", now=test_date
        )

        # アップロードが呼ばれたか確認
        assert mock_s3.upload_file.called

        # 正しいS3キーでアップロードされたか確認
        upload_call = mock_s3.upload_file.call_args
        assert upload_call[1]["Key"] == "charts/2026/01/12/vt_chart.png"

        # URLが返されたか確認
        assert url.startswith("https://")


class TestCHARTFILENAME:
    """CHART_FILENAME定数のテスト"""

    def test_chart_filename_constant(self):
        """チャートファイル名定数の値確認"""
        assert CHART_FILENAME == "vt_chart.png"
