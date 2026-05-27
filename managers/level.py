import json
import os
from typing import Dict, Any, List, Tuple
from datetime import datetime

from astrbot.api import logger


# 等级经验表：每级所需累计经验
LEVEL_TABLE = [
    0,      # Lv.0
    100,    # Lv.1
    300,    # Lv.2
    600,    # Lv.3
    1000,   # Lv.4
    1500,   # Lv.5
    2200,   # Lv.6
    3000,   # Lv.7
    4000,   # Lv.8
    5200,   # Lv.9
    6500,   # Lv.10
    8000,   # Lv.11
    10000,  # Lv.12
    12500,  # Lv.13
    15500,  # Lv.14
    19000,  # Lv.15
    23000,  # Lv.16
    28000,  # Lv.17
    34000,  # Lv.18
    41000,  # Lv.19
    50000,  # Lv.20
]

# 签到奖励
SIGN_IN_BASE_XP = 30
SIGN_IN_STREAK_BONUS = 5  # 每连续签到一天额外加的经验


class LevelManager:
    """
    等级系统
    - 经验来源：签到、赚钱（表扬信/卖股票盈利等）
    - 等级影响：解锁更贵的股票、银行利率加成等
    - 签到：每日一次，连续签到有加成
    """

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)
        self.data = self._load_data()

    def _load_data(self) -> Dict[str, Any]:
        path = os.path.join(self.data_dir, "levels.json")
        if not os.path.exists(path):
            return {"users": {}}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                data.setdefault("users", {})
                return data
        except (json.JSONDecodeError, TypeError):
            return {"users": {}}

    def _save_data(self):
        path = os.path.join(self.data_dir, "levels.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def _get_user(self, user_id: str) -> Dict:
        users = self.data.setdefault("users", {})
        if user_id not in users:
            users[user_id] = {
                "xp": 0,
                "level": 0,
                "total_xp": 0,
                "sign_in_date": "",
                "sign_in_streak": 0,
                "total_sign_ins": 0,
            }
        return users[user_id]

    def get_level(self, user_id: str) -> int:
        return self._get_user(user_id).get("level", 0)

    def get_xp(self, user_id: str) -> int:
        return self._get_user(user_id).get("xp", 0)

    def get_xp_for_next_level(self, user_id: str) -> Tuple[int, int]:
        """返回 (当前经验, 下一级所需经验)"""
        user = self._get_user(user_id)
        level = user.get("level", 0)
        xp = user.get("xp", 0)
        if level >= len(LEVEL_TABLE) - 1:
            return xp, xp  # 满级
        return xp, LEVEL_TABLE[level + 1]

    def add_xp(self, user_id: str, amount: int, reason: str = "") -> Tuple[int, bool]:
        """
        增加经验值
        :return: (新等级, 是否升级了)
        """
        if amount <= 0:
            return self.get_level(user_id), False

        user = self._get_user(user_id)
        user["xp"] = user.get("xp", 0) + amount
        user["total_xp"] = user.get("total_xp", 0) + amount

        # 检查升级
        old_level = user.get("level", 0)
        new_level = old_level
        while new_level < len(LEVEL_TABLE) - 1 and user["xp"] >= LEVEL_TABLE[new_level + 1]:
            new_level += 1

        leveled_up = new_level > old_level
        user["level"] = new_level
        self._save_data()

        if leveled_up:
            logger.info(f"[Level] 用户 {user_id} 升级: Lv.{old_level} → Lv.{new_level} (原因: {reason})")

        return new_level, leveled_up

    def sign_in(self, user_id: str) -> Tuple[bool, int, int, int]:
        """
        签到
        :return: (是否成功, 获得经验, 连续天数, 新等级)
        """
        user = self._get_user(user_id)
        today = datetime.now().strftime("%Y-%m-%d")

        if user.get("sign_in_date") == today:
            return False, 0, user.get("sign_in_streak", 0), user.get("level", 0)

        # 检查连续签到
        yesterday = (datetime.now().replace(hour=0, minute=0, second=0) -
                     __import__('datetime').timedelta(days=1)).strftime("%Y-%m-%d")
        if user.get("sign_in_date") == yesterday:
            user["sign_in_streak"] = user.get("sign_in_streak", 0) + 1
        else:
            user["sign_in_streak"] = 1

        user["sign_in_date"] = today
        user["total_sign_ins"] = user.get("total_sign_ins", 0) + 1

        # 计算经验
        streak = user["sign_in_streak"]
        xp = SIGN_IN_BASE_XP + min(streak, 30) * SIGN_IN_STREAK_BONUS
        new_level, _ = self.add_xp(user_id, xp, "签到")

        self._save_data()
        return True, xp, streak, new_level

    def get_sign_in_info(self, user_id: str) -> Dict:
        user = self._get_user(user_id)
        return {
            "streak": user.get("sign_in_streak", 0),
            "total": user.get("total_sign_ins", 0),
            "last_date": user.get("sign_in_date", ""),
        }

    def format_level_card(self, user_id: str, user_name: str = "") -> str:
        user = self._get_user(user_id)
        level = user.get("level", 0)
        xp = user.get("xp", 0)
        total_xp = user.get("total_xp", 0)

        if level >= len(LEVEL_TABLE) - 1:
            progress = "MAX"
            next_xp = xp
        else:
            next_xp = LEVEL_TABLE[level + 1]
            bar_len = 10
            filled = int((xp / next_xp) * bar_len) if next_xp > 0 else bar_len
            bar = "█" * filled + "░" * (bar_len - filled)
            progress = f"{bar} {xp}/{next_xp}"

        sign_info = self.get_sign_in_info(user_id)
        name_str = f" {user_name}" if user_name else ""

        return (
            f"📊{name_str} 等级信息\n"
            f"⭐ Lv.{level}\n"
            f"✨ {progress}\n"
            f"📅 连续签到: {sign_info['streak']}天 | 累计: {sign_info['total']}次\n"
            f"🏆 累计经验: {total_xp}"
        )
