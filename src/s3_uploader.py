import os
from logging import getLogger

import boto3
from botocore.exceptions import NoCredentialsError, PartialCredentialsError

logger = getLogger(__name__)


class S3Uploader:
    """
    S3へのファイルアップロードを行うクラス
    """

    def __init__(self, bucket_name: str, region_name: str = "ap-northeast-1"):
        """
        初期化

        Args:
            bucket_name (str): アップロード先のS3バケット名
            region_name (str): AWSリージョン
        """
        if not bucket_name:
            raise ValueError("S3バケット名が指定されていません。")

        self.bucket_name = bucket_name
        self.s3_client = boto3.client("s3", region_name=region_name)

    def upload_file(self, file_path: str, s3_key: str) -> str:
        """
        ファイルをS3にアップロードし、公開URLを返す

        Args:
            file_path (str): アップロードするファイルのパス
            s3_key (str): S3上でのファイルキー

        Returns:
            str: アップロードされたファイルの公開URL
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"ファイルが見つかりません: {file_path}")

        try:
            self.s3_client.upload_file(
                file_path, self.bucket_name, s3_key, ExtraArgs={"ACL": "public-read"}
            )
            logger.info(f"File '{file_path}' uploaded to '{self.bucket_name}/{s3_key}'")

            # オブジェクトのURLを取得
            return f"https://{self.bucket_name}.s3.amazonaws.com/{s3_key}"

        except (NoCredentialsError, PartialCredentialsError) as e:
            logger.error(f"AWS認証情報が見つかりません: {e}")
            raise
        except Exception as e:
            logger.error(f"S3へのアップロード中にエラーが発生しました: {e}")
            raise
