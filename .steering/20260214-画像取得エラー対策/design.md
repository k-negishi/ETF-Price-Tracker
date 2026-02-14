# 設計

## アプローチ

LINE画像送信失敗の根本原因を特定し、修正する。

## 実装方針

### 1. 詳細ログの追加 (handler.py)

**現状 (handler.py:119-152):**
```python
try:
    vt_df_6mo = _download_with_retry(tickers="VT", period="6mo", auto_adjust=True)
    chart_filepath = create_chart(vt_df_6mo)

    s3_storage = S3Storage()
    now = datetime.datetime.now()
    image_url = s3_storage.upload_and_get_url(
        filepath=chart_filepath, filename_hint=CHART_FILENAME, now=now
    )
except S3StorageError as e:
    print(f"S3アップロードエラー: {e}")
except ValueError as e:
    print(f"S3設定エラー: {e}")
except Exception as e:
    print(f"画像通知の送信に失敗しました: {e}")

# ... (中略)

if image_url:
    try:
        line_notifier.send_messages([...])
    except Exception as e:
        print(f"画像通知の送信に失敗しました: {e}")
```

**改善点:**
- 画像ファイルサイズをログ出力
- presigned URLをログ出力
- LINE送信エラーの詳細を記録 (HTTPステータス、エラーメッセージ)

### 2. 画像サイズの確認と最適化 (handler.py:create_chart)

**現状:**
```python
fig, ax = plt.subplots(figsize=(12, 6))
...
plt.savefig(filepath, bbox_inches="tight")
```

**改善点:**
- `dpi` パラメータを明示的に指定 (デフォルト100 → 必要に応じて調整)
- 保存後のファイルサイズを確認
- LINE API制限 (10MB) を超える場合は警告

### 3. presigned URL有効期限の延長 (s3_storage.py)

**現状:**
```python
def upload_and_get_url(self, filepath: str, filename_hint: str, now: datetime) -> str:
    ...
    return self.create_presigned_url(s3_key)  # デフォルト3600秒
```

**改善点:**
- 有効期限を延長 (例: 86400秒 = 24時間)
- または、handler.py から明示的に指定

### 4. LINE送信エラーの詳細化 (line_notifier.py)

**現状の確認:**
- `send_messages` メソッドは既にリトライロジックあり (max_retries=3, retry_delay=10)
- HTTPステータスコードに応じたエラーハンドリングあり

**改善点:**
- 画像URL送信時の特別なバリデーション追加
- エラーメッセージにHTTPステータスコードを含める

## ファイル変更計画

### 変更対象ファイル
1. `src/handler.py`
   - 画像処理部分の詳細ログ追加
   - ファイルサイズ確認処理追加
   - presigned URL有効期限の明示的指定

2. `src/s3_storage.py`
   - `upload_and_get_url` メソッドに有効期限パラメータ追加

3. (オプション) `src/line_notifier.py`
   - 画像送信時のエラーメッセージ改善

## 考慮事項

### LINE Messaging API 画像送信制限
- 画像形式: JPEG, PNG
- 最大ファイルサイズ: 10MB
- 推奨サイズ: 1MB以下
- 画像URLはHTTPS必須
- LINEサーバーから画像URLにアクセス可能である必要がある

### 既存パターンとの整合性
- エラーハンドリング: 既存の try-except パターンを維持
- ログ出力: `print()` を使用 (AWS Lambda PowerTools のロガーは未使用)
- リトライロジック: `_download_with_retry` と同様のパターン
