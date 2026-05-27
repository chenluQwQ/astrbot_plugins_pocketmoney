import json
import os
from typing import Dict, Any, List
from datetime import datetime, timedelta


class ThankLetterManager:
    """
    表扬信管理系统
    - 每账号每天一封
    - 排行榜
    - 随机奖金
    """

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)
        self.data = self._load_data()

    def _load_data(self) -> Dict[str, Any]:
        path = os.path.join(self.data_dir, "thank_letters.json")
        if not os.path.exists(path):
            return {"daily_senders": {}, "ranking": {}, "today_bonus": 0, "today_date": "", "total_bonus": 0}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                data.setdefault("daily_senders", {})
                data.setdefault("ranking", {})
                data.setdefault("today_bonus", 0)
                data.setdefault("today_date", "")
                data.setdefault("total_bonus", 0)
                return data
        except (json.JSONDecodeError, TypeError):
            return {"daily_senders": {}, "ranking": {}, "today_bonus": 0, "today_date": "", "total_bonus": 0}

    def _save_data(self):
        path = os.path.join(self.data_dir, "thank_letters.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def _check_and_reset_daily(self):
        today = datetime.now().strftime("%Y-%m-%d")
        if self.data["today_date"] != today:
            self.data["today_date"] = today
            self.data["today_bonus"] = 0
            cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            self.data["daily_senders"] = {k: v for k, v in self.data["daily_senders"].items() if k >= cutoff}
            self._save_data()

    def can_send_today(self, sender_id: str) -> bool:
        self._check_and_reset_daily()
        today = datetime.now().strftime("%Y-%m-%d")
        return sender_id not in self.data["daily_senders"].get(today, [])

    def record_thank_letter(self, sender_id: str, sender_name: str, amount: int) -> bool:
        self._check_and_reset_daily()
        today = datetime.now().strftime("%Y-%m-%d")
        if not self.can_send_today(sender_id):
            return False
        if today not in self.data["daily_senders"]:
            self.data["daily_senders"][today] = []
        self.data["daily_senders"][today].append(sender_id)

        ranking_key = f"{sender_id}|{sender_name}"
        old_key = None
        for key in self.data["ranking"]:
            if key.startswith(f"{sender_id}|"):
                old_key = key
                break
        if old_key and old_key != ranking_key:
            self.data["ranking"][ranking_key] = self.data["ranking"].pop(old_key) + 1
        else:
            self.data["ranking"][ranking_key] = self.data["ranking"].get(ranking_key, 0) + 1

        self.data["today_bonus"] += amount
        self.data["total_bonus"] += amount
        self._save_data()
        return True

    def get_today_bonus(self) -> int:
        self._check_and_reset_daily()
        return self.data.get("today_bonus", 0)

    def get_total_bonus(self) -> int:
        return self.data.get("total_bonus", 0)

    def get_ranking(self, top_n: int = 10) -> List[tuple]:
        ranking = self.data.get("ranking", {})
        sorted_ranking = sorted(ranking.items(), key=lambda x: x[1], reverse=True)
        return sorted_ranking[:top_n]
