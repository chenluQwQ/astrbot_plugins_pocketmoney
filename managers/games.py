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
                data.setdefault("slots_stats", {})
                return data
        except (json.JSONDecodeError, TypeError):
            return {"stocks": {}, "stock_date": "", "user_portfolios": {}, "scratch_stats": {},
                    "slots_stats": {}}

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

    # ============================================================
    #  老虎机
    # ============================================================

    # 符号定义：(emoji, 名称, 三连倍率, 权重)
    # 权重越高越常见；三连倍率是相对投币额的倍数
    SLOT_SYMBOLS = [
        ("🍒", "樱桃", 3, 30),
        ("🍋", "柠檬", 4, 25),
        ("🍊", "橘子", 5, 20),
        ("🔔", "铃铛", 8, 14),
        ("⭐", "星星", 12, 7),
        ("💎", "钻石", 20, 3),
        ("7️⃣", "幸运7", 50, 1),
    ]

    def _spin_reel(self) -> Tuple[str, str]:
        """转一个轮子，返回 (emoji, 名称)"""
        pool = []
        for emoji, name, _, weight in self.SLOT_SYMBOLS:
            pool.extend([(emoji, name)] * weight)
        return random.choice(pool)

    def play_slots(self, user_id: str, bet: float = None) -> Tuple[str, float, float, List[str]]:
        """
        玩老虎机
        :param bet: 投币额，默认从配置读取
        :return: (结果描述, 奖金, 投入, [reel1_emoji, reel2_emoji, reel3_emoji])
        """
        if bet is None:
            bet = self.config.get("slots_bet", 5)

        # 转三个轮子
        r1_emoji, r1_name = self._spin_reel()
        r2_emoji, r2_name = self._spin_reel()
        r3_emoji, r3_name = self._spin_reel()
        reels = [r1_emoji, r2_emoji, r3_emoji]

        # 判定结果
        if r1_emoji == r2_emoji == r3_emoji:
            # 三连！查找倍率
            multiplier = 3  # 默认
            for emoji, name, mult, _ in self.SLOT_SYMBOLS:
                if emoji == r1_emoji:
                    multiplier = mult
                    break
            winnings = round(bet * multiplier, 2)
            desc = f"🎰 三连{r1_name}！ x{multiplier}倍"
        elif r1_emoji == r2_emoji or r2_emoji == r3_emoji or r1_emoji == r3_emoji:
            # 两个相同 = 回本
            winnings = round(bet * 1.5, 2)
            desc = "🎰 两个相同，小赚一笔~"
        else:
            winnings = 0
            desc = "🎰 没有匹配，再试试运气！"

        # 记录统计
        stats = self.data.setdefault("slots_stats", {})
        user_stats = stats.setdefault(user_id, {
            "played": 0, "spent": 0, "won": 0, "jackpots": 0, "best_multi": 0
        })
        user_stats["played"] += 1
        user_stats["spent"] = round(user_stats["spent"] + bet, 2)
        user_stats["won"] = round(user_stats["won"] + winnings, 2)
        if r1_emoji == r2_emoji == r3_emoji:
            user_stats["jackpots"] += 1
            for emoji, _, mult, _ in self.SLOT_SYMBOLS:
                if emoji == r1_emoji and mult > user_stats.get("best_multi", 0):
                    user_stats["best_multi"] = mult
        self._save_data()

        return desc, winnings, bet, reels

    def get_slots_stats(self, user_id: str) -> Dict:
        """获取用户老虎机统计"""
        return self.data.get("slots_stats", {}).get(
            user_id, {"played": 0, "spent": 0, "won": 0, "jackpots": 0, "best_multi": 0}
        )

    # ============================================================
    #  LLM 工具专用：沉浸式格式化输出
    # ============================================================

    @staticmethod
    def format_scratch_immersive(prize_name: str, winnings: float, ticket_price: float, balance: float) -> str:
        """刮刮乐 LLM 工具沉浸式输出（类似指令格式）"""
        net = round(winnings - ticket_price, 2)
        # 生成3个刮开区域
        symbols = ["💰", "🎁", "⭐", "🍀", "💎", "🎊", "❌", "🔔"]
        if winnings > 0:
            # 赢了：根据奖项给不同的展示
            if "头奖" in prize_name:
                slots = ["💎", "💎", "💎"]
            elif "大奖" in prize_name:
                slots = ["⭐", "⭐", "⭐"]
            elif "中奖" in prize_name:
                slots = ["🎁", "🎁", random.choice(["🎁", "⭐"])]
            elif "小奖" in prize_name:
                slots = ["💰", "💰", random.choice(symbols)]
            elif "回本" in prize_name:
                slots = ["🍀", "🍀", random.choice(symbols)]
            else:
                slots = [random.choice(["🍀", "💰"]), random.choice(symbols), random.choice(symbols)]
            net_str = f"+{net}" if net >= 0 else str(net)
            result = (
                f"┌─────────────────┐\n"
                f"│   🎰 刮 刮 乐   │\n"
                f"├─────────────────┤\n"
                f"│  {slots[0]}  │  {slots[1]}  │  {slots[2]}  │\n"
                f"├─────────────────┤\n"
                f"│  {prize_name}！\n"
                f"│  💰 奖金：{winnings}元\n"
                f"│  📊 净收益：{net_str}元\n"
                f"│  💳 余额：{balance}元\n"
                f"└─────────────────┘"
            )
        else:
            slots = [random.choice(["❌", "😅"]), random.choice(symbols), random.choice(["❌", "😅"])]
            result = (
                f"┌─────────────────┐\n"
                f"│   🎰 刮 刮 乐   │\n"
                f"├─────────────────┤\n"
                f"│  {slots[0]}  │  {slots[1]}  │  {slots[2]}  │\n"
                f"├─────────────────┤\n"
                f"│  {prize_name}\n"
                f"│  💸 花费 {ticket_price}元\n"
                f"│  💳 余额：{balance}元\n"
                f"└─────────────────┘"
            )
        return result

    @staticmethod
    def format_slots_immersive(desc: str, winnings: float, bet: float, reels: List[str], balance: float) -> str:
        """老虎机 LLM 工具沉浸式输出（类似指令格式）"""
        net = round(winnings - bet, 2)
        header = (
            f"┌─────────────────┐\n"
            f"│   🎰 老 虎 机   │\n"
            f"├─────────────────┤\n"
            f"│  ┃ {reels[0]} ┃ {reels[1]} ┃ {reels[2]} ┃  │\n"
            f"├─────────────────┤\n"
        )
        if winnings > 0:
            net_str = f"+{net}" if net >= 0 else str(net)
            body = (
                f"│  {desc}\n"
                f"│  💰 奖金：{winnings}元\n"
                f"│  📊 净赚：{net_str}元\n"
                f"│  💳 余额：{balance}元\n"
            )
        else:
            body = (
                f"│  {desc}\n"
                f"│  💸 投入 {bet}元\n"
                f"│  💳 余额：{balance}元\n"
            )
        return header + body + f"└─────────────────┘"

    # ============================================================
    #  21点 (Blackjack)
    # ============================================================

    CARD_SUITS = ["♠️", "♥️", "♣️", "♦️"]
    CARD_RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]

    @staticmethod
    def _card_value(rank: str) -> int:
        """单张牌的基础点数"""
        if rank in ("J", "Q", "K"):
            return 10
        if rank == "A":
            return 11
        return int(rank)

    @staticmethod
    def _hand_value(hand: List[Dict]) -> int:
        """计算手牌总点数（A自动降为1）"""
        total = sum(GamesManager._card_value(c["rank"]) for c in hand)
        aces = sum(1 for c in hand if c["rank"] == "A")
        while total > 21 and aces > 0:
            total -= 10
            aces -= 1
        return total

    @staticmethod
    def _format_hand(hand: List[Dict], hide_second: bool = False) -> str:
        """格式化手牌显示"""
        if hide_second and len(hand) >= 2:
            return f"{hand[0]['suit']}{hand[0]['rank']}  🂠"
        return "  ".join(f"{c['suit']}{c['rank']}" for c in hand)

    def _new_deck(self) -> List[Dict]:
        """创建一副洗好的牌"""
        deck = []
        for suit in self.CARD_SUITS:
            for rank in self.CARD_RANKS:
                deck.append({"suit": suit, "rank": rank})
        random.shuffle(deck)
        return deck

    def start_blackjack(self, user_id: str, bet: float) -> Dict:
        """
        开始21点游戏
        :return: 游戏状态dict
        """
        deck = self._new_deck()
        player_hand = [deck.pop(), deck.pop()]
        dealer_hand = [deck.pop(), deck.pop()]

        game = {
            "user_id": user_id,
            "bet": bet,
            "deck": deck,
            "player_hand": player_hand,
            "dealer_hand": dealer_hand,
            "status": "playing",  # playing / player_bust / dealer_bust / player_win / dealer_win / push / blackjack
        }

        # 检查天胡21点
        player_val = self._hand_value(player_hand)
        dealer_val = self._hand_value(dealer_hand)
        if player_val == 21 and dealer_val == 21:
            game["status"] = "push"
        elif player_val == 21:
            game["status"] = "blackjack"
        elif dealer_val == 21:
            game["status"] = "dealer_win"

        return game

    def blackjack_hit(self, game: Dict) -> Dict:
        """玩家要牌"""
        if game["status"] != "playing":
            return game
        card = game["deck"].pop()
        game["player_hand"].append(card)
        if self._hand_value(game["player_hand"]) > 21:
            game["status"] = "player_bust"
        return game

    def blackjack_stand(self, game: Dict) -> Dict:
        """玩家停牌，庄家按规则补牌"""
        if game["status"] != "playing":
            return game

        # 庄家补牌规则：< 17必须补
        while self._hand_value(game["dealer_hand"]) < 17:
            game["dealer_hand"].append(game["deck"].pop())

        player_val = self._hand_value(game["player_hand"])
        dealer_val = self._hand_value(game["dealer_hand"])

        if dealer_val > 21:
            game["status"] = "dealer_bust"
        elif player_val > dealer_val:
            game["status"] = "player_win"
        elif player_val < dealer_val:
            game["status"] = "dealer_win"
        else:
            game["status"] = "push"

        return game

    def blackjack_double(self, game: Dict) -> Dict:
        """加倍：只能在初始两张牌时使用，加倍赌注并只拿一张牌然后自动停牌"""
        if game["status"] != "playing" or len(game["player_hand"]) != 2:
            return game
        game["bet"] = round(game["bet"] * 2, 2)
        card = game["deck"].pop()
        game["player_hand"].append(card)
        if self._hand_value(game["player_hand"]) > 21:
            game["status"] = "player_bust"
        else:
            game = self.blackjack_stand(game)
        return game

    def blackjack_settle(self, game: Dict) -> Tuple[float, str]:
        """
        结算21点
        :return: (净收益, 结果描述) 正数=赢钱 负数=输钱 0=平局
        """
        bet = game["bet"]
        status = game["status"]
        player_val = self._hand_value(game["player_hand"])
        dealer_val = self._hand_value(game["dealer_hand"])

        if status == "blackjack":
            winnings = round(bet * 1.5, 2)  # 天胡21点赔1.5倍
            return winnings, "🃏 Blackjack！天胡21点！"
        elif status == "player_bust":
            return -bet, "💥 爆牌了！超过21点"
        elif status == "dealer_bust":
            return bet, f"🎉 庄家爆牌！（庄家 {dealer_val} 点）"
        elif status == "player_win":
            return bet, f"🎉 你赢了！（{player_val} vs 庄家 {dealer_val}）"
        elif status == "dealer_win":
            return -bet, f"😢 庄家赢了（{player_val} vs 庄家 {dealer_val}）"
        elif status == "push":
            return 0, f"🤝 平局！（都是 {player_val} 点）"
        return 0, "未知状态"

    def format_blackjack_table(self, game: Dict, reveal_dealer: bool = False) -> str:
        """格式化21点牌桌显示"""
        player_val = self._hand_value(game["player_hand"])
        hide = not reveal_dealer and game["status"] == "playing"
        dealer_display = self._format_hand(game["dealer_hand"], hide_second=hide)
        if hide:
            dealer_val_str = f"{self._card_value(game['dealer_hand'][0]['rank'])}+?"
        else:
            dealer_val_str = str(self._hand_value(game["dealer_hand"]))

        player_display = self._format_hand(game["player_hand"])

        table = (
            f"┌──────────────────────┐\n"
            f"│    🃏  21点  🃏      │\n"
            f"├──────────────────────┤\n"
            f"│ 庄家：{dealer_display}\n"
            f"│ 　　　（{dealer_val_str}点）\n"
            f"│                      │\n"
            f"│ 你的：{player_display}\n"
            f"│ 　　　（{player_val}点）\n"
            f"├──────────────────────┤\n"
            f"│ 💰 赌注：{game['bet']}元\n"
            f"└──────────────────────┘"
        )
        return table

    def record_blackjack_stats(self, user_id: str, bet: float, net: float, status: str = ""):
        """记录21点统计"""
        stats = self.data.setdefault("blackjack_stats", {})
        user_stats = stats.setdefault(user_id, {
            "played": 0, "won": 0, "lost": 0, "push": 0,
            "total_bet": 0, "total_net": 0, "blackjacks": 0
        })
        user_stats["played"] += 1
        user_stats["total_bet"] = round(user_stats["total_bet"] + bet, 2)
        user_stats["total_net"] = round(user_stats["total_net"] + net, 2)
        if net > 0:
            user_stats["won"] += 1
        elif net < 0:
            user_stats["lost"] += 1
        else:
            user_stats["push"] += 1
        if status == "blackjack":
            user_stats["blackjacks"] = user_stats.get("blackjacks", 0) + 1
        self._save_data()

    def get_blackjack_stats(self, user_id: str) -> Dict:
        """获取用户21点统计"""
        return self.data.get("blackjack_stats", {}).get(
            user_id, {"played": 0, "won": 0, "lost": 0, "push": 0,
                       "total_bet": 0, "total_net": 0, "blackjacks": 0}
        )
