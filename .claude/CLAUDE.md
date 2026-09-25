## 指針
- 実装に変更を加えた場合は、コードの静的解析、フォーマット、型チェック、テストを必ず実行してください。
```bash
ruff check src --fix
ruff format src
mypy src
python -m pytest tests/
```

- ローカル実行は以下のコマンドで実行すること
```bash
python -c "from src.handler import lambda_handler; from aws_lambda_powertools.utilities.typing import LambdaContext; print(lambda_handler({}, LambdaContext()))"
```
