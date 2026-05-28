import json
import os
import random
import time
from typing import Dict, Any, List, Optional
from datetime import datetime

from astrbot.api import logger


class TurtleSoupManager:
    """
    海龟汤管理器
    - 20 个自定义题目库位（汤面 + 汤底）
    - 在线搜索开关（LLM 联网查找题目）
    - 活跃汤缓存（注入 LLM 上下文，1 天 TTL）
    """

    MAX_SLOTS = 20
    CACHE_TTL = 86400  # 活跃汤 1 天（秒）
    ONLINE_CACHE_TTL = 86400 * 10  # 在线题目缓存 10 天（秒）

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)
        self.data = self._load_data()
        # 内存中的活跃汤缓存  {session_key: {puzzle, created_at, starter_id}}
        self._active_soups: Dict[str, Dict] = {}
        self._online_counter = self.data.get("online_counter", 0)
        self._cleanup_expired_cache()
        self._cleanup_online_cache()

    # ========== 数据持久化 ==========

    def _load_data(self) -> Dict[str, Any]:
        path = os.path.join(self.data_dir, "turtle_soup.json")
        if not os.path.exists(path):
            return self._default_data()
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                data.setdefault("puzzles", self._make_empty_puzzles())
                data.setdefault("online_enabled", False)
                data.setdefault("stats", {"played": 0, "revealed": 0})
                data.setdefault("online_counter", 0)
                data.setdefault("cached_online", [])
                # 确保 20 个位置
                existing_ids = {p["id"] for p in data["puzzles"]}
                for i in range(1, self.MAX_SLOTS + 1):
                    if i not in existing_ids:
                        data["puzzles"].append(
                            {"id": i, "title": "", "surface": "", "answer": ""}
                        )
                data["puzzles"].sort(key=lambda p: p["id"])
                return data
        except (json.JSONDecodeError, TypeError):
            return self._default_data()

    def _default_data(self) -> Dict:
        return {
            "puzzles": self._make_empty_puzzles(),
            "online_enabled": False,
            "stats": {"played": 0, "revealed": 0},
            "online_counter": 0,
            "cached_online": [],
        }

    @classmethod
    def _make_empty_puzzles(cls) -> List[Dict]:
        return [
            {"id": i, "title": "", "surface": "", "answer": ""}
            for i in range(1, cls.MAX_SLOTS + 1)
        ]

    def _save_data(self):
        path = os.path.join(self.data_dir, "turtle_soup.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    # ========== 库位操作 ==========

    def get_puzzle(self, puzzle_id: int) -> Optional[Dict]:
        for p in self.data["puzzles"]:
            if p["id"] == puzzle_id:
                if p.get("surface") and p.get("answer"):
                    return dict(p)
                return None
        return None

    def get_available_puzzles(self) -> List[Dict]:
        return [
            dict(p) for p in self.data["puzzles"]
            if p.get("surface") and p.get("answer")
        ]

    def get_random_puzzle(self, exclude_id=None) -> Optional[Dict]:
        available = self.get_available_puzzles()
        if exclude_id is not None:
            available = [p for p in available if p["id"] != exclude_id]
        return random.choice(available) if available else None

    def set_puzzle(self, puzzle_id: int, title: str, surface: str, answer: str) -> bool:
        if puzzle_id < 1 or puzzle_id > self.MAX_SLOTS:
            return False
        for p in self.data["puzzles"]:
            if p["id"] == puzzle_id:
                p["title"] = title
                p["surface"] = surface
                p["answer"] = answer
                self._save_data()
                return True
        return False

    def clear_puzzle(self, puzzle_id: int) -> bool:
        return self.set_puzzle(puzzle_id, "", "", "")

    def list_puzzles(self) -> str:
        lines = ["🐢 海龟汤题库：\n"]
        has_any = False
        for p in self.data["puzzles"]:
            if p.get("surface") and p.get("answer"):
                title = p.get("title") or f"第{p['id']}题"
                lines.append(f"  #{p['id']} ✅ {title}")
                has_any = True
            else:
                lines.append(f"  #{p['id']} ⬜ (空)")
        if not has_any:
            lines.append("\n💡 题库是空的，编辑 turtle_soup.json 添加题目吧~")
        online_status = "🌐 在线搜索：开启" if self.is_online_enabled() else "🔒 在线搜索：关闭"
        lines.append(f"\n{online_status}")
        return "\n".join(lines)

    # ========== 在线搜索开关 ==========

    def is_online_enabled(self) -> bool:
        return self.data.get("online_enabled", False)

    def set_online(self, enabled: bool):
        self.data["online_enabled"] = enabled
        self._save_data()

    def next_online_id(self) -> str:
        """生成下一个在线汤的 s- 编号"""
        self._online_counter += 1
        self.data["online_counter"] = self._online_counter
        self._save_data()
        return f"s-{self._online_counter}"

    # ========== 统计 ==========

    def record_play(self):
        self.data.setdefault("stats", {"played": 0, "revealed": 0})["played"] += 1
        self._save_data()

    def record_reveal(self):
        self.data.setdefault("stats", {"played": 0, "revealed": 0})["revealed"] += 1
        self._save_data()

    # ========== 在线题目缓存 ==========

    def _puzzle_fingerprint(self, puzzle: Dict) -> str:
        """生成题目指纹（用汤面前50字去重）"""
        surface = (puzzle.get("surface") or "").strip()[:50]
        return surface

    def is_duplicate_online(self, puzzle: Dict) -> bool:
        """检查在线题目是否在缓存期内已出现过"""
        fp = self._puzzle_fingerprint(puzzle)
        if not fp:
            return False
        now = time.time()
        for entry in self.data.get("cached_online", []):
            if now - entry.get("fetched_at", 0) > self.ONLINE_CACHE_TTL:
                continue
            if self._puzzle_fingerprint(entry.get("puzzle", {})) == fp:
                return True
        return False

    def cache_online_puzzle(self, puzzle: Dict):
        """将在线获取的题目加入缓存"""
        self.data.setdefault("cached_online", []).append({
            "puzzle": puzzle,
            "fetched_at": time.time(),
        })
        self._save_data()

    def get_cached_titles(self) -> List[str]:
        """获取缓存中所有未过期题目的标题（用于搜索排除）"""
        now = time.time()
        titles = []
        for entry in self.data.get("cached_online", []):
            if now - entry.get("fetched_at", 0) > self.ONLINE_CACHE_TTL:
                continue
            t = entry.get("puzzle", {}).get("title", "")
            if t:
                titles.append(t)
        return titles

    def get_cached_online_puzzle(self, exclude_fps: set = None) -> Optional[Dict]:
        """从缓存中随机取一道未过期的题目（可排除指定指纹）"""
        now = time.time()
        exclude_fps = exclude_fps or set()
        candidates = []
        for entry in self.data.get("cached_online", []):
            if now - entry.get("fetched_at", 0) > self.ONLINE_CACHE_TTL:
                continue
            p = entry.get("puzzle", {})
            if self._puzzle_fingerprint(p) not in exclude_fps:
                candidates.append(p)
        return random.choice(candidates) if candidates else None

    def _cleanup_online_cache(self):
        """清理过期的在线缓存"""
        now = time.time()
        cached = self.data.get("cached_online", [])
        before = len(cached)
        self.data["cached_online"] = [
            e for e in cached
            if now - e.get("fetched_at", 0) <= self.ONLINE_CACHE_TTL
        ]
        if len(self.data["cached_online"]) < before:
            self._save_data()

    # ========== 活跃汤缓存 ==========

    def set_active_soup(self, session_key: str, puzzle: Dict, starter_id: str = ""):
        """设置某个会话的活跃汤"""
        self._cleanup_expired_cache()
        self._active_soups[session_key] = {
            "puzzle": puzzle,
            "created_at": time.time(),
            "starter_id": starter_id,
        }

    def get_active_soup(self, session_key: str) -> Optional[Dict]:
        """获取某个会话的活跃汤，过期返回 None"""
        entry = self._active_soups.get(session_key)
        if not entry:
            return None
        if time.time() - entry["created_at"] > self.CACHE_TTL:
            del self._active_soups[session_key]
            return None
        return entry["puzzle"]

    def clear_active_soup(self, session_key: str) -> Optional[Dict]:
        """清除某个会话的活跃汤，返回被清除的 puzzle"""
        entry = self._active_soups.pop(session_key, None)
        return entry["puzzle"] if entry else None

    def has_active_soup(self, session_key: str) -> bool:
        return self.get_active_soup(session_key) is not None

    def _cleanup_expired_cache(self):
        now = time.time()
        expired = [k for k, v in self._active_soups.items()
                   if now - v["created_at"] > self.CACHE_TTL]
        for k in expired:
            del self._active_soups[k]

    @staticmethod
    def get_session_key(event) -> str:
        """从 event 中提取会话 key（群聊用 group_id，私聊用 sender_id）"""
        gid = event.get_group_id() if hasattr(event, "get_group_id") else None
        return gid if gid else event.get_sender_id()

    # ========== LLM Prompt ==========

    @staticmethod
    def build_search_prompt(exclude_titles: list = None) -> str:
        """构建让 LLM 联网搜索海龟汤题目的 prompt（兼容 Bocha/Tavily/Grok/OpenAI）"""
        exclude_hint = ""
        if exclude_titles:
            titles_str = "、".join(exclude_titles[:10])
            exclude_hint = f"5. 不要选以下已经出过的题目：{titles_str}\n"
        return (
            "请使用联网搜索功能，搜索一道有趣的「海龟汤」（情境猜谜/横向思维谜题）题目。\n"
            "搜索关键词建议：海龟汤 情境猜谜 横向思维 谜题 汤面 汤底\n\n"
            "要求：\n"
            "1. 从搜索结果中找到一道完整的海龟汤题目（必须同时包含汤面和汤底）\n"
            "2. 如果搜索结果中没有完整题目，可以基于搜索到的素材整理一道\n"
            "3. 汤面要简短有悬念（1-3句话），汤底要合理有反转（3-5句话）\n"
            "4. 不要太恐怖或血腥\n"
            f"{exclude_hint}\n"
            "请严格按以下 JSON 格式返回，不要有任何其他内容（不要 markdown 代码块）：\n"
            '{"title": "简短标题", "surface": "汤面内容", "answer": "汤底内容"}'
        )

    @staticmethod
    def build_judge_system_prompt(puzzle: Dict) -> str:
        """构建注入 system_prompt 的裁判上下文"""
        title = puzzle.get("title", "海龟汤")
        surface = puzzle.get("surface", "")
        answer = puzzle.get("answer", "")
        return (
            "你是海龟汤游戏裁判，不要使用任何角色人设。\n\n"
            f"题目：{title}\n"
            f"汤面（玩家已知）：{surface}\n"
            f"汤底（绝对保密）：{answer}\n\n"
            "裁判规则（严格遵守）：\n"
            "- 玩家针对海龟汤提问时，你的完整回复只能是以下四个词之一：是、不是、不相关、不完全是\n"
            "- 除了这四个词之外，不准输出任何其他内容，包括但不限于：解释、提示、引导、补充说明、emoji、标点\n"
            "- 如果玩家基本猜出完整真相，回复「🎉 正确！」加一句简短复述\n"
            "- 绝对不能透露或暗示汤底的任何细节\n"
            "- 玩家在聊与海龟汤无关的话题时，正常回复\n"
        )

    @staticmethod
    def build_judge_direct_prompt(answer: str, question: str) -> str:
        """构建直接调用 LLM 的裁判 prompt（用于单独 API 模式）"""
        return (
            "你是海龟汤游戏裁判。\n"
            f"【汤底（绝对保密）】：{answer}\n\n"
            "规则（严格遵守）：你的完整回复只能是以下四个词之一：是、不是、不相关、不完全是。\n"
            "除此之外不准输出任何其他内容，包括解释、提示、引导、补充说明、emoji。\n"
            "如果玩家基本猜出完整真相，回复「🎉 正确！」加一句简短复述。\n"
            "绝不透露或暗示汤底细节。\n\n"
            f"玩家提问：{question}"
        )
