import json
import os
import re
from typing import Dict, Any, List, Optional
from datetime import datetime

from astrbot.api import logger


def _strip_emoji(text: str) -> str:
    cleaned = re.sub(r'^[\U0001F000-\U0001FFFF\u2600-\u27BF\uFE0F\u200D\u20E3\u2000-\u3300]+\s*', '', text)
    return cleaned.strip() if cleaned.strip() else text.strip()


def _name_match(a: str, b: str) -> bool:
    """模糊匹配物品名，忽略emoji和空格"""
    a_full = a.strip().lower().replace(" ", "").replace("\u3000", "")
    b_full = b.strip().lower().replace(" ", "").replace("\u3000", "")
    a_no = _strip_emoji(a).lower().replace(" ", "")
    b_no = _strip_emoji(b).lower().replace(" ", "")
    return a_full == b_full or a_no == b_no or a_full == b_no or a_no == b_full


class BackpackManager:
    """
    小背包管理系统
    - 共享背包：bot自己的物品存储
    - 专属格子：每个用户有独立的格子（跨窗口，存放礼物/购买的东西）
    - 支持食品保质期（expires_at字段，过期自动清理）
    """

    def __init__(self, data_dir: str, max_shared_slots: int = 10, max_user_slots: int = 3):
        self.data_dir = data_dir
        self.max_shared_slots = max_shared_slots
        self.max_user_slots = max_user_slots
        os.makedirs(self.data_dir, exist_ok=True)
        self.data = self._load_data()

    def _load_data(self) -> Dict[str, Any]:
        path = os.path.join(self.data_dir, "backpack.json")
        if not os.path.exists(path):
            return {"shared_items": [], "user_slots": {}}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # 兼容旧版本
                if "items" in data and "shared_items" not in data:
                    data["shared_items"] = data.pop("items")
                data.setdefault("shared_items", [])
                data.setdefault("user_slots", {})
                return data
        except (json.JSONDecodeError, TypeError):
            return {"shared_items": [], "user_slots": {}}

    def _save_data(self):
        path = os.path.join(self.data_dir, "backpack.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def _cleanup_expired(self, items: List[Dict]) -> List[Dict]:
        """清理过期物品，返回清理后的列表"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        before = len(items)
        items[:] = [
            item for item in items
            if not item.get("expires_at") or item["expires_at"] > now
        ]
        removed = before - len(items)
        if removed > 0:
            logger.debug(f"[Backpack] 清理了 {removed} 件过期物品")
            self._save_data()
        return items

    # ========== 共享背包操作 ==========

    def get_shared_items(self) -> List[Dict[str, Any]]:
        items = self.data.get("shared_items", [])
        self._cleanup_expired(items)
        return items

    def get_shared_item_count(self) -> int:
        return len(self.get_shared_items())

    def is_shared_full(self) -> bool:
        return self.get_shared_item_count() >= self.max_shared_slots

    def add_shared_item(self, name: str, description: str, expires_at: str = None) -> bool:
        """
        添加物品到共享背包
        :param expires_at: 过期时间字符串 (YYYY-MM-DD HH:MM:SS)，None表示永不过期
        """
        if self.is_shared_full():
            return False
        item = {
            "name": name,
            "description": description,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        if expires_at:
            item["expires_at"] = expires_at
        self.data["shared_items"].append(item)
        self._save_data()
        return True

    def use_shared_item(self, name: str) -> bool:
        items = self.data.get("shared_items", [])
        self._cleanup_expired(items)
        for i, item in enumerate(items):
            if _name_match(item["name"], name):
                items.pop(i)
                self._save_data()
                return True
        return False

    def clear_shared_items(self):
        self.data["shared_items"] = []
        self._save_data()

    # ========== 用户专属格子操作 ==========

    def get_user_items(self, user_id: str) -> List[Dict[str, Any]]:
        items = self.data.get("user_slots", {}).get(user_id, [])
        self._cleanup_expired(items)
        return items

    def get_user_item_count(self, user_id: str) -> int:
        return len(self.get_user_items(user_id))

    def is_user_slots_full(self, user_id: str) -> bool:
        return self.get_user_item_count(user_id) >= self.max_user_slots

    def add_user_gift(self, user_id: str, name: str, description: str, from_who: str,
                      expires_at: str = None) -> bool:
        if self.is_user_slots_full(user_id):
            return False
        if "user_slots" not in self.data:
            self.data["user_slots"] = {}
        if user_id not in self.data["user_slots"]:
            self.data["user_slots"][user_id] = []
        item = {
            "name": name,
            "description": description,
            "from": from_who,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        if expires_at:
            item["expires_at"] = expires_at
        self.data["user_slots"][user_id].append(item)
        self._save_data()
        return True

    def use_user_item(self, user_id: str, name: str) -> bool:
        items = self.data.get("user_slots", {}).get(user_id, [])
        self._cleanup_expired(items)
        for i, item in enumerate(items):
            if _name_match(item["name"], name):
                items.pop(i)
                self._save_data()
                return True
        return False

    def clear_user_items(self, user_id: str):
        if user_id in self.data.get("user_slots", {}):
            self.data["user_slots"][user_id] = []
            self._save_data()

    def get_all_user_slots(self) -> Dict[str, List[Dict[str, Any]]]:
        return self.data.get("user_slots", {})

    # ========== 格式化方法 ==========

    def format_shared_items_for_prompt(self) -> str:
        items = self.get_shared_items()
        if not items:
            return "空空如也"
        parts = []
        for item in items:
            s = f"{item['name']}({item['description']})"
            if item.get("expires_at"):
                s += f"[保质期至{item['expires_at'][:10]}]"
            parts.append(s)
        return "、".join(parts)

    def format_user_items_for_prompt(self, user_id: str) -> str:
        items = self.get_user_items(user_id)
        if not items:
            return "空空如也"
        parts = []
        for item in items:
            s = f"{item['name']}(来自{item['from']}: {item['description']})"
            if item.get("expires_at"):
                s += f"[保质期至{item['expires_at'][:10]}]"
            parts.append(s)
        return "、".join(parts)
