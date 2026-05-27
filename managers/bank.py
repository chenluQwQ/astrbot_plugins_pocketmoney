import json
import os
from typing import Dict, Any, List, Tuple
from datetime import datetime, timedelta

from astrbot.api import logger


class BankManager:
    """
    银行系统
    - 最低存款 10000 元
    - 每日结算利息（按年利率折算日利率）
    - 基础年利率 3%，等级每提升1级 +0.2%（最高翻倍）
    - 支持多笔存款
    """

    BASE_ANNUAL_RATE = 0.03   # 基础年利率 3%
    LEVEL_RATE_BONUS = 0.002  # 每级 +0.2%
    MAX_RATE_MULTIPLIER = 2.0 # 最高利率倍数
    MIN_DEPOSIT = 10000       # 最低存款

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)
        self.data = self._load_data()

    def _load_data(self) -> Dict[str, Any]:
        path = os.path.join(self.data_dir, "bank.json")
        if not os.path.exists(path):
            return {"accounts": {}}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                data.setdefault("accounts", {})
                return data
        except (json.JSONDecodeError, TypeError):
            return {"accounts": {}}

    def _save_data(self):
        path = os.path.join(self.data_dir, "bank.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def _get_account(self, user_id: str) -> Dict:
        accounts = self.data.setdefault("accounts", {})
        if user_id not in accounts:
            accounts[user_id] = {
                "deposits": [],      # [{amount, deposited_at, last_interest_date}]
                "total_interest": 0,  # 累计利息
            }
        return accounts[user_id]

    def get_annual_rate(self, user_level: int = 0) -> float:
        """根据等级计算年利率"""
        bonus = user_level * self.LEVEL_RATE_BONUS
        rate = self.BASE_ANNUAL_RATE + bonus
        max_rate = self.BASE_ANNUAL_RATE * self.MAX_RATE_MULTIPLIER
        return min(rate, max_rate)

    def get_total_balance(self, user_id: str) -> float:
        """获取银行总余额（本金+未结算利息不算）"""
        account = self._get_account(user_id)
        return sum(d["amount"] for d in account["deposits"])

    def deposit(self, user_id: str, amount: float) -> Tuple[bool, str]:
        """
        存款
        :return: (成功, 消息)
        """
        if amount < self.MIN_DEPOSIT:
            return False, f"最低存款 {self.MIN_DEPOSIT} 元"

        account = self._get_account(user_id)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        account["deposits"].append({
            "amount": round(amount, 2),
            "deposited_at": now,
            "last_interest_date": now[:10],
        })
        self._save_data()
        return True, f"存入 {amount} 元成功"

    def withdraw(self, user_id: str, deposit_index: int = 0) -> Tuple[bool, str, float]:
        """
        取款（取出指定笔存款的全部本金）
        :return: (成功, 消息, 取出金额)
        """
        account = self._get_account(user_id)
        deposits = account["deposits"]

        if not deposits:
            return False, "没有存款", 0

        if deposit_index < 0 or deposit_index >= len(deposits):
            return False, f"存款编号无效（共{len(deposits)}笔）", 0

        removed = deposits.pop(deposit_index)
        amount = removed["amount"]
        self._save_data()
        return True, f"取出 {amount} 元", amount

    def settle_interest(self, user_id: str, user_level: int = 0) -> float:
        """
        结算利息（每日调用一次）
        :return: 本次结算的利息总额
        """
        account = self._get_account(user_id)
        if not account["deposits"]:
            return 0

        today = datetime.now().strftime("%Y-%m-%d")
        annual_rate = self.get_annual_rate(user_level)
        daily_rate = annual_rate / 365

        total_interest = 0
        for deposit in account["deposits"]:
            last_date = deposit.get("last_interest_date", today)
            if last_date >= today:
                continue  # 今天已结算
            # 计算天数差
            try:
                d1 = datetime.strptime(last_date, "%Y-%m-%d")
                d2 = datetime.strptime(today, "%Y-%m-%d")
                days = (d2 - d1).days
            except ValueError:
                days = 1

            interest = round(deposit["amount"] * daily_rate * days, 2)
            deposit["amount"] = round(deposit["amount"] + interest, 2)
            deposit["last_interest_date"] = today
            total_interest += interest

        if total_interest > 0:
            account["total_interest"] = round(
                account.get("total_interest", 0) + total_interest, 2
            )
            self._save_data()

        return total_interest

    def format_bank_info(self, user_id: str, user_level: int = 0) -> str:
        """格式化银行信息"""
        account = self._get_account(user_id)
        deposits = account["deposits"]
        rate = self.get_annual_rate(user_level)

        if not deposits:
            return (
                f"🏦 银行账户\n"
                f"💰 余额：0 元\n"
                f"📈 年利率：{rate*100:.1f}%（Lv.{user_level}加成）\n"
                f"💡 最低存款 {self.MIN_DEPOSIT} 元，指令：存银行 <金额>"
            )

        total = sum(d["amount"] for d in deposits)
        lines = [
            f"🏦 银行账户",
            f"💰 总余额：{round(total, 2)} 元（{len(deposits)}笔）",
            f"📈 年利率：{rate*100:.1f}%（Lv.{user_level}加成）",
            f"📊 累计利息：{account.get('total_interest', 0)} 元",
            "",
        ]
        for i, d in enumerate(deposits):
            lines.append(
                f"  [{i+1}] {d['amount']}元 | 存入 {d['deposited_at'][:10]}"
            )

        lines.append(f"\n💡 取款：取银行 <编号>")
        return "\n".join(lines)
