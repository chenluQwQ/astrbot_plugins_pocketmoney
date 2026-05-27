import json
import os
import random
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta

from astrbot.api import logger


class GamesManager:
    """
    小游戏框架
    - 刮刮乐：花钱买一张，刮开随机获得奖金
    - 炒股：虚拟股市，买入卖出赚差价
    - 可扩展更多游戏
    """

    def __init__(self, data_dir: str, config: dict = None):
        self.data_dir = data_dir
        self.config = config or {}
        os.makedirs(self.data_dir, exist_ok=True)
        self.data = self._load_data()
        self._refresh_stocks_if_needed()

    def _load_data(self) -> Dict[str, Any]:
        path = os.path.join(self.data_dir, "games.json")
        if not os.path.exists(path):
            return {"stocks": {}, "stock_date": "", "user_portfolios": {}, "scratch_stats": {}}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                data.setdefault("stocks", {})
                data.setdefault("stock_date", "")
                data.setdefault("user_portfolios", {})
                data.setdefault("scratch_stats", {})
                return data
        except (json.JSONDecodeError, TypeError):
            return {"stocks": {}, "stock_date": "", "user_portfolios": {}, "scratch_stats": {}}

    def _save_data(self):
        path = os.path.join(self.data_dir, "games.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    # ============================================================
    #  刮刮乐
    # ============================================================

    # 奖池定义：(奖项名, 倍率, 权重)
    # 倍率是相对于票价的倍数，0表示谢谢参与
    SCRATCH_PRIZES = [
        ("🎊 头奖", 10.0, 1),
        ("🎉 大奖", 5.0, 3),
        ("🎈 中奖", 3.0, 8),
        ("🎁 小奖", 2.0, 15),
        ("💰 回本", 1.0, 20),
        ("🍀 安慰奖", 0.5, 25),
        ("😅 谢谢参与", 0.0, 28),
    ]

    def play_scratch_card(self, user_id: str, ticket_price: int = None) -> Tuple[str, float, float]:
        """
        刮刮乐
        :param ticket_price: 票价，默认从配置读取
        :return: (奖项名, 奖金, 票价)
        """
        if ticket_price is None:
            ticket_price = self.config.get("scratch_ticket_price", 3)

        # 按权重随机
        prizes = self.config.get("scratch_prizes", None)
        if prizes:
            # 从配置中读取自定义奖池
            pool = [(p["name"], p["multiplier"], p["weight"]) for p in prizes]
        else:
            pool = self.SCRATCH_PRIZES

        total_weight = sum(w for _, _, w in pool)
        roll = random.uniform(0, total_weight)
        cumulative = 0
        prize_name = "😅 谢谢参与"
        multiplier = 0.0

        for name, mult, weight in pool:
            cumulative += weight
            if roll <= cumulative:
                prize_name = name
                multiplier = mult
                break

        winnings = round(ticket_price * multiplier, 2)

        # 记录统计
        stats = self.data.setdefault("scratch_stats", {})
        user_stats = stats.setdefault(user_id, {"played": 0, "spent": 0, "won": 0})
        user_stats["played"] += 1
        user_stats["spent"] += ticket_price
        user_stats["won"] += winnings
        self._save_data()

        return prize_name, winnings, ticket_price

    def get_scratch_stats(self, user_id: str) -> Dict:
        """获取用户刮刮乐统计"""
        return self.data.get("scratch_stats", {}).get(user_id, {"played": 0, "spent": 0, "won": 0})

    # ============================================================
    #  炒股
    # ============================================================

    # 虚拟股票列表（30只，min_level 控制解锁等级）
    STOCK_LIST = [
        # Lv.0 入门股（便宜，波动小）
        {"code": "FISH", "name": "摸鱼集团", "base_price": 4, "min_level": 0},
        {"code": "RAIN", "name": "雨天书屋", "base_price": 5, "min_level": 0},
        {"code": "RICE", "name": "干饭人餐饮", "base_price": 3, "min_level": 0},
        {"code": "DUCK", "name": "鸭鸭农场", "base_price": 4, "min_level": 0},
        {"code": "LEAF", "name": "绿叶文具", "base_price": 5, "min_level": 0},
        # Lv.3
        {"code": "CAKE", "name": "蛋糕工坊", "base_price": 8, "min_level": 3},
        {"code": "NEKO", "name": "猫猫科技", "base_price": 10, "min_level": 3},
        {"code": "MILK", "name": "牛奶公社", "base_price": 7, "min_level": 3},
        {"code": "GAME", "name": "快乐游戏", "base_price": 9, "min_level": 3},
        # Lv.5
        {"code": "STAR", "name": "星星传媒", "base_price": 15, "min_level": 5},
        {"code": "WIFI", "name": "蹭网科技", "base_price": 12, "min_level": 5},
        {"code": "BEAR", "name": "熊抱枕业", "base_price": 14, "min_level": 5},
        # Lv.8
        {"code": "MOON", "name": "月亮快递", "base_price": 20, "min_level": 8},
        {"code": "SOFA", "name": "躺平家居", "base_price": 18, "min_level": 8},
        {"code": "MEME", "name": "表情包传媒", "base_price": 22, "min_level": 8},
        # Lv.10
        {"code": "ROBO", "name": "机器人工业", "base_price": 30, "min_level": 10},
        {"code": "BREW", "name": "奶茶联盟", "base_price": 28, "min_level": 10},
        {"code": "KUMA", "name": "熊本控股", "base_price": 32, "min_level": 10},
        # Lv.13
        {"code": "DRGN", "name": "龙腾资本", "base_price": 50, "min_level": 13},
        {"code": "FIRE", "name": "火锅帝国", "base_price": 45, "min_level": 13},
        {"code": "PIXL", "name": "像素互娱", "base_price": 48, "min_level": 13},
        # Lv.16
        {"code": "COSM", "name": "宇宙航天", "base_price": 80, "min_level": 16},
        {"code": "DEEP", "name": "深海探索", "base_price": 75, "min_level": 16},
        {"code": "VOLT", "name": "闪电能源", "base_price": 85, "min_level": 16},
        {"code": "AURA", "name": "灵光医疗", "base_price": 70, "min_level": 16},
        # Lv.20 终极股
        {"code": "MYTH", "name": "神话控股", "base_price": 120, "min_level": 20},
        {"code": "VOID", "name": "虚空科技", "base_price": 150, "min_level": 20},
        {"code": "FATE", "name": "命运集团", "base_price": 130, "min_level": 20},
        {"code": "ZERO", "name": "零号实验室", "base_price": 140, "min_level": 20},
        {"code": "APEX", "name": "顶点资产", "base_price": 200, "min_level": 20},
    ]

    # 每日从各档随机抽取的数量
    DAILY_TIER_PICKS = {
        0: 3,    # Lv.0 档抽3只
        3: 2,    # Lv.3 档抽2只
        5: 1,    # Lv.5 档抽1只
        8: 1,    # Lv.8 档抽1只
        10: 1,   # Lv.10 档抽1只
        13: 1,   # Lv.13 档抽1只
        16: 0,   # Lv.16 有时出有时不出
        20: 0,   # Lv.20 有时出有时不出
    }

    def _refresh_stocks_if_needed(self):
        """每日刷新股价"""
        today = datetime.now().strftime("%Y-%m-%d")
        if self.data.get("stock_date") != today:
            self._generate_stock_prices(today)

    def _generate_stock_prices(self, today: str):
        """每日从30只股票中随机选10只，生成价格"""
        old_stocks = self.data.get("stocks", {})

        # 按等级分组
        tiers = {}
        for stock in self.STOCK_LIST:
            lv = stock.get("min_level", 0)
            tiers.setdefault(lv, []).append(stock)

        # 按配额从每档抽取
        selected = []
        for lv, count in self.DAILY_TIER_PICKS.items():
            pool = tiers.get(lv, [])
            if pool and count > 0:
                pick = min(count, len(pool))
                selected += random.sample(pool, pick)

        # 剩余名额随机补（高等级档有小概率出现）
        remaining = 10 - len(selected)
        if remaining > 0:
            already = {s["code"] for s in selected}
            extras = [s for s in self.STOCK_LIST if s["code"] not in already]
            if extras:
                selected += random.sample(extras, min(remaining, len(extras)))

        # 生成价格
        new_stocks = {}
        for stock in selected:
            code = stock["code"]
            yesterday_price = old_stocks.get(code, {}).get("price", stock["base_price"])
            change_pct = random.uniform(-0.30, 0.40)
            new_price = max(1, round(yesterday_price * (1 + change_pct), 1))

            new_stocks[code] = {
                "name": stock["name"],
                "price": new_price,
                "yesterday": yesterday_price,
                "change_pct": round(change_pct * 100, 1),
                "min_level": stock.get("min_level", 0),
            }

        self.data["stocks"] = new_stocks
        self.data["stock_date"] = today
        self._save_data()
        logger.info(f"[Games] 今日股市已开盘，{len(new_stocks)}只股票上市")

    def get_visible_stocks(self, user_level: int = 0) -> Dict[str, Dict]:
        """获取该等级可见的股票"""
        self._refresh_stocks_if_needed()
        return {
            code: info for code, info in self.data.get("stocks", {}).items()
            if info.get("min_level", 0) <= user_level
        }

    def get_stock_market(self) -> Dict[str, Dict]:
        """获取全部股市行情"""
        self._refresh_stocks_if_needed()
        return self.data.get("stocks", {})

    def buy_stock(self, user_id: str, code: str, shares: int) -> Tuple[bool, str, float]:
        """
        买入股票
        :return: (成功, 消息, 总花费)
        """
        self._refresh_stocks_if_needed()
        code = code.upper()
        stocks = self.data.get("stocks", {})

        if code not in stocks:
            return False, f"没有这支股票: {code}", 0

        if shares <= 0:
            return False, "买入数量必须大于0", 0

        stock = stocks[code]
        total_cost = round(stock["price"] * shares, 2)

        # 记录持仓
        portfolios = self.data.setdefault("user_portfolios", {})
        user_portfolio = portfolios.setdefault(user_id, {})
        holding = user_portfolio.setdefault(code, {"shares": 0, "total_cost": 0})
        holding["shares"] += shares
        holding["total_cost"] = round(holding["total_cost"] + total_cost, 2)
        self._save_data()

        return True, f"买入 {stock['name']}({code}) x{shares}股，花费 {total_cost}元", total_cost

    def sell_stock(self, user_id: str, code: str, shares: int) -> Tuple[bool, str, float]:
        """
        卖出股票
        :return: (成功, 消息, 收入)
        """
        self._refresh_stocks_if_needed()
        code = code.upper()
        stocks = self.data.get("stocks", {})

        if code not in stocks:
            return False, f"没有这支股票: {code}", 0

        portfolios = self.data.get("user_portfolios", {})
        user_portfolio = portfolios.get(user_id, {})
        holding = user_portfolio.get(code)

        if not holding or holding.get("shares", 0) <= 0:
            return False, f"你没有持有 {code}", 0

        if shares <= 0 or shares > holding["shares"]:
            return False, f"你只持有 {holding['shares']}股 {code}", 0

        stock = stocks[code]
        total_income = round(stock["price"] * shares, 2)

        # 计算成本均价和盈亏
        avg_cost = holding["total_cost"] / holding["shares"] if holding["shares"] > 0 else 0
        cost_of_sold = round(avg_cost * shares, 2)
        profit = round(total_income - cost_of_sold, 2)

        holding["shares"] -= shares
        holding["total_cost"] = round(holding["total_cost"] - cost_of_sold, 2)
        if holding["shares"] <= 0:
            del user_portfolio[code]
        self._save_data()

        profit_str = f"+{profit}" if profit >= 0 else str(profit)
        return True, f"卖出 {stock['name']}({code}) x{shares}股，收入 {total_income}元（盈亏 {profit_str}元）", total_income

    def get_user_portfolio(self, user_id: str) -> Dict[str, Dict]:
        """获取用户持仓"""
        self._refresh_stocks_if_needed()
        stocks = self.data.get("stocks", {})
        portfolio = self.data.get("user_portfolios", {}).get(user_id, {})

        result = {}
        for code, holding in portfolio.items():
            if holding.get("shares", 0) > 0:
                current_price = stocks.get(code, {}).get("price", 0)
                avg_cost = holding["total_cost"] / holding["shares"] if holding["shares"] > 0 else 0
                market_value = round(current_price * holding["shares"], 2)
                profit = round(market_value - holding["total_cost"], 2)
                result[code] = {
                    "name": stocks.get(code, {}).get("name", code),
                    "shares": holding["shares"],
                    "avg_cost": round(avg_cost, 2),
                    "current_price": current_price,
                    "market_value": market_value,
                    "profit": profit,
                }
        return result

    def format_stock_market(self, user_level: int = 0) -> str:
        """格式化股市行情显示（按等级过滤）"""
        all_stocks = self.get_stock_market()
        if not all_stocks:
            return "📈 股市暂未开盘"

        lines = [f"📈 今日股市行情（{self.data['stock_date']}）：\n"]
        for code, info in all_stocks.items():
            min_lv = info.get("min_level", 0)
            if min_lv > user_level:
                lines.append(f"  🔒 ???({code}): Lv.{min_lv}解锁")
                continue
            change = info.get("change_pct", 0)
            if change > 0:
                arrow = "🔴↑"
            elif change < 0:
                arrow = "🟢↓"
            else:
                arrow = "⚪️→"
            lines.append(
                f"  {arrow} {info['name']}({code}): {info['price']}元"
                f" ({'+' if change >= 0 else ''}{change}%)"
            )

        lines.append(f"\n💡 买入：买股票 <代码> <数量>")
        lines.append(f"💡 卖出：卖股票 <代码> <数量>")
        lines.append(f"💡 持仓：我的股票")
        return "\n".join(lines)

    def format_user_portfolio(self, user_id: str) -> str:
        """格式化用户持仓显示"""
        portfolio = self.get_user_portfolio(user_id)
        if not portfolio:
            return "📊 你还没有持仓，去股市看看吧~"

        lines = ["📊 我的股票持仓：\n"]
        total_value = 0
        total_profit = 0
        for code, info in portfolio.items():
            profit_str = f"+{info['profit']}" if info['profit'] >= 0 else str(info['profit'])
            emoji = "🔴" if info['profit'] >= 0 else "🟢"
            lines.append(
                f"  {emoji} {info['name']}({code}): {info['shares']}股"
                f" | 均价{info['avg_cost']}元 | 现价{info['current_price']}元"
                f" | 市值{info['market_value']}元 | 盈亏{profit_str}元"
            )
            total_value += info['market_value']
            total_profit += info['profit']

        total_profit_str = f"+{total_profit}" if total_profit >= 0 else str(total_profit)
        lines.append(f"\n💰 总市值：{round(total_value, 2)}元 | 总盈亏：{total_profit_str}元")
        return "\n".join(lines)
