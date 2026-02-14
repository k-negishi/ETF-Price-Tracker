# タスクリスト

## 実装タスク

- [x] handler.py: create_chart関数にdpiパラメータを追加し、画像サイズを最適化
- [x] handler.py: チャート生成後、ファイルサイズをログ出力
- [x] s3_storage.py: upload_and_get_urlメソッドにexpires_inパラメータを追加
- [x] handler.py: presigned URL有効期限を24時間 (86400秒) に延長
- [x] handler.py: 画像URL生成成功時にURLをログ出力
- [x] handler.py: LINE画像送信エラー時に詳細なエラー情報をログ出力
- [ ] テスト: ruff check, ruff format, mypy, pytest を実行して全て成功することを確認

## 完了条件

- [ ] 全ての静的解析・型チェック・テストがパス
- [ ] 画像処理の各段階で詳細ログが出力される
- [ ] presigned URLの有効期限が延長されている
- [ ] 画像ファイルサイズが確認可能
