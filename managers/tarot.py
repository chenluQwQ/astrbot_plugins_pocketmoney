import json
import os
import random
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from astrbot.api import logger


class TarotManager:
    """
    塔罗牌系统
    - 经典韦特塔罗 78 张（22 大阿卡纳 + 56 小阿卡纳）
    - 牌阵：单牌(1) / 时间之流(3) / 六芒星(6)
    - 日运：每日免费三张
    - 正位/逆位
    """

    def __init__(self, data_dir: str, config: dict = None):
        self.data_dir = data_dir
        self.config = config or {}
        os.makedirs(self.data_dir, exist_ok=True)
        self.data = self._load_data()
        # 图片目录：插件根目录下的 images/tarot/
        self._images_dir = ""

    def set_images_dir(self, images_dir: str):
        """设置塔罗牌图片目录"""
        self._images_dir = images_dir

    # 文件名映射：card_id → 图片文件名
    _IMAGE_MAP = {
        # 大阿卡纳
        "major_0": "tarot-0-fool.jpg",
        "major_1": "tarot-1-magician.jpg",
        "major_2": "tarot-2-high-priestess.jpg",
        "major_3": "tarot-3-the-empress.jpg",
        "major_4": "tarot-4-the-emperor.jpg",
        "major_5": "tarot-5-the-hierophant.jpg",
        "major_6": "tarot-6-the-lovers.jpg",
        "major_7": "tarot-7-the-chariot.jpg",
        "major_8": "tarot-8-strength.jpg",
        "major_9": "tarot-9-hermit.jpg",
        "major_10": "tarot-10-wheel-of-fortune.jpg",
        "major_11": "tarot-11-justice.jpg",
        "major_12": "tarot-12-the-hanged-man.jpg",
        "major_13": "tarot-13-death.jpg",
        "major_14": "tarot-14-temperance.jpg",
        "major_15": "tarot-15-the-devil.jpg",
        "major_16": "tarot-16-the-tower.jpg",
        "major_17": "tarot-17-the-star.jpg",
        "major_18": "tarot-18-the-moon.jpg",
        "major_19": "tarot-19-the-sun.jpg",
        "major_20": "tarot-20-judgement.jpg",
        "major_21": "tarot-21-the-world.jpg",
        # 权杖 (wands) 01-10=数字牌, 11=page, 12=knight, 13=queen, 14=king
        "wands_1": "wands01.jpg", "wands_2": "wands02.jpg", "wands_3": "wands03.jpg",
        "wands_4": "wands04.jpg", "wands_5": "wands05.jpg", "wands_6": "wands06.jpg",
        "wands_7": "wands07.jpg", "wands_8": "wands08.jpg", "wands_9": "wands09.jpg",
        "wands_10": "wands10.jpg",
        "wands_page": "wands11.jpg", "wands_knight": "wands12.jpg",
        "wands_queen": "wands13.jpg", "wands_king": "wands14.jpg",
        # 圣杯 (cups)
        "cups_1": "cups01.jpg", "cups_2": "cups02.jpg", "cups_3": "cups03.jpg",
        "cups_4": "cups04.jpg", "cups_5": "cups05.jpg", "cups_6": "cups06.jpg",
        "cups_7": "cups07.jpg", "cups_8": "cups08.jpg", "cups_9": "cups09.jpg",
        "cups_10": "cups10.jpg",
        "cups_page": "cups11.jpg", "cups_knight": "cups12.jpg",
        "cups_queen": "cups13.jpg", "cups_king": "cups14.jpg",
        # 宝剑 (swords)
        "swords_1": "swords01.jpg", "swords_2": "swords02.jpg", "swords_3": "swords03.jpg",
        "swords_4": "swords04.jpg", "swords_5": "swords05.jpg", "swords_6": "swords06.jpg",
        "swords_7": "swords07.jpg", "swords_8": "swords08.jpg", "swords_9": "swords09.jpg",
        "swords_10": "swords10.jpg",
        "swords_page": "swords11.jpg", "swords_knight": "swords12.jpg",
        "swords_queen": "swords13.jpg", "swords_king": "swords14.jpg",
        # 星币 (pentacles)
        "pentacles_1": "pents01.jpg", "pentacles_2": "pents02.jpg", "pentacles_3": "pents03.jpg",
        "pentacles_4": "pents04.jpg", "pentacles_5": "pents05.jpg", "pentacles_6": "pents06.jpg",
        "pentacles_7": "pents07.jpg", "pentacles_8": "pents08.jpg", "pentacles_9": "pents09.jpg",
        "pentacles_10": "pents10.jpg",
        "pentacles_page": "pents11.jpg", "pentacles_knight": "pents12.jpg",
        "pentacles_queen": "pents13.jpg", "pentacles_king": "pents14.jpg",
    }

    def get_card_image_path(self, card: Dict) -> Optional[str]:
        """获取牌面图片路径，没有则返回None"""
        if not self._images_dir:
            return None
        card_id = card.get("id", "")
        filename = self._IMAGE_MAP.get(card_id)
        if not filename:
            return None
        path = os.path.join(self._images_dir, filename)
        if os.path.exists(path):
            return path
        return None

    def get_cards_image_paths(self, cards: List[Dict]) -> List[Optional[str]]:
        """批量获取牌面图片路径"""
        return [self.get_card_image_path(card) for card in cards]

    def has_images(self) -> bool:
        """检查是否有可用的图片"""
        if not self._images_dir or not os.path.isdir(self._images_dir):
            return False
        return any(f.endswith(('.jpg', '.png')) for f in os.listdir(self._images_dir))

    def _load_data(self) -> Dict[str, Any]:
        path = os.path.join(self.data_dir, "tarot.json")
        if not os.path.exists(path):
            return {"daily_records": {}, "user_stats": {}}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                data.setdefault("daily_records", {})
                data.setdefault("user_stats", {})
                return data
        except (json.JSONDecodeError, TypeError):
            return {"daily_records": {}, "user_stats": {}}

    def _save_data(self):
        path = os.path.join(self.data_dir, "tarot.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    # ============================================================
    #  78 张经典韦特塔罗牌
    # ============================================================

    # 大阿卡纳 22 张
    MAJOR_ARCANA = [
        {"id": 0,  "name": "愚者",   "emoji": "🃏", "en": "The Fool",
         "upright": "新开始、冒险、自由、天真", "reversed": "鲁莽、冒失、停滞不前"},
        {"id": 1,  "name": "魔术师", "emoji": "🎩", "en": "The Magician",
         "upright": "创造力、自信、技能、意志力", "reversed": "欺骗、操控、才能浪费"},
        {"id": 2,  "name": "女祭司", "emoji": "🌙", "en": "The High Priestess",
         "upright": "直觉、潜意识、内在智慧、神秘", "reversed": "隐藏的动机、表面化、忽略直觉"},
        {"id": 3,  "name": "女皇",   "emoji": "👑", "en": "The Empress",
         "upright": "丰饶、母性、自然、感官享受", "reversed": "依赖、空虚、创造力受阻"},
        {"id": 4,  "name": "皇帝",   "emoji": "🏛️", "en": "The Emperor",
         "upright": "权威、结构、控制、父性", "reversed": "专制、僵化、控制欲过强"},
        {"id": 5,  "name": "教皇",   "emoji": "📿", "en": "The Hierophant",
         "upright": "传统、信仰、指引、顺从", "reversed": "打破常规、叛逆、新的方法"},
        {"id": 6,  "name": "恋人",   "emoji": "💕", "en": "The Lovers",
         "upright": "爱情、和谐、选择、价值观", "reversed": "失衡、价值冲突、不和谐"},
        {"id": 7,  "name": "战车",   "emoji": "⚔️", "en": "The Chariot",
         "upright": "意志力、决心、胜利、行动", "reversed": "失控、攻击性、方向迷失"},
        {"id": 8,  "name": "力量",   "emoji": "🦁", "en": "Strength",
         "upright": "勇气、耐心、内在力量、柔中带刚", "reversed": "自我怀疑、软弱、缺乏勇气"},
        {"id": 9,  "name": "隐者",   "emoji": "🏔️", "en": "The Hermit",
         "upright": "内省、独处、指引、智慧", "reversed": "孤立、偏执、逃避"},
        {"id": 10, "name": "命运之轮", "emoji": "🎡", "en": "Wheel of Fortune",
         "upright": "转变、命运、好运、循环", "reversed": "厄运、抗拒变化、失控"},
        {"id": 11, "name": "正义",   "emoji": "⚖️", "en": "Justice",
         "upright": "公正、真相、因果、法律", "reversed": "不公、不诚实、逃避责任"},
        {"id": 12, "name": "倒吊人", "emoji": "🙃", "en": "The Hanged Man",
         "upright": "牺牲、等待、新视角、放下", "reversed": "拖延、无谓牺牲、固执"},
        {"id": 13, "name": "死神",   "emoji": "💀", "en": "Death",
         "upright": "结束、转变、告别过去、重生", "reversed": "抗拒改变、恐惧、停滞"},
        {"id": 14, "name": "节制",   "emoji": "🏺", "en": "Temperance",
         "upright": "平衡、耐心、调和、中庸", "reversed": "失衡、过度、缺乏耐心"},
        {"id": 15, "name": "恶魔",   "emoji": "😈", "en": "The Devil",
         "upright": "束缚、执念、物质主义、欲望", "reversed": "解放、摆脱束缚、面对阴影"},
        {"id": 16, "name": "塔",     "emoji": "🗼", "en": "The Tower",
         "upright": "剧变、崩塌、觉醒、真相揭露", "reversed": "恐惧改变、逃避灾难、延迟"},
        {"id": 17, "name": "星星",   "emoji": "⭐", "en": "The Star",
         "upright": "希望、信念、灵感、宁静", "reversed": "失去希望、悲观、脱节"},
        {"id": 18, "name": "月亮",   "emoji": "🌛", "en": "The Moon",
         "upright": "幻象、潜意识、恐惧、直觉", "reversed": "释放恐惧、真相浮现、困惑消散"},
        {"id": 19, "name": "太阳",   "emoji": "☀️", "en": "The Sun",
         "upright": "快乐、成功、活力、光明", "reversed": "暂时的低落、过度乐观"},
        {"id": 20, "name": "审判",   "emoji": "📯", "en": "Judgement",
         "upright": "觉醒、重生、反思、召唤", "reversed": "自我怀疑、拒绝反思、后悔"},
        {"id": 21, "name": "世界",   "emoji": "🌍", "en": "The World",
         "upright": "完成、成就、圆满、旅程终点", "reversed": "未完成、缺少结束感、延迟"},
    ]

    # 小阿卡纳花色定义
    SUITS = {
        "wands": {"name": "权杖", "emoji": "🔥", "element": "火"},
        "cups": {"name": "圣杯", "emoji": "💧", "element": "水"},
        "swords": {"name": "宝剑", "emoji": "💨", "element": "风"},
        "pentacles": {"name": "星币", "emoji": "🪙", "element": "土"},
    }

    # 小阿卡纳数字牌含义（1-10）
    _MINOR_PIPS = {
        1:  {"name": "Ace", "cn": "王牌",
             "upright": "新的开始、潜力、机会",  "reversed": "错失机会、延迟、方向不明"},
        2:  {"name": "Two", "cn": "二",
             "upright": "平衡、选择、合作",      "reversed": "犹豫、失衡、冲突"},
        3:  {"name": "Three", "cn": "三",
             "upright": "成长、创造、团队",      "reversed": "过度扩张、缺乏计划"},
        4:  {"name": "Four", "cn": "四",
             "upright": "稳定、基础、休息",      "reversed": "不安、不满、停滞"},
        5:  {"name": "Five", "cn": "五",
             "upright": "冲突、挑战、竞争",      "reversed": "和解、接受、学会放手"},
        6:  {"name": "Six", "cn": "六",
             "upright": "和谐、回忆、慷慨",      "reversed": "执着过去、不平等"},
        7:  {"name": "Seven", "cn": "七",
             "upright": "反思、评估、耐心",      "reversed": "焦虑、缺乏信心、偷懒"},
        8:  {"name": "Eight", "cn": "八",
             "upright": "行动、速度、进展",      "reversed": "拖延、受困、方向混乱"},
        9:  {"name": "Nine", "cn": "九",
             "upright": "接近完成、满足、独立",  "reversed": "未尽之事、担忧、孤独"},
        10: {"name": "Ten", "cn": "十",
             "upright": "圆满、结束、传承",      "reversed": "负担过重、抗拒结束"},
    }

    # 宫廷牌
    _COURT_CARDS = {
        "page":   {"cn": "侍从", "upright": "好奇、学习、新消息",    "reversed": "不成熟、缺乏方向"},
        "knight": {"cn": "骑士", "upright": "行动、冒险、追求",      "reversed": "冲动、鲁莽、缺乏计划"},
        "queen":  {"cn": "王后", "upright": "滋养、直觉、温柔力量",  "reversed": "过度保护、情绪化"},
        "king":   {"cn": "国王", "upright": "领导、成熟、掌控",      "reversed": "独断、控制欲、僵化"},
    }

    @classmethod
    def _build_full_deck(cls) -> List[Dict]:
        """构建完整78张牌"""
        deck = []

        # 大阿卡纳
        for card in cls.MAJOR_ARCANA:
            deck.append({
                "id": f"major_{card['id']}",
                "name": card["name"],
                "emoji": card["emoji"],
                "en": card["en"],
                "type": "major",
                "upright": card["upright"],
                "reversed": card["reversed"],
            })

        # 小阿卡纳
        for suit_key, suit_info in cls.SUITS.items():
            # 数字牌 1-10
            for num, pip_info in cls._MINOR_PIPS.items():
                name = f"{suit_info['name']}{pip_info['cn']}"
                deck.append({
                    "id": f"{suit_key}_{num}",
                    "name": name,
                    "emoji": suit_info["emoji"],
                    "en": f"{pip_info['name']} of {suit_key.title()}",
                    "type": "minor",
                    "suit": suit_key,
                    "number": num,
                    "upright": pip_info["upright"],
                    "reversed": pip_info["reversed"],
                })
            # 宫廷牌
            for court_key, court_info in cls._COURT_CARDS.items():
                name = f"{suit_info['name']}{court_info['cn']}"
                deck.append({
                    "id": f"{suit_key}_{court_key}",
                    "name": name,
                    "emoji": suit_info["emoji"],
                    "en": f"{court_key.title()} of {suit_key.title()}",
                    "type": "court",
                    "suit": suit_key,
                    "upright": court_info["upright"],
                    "reversed": court_info["reversed"],
                })

        return deck

    # ============================================================
    #  抽牌核心
    # ============================================================

    def draw_cards(self, count: int) -> List[Dict]:
        """
        从牌堆中抽取指定数量的牌（不重复），每张随机正/逆位
        :return: [{...card_data, "position": "正位"/"逆位"}, ...]
        """
        deck = self._build_full_deck()
        selected = random.sample(deck, min(count, len(deck)))
        result = []
        for card in selected:
            pos = random.choice(["正位", "逆位"])
            card_with_pos = dict(card)
            card_with_pos["position"] = pos
            card_with_pos["keywords"] = card["upright"] if pos == "正位" else card["reversed"]
            result.append(card_with_pos)
        return result

    # ============================================================
    #  牌阵定义
    # ============================================================

    # 牌阵配置：(名称, 牌数, 位置标签列表, 价格)
    SPREADS = {
        "single": {
            "name": "单牌占卜",
            "count": 1,
            "labels": ["指引"],
            "price": 2,
            "desc": "一张牌，一个答案",
        },
        "three": {
            "name": "时间之流",
            "count": 3,
            "labels": ["过去", "现在", "未来"],
            "price": 5,
            "desc": "过去·现在·未来，三张牌揭示时间的脉络",
        },
        "hexagram": {
            "name": "六芒星",
            "count": 6,
            "labels": ["过去", "现在", "未来", "潜意识", "外部影响", "建议"],
            "price": 10,
            "desc": "六芒星牌阵，全方位深度解读",
        },
    }

    # ============================================================
    #  格式化显示
    # ============================================================

    @staticmethod
    def format_single_card(card: Dict, label: str = "") -> str:
        """格式化单张牌显示"""
        pos_icon = "△" if card["position"] == "正位" else "▽"
        label_str = f" {label} " if label else ""
        return (
            f"┌─────────┐\n"
            f"│ {card['emoji']}      │\n"
            f"│ {card['name']:<6} │\n"
            f"│ {pos_icon} {card['position']}  │\n"
            f"└─────────┘\n"
            f"{label_str}"
        )

    @staticmethod
    def format_card_row(cards: List[Dict], labels: List[str]) -> str:
        """横排格式化多张牌"""
        lines_top = []
        lines_emoji = []
        lines_name = []
        lines_pos = []
        lines_bot = []
        lines_label = []

        for i, card in enumerate(cards):
            pos_icon = "△" if card["position"] == "正位" else "▽"
            label = labels[i] if i < len(labels) else ""

            lines_top.append("┌─────────┐")
            lines_emoji.append(f"│ {card['emoji']}      │")
            # 牌名最多4字，pad到合适宽度
            name = card["name"]
            lines_name.append(f"│  {name:<5} │")
            lines_pos.append(f"│ {pos_icon} {card['position']}  │")
            lines_bot.append("└─────────┘")
            lines_label.append(f"  {label:<7} ")

        sep = " "
        result = (
            sep.join(lines_top) + "\n" +
            sep.join(lines_emoji) + "\n" +
            sep.join(lines_name) + "\n" +
            sep.join(lines_pos) + "\n" +
            sep.join(lines_bot) + "\n" +
            sep.join(lines_label)
        )
        return result

    def format_spread_display(self, spread_type: str, cards: List[Dict]) -> str:
        """格式化完整牌阵展示"""
        spread = self.SPREADS.get(spread_type)
        if not spread:
            return "未知牌阵"

        labels = spread["labels"]
        title = spread["name"]

        header = f"🔮 ── {title} ──\n\n"

        if spread_type == "single":
            body = self.format_single_card(cards[0], labels[0])
            body += f"\n🔑 {cards[0]['keywords']}"
        elif spread_type == "three":
            body = self.format_card_row(cards, labels)
            body += "\n"
            for i, card in enumerate(cards):
                body += f"\n{labels[i]}：{card['name']}（{card['position']}）— {card['keywords']}"
        elif spread_type == "hexagram":
            # 六芒星：上排3张 + 下排3张
            body = self.format_card_row(cards[:3], labels[:3])
            body += "\n"
            body += self.format_card_row(cards[3:], labels[3:])
            body += "\n"
            for i, card in enumerate(cards):
                body += f"\n{labels[i]}：{card['name']}（{card['position']}）— {card['keywords']}"
        else:
            body = ""

        return header + body

    def format_daily_display(self, cards: List[Dict]) -> str:
        """格式化日运展示"""
        labels = ["总运", "事业/学业", "感情"]
        header = "🌅 ── 今日运势 ──\n\n"
        body = self.format_card_row(cards, labels)
        body += "\n"
        for i, card in enumerate(cards):
            body += f"\n{labels[i]}：{card['name']}（{card['position']}）— {card['keywords']}"
        return header + body

    # ============================================================
    #  LLM 解读 prompt 构建
    # ============================================================

    @staticmethod
    def build_interpretation_prompt(spread_type: str, cards: List[Dict],
                                     labels: List[str], question: str = "") -> str:
        """构建给 LLM 的解读 prompt"""
        cards_desc = []
        for i, card in enumerate(cards):
            label = labels[i] if i < len(labels) else f"第{i+1}张"
            major_minor = "大阿卡纳" if card["type"] == "major" else "小阿卡纳"
            cards_desc.append(
                f"- {label}位：{card['name']}（{card['en']}）{card['position']}，"
                f"{major_minor}，关键词：{card['keywords']}"
            )

        question_str = f"\n提问者的问题：{question}" if question else ""

        prompt = (
            f"你正在为提问者做塔罗牌占卜解读。{question_str}\n\n"
            f"牌阵类型：{spread_type}\n"
            f"抽到的牌：\n" + "\n".join(cards_desc) + "\n\n"
            "请根据牌面组合做出整体解读。注意：\n"
            "1. 综合所有牌面的关联性，不要逐张孤立解释\n"
            "2. 语气柔和但有洞察力，像一位资深占卜师\n"
            "3. 给出实际可行的建议\n"
            "4. 控制在150字以内\n"
            "5. 直接给出解读内容，不要有多余的开场白"
        )
        return prompt

    @staticmethod
    def build_daily_prompt(cards: List[Dict]) -> str:
        """构建日运解读 prompt"""
        labels = ["总运", "事业/学业", "感情"]
        cards_desc = []
        for i, card in enumerate(cards):
            cards_desc.append(
                f"- {labels[i]}：{card['name']}（{card['position']}）— {card['keywords']}"
            )

        prompt = (
            "你正在为用户做今日运势解读。\n\n"
            "抽到的三张牌：\n" + "\n".join(cards_desc) + "\n\n"
            "请做一段简洁的日运解读：\n"
            "1. 整体概括今天的运势走向\n"
            "2. 分别点一下总运/事业学业/感情\n"
            "3. 给一句今日小建议\n"
            "4. 语气轻松温暖\n"
            "5. 控制在120字以内\n"
            "6. 直接给出解读，不要有开场白"
        )
        return prompt

    # ============================================================
    #  日运限制
    # ============================================================

    def has_daily_fortune_today(self, user_id: str) -> bool:
        """检查用户今天是否已经看过日运"""
        today = datetime.now().strftime("%Y-%m-%d")
        return self.data.get("daily_records", {}).get(user_id) == today

    def record_daily_fortune(self, user_id: str):
        """记录用户今天已看日运"""
        today = datetime.now().strftime("%Y-%m-%d")
        self.data.setdefault("daily_records", {})[user_id] = today
        self._save_data()

    # ============================================================
    #  统计
    # ============================================================

    def record_reading(self, user_id: str, spread_type: str):
        """记录占卜次数"""
        stats = self.data.setdefault("user_stats", {})
        user_stats = stats.setdefault(user_id, {"total": 0, "spreads": {}})
        user_stats["total"] += 1
        spread_counts = user_stats.setdefault("spreads", {})
        spread_counts[spread_type] = spread_counts.get(spread_type, 0) + 1
        self._save_data()

    def get_stats(self, user_id: str) -> Dict:
        """获取用户占卜统计"""
        return self.data.get("user_stats", {}).get(
            user_id, {"total": 0, "spreads": {}}
        )

    def format_menu(self) -> str:
        """格式化塔罗菜单"""
        lines = [
            "🔮 ── 塔罗占卜 ──\n",
        ]
        for key, spread in self.SPREADS.items():
            lines.append(f"  {spread['emoji'] if 'emoji' in spread else '🃏'} {spread['name']}（{spread['count']}张）— {spread['price']}元")
            lines.append(f"     {spread['desc']}")
        lines.append(f"  🌅 今日运势（3张）— 免费，每日一次")
        lines.append(f"\n💡 指令：")
        lines.append(f"  塔罗 单牌 [问题]")
        lines.append(f"  塔罗 三牌 [问题]")
        lines.append(f"  塔罗 六芒星 [问题]")
        lines.append(f"  今日运势")
        return "\n".join(lines)
