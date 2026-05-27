import json
import os
import hashlib
import hmac
import time
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from astrbot.api import logger


# 7个盐值，按星期一~日轮换（写死在代码里，所有插件实例共享）
_WEEKLY_SALTS = [
    "pM_g1ft_s4Lt_8Kx3Qw",   # 周一
    "zR7_bN2p_vL5m_Yh9Jf",   # 周二
    "cW4_dT8s_nQ1k_Xp6Ub",   # 周三
    "fE5_hJ3r_mA7y_Zv2Gc",   # 周四
    "iK9_jL6t_oB4w_Sd1Ne",   # 周五
    "lM2_nP8u_qC5x_Tf3Rg",   # 周六
    "oQ7_rS4v_tD9z_Wh6Ai",   # 周日
]


def _get_daily_key() -> str:
    """获取今日密钥：hash(日期 + 当日盐)"""
    today = datetime.now().strftime("%Y-%m-%d")
    weekday = datetime.now().weekday()  # 0=周一, 6=周日
    salt = _WEEKLY_SALTS[weekday]
    raw = f"{today}:{salt}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def sign_gift(item_name: str, from_bot: str, timestamp: int = None) -> str:
    """对赠送消息生成6位签名"""
    if timestamp is None:
        timestamp = int(time.time())
    key = _get_daily_key()
    payload = f"{item_name}|{from_bot}|{timestamp}"
    sig = hmac.new(key.encode(), payload.encode(), hashlib.sha256).hexdigest()[:6]
    return sig


def verify_gift(item_name: str, from_bot: str, timestamp: int, signature: str) -> bool:
    """验证赠送消息签名"""
    # 允许5分钟时间差
    now = int(time.time())
    if abs(now - timestamp) > 330:  # 5.5分钟容差
        return False
    expected = sign_gift(item_name, from_bot, timestamp)
    return hmac.compare_digest(expected, signature)


class GiftManager:
    """
    跨bot赠送管理
    - 管理待接收的赠送记录
    - 5分钟超时自动收回
    - 签名验证防伪造
    """

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)
        self.data = self._load_data()

    def _load_data(self) -> Dict[str, Any]:
        path = os.path.join(self.data_dir, "gifts.json")
        if not os.path.exists(path):
            return {"pending_outgoing": [], "received_log": []}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                data.setdefault("pending_outgoing", [])
                data.setdefault("received_log", [])
                return data
        except (json.JSONDecodeError, TypeError):
            return {"pending_outgoing": [], "received_log": []}

    def _save_data(self):
        path = os.path.join(self.data_dir, "gifts.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def create_outgoing(self, item_name: str, item_desc: str, from_bot: str,
                        to_user: str, sender_user_id: str,
                        expires_at: str = None) -> Dict:
        """
        创建一条待发送的赠送记录
        :return: 包含签名信息的记录
        """
        ts = int(time.time())
        sig = sign_gift(item_name, from_bot, ts)

        record = {
            "item_name": item_name,
            "item_desc": item_desc,
            "from_bot": from_bot,
            "to_user": to_user,
            "sender_user_id": sender_user_id,
            "timestamp": ts,
            "signature": sig,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "pending",  # pending / accepted / rejected / expired
        }
        if expires_at:
            record["item_expires_at"] = expires_at

        self.data["pending_outgoing"].append(record)
        self._save_data()
        return record

    def find_pending(self, item_name: str, from_bot: str) -> Optional[Dict]:
        """查找匹配的待处理赠送"""
        for record in self.data["pending_outgoing"]:
            if (record["status"] == "pending"
                    and record["item_name"] == item_name
                    and record["from_bot"] == from_bot):
                return record
        return None

    def mark_accepted(self, item_name: str, from_bot: str) -> Optional[Dict]:
        """标记赠送已被接收"""
        record = self.find_pending(item_name, from_bot)
        if record:
            record["status"] = "accepted"
            self._save_data()
        return record

    def mark_rejected(self, item_name: str, from_bot: str) -> Optional[Dict]:
        """标记赠送被拒绝"""
        record = self.find_pending(item_name, from_bot)
        if record:
            record["status"] = "rejected"
            self._save_data()
        return record

    def cleanup_expired(self) -> List[Dict]:
        """清理超过5分钟的待处理赠送，返回过期的记录列表"""
        now = int(time.time())
        expired = []
        for record in self.data["pending_outgoing"]:
            if record["status"] == "pending" and now - record["timestamp"] > 300:
                record["status"] = "expired"
                expired.append(record)
        if expired:
            self._save_data()
        return expired

    def log_received(self, item_name: str, item_desc: str, from_bot: str,
                     to_bot: str, to_user_id: str):
        """记录收到的礼物日志"""
        self.data["received_log"].append({
            "item_name": item_name,
            "item_desc": item_desc,
            "from_bot": from_bot,
            "to_bot": to_bot,
            "to_user_id": to_user_id,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        # 只保留最近50条
        if len(self.data["received_log"]) > 50:
            self.data["received_log"] = self.data["received_log"][-50:]
        self._save_data()

    @staticmethod
    def format_gift_offer(bot_name: str, item_name: str, to_user: str,
                          timestamp: int, signature: str) -> str:
        """构建赠送消息（固定格式）"""
        return (
            f"「{bot_name}」发起赠送「{item_name}」给 @{to_user}，"
            f"是否接收？[GK:{signature}:{timestamp}]"
        )

    @staticmethod
    def format_accept(bot_name: str, item_name: str, flavor_text: str,
                      timestamp: int, signature: str) -> str:
        """构建接收回复（固定格式）"""
        return (
            f"「{bot_name}」接收了「{item_name}」！"
            f"{flavor_text} [GA:{signature}:{timestamp}]"
        )

    @staticmethod
    def format_reject(bot_name: str, item_name: str, flavor_text: str,
                      timestamp: int, signature: str) -> str:
        """构建拒绝回复（固定格式）"""
        return (
            f"「{bot_name}」拒绝了「{item_name}」。"
            f"{flavor_text} [GR:{signature}:{timestamp}]"
        )

    @staticmethod
    def parse_gift_offer(text: str) -> Optional[Dict]:
        """
        解析赠送消息
        :return: {bot_name, item_name, to_user, timestamp, signature} 或 None
        """
        import re
        pattern = r"「(.+?)」发起赠送「(.+?)」给 @(.+?)，是否接收？\[GK:([a-f0-9]{6}):(\d+)\]"
        m = re.search(pattern, text)
        if not m:
            return None
        return {
            "bot_name": m.group(1),
            "item_name": m.group(2),
            "to_user": m.group(3),
            "timestamp": int(m.group(4 + 1)),
            "signature": m.group(4),
        }

    @staticmethod
    def parse_gift_response(text: str) -> Optional[Dict]:
        """
        解析接收/拒绝回复
        :return: {bot_name, item_name, accepted, timestamp, signature} 或 None
        """
        import re
        # 接收
        m = re.search(r"「(.+?)」接收了「(.+?)」！.*?\[GA:([a-f0-9]{6}):(\d+)\]", text)
        if m:
            return {
                "bot_name": m.group(1),
                "item_name": m.group(2),
                "accepted": True,
                "signature": m.group(3),
                "timestamp": int(m.group(4)),
            }
        # 拒绝
        m = re.search(r"「(.+?)」拒绝了「(.+?)」。.*?\[GR:([a-f0-9]{6}):(\d+)\]", text)
        if m:
            return {
                "bot_name": m.group(1),
                "item_name": m.group(2),
                "accepted": False,
                "signature": m.group(3),
                "timestamp": int(m.group(4)),
            }
        return None
