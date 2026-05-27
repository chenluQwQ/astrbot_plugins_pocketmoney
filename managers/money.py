import json
import os
import random
from typing import Dict, Any, List
from datetime import datetime, timedelta

from astrbot.api import logger


class PocketMoneyManager:
    """
    小金库管理系统（含存折功能）
    - 全局余额管理（不区分会话）
    - 入账/出账记录
    - 存折：需要审批才能取款的安全余额
    - 笔记功能：备忘录
    """

    def __init__(self, data_dir: str, initial_balance: float = 0, max_records: int = 100):
        self.data_dir = data_dir
        self.initial_balance = initial_balance
        self.max_records = max_records
        os.makedirs(self.data_dir, exist_ok=True)
        self.data = self._load_data()
        self._migrate_savings_data()

    def _load_data(self) -> Dict[str, Any]:
        path = os.path.join(self.data_dir, "pocket_money.json")
        if not os.path.exists(path):
            return {"balance": self.initial_balance, "records": [], "savings_balance": 0, "pending_withdrawals": []}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                data.setdefault("balance", self.initial_balance)
                data.setdefault("records", [])
                data.setdefault("savings_balance", 0)
                data.setdefault("pending_withdrawals", [])
                return data
        except (json.JSONDecodeError, TypeError):
            return {"balance": self.initial_balance, "records": [], "savings_balance": 0, "pending_withdrawals": []}

    def _migrate_savings_data(self):
        """迁移旧的存折数据到小金库（仅执行一次）"""
        old_path = os.path.join(self.data_dir, "savings_book.json")
        if os.path.exists(old_path):
            try:
                with open(old_path, "r", encoding="utf-8") as f:
                    old_data = json.load(f)
                    if old_data.get("balance", 0) > 0:
                        self.data["savings_balance"] = old_data.get("balance", 0)
                    if old_data.get("pending_withdrawals"):
                        self.data["pending_withdrawals"] = old_data.get("pending_withdrawals", [])
                    self._save_data()
                    logger.info(f"[PocketMoney] 已迁移旧存折数据: 余额{old_data.get('balance', 0)}元")
                migrated_path = old_path + ".migrated"
                os.rename(old_path, migrated_path)
            except (json.JSONDecodeError, IOError):
                pass

    def _save_data(self):
        path = os.path.join(self.data_dir, "pocket_money.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def get_balance(self) -> float:
        return self.data.get("balance", 0)

    def get_recent_records(self, count: int = 5) -> List[Dict[str, Any]]:
        records = self.data.get("records", [])
        return records[-count:] if records else []

    def get_recent_income_records(self, count: int = 2) -> List[Dict[str, Any]]:
        records = self.data.get("records", [])
        income_records = [r for r in records if r["type"] == "income"]
        return income_records[-count:] if income_records else []

    def get_recent_expense_records(self, count: int = 5) -> List[Dict[str, Any]]:
        records = self.data.get("records", [])
        expense_records = [r for r in records if r["type"] == "expense"]
        return expense_records[-count:] if expense_records else []

    def get_today_expense(self) -> float:
        today = datetime.now().strftime("%Y-%m-%d")
        records = self.data.get("records", [])
        return sum(r["amount"] for r in records if r["type"] == "expense" and r["time"].startswith(today))

    def get_all_records(self) -> List[Dict[str, Any]]:
        return self.data.get("records", [])

    def add_income(self, amount: float, reason: str, operator_id: str = "") -> bool:
        if amount <= 0:
            return False
        self.data["balance"] = round(self.get_balance() + amount, 2)
        self.data["records"].append({
            "type": "income", "amount": amount, "reason": reason,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "operator_id": operator_id
        })
        if len(self.data["records"]) > self.max_records:
            self.data["records"] = self.data["records"][-self.max_records:]
        self._save_data()
        return True

    def add_expense(self, amount: float, reason: str, operator_id: str = "", isolation: bool = False) -> bool:
        if amount <= 0 or amount > self.get_balance():
            return False
        self.data["balance"] = round(self.get_balance() - amount, 2)
        record = {
            "type": "expense", "amount": amount, "reason": reason,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "operator_id": operator_id
        }
        if isolation:
            record["isolation"] = True
        self.data["records"].append(record)
        if len(self.data["records"]) > self.max_records:
            self.data["records"] = self.data["records"][-self.max_records:]
        self._save_data()
        return True

    def set_balance(self, amount: float, reason: str, operator_id: str = "") -> bool:
        old_balance = self.get_balance()
        self.data["balance"] = round(amount, 2)
        diff = amount - old_balance
        record_type = "income" if diff >= 0 else "expense"
        self.data["records"].append({
            "type": record_type, "amount": abs(diff),
            "reason": f"[余额调整] {reason}",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "operator_id": operator_id
        })
        if len(self.data["records"]) > self.max_records:
            self.data["records"] = self.data["records"][-self.max_records:]
        self._save_data()
        return True

    # ========== 笔记功能 ==========

    def get_notes(self) -> list:
        notes = self.data.get("notes", [])
        if not notes and self.data.get("note"):
            return [self.data.get("note")]
        return notes

    def get_note(self) -> str:
        notes = self.get_notes()
        if not notes:
            return ""
        return "\n".join([f"{i+1}. {note}" for i, note in enumerate(notes)])

    def add_note(self, content: str, max_entries: int = 5) -> bool:
        content = content.strip()
        if not content:
            return False
        notes = self.data.get("notes", [])
        if not notes and self.data.get("note"):
            notes = [self.data.get("note")]
            self.data.pop("note", None)
        notes.append(content)
        if len(notes) > max_entries:
            notes = notes[-max_entries:]
        self.data["notes"] = notes
        self._save_data()
        return True

    def set_note(self, content: str, max_entries: int = 5) -> bool:
        return self.add_note(content, max_entries)

    def clear_notes(self) -> bool:
        self.data["notes"] = []
        self.data.pop("note", None)
        self._save_data()
        return True

    def clear_note(self) -> bool:
        return self.clear_notes()

    def delete_note(self, index: int) -> bool:
        notes = self.get_notes()
        if not notes:
            return False
        idx = index - 1
        if idx < 0 or idx >= len(notes):
            return False
        if "notes" not in self.data:
            self.data["notes"] = notes
        self.data["notes"].pop(idx)
        self._save_data()
        return True

    # ========== 存折功能 ==========

    def get_savings_balance(self) -> float:
        return self.data.get("savings_balance", 0)

    def deposit_to_savings(self, amount: float, reason: str, operator_id: str = "") -> bool:
        if amount <= 0 or amount > self.get_balance():
            return False
        self.data["balance"] = round(self.get_balance() - amount, 2)
        self.data["savings_balance"] = round(self.get_savings_balance() + amount, 2)
        self.data["records"].append({
            "type": "expense", "amount": amount,
            "reason": f"[转入存折] {reason}",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "operator_id": operator_id
        })
        self._save_data()
        return True

    def withdraw_from_savings(self, amount: float, reason: str, operator_id: str = "") -> bool:
        if amount <= 0 or amount > self.get_savings_balance():
            return False
        self.data["savings_balance"] = round(self.get_savings_balance() - amount, 2)
        self.data["balance"] = round(self.get_balance() + amount, 2)
        self.data["records"].append({
            "type": "income", "amount": amount,
            "reason": f"[存折取款] {reason}",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "operator_id": operator_id
        })
        self._save_data()
        return True

    def apply_withdrawal(self, amount: float, reason: str, source_info: dict = None) -> str:
        if amount <= 0 or amount > self.get_savings_balance():
            return ""
        existing_ids = {w.get("id") for w in self.data.get("pending_withdrawals", [])}
        application_id = ""
        for _ in range(100):
            application_id = str(random.randint(1000, 9999))
            if application_id not in existing_ids:
                break
        self.data["pending_withdrawals"].append({
            "id": application_id, "amount": amount, "reason": reason,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "pending", "source_info": source_info or {}
        })
        self._save_data()
        return application_id

    def get_pending_withdrawals(self) -> List[Dict[str, Any]]:
        return [w for w in self.data.get("pending_withdrawals", []) if w.get("status") == "pending"]

    def approve_withdrawal(self, application_id: str, operator_id: str = "", approve_reason: str = "") -> tuple:
        for w in self.data.get("pending_withdrawals", []):
            if w.get("id") == application_id and w.get("status") == "pending":
                amount, reason = w.get("amount", 0), w.get("reason", "")
                if amount > self.get_savings_balance():
                    return (False, 0, "余额不足", {})
                w["status"] = "approved"
                w["approved_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if approve_reason:
                    w["approve_reason"] = approve_reason
                withdraw_reason = f"[申请取款] {reason}"
                if approve_reason:
                    withdraw_reason += f"（批准备注：{approve_reason}）"
                self.withdraw_from_savings(amount, withdraw_reason, operator_id)
                return (True, amount, reason, w.get("source_info", {}))
        return (False, 0, "申请不存在或已处理", {})

    def reject_withdrawal(self, application_id: str, reject_reason: str = "", operator_id: str = "") -> tuple:
        for w in self.data.get("pending_withdrawals", []):
            if w.get("id") == application_id and w.get("status") == "pending":
                w["status"] = "rejected"
                w["reject_reason"] = reject_reason
                self._save_data()
                return (True, w.get("amount", 0), w.get("reason", ""), w.get("source_info", {}))
        return (False, 0, "申请不存在或已处理", {})

    def ignore_withdrawal(self, application_id: str) -> tuple:
        pending = self.data.get("pending_withdrawals", [])
        for i, w in enumerate(pending):
            if w.get("id") == application_id and w.get("status") == "pending":
                amount = w.get("amount", 0)
                reason = w.get("reason", "")
                pending.pop(i)
                self._save_data()
                return (True, amount, reason)
        return (False, 0, "申请不存在或已处理")
