import json
import os
from typing import Dict, Any, List
from datetime import datetime, timedelta

from astrbot.api import logger

from .money import PocketMoneyManager
from .backpack import BackpackManager


class UserIsolationManager:
    """
    用户隔离池管理系统（共享池模式）
    - 所有黑名单用户共享一个隔离池
    - 黑名单用户的背包操作使用隔离池
    - 金额同进同出（共用真实金库）
    - 进入/退出隔离池时，用户专属格子数据会迁移
    """

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.isolation_dir = os.path.join(data_dir, "isolation")
        self.shared_isolation_dir = os.path.join(self.isolation_dir, "shared")
        os.makedirs(self.shared_isolation_dir, exist_ok=True)
        self.blacklist = self._load_blacklist()
        self.pending_refunds = self._load_pending_refunds()
        self._shared_managers: Dict[str, Any] = None
        self._migrate_old_isolation_data()

    def _load_blacklist(self) -> List[str]:
        path = os.path.join(self.data_dir, "blacklist.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return []

    def _save_blacklist(self):
        path = os.path.join(self.data_dir, "blacklist.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.blacklist, f, ensure_ascii=False, indent=2)

    def _migrate_old_isolation_data(self):
        """将旧版用户独立隔离池数据迁移到共享隔离池"""
        if not os.path.exists(self.isolation_dir):
            return
        shared_money_file = os.path.join(self.shared_isolation_dir, "pocket_money.json")
        if os.path.exists(shared_money_file):
            return

        migrated_users = []
        total_balance = 0
        all_records = []
        all_shared_items = []
        all_user_slots = {}

        for item in os.listdir(self.isolation_dir):
            user_dir = os.path.join(self.isolation_dir, item)
            if item == "shared" or not os.path.isdir(user_dir):
                continue
            user_id = item
            old_money_file = os.path.join(user_dir, "pocket_money.json")
            if os.path.exists(old_money_file):
                try:
                    with open(old_money_file, "r", encoding="utf-8") as f:
                        old_data = json.load(f)
                        user_balance = old_data.get("balance", 0)
                        if user_balance > total_balance:
                            total_balance = user_balance
                        for record in old_data.get("records", []):
                            record["migrated_from"] = user_id
                            all_records.append(record)
                except (json.JSONDecodeError, IOError):
                    pass
            old_backpack_file = os.path.join(user_dir, "backpack.json")
            if os.path.exists(old_backpack_file):
                try:
                    with open(old_backpack_file, "r", encoding="utf-8") as f:
                        old_bp = json.load(f)
                        for item_data in old_bp.get("shared_items", []):
                            if item_data not in all_shared_items:
                                all_shared_items.append(item_data)
                        for uid, items in old_bp.get("user_slots", {}).items():
                            if uid not in all_user_slots:
                                all_user_slots[uid] = []
                            for item_data in items:
                                if item_data not in all_user_slots[uid]:
                                    all_user_slots[uid].append(item_data)
                except (json.JSONDecodeError, IOError):
                    pass
            migrated_users.append(user_id)

        if not migrated_users:
            return

        all_records.sort(key=lambda x: x.get("time", ""))
        with open(shared_money_file, "w", encoding="utf-8") as f:
            json.dump({
                "balance": total_balance,
                "records": all_records[-50:],
                "notes": [], "savings_balance": 0, "pending_withdrawals": []
            }, f, ensure_ascii=False, indent=2)

        shared_backpack_file = os.path.join(self.shared_isolation_dir, "backpack.json")
        with open(shared_backpack_file, "w", encoding="utf-8") as f:
            json.dump({"shared_items": all_shared_items, "user_slots": all_user_slots}, f, ensure_ascii=False, indent=2)

        logger.info(f"[PocketMoney] 已迁移 {len(migrated_users)} 个用户的隔离池数据到共享池")

    def is_blacklisted(self, user_id: str) -> bool:
        return str(user_id) in self.blacklist

    def add_to_blacklist(self, user_id: str, real_money_mgr: PocketMoneyManager = None,
                         real_backpack_mgr: BackpackManager = None) -> bool:
        user_id = str(user_id)
        if user_id not in self.blacklist:
            self.blacklist.append(user_id)
            self._save_blacklist()
            if real_backpack_mgr:
                self._migrate_user_slots_to_isolation(user_id, real_backpack_mgr)
            return True
        return False

    def remove_from_blacklist(self, user_id: str, real_backpack_mgr: BackpackManager = None) -> bool:
        user_id = str(user_id)
        if user_id in self.blacklist:
            if real_backpack_mgr and self._shared_managers:
                self._migrate_user_slots_from_isolation(user_id, real_backpack_mgr)
            self.blacklist.remove(user_id)
            self._save_blacklist()
            return True
        return False

    def _migrate_user_slots_to_isolation(self, user_id: str, real_backpack_mgr: BackpackManager):
        user_items = real_backpack_mgr.get_user_items(user_id)
        if not user_items:
            return
        managers = self._get_or_create_shared_managers(None, real_backpack_mgr)
        isolated_backpack = managers["backpack"]
        for item in user_items:
            isolated_backpack.add_user_gift(user_id, item.get("name", ""), item.get("description", ""), item.get("from", "未知"))
        real_backpack_mgr.clear_user_items(user_id)
        logger.info(f"[PocketMoney] 已迁移用户 {user_id} 的 {len(user_items)} 件专属物品到隔离池")

    def _migrate_user_slots_from_isolation(self, user_id: str, real_backpack_mgr: BackpackManager):
        if not self._shared_managers:
            return
        isolated_backpack = self._shared_managers["backpack"]
        user_items = isolated_backpack.get_user_items(user_id)
        if not user_items:
            return
        for item in user_items:
            real_backpack_mgr.add_user_gift(user_id, item.get("name", ""), item.get("description", ""), item.get("from", "未知"))
        isolated_backpack.clear_user_items(user_id)
        logger.info(f"[PocketMoney] 已迁移用户 {user_id} 的 {len(user_items)} 件专属物品回真实背包")

    def get_blacklist(self) -> List[str]:
        return self.blacklist.copy()

    def _get_or_create_shared_managers(self, real_money_mgr: PocketMoneyManager,
                                       real_backpack_mgr: BackpackManager) -> Dict[str, Any]:
        if self._shared_managers is not None:
            return self._shared_managers
        money_file = os.path.join(self.shared_isolation_dir, "pocket_money.json")
        if not os.path.exists(money_file) and real_money_mgr:
            with open(money_file, "w", encoding="utf-8") as f:
                json.dump({"balance": real_money_mgr.get_balance(), "records": [], "notes": []}, f, ensure_ascii=False, indent=2)
        self._shared_managers = {
            "money": PocketMoneyManager(self.shared_isolation_dir, 0, 50),
            "backpack": BackpackManager(self.shared_isolation_dir, 10, 3)
        }
        return self._shared_managers

    def get_isolated_managers(self, user_id: str, real_money_mgr: PocketMoneyManager,
                              real_backpack_mgr: BackpackManager) -> Dict[str, Any]:
        return self._get_or_create_shared_managers(real_money_mgr, real_backpack_mgr)

    def _save_data(self):
        if self._shared_managers:
            self._shared_managers["money"]._save_data()
            self._shared_managers["backpack"]._save_data()
        self._save_blacklist()
        self._save_pending_refunds()

    # ========== 同步方法 ==========

    def sync_expense_to_shared(self, amount: float, reason: str, operator_id: str, real_money_mgr: PocketMoneyManager):
        if not self.blacklist:
            return
        managers = self._get_or_create_shared_managers(real_money_mgr, None)
        mgr = managers["money"]
        if amount <= mgr.get_balance():
            mgr.add_expense(amount, reason, operator_id)

    def sync_income_to_shared(self, amount: float, reason: str, operator_id: str, real_money_mgr: PocketMoneyManager):
        if not self.blacklist:
            return
        managers = self._get_or_create_shared_managers(real_money_mgr, None)
        managers["money"].add_income(amount, reason, operator_id)

    def sync_store_to_shared(self, item_name: str, item_desc: str, real_backpack_mgr: BackpackManager):
        if not self.blacklist:
            return
        managers = self._get_or_create_shared_managers(None, real_backpack_mgr)
        managers["backpack"].add_shared_item(item_name, item_desc)

    def sync_use_to_shared(self, item_name: str, real_backpack_mgr: BackpackManager):
        if not self.blacklist:
            return
        managers = self._get_or_create_shared_managers(None, real_backpack_mgr)
        managers["backpack"].use_shared_item(item_name)

    def sync_set_balance_to_shared(self, new_balance: float, reason: str, operator_id: str, real_money_mgr: PocketMoneyManager):
        if not self.blacklist:
            return
        managers = self._get_or_create_shared_managers(real_money_mgr, None)
        managers["money"].set_balance(new_balance, reason, operator_id)

    # ========== 隔离池退款 ==========

    def _load_pending_refunds(self) -> List[Dict]:
        path = os.path.join(self.shared_isolation_dir, "pending_refunds.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return []

    def _save_pending_refunds(self):
        path = os.path.join(self.shared_isolation_dir, "pending_refunds.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.pending_refunds, f, ensure_ascii=False, indent=2)

    def add_pending_refund(self, amount: float, reason: str, operator_id: str):
        self.pending_refunds.append({
            "amount": amount, "reason": reason, "operator_id": operator_id,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "refund_at": (datetime.now() + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
        })
        self._save_pending_refunds()

    def process_pending_refunds(self, money_mgr: PocketMoneyManager):
        now = datetime.now()
        remaining = []
        refunded_total = 0
        refunded_times = []
        for refund in self.pending_refunds:
            try:
                refund_at = datetime.strptime(refund["refund_at"], "%Y-%m-%d %H:%M:%S")
                if now >= refund_at:
                    money_mgr.data["balance"] = round(money_mgr.get_balance() + refund["amount"], 2)
                    refunded_total += refund["amount"]
                    refunded_times.append(refund.get("time"))
                else:
                    remaining.append(refund)
            except (ValueError, KeyError):
                pass
        if refunded_total > 0:
            if refunded_times:
                money_mgr.data["records"] = [
                    r for r in money_mgr.data.get("records", [])
                    if not (r.get("isolation") and r.get("time") in refunded_times)
                ]
            money_mgr._save_data()
            self.pending_refunds = remaining
            self._save_pending_refunds()
            logger.info(f"[PocketMoney] 隔离池静默退款合计: +{refunded_total}元")
        elif len(remaining) != len(self.pending_refunds):
            self.pending_refunds = remaining
            self._save_pending_refunds()
