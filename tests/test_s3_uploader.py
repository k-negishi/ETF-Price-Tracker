import os
import unittest
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import NoCredentialsError, PartialCredentialsError

from src.s3_uploader import S3Uploader


class TestS3Uploader(unittest.TestCase):
    def setUp(self):
        """テストのセットアップ"""
        self.bucket_name = "test-bucket"
        self.region_name = "ap-northeast-1"
        self.test_file_path = "test_file.txt"
        with open(self.test_file_path, "w") as f:
            f.write("test data")

    def tearDown(self):
        """テストの後片付け"""
        if os.path.exists(self.test_file_path):
            os.remove(self.test_file_path)

    @patch("src.s3_uploader.boto3.client")
    def test_init_success(self, mock_boto_client):
        """S3Uploaderが正常に初期化されることをテスト"""
        uploader = S3Uploader(self.bucket_name, self.region_name)
        self.assertEqual(uploader.bucket_name, self.bucket_name)
        mock_boto_client.assert_called_with("s3", region_name=self.region_name)

    def test_init_no_bucket_name(self):
        """バケット名がない場合にValueErrorが発生することをテスト"""
        with self.assertRaises(ValueError):
            S3Uploader("")

    @patch("src.s3_uploader.boto3.client")
    def test_upload_file_success(self, mock_boto_client):
        """ファイルのアップロードが成功し、正しいURLが返されることをテスト"""
        mock_s3_client = MagicMock()
        mock_boto_client.return_value = mock_s3_client

        uploader = S3Uploader(self.bucket_name, self.region_name)
        s3_key = "test_key.txt"
        expected_url = f"https://{self.bucket_name}.s3.amazonaws.com/{s3_key}"

        result_url = uploader.upload_file(self.test_file_path, s3_key)

        mock_s3_client.upload_file.assert_called_with(
            self.test_file_path,
            self.bucket_name,
            s3_key,
            ExtraArgs={"ACL": "public-read"},
        )
        self.assertEqual(result_url, expected_url)

    def test_upload_file_not_found(self):
        """存在しないファイルをアップロードしようとした場合にFileNotFoundErrorが発生することをテスト"""
        uploader = S3Uploader(self.bucket_name, self.region_name)
        with self.assertRaises(FileNotFoundError):
            uploader.upload_file("non_existent_file.txt", "some_key")

    @patch("src.s3_uploader.boto3.client")
    def test_upload_file_no_credentials(self, mock_boto_client):
        """AWS認証情報がない場合にNoCredentialsErrorが発生することをテスト"""
        mock_s3_client = MagicMock()
        mock_s3_client.upload_file.side_effect = NoCredentialsError()
        mock_boto_client.return_value = mock_s3_client

        uploader = S3Uploader(self.bucket_name, self.region_name)
        with self.assertRaises(NoCredentialsError):
            uploader.upload_file(self.test_file_path, "some_key")

    @patch("src.s3_uploader.boto3.client")
    def test_upload_file_partial_credentials(self, mock_boto_client):
        """AWS認証情報が不完全な場合にPartialCredentialsErrorが発生することをテスト"""
        mock_s3_client = MagicMock()
        mock_s3_client.upload_file.side_effect = PartialCredentialsError(
            provider="test", cred_var="test"
        )
        mock_boto_client.return_value = mock_s3_client

        uploader = S3Uploader(self.bucket_name, self.region_name)
        with self.assertRaises(PartialCredentialsError):
            uploader.upload_file(self.test_file_path, "some_key")

    @patch("src.s3_uploader.boto3.client")
    def test_upload_file_other_exception(self, mock_boto_client):
        """その他の例外が発生した場合に正しく処理されることをテスト"""
        mock_s3_client = MagicMock()
        mock_s3_client.upload_file.side_effect = Exception("S3 upload failed")
        mock_boto_client.return_value = mock_s3_client

        uploader = S3Uploader(self.bucket_name, self.region_name)
        with self.assertRaises(Exception) as context:
            uploader.upload_file(self.test_file_path, "some_key")
        self.assertIn("S3 upload failed", str(context.exception))


if __name__ == "__main__":
    unittest.main()
