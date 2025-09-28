import os
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from src.line_notifier import LineMessagingNotifier
load_dotenv()

class TestLineNotifier:
    def test_line_notifier(self):
        # CI環境ではスキップ
        if os.getenv('CI') == 'true' or os.getenv('GITHUB_ACTIONS') == 'true':
            return

        line_notifier = LineMessagingNotifier()

        jst_timezone = ZoneInfo("Asia/Tokyo")
        datetime_format = "%Y/%m/%d %H:%M:%S"
        current_jst_time = datetime.now(jst_timezone).strftime(datetime_format)
        test_message = f"test{current_jst_time}"

        line_notifier.send_message(test_message)
