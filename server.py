#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PortMasters multiplayer online server v4 (account edition)
- Account system: register / log in (username + password, persisted per user in users.json)
- Online lobby: logging in puts you online, with the online player list broadcast live; disconnecting takes you offline
- Invite system: each player can send at most one invite per minute, which auto-expires after 60 seconds with no response;
  the other player can accept (both enter a shared session) or decline (the sender gets a decline notice)
- Shared session: 8 rounds x 4 phases per round, with both players always on the same round and phase,
  advancing in sync via a "Continue (n/2)" mechanism
- The barter phase requires both players to click "Ready" before moving on to artisan management
- Chat system: both players in a session can message each other while online; sending is disabled while offline
- The web page and WebSocket share the same port 8080 (so a single ngrok tunnel can expose both, with wss support)
"""

import asyncio
import json
import math
import random
import http
import mimetypes
import websockets
from websockets.datastructures import Headers
from websockets.http11 import Response
import os
import time
import hashlib
import secrets

# -------------------- Constants --------------------
RESOURCES_TIER0 = ["麻布", "丝绸", "茶叶"]
RESOURCES_TIER1 = ["瓷土", "铜矿"]
RESOURCES_TIER2 = ["香料", "珍珠"]
RESOURCES = RESOURCES_TIER0 + RESOURCES_TIER1 + RESOURCES_TIER2

PRODUCTS_TIER0 = ["麻衣", "布衣", "绫罗绸缎", "香囊"]
PRODUCTS_TIER1 = ["紫铜镜", "青瓷器"]
PRODUCTS_TIER2 = ["蕃香脂", "珠链"]
PRODUCTS = PRODUCTS_TIER0 + PRODUCTS_TIER1 + PRODUCTS_TIER2

PORTS_TIER0 = ["泉州港", "广州港", "宁波港", "扬州港", "杭州港"]
PORTS_TIER1 = ["福州港", "高丽港"]
PORTS_TIER2 = ["三佛齐港", "大食港"]
PORTS = PORTS_TIER0 + PORTS_TIER1 + PORTS_TIER2

ESCORT_COST = 10

# -------------------- Difficulty --------------------
# Difficulty is a single, per-session cap on the highest content tier that may ever
# unlock. It is intentionally expressed in the same Tier 0/1/2 vocabulary the rest of
# the game already uses, so there is exactly one gating concept rather than a parallel
# system. Easy keeps the whole voyage inside the founding Tier 0 set (the first three
# raw materials, the four starter products, the first three artisan guilds, and only the
# fortunes, ship modules, ports and weather tied to them). Hard lifts the cap to the full
# pool and lets the existing Silk Road Charter reveal Tier 1 at round 3 and Tier 2 at
# round 5 exactly as before. New tiers added later need no difficulty-specific code: they
# inherit this cap automatically.
DIFFICULTIES = {
    "easy": {"max_tier": 0},
    "hard": {"max_tier": 2},
}
DEFAULT_DIFFICULTY = "easy"


def normalize_difficulty(value):
    """Coerce any client-supplied value to a known difficulty, defaulting to easy."""
    return value if value in DIFFICULTIES else DEFAULT_DIFFICULTY


def difficulty_max_tier(difficulty):
    return DIFFICULTIES[normalize_difficulty(difficulty)]["max_tier"]


def unlocked(tier0, tier1, tier2, round_no, max_tier=2):
    """Unlock content pools by round, but never above the difficulty's tier cap.
    Round 3 unlocks Tier 1 (New Maritime Edict) and round 5 unlocks Tier 2 (Ten Thousand
    Kingdoms Trade); max_tier caps that progression so easy mode (max_tier 0) stays on
    Tier 0 for the entire voyage while hard mode (max_tier 2) keeps today's progression."""
    items = tier0[:]
    if round_no >= 3 and max_tier >= 1:
        items += tier1
    if round_no >= 5 and max_tier >= 2:
        items += tier2
    return items


# Silk Road Charter: announces newly unlocked content on the Set Sail page.
# Each announcement belongs to the tier it reveals, so it must stay silent when the
# difficulty cap keeps that tier locked (in easy mode no further tier ever opens).
CHARTER_TIER_BY_ROUND = {3: 1, 5: 2}
CHARTER_EVENTS = {
    3: {
        "id": "tier1",
        "icon": "🗺️",
        "name": "市舶新政",
        "desc": "福建市舶司新政颁布！瓷土、铜矿、青瓷器、紫铜镜加入行情；福州港、高丽港正式开埠；陶匠与铜匠加入劳务市场；新的福缘与战船改装随之而来。",
    },
    5: {
        "id": "tier2",
        "icon": "🌏",
        "name": "万国通商",
        "desc": "万国通商盛况空前！香料、珍珠、蕃香脂、珠链加入行情；三佛齐港、大食港正式开埠；香料师与珠宝匠加入劳务市场；更多福缘与战船改装随之而来。",
    },
}

MONSOON_TIER0 = [
    {
        "id": "spring_current",
        "name": "春潮顺流",
        "icon": "🌦️",
        "desc": "泉州港与广州港订单报酬提高15%，茶叶采购价降低10%。海盗风险较低。",
        "rewardPorts": ["泉州港", "广州港"],
        "rewardMultiplier": 1.15,
        "resource": "茶叶",
        "purchaseMultiplier": 0.90,
        "pirateRisk": 0.10,
        "pirateLoss": 8,
    },
    {
        "id": "summer_monsoon",
        "name": "盛夏季风",
        "icon": "⛈️",
        "desc": "杭州港与扬州港订单报酬提高20%，丝绸采购价提高15%。海盗风险升高。",
        "rewardPorts": ["杭州港", "扬州港"],
        "rewardMultiplier": 1.20,
        "resource": "丝绸",
        "purchaseMultiplier": 1.15,
        "pirateRisk": 0.25,
        "pirateLoss": 14,
    },
    {
        "id": "autumn_gales",
        "name": "秋汛乱流",
        "icon": "🍂",
        "desc": "宁波港与泉州港订单报酬提高18%，麻布采购价降低15%。海盗风险中等。",
        "rewardPorts": ["宁波港", "泉州港"],
        "rewardMultiplier": 1.18,
        "resource": "麻布",
        "purchaseMultiplier": 0.85,
        "pirateRisk": 0.18,
        "pirateLoss": 11,
    },
    {
        "id": "winter_blockade",
        "name": "冬海封锁",
        "icon": "❄️",
        "desc": "广州港与杭州港订单报酬提高25%，茶叶采购价提高15%。海盗风险最高。",
        "rewardPorts": ["广州港", "杭州港"],
        "rewardMultiplier": 1.25,
        "resource": "茶叶",
        "purchaseMultiplier": 1.15,
        "pirateRisk": 0.30,
        "pirateLoss": 18,
    },
]

MONSOON_TIER1 = [
    {
        "id": "fujian_kiln_smoke",
        "name": "闽江窑烟",
        "icon": "🌫️",
        "desc": "福州港与泉州港订单报酬提高18%，瓷土采购价降低12%。海盗风险中等。",
        "rewardPorts": ["福州港", "泉州港"],
        "rewardMultiplier": 1.18,
        "resource": "瓷土",
        "purchaseMultiplier": 0.88,
        "pirateRisk": 0.15,
        "pirateLoss": 10,
    },
    {
        "id": "goryeo_dawn_route",
        "name": "高丽晓航",
        "icon": "🌅",
        "desc": "高丽港与广州港订单报酬提高20%，铜矿采购价降低10%。海盗风险较高。",
        "rewardPorts": ["高丽港", "广州港"],
        "rewardMultiplier": 1.20,
        "resource": "铜矿",
        "purchaseMultiplier": 0.90,
        "pirateRisk": 0.20,
        "pirateLoss": 12,
    },
]

MONSOON_TIER2 = [
    {
        "id": "srivijaya_spice_breeze",
        "name": "三佛齐香风",
        "icon": "🌴",
        "desc": "三佛齐港与大食港订单报酬提高22%，香料采购价降低15%。海盗风险较高。",
        "rewardPorts": ["三佛齐港", "大食港"],
        "rewardMultiplier": 1.22,
        "resource": "香料",
        "purchaseMultiplier": 0.85,
        "pirateRisk": 0.22,
        "pirateLoss": 14,
    },
    {
        "id": "dashi_pearl_moon",
        "name": "大食珠月",
        "icon": "🌙",
        "desc": "大食港与三佛齐港订单报酬提高25%，珍珠采购价降低15%。海盗风险最高。",
        "rewardPorts": ["大食港", "三佛齐港"],
        "rewardMultiplier": 1.25,
        "resource": "珍珠",
        "purchaseMultiplier": 0.85,
        "pirateRisk": 0.25,
        "pirateLoss": 16,
    },
]

MONSOON_STATES = MONSOON_TIER0 + MONSOON_TIER1 + MONSOON_TIER2

RECIPES = {
    "麻衣": {"materials": {"麻布": 2}, "value": 15, "worker_type": "weaver"},
    "布衣": {"materials": {"麻布": 2, "丝绸": 1}, "value": 35, "worker_type": "weaver"},
    "绫罗绸缎": {"materials": {"丝绸": 3}, "value": 60, "worker_type": "master"},
    "香囊": {"materials": {"丝绸": 1, "茶叶": 2}, "value": 80, "worker_type": "sachet_maker"},
    "紫铜镜": {"materials": {"铜矿": 3}, "value": 45, "worker_type": "coppersmith"},
    "青瓷器": {"materials": {"瓷土": 3}, "value": 65, "worker_type": "potter"},
    "蕃香脂": {"materials": {"香料": 2, "丝绸": 1}, "value": 85, "worker_type": "perfumer"},
    "珠链": {"materials": {"珍珠": 2, "丝绸": 1}, "value": 105, "worker_type": "jeweler"}
}

COMMODITIES = {
    "麻布": {"ports": ["泉州港", "宁波港"], "basePrice": (3, 6)},
    "丝绸": {"ports": ["杭州港", "扬州港"], "basePrice": (6, 10)},
    "茶叶": {"ports": ["广州港", "泉州港"], "basePrice": (10, 14)},
    "瓷土": {"ports": ["泉州港", "福州港"], "basePrice": (8, 12)},
    "铜矿": {"ports": ["广州港", "高丽港"], "basePrice": (10, 15)},
    "香料": {"ports": ["三佛齐港", "大食港"], "basePrice": (14, 20)},
    "珍珠": {"ports": ["广州港", "三佛齐港"], "basePrice": (16, 24)}
}

PRODUCT_PRICES = {
    "麻衣": (30, 42), "布衣": (50, 65),
    "绫罗绸缎": (70, 90), "香囊": (95, 120),
    "紫铜镜": (55, 72), "青瓷器": (78, 100),
    "蕃香脂": (100, 130), "珠链": (125, 160)
}

RESOURCE_PROBS = {"麻布": 0.30, "丝绸": 0.26, "茶叶": 0.18, "瓷土": 0.14, "铜矿": 0.12, "香料": 0.08, "珍珠": 0.06}
WAGES = {"weaver": 8, "master": 12, "sachet_maker": 20, "coppersmith": 12, "potter": 14, "perfumer": 18, "jeweler": 24}

# Worker-type storage: each worker type maps to a worker-list attribute name on PlayerGame
WORKER_TYPES_BACKEND = [
    {"id": "weaver", "attr": "weavers"},
    {"id": "master", "attr": "masterWeavers"},
    {"id": "sachet_maker", "attr": "sachetMakers"},
    {"id": "coppersmith", "attr": "coppersmiths"},
    {"id": "potter", "attr": "potters"},
    {"id": "perfumer", "attr": "perfumers"},
    {"id": "jeweler", "attr": "jewelers"},
]
WORKER_ATTR = {w["id"]: w["attr"] for w in WORKER_TYPES_BACKEND}
WORKER_IDS_TIER0 = ["weaver", "master", "sachet_maker"]
WORKER_IDS_TIER1 = ["coppersmith", "potter"]
WORKER_IDS_TIER2 = ["perfumer", "jeweler"]

BOONS_TIER0 = [
    {"id": "silk_wind", "name": "丝路顺风", "icon": "🌬️", "desc": "本回合丝绸及成品运费减半。", "modifiers": {"transport_silk_discount": 0.5}},
    {"id": "favorable_tides", "name": "顺风顺水", "icon": "🌊", "desc": "本回合基础运费减4金币。", "modifiers": {"transport_flat_discount": 4}},
    {"id": "merchant_charm", "name": "商贾魅力", "icon": "✨", "desc": "本回合采购85折优惠。", "modifiers": {"purchase_discount": 0.15}},
    {"id": "artisan_inspiration", "name": "匠人灵感", "icon": "🔨", "desc": "本回合所有工人多生产1件。", "modifiers": {"worker_bonus_production": 1}},
    {"id": "emergency_loan", "name": "紧急钱庄", "icon": "💰", "desc": "立即获得40金币。", "modifiers": {"instant_gold": 40}},
    {"id": "tax_shelter", "name": "免税令", "icon": "📜", "desc": "本回合所得税率降至5%。", "modifiers": {"income_tax_override": 0.05}},
    {"id": "hemp_monopoly", "name": "麻布专营", "icon": "🧶", "desc": "麻布采购单价降低2金币。", "modifiers": {"hemp_price_reduction": 2}},
    {"id": "master_apprentice", "name": "学徒传承", "icon": "🎓", "desc": "本回合雇佣工资减半。", "modifiers": {"hire_discount": 0.5}}
]

BOONS_TIER1 = [
    {"id": "farsight", "name": "千里眼", "icon": "🔮", "desc": "本回合免费获得1条牙行密语线索。", "modifiers": {"free_intel": 1}},
    {"id": "porcelain_bronze_guild", "name": "陶铜联号", "icon": "🏮", "desc": "本回合「青瓷器」与「紫铜镜」订单报酬提高15%。", "modifiers": {"product_order_bonus": {"products": ["青瓷器", "紫铜镜"], "pct": 0.15}}},
    {"id": "frontier_tariff_relief", "name": "拓商减负", "icon": "🧾", "desc": "本回合交付成品订单的增值税减半。", "modifiers": {"vat_discount": 0.5}},
]

BOONS_TIER2 = [
    {"id": "exotic_treasures", "name": "蕃国奇珍", "icon": "💎", "desc": "本回合「蕃香脂」与「珠链」订单报酬提高15%。", "modifiers": {"product_order_bonus": {"products": ["蕃香脂", "珠链"], "pct": 0.15}}},
    {"id": "deep_sea_escort_pact", "name": "远洋护航", "icon": "🛡️", "desc": "本回合雇佣护航费用减半，海盗风险减半。", "modifiers": {"escort_discount": 0.5, "pirate_risk_discount": 0.5}},
    {"id": "merchants_converge", "name": "万商云集", "icon": "🛍️", "desc": "本回合贸易阶段额外出现1张订单。", "modifiers": {"extra_order": 1}},
]

BOONS = BOONS_TIER0 + BOONS_TIER1 + BOONS_TIER2

MODULES_TIER0 = [
    {"id": "smugglers_hold", "name": "走私暗舱", "icon": "🏴‍☠️", "desc": "采购成本-15%。所得税+20%。"},
    {"id": "bulk_hauler", "name": "散货索具", "icon": "🏗️", "desc": "每件货物运费-1。船坞升级费用+15金币。"},
    {"id": "artisans_workshop", "name": "工匠工坊", "icon": "🛠️", "desc": "工人产量+1。工资+20%。"},
    {"id": "tax_evasion", "name": "避税账本", "icon": "📒", "desc": "所得税按增值税后利润计。15%概率在订单完成时罚款20金币(稽查)。"},
    {"id": "silk_monopoly", "name": "丝路垂断", "icon": "🐍", "desc": "丝绸运费为0。丝绸产品订单收入+20%。"},
    {"id": "brokers_network", "name": "牙行网络", "icon": "🕵️", "desc": "每次花费2金币。每次购买密语显示2条线索。"},
    {"id": "salvage_crane", "name": "打捞起重机", "icon": "♻️", "desc": "30%概率在订单完成时退还运费。"},
    {"id": "overdrive_engine", "name": "超载引擎", "icon": "⚡", "desc": "运费-5金币。维护费+10金币。"}
]

MODULES_TIER1 = [
    {"id": "bureau_token", "name": "市舶司令牌", "icon": "🎫", "desc": "新航线货品（瓷土、铜矿及其成品）订单收入+10%。"},
    {"id": "kiln_cellar", "name": "陶土窖", "icon": "🔥", "desc": "瓷土与铜矿采购单价各降低2金币。"},
    {"id": "ocean_relay", "name": "远洋通译", "icon": "📡", "desc": "牙行密语每次额外显示1条线索（不增加花费）。"},
]

MODULES_TIER2 = [
    {"id": "foreign_quarter_pass", "name": "蕃坊行会证", "icon": "🪪", "desc": "香料与珍珠采购单价各降低3金币。"},
    {"id": "persian_dome_compass", "name": "波斯穹顶罗盘", "icon": "🧿", "desc": "海盗风险降低30%。"},
    {"id": "fleet_of_treasures", "name": "万宝商船", "icon": "⛵", "desc": "「蕃香脂」与「珠链」每件运费降低3金币。"},
]

MODULES = MODULES_TIER0 + MODULES_TIER1 + MODULES_TIER2


def boon_pool(round_no, max_tier=2):
    return unlocked(BOONS_TIER0, BOONS_TIER1, BOONS_TIER2, round_no, max_tier)


def module_pool(round_no, max_tier=2):
    return unlocked(MODULES_TIER0, MODULES_TIER1, MODULES_TIER2, round_no, max_tier)


def monsoon_pool(round_no, max_tier=2):
    return unlocked(MONSOON_TIER0, MONSOON_TIER1, MONSOON_TIER2, round_no, max_tier)


def charter_event(round_no, max_tier=2):
    """The Set Sail announcement for this round, unless its tier is capped out by difficulty."""
    if CHARTER_TIER_BY_ROUND.get(round_no, 0) > max_tier:
        return None
    return CHARTER_EVENTS.get(round_no)

INVITE_COOLDOWN = 60          # invite cooldown / expiry (seconds)
CHAT_HISTORY_LIMIT = 200      # number of chat messages kept per session

# -------------------- Utility functions --------------------
def rand(a, b):
    return random.randint(a, b)

def choice(arr):
    return random.choice(arr)

def weighted_choice(items):
    total = sum(w for _, w in items)
    r = random.random() * total
    for item, w in items:
        r -= w
        if r <= 0:
            return item
    return items[0][0]

# -------------------- PlayerGame class --------------------
class PlayerGame:
    def __init__(self, difficulty=DEFAULT_DIFFICULTY):
        self.difficulty = normalize_difficulty(difficulty)
        self.max_tier = difficulty_max_tier(self.difficulty)
        self.inventory = {item: 0 for item in RESOURCES + PRODUCTS}
        self.inventory.update({"麻布": 8, "丝绸": 5, "茶叶": 3})
        self.money = 100
        self.score = 0
        self.currentRound = 1
        self.maxRounds = 8
        self.totalRevenue = 0
        self.totalCosts = 0
        self.materialCosts = 0
        self.workerWages = 0
        self.maintenanceCosts = 0
        self.vatPaid = 0
        self.incomeTaxPaid = 0
        self.roundRevenue = 0
        self.roundCosts = 0
        for w in WORKER_TYPES_BACKEND:
            setattr(self, w["attr"], [])
        self.fixedCost = 15
        self.shipLevel = 0
        self.shipUpgradeCost = [15, 25, 40]
        self.shipUpgradePenalty = 0
        self.maintenancePenalty = 0
        self.phase = 0          # 0:welcome, 5:boon, 1:purchase, 'trade':barter, 'worker_mgmt':artisans, 2:trade, 3:upkeep, 4:shipyard
        self.resourceCards = []
        self.customerCards = []
        self.purchasedCards = set()
        self.completedOrders = set()
        self.purchaseCount = 0
        self.orderCount = 0
        self.gameOver = False
        self.bankrupt = False
        self.modifierFlags = {}
        self.monsoon_state = MONSOON_STATES[0].copy()
        self.pirate_immunity = False
        self.escortCost = ESCORT_COST
        self.phase2DemandTags = []
        self.revealedIntel = []
        self.intelCost = 5
        self.boonChoices = []
        self.equippedModules = []
        self.draftChoices = []
        self.lastRoundSummary = None
        self.lastLogs = []
        # Slot info, injected by SharedSession
        self.slot = None

    def log(self, msg):
        self.lastLogs.append(msg)
        if len(self.lastLogs) > 100:
            self.lastLogs.pop(0)

    # ---------- Silk Road Charter: content unlocks ----------
    def unlocked_resources(self):
        return unlocked(RESOURCES_TIER0, RESOURCES_TIER1, RESOURCES_TIER2, self.currentRound, self.max_tier)

    def unlocked_products(self):
        return unlocked(PRODUCTS_TIER0, PRODUCTS_TIER1, PRODUCTS_TIER2, self.currentRound, self.max_tier)

    def unlocked_ports(self):
        return unlocked(PORTS_TIER0, PORTS_TIER1, PORTS_TIER2, self.currentRound, self.max_tier)

    def unlocked_worker_types(self):
        return unlocked(WORKER_IDS_TIER0, WORKER_IDS_TIER1, WORKER_IDS_TIER2, self.currentRound, self.max_tier)

    # ---------- Cost calculations ----------
    def calc_transport_cost(self, total_items, has_silk=False, resources=None):
        base = total_items * 2
        discount = self.shipLevel * 5
        if self.modifierFlags.get("transport_flat_discount"):
            discount += self.modifierFlags["transport_flat_discount"]
        cost = max(5, base - discount)
        if has_silk and self.modifierFlags.get("transport_silk_discount"):
            cost = max(5, int(cost * self.modifierFlags["transport_silk_discount"]))
        if self.has_module("bulk_hauler"): cost = max(0, cost - total_items)
        if self.has_module("overdrive_engine"): cost = max(0, cost - 5)
        if self.has_module("silk_monopoly") and has_silk: cost = 0
        if self.has_module("fleet_of_treasures") and resources:
            treasure_qty = sum(r["required"] for r in resources if r["type"] in ("蕃香脂", "珠链"))
            cost = max(0, cost - 3 * treasure_qty)
        return max(0, cost)

    def calc_vat(self, product, selling_price):
        recipe = RECIPES[product]
        mat_cost = 0
        for m, a in recipe["materials"].items():
            avg = sum(COMMODITIES[m]["basePrice"]) / 2
            mat_cost += avg * a
        worker_cost = WAGES[recipe["worker_type"]]
        taxable = selling_price - mat_cost - worker_cost
        if taxable > 0:
            vat = int(taxable * 0.05)
            if self.has_module("tax_evasion"): vat = int(vat * 0.5)
            if self.modifierFlags.get("vat_discount"): vat = int(vat * (1 - self.modifierFlags["vat_discount"]))
            return vat
        return 0

    def calc_income_tax(self, pre_tax):
        if pre_tax <= 0: return 0
        rate = self.modifierFlags.get("income_tax_override", 0.1)
        tax = int(pre_tax * rate)
        if self.has_module("smugglers_hold"): tax = int(tax * 1.2)
        if self.has_module("tax_evasion"): tax = int(tax * 0.5)
        return tax

    def has_module(self, mid):
        return any(m["id"] == mid for m in self.equippedModules)

    def get_card_final_cost(self, card):
        cost = card["totalCost"]
        if self.modifierFlags.get("purchase_discount"):
            cost = int(cost * (1 - self.modifierFlags["purchase_discount"]))
        if self.modifierFlags.get("hemp_price_reduction"):
            for r in card["resources"]:
                if r["type"] == "麻布":
                    cost -= r["quantity"] * self.modifierFlags["hemp_price_reduction"]
        if self.has_module("kiln_cellar"):
            for r in card["resources"]:
                if r["type"] in ("瓷土", "铜矿"):
                    cost -= r["quantity"] * 2
        if self.has_module("foreign_quarter_pass"):
            for r in card["resources"]:
                if r["type"] in ("香料", "珍珠"):
                    cost -= r["quantity"] * 3
        if self.has_module("smugglers_hold"):
            cost = int(cost * 0.85)
        return max(0, cost)

    def get_hire_cost(self, wtype):
        wage = WAGES[wtype]
        if self.modifierFlags.get("hire_discount"):
            wage = int(wage * 0.5)
        return wage

    def set_monsoon_state(self, state):
        self.monsoon_state = state.copy()

    def env_purchase_price(self, item, price):
        state = self.monsoon_state or {}
        if item == state.get("resource"):
            return max(1, int(round(price * state.get("purchaseMultiplier", 1))))
        return price

    def env_reward(self, port, reward):
        state = self.monsoon_state or {}
        if port in state.get("rewardPorts", []):
            return max(1, int(round(reward * state.get("rewardMultiplier", 1))))
        return reward

    def gen_emperor_mandate_order(self):
        round_no = self.currentRound
        if round_no >= 8:
            resources = [
                {"type": "布衣", "required": 2},
                {"type": "绫罗绸缎", "required": 2},
                {"type": "香囊", "required": 2},
            ]
            reward = 420
            port = "杭州港"
        elif round_no >= 6:
            resources = [
                {"type": "绫罗绸缎", "required": 2},
                {"type": "香囊", "required": 1},
            ]
            reward = 260
            port = "扬州港"
        else:
            resources = [
                {"type": "丝绸", "required": 4},
                {"type": "茶叶", "required": 3},
            ]
            reward = 135
            port = "泉州港"
        total = sum(r["required"] for r in resources)
        return {
            "kind": "EmperorMandate",
            "demandPort": port,
            "resources": resources,
            "reward": self.env_reward(port, reward),
            "totalItems": total,
            "isProductOrder": any(r["type"] in PRODUCTS for r in resources),
        }

    # ---------- Card generation ----------
    def gen_raw_order(self, filter=None):
        num = rand(1, 3)
        resources = []
        unlocked_res = self.unlocked_resources()
        available = unlocked_res[:]
        port = choice(self.unlocked_ports())
        total = 0
        if filter and filter in unlocked_res:
            req = rand(2, 5)
            total += req
            resources.append({"type": filter, "required": req})
        else:
            for _ in range(num):
                if not available: break
                r = choice(available)
                available.remove(r)
                req = rand(2, 5)
                total += req
                resources.append({"type": r, "required": req})
        base = sum(r["required"] * 5 for r in resources)
        reward = self.env_reward(port, base + rand(10, 25))
        return {"demandPort": port, "resources": resources, "reward": reward, "totalItems": total, "isProductOrder": False}

    def gen_product_order(self, filter=None):
        unlocked_prod = self.unlocked_products()
        product = filter if (filter in unlocked_prod) else choice(unlocked_prod)
        req = rand(1, 3)
        port = choice(self.unlocked_ports())
        base_price = rand(*PRODUCT_PRICES[product])
        return {"demandPort": port, "resources": [{"type": product, "required": req}], "reward": self.env_reward(port, base_price * req), "totalItems": req, "isProductOrder": True}

    def gen_mixed_order(self):
        # Each purchased clue resolves into exactly one order, with matching good and port
        intel = next((i for i in self.revealedIntel if not i.get("used")), None)
        if intel:
            intel["used"] = True
            if intel["item"] in RESOURCES:
                order = self.gen_raw_order(intel["item"])
            else:
                order = self.gen_product_order(intel["item"])
            order["demandPort"] = intel["port"]
            order["fromIntel"] = True
            return order
        return self.gen_raw_order() if random.random() < 0.5 else self.gen_product_order()

    def gen_resource_card(self):
        if random.random() < 0.3:
            return self.gen_product_purchase_card()
        num = rand(1, 3)
        resources = []
        unlocked_res = self.unlocked_resources()
        available = [r for r in RESOURCE_PROBS if r in unlocked_res]
        probs = [RESOURCE_PROBS[r] for r in available]
        port = choice(self.unlocked_ports())
        for _ in range(num):
            if not available: break
            chosen = weighted_choice(list(zip(available, probs)))
            idx = available.index(chosen)
            available.pop(idx)
            probs.pop(idx)
            qty = rand(1, 3)
            minP, maxP = COMMODITIES[chosen]["basePrice"]
            base = rand(minP, maxP)
            price = base - 1 if port in COMMODITIES[chosen]["ports"] else base + 1
            price = self.env_purchase_price(chosen, price)
            resources.append({"type": chosen, "quantity": qty, "price": price})
        total = sum(r["quantity"] * r["price"] for r in resources)
        return {"port": port, "resources": resources, "totalCost": total, "isProductCard": False}

    def gen_product_purchase_card(self):
        product = choice(self.unlocked_products())
        qty = rand(1, 2)
        port = choice(self.unlocked_ports())
        recipe = RECIPES[product]
        mat_cost = 0
        details = []
        for m, a in recipe["materials"].items():
            avg = sum(COMMODITIES[m]["basePrice"]) / 2
            mat_cost += avg * a
            details.append(f"{m}×{a}")
        markup = 1.4 + random.random() * 0.4
        unit_price = int(mat_cost * markup)
        unit_price = max(PRODUCT_PRICES[product][0], min(unit_price, PRODUCT_PRICES[product][1]))
        unit_price = self.env_purchase_price(product, unit_price)
        return {
            "port": port,
            "resources": [{
                "type": product, "quantity": qty, "price": unit_price,
                "materialCost": mat_cost, "materialDetails": " + ".join(details)
            }],
            "totalCost": unit_price * qty,
            "isProductCard": True
        }

    # ---------- Core actions ----------
    def apply_boon(self, boon):
        self.modifierFlags = boon["modifiers"]
        if boon["modifiers"].get("instant_gold"):
            self.money += boon["modifiers"]["instant_gold"]
            self.log(f"💰 福缘：获得 {boon['modifiers']['instant_gold']} 金币")

    def purchase_card(self, card):
        cost = self.get_card_final_cost(card)
        if self.money < cost:
            self.log(f"❌ 资金不足！需要{cost}金币")
            return False
        self.money -= cost
        self.roundCosts += cost
        self.totalCosts += cost
        for r in card["resources"]:
            self.inventory[r["type"]] += r["quantity"]
        self.purchasedCards.add(card["id"])
        self.purchaseCount += 1
        self.log(f"🛒 采购完成，花费{cost}金币")
        return True

    def complete_order(self, order):
        for r in order["resources"]:
            if self.inventory.get(r["type"], 0) < r["required"]:
                self.log(f"❌ 库存不足：{r['type']}×{r['required']}")
                return False
        has_silk = any(r["type"] in ["丝绸", "绫罗绸缎", "香囊", "布衣"] for r in order["resources"])
        transport = self.calc_transport_cost(order["totalItems"], has_silk, order["resources"])
        for r in order["resources"]:
            self.inventory[r["type"]] -= r["required"]
        reward = order["reward"]
        total_vat = 0
        if order.get("isProductOrder"):
            product = order["resources"][0]["type"]
            unit_vat = self.calc_vat(product, reward // order["resources"][0]["required"])
            total_vat = unit_vat * order["resources"][0]["required"]
            reward -= total_vat
            self.vatPaid += total_vat
        self.money -= transport
        self.roundCosts += transport
        self.totalCosts += transport
        if self.has_module("silk_monopoly") and has_silk:
            reward = int(reward * 1.2)
        bonus = self.modifierFlags.get("product_order_bonus")
        if bonus and order["resources"][0]["type"] in bonus["products"]:
            reward = int(reward * (1 + bonus["pct"]))
        if self.has_module("bureau_token") and order["resources"][0]["type"] in (PRODUCTS_TIER1 + PRODUCTS_TIER2):
            reward = int(reward * 1.1)
        if self.has_module("salvage_crane") and random.random() < 0.3:
            self.money += transport
            self.log(f"♻️ 打捞起重机退还{transport}金币")
        if self.has_module("tax_evasion") and random.random() < 0.15:
            self.money -= 20
            self.log("🚨 避税账本触发，罚款20金币！")
        self.money += reward
        self.roundRevenue += reward
        self.totalRevenue += reward
        self.score += max(0, reward - transport)
        self.completedOrders.add(order["id"])
        self.orderCount += 1
        self.log(f"📦 订单完成，净利润{reward - transport}金币")
        return True

    # ---------- Shipyard modules ----------
    def start_module_draft(self):
        if self.shipLevel == 0:
            self.log("❌ 旗舰尚无模块槽位，请先升级船坞")
            return False
        tier_pool = module_pool(self.currentRound, self.max_tier)
        available = [m for m in tier_pool if not self.has_module(m["id"])]
        pool = available if len(available) >= 3 else tier_pool
        copy = pool[:]
        random.shuffle(copy)
        self.draftChoices = copy[:3]
        return True

    def equip_module(self, mod, swap_idx=None):
        if swap_idx is not None:
            if swap_idx < 0 or swap_idx >= len(self.equippedModules):
                return False
            old = self.equippedModules[swap_idx]
            if old["id"] == "bulk_hauler": self.shipUpgradePenalty -= 15
            if old["id"] == "overdrive_engine": self.maintenancePenalty -= 10
            if old["id"] == "brokers_network": self.intelCost = 5
            self.equippedModules[swap_idx] = mod
            self.log(f"🔄 将 {old['name']} 替换为 {mod['name']}！")
        else:
            if len(self.equippedModules) < self.shipLevel:
                self.equippedModules.append(mod)
                self.log(f"✅ 安装了 {mod['name']}！")
            else:
                self.log("❌ 没有空置槽位，必须替换现有模块")
                return False
        if mod["id"] == "bulk_hauler": self.shipUpgradePenalty += 15
        if mod["id"] == "overdrive_engine": self.maintenancePenalty += 10
        if mod["id"] == "brokers_network": self.intelCost = 2
        self.draftChoices = []
        return True

    def _reveal_intel(self, count):
        revealed = 0
        for _ in range(count):
            if not self.phase2DemandTags:
                break
            item = choice(self.phase2DemandTags)
            self.phase2DemandTags.remove(item)
            port = choice(self.unlocked_ports())
            self.revealedIntel.append({"item": item, "port": port, "used": False})
            self.log(f"🗣️ 牙行密语：'来自{port}的消息，对{item}的需求很大！'")
            revealed += 1
        return revealed

    def purchase_intel(self):
        if not self.phase2DemandTags:
            self.log("🔮 牙行已无更多密语...")
            return False
        if self.money < self.intelCost:
            self.log(f"❌ 需要{self.intelCost}金币才能购买消息")
            return False
        # Each purchase costs gold only once; with Broker's Network equipped it reveals 2 clues at a time, and Ocean-Going Interpreter reveals 1 more on top of that
        count = 2 if self.has_module("brokers_network") else 1
        if self.has_module("ocean_relay"):
            count += 1
        self.money -= self.intelCost
        self._reveal_intel(count)
        return True

    def hire_worker(self, wtype):
        if wtype not in self.unlocked_worker_types():
            self.log("❌ 该工种尚未开放")
            return False
        wage = self.get_hire_cost(wtype)
        if self.money < wage:
            self.log("❌ 资金不足，无法雇佣")
            return False
        lst = getattr(self, WORKER_ATTR[wtype])
        lst.append({"task": None, "progress": 0, "producedCount": 0, "isSkilled": False})
        self.log(f"👥 雇佣了新工匠（{wtype}）")
        return True

    def fire_worker(self, wtype, idx):
        lst = getattr(self, WORKER_ATTR[wtype])
        if idx < 0 or idx >= len(lst):
            return False
        wage = WAGES[wtype]
        if self.money < wage:
            self.log("❌ 资金不足，无法解雇")
            return False
        self.money -= wage
        lst.pop(idx)
        self.log(f"💔 解雇了{wtype}，支付{wage}金币")
        return True

    def assign_task(self, wtype, task):
        lst = getattr(self, WORKER_ATTR[wtype])
        recipe = RECIPES[task]
        for worker in lst:
            if worker["task"] is None:
                for m, a in recipe["materials"].items():
                    if self.inventory.get(m, 0) < a:
                        self.log(f"❌ 材料不足，无法生产{task}")
                        return False
                for m, a in recipe["materials"].items():
                    self.inventory[m] -= a
                worker["task"] = task
                worker["progress"] = 0
                self.log(f"📋 分配任务：生产{task}")
                return True
        self.log("❌ 所有工匠都在忙")
        return False

    def process_production(self):
        bonus = self.modifierFlags.get("worker_bonus_production", 0)
        for w_def in WORKER_TYPES_BACKEND:
            lst = getattr(self, w_def["attr"])
            for w in lst:
                if w["task"]:
                    base = 2 if w["isSkilled"] else 1
                    amt = base + bonus
                    if self.has_module("artisans_workshop"):
                        amt += 1
                    self.inventory[w["task"]] = self.inventory.get(w["task"], 0) + amt
                    w["producedCount"] += amt
                    if w["producedCount"] >= 2 and not w["isSkilled"]:
                        w["isSkilled"] = True
                    w["task"] = None
                    w["progress"] = 0

    def pay_wages(self):
        total = 0
        for w_def in WORKER_TYPES_BACKEND:
            lst = getattr(self, w_def["attr"])
            wtype = w_def["id"]
            for _ in lst:
                wage = WAGES[wtype]
                if self.has_module("artisans_workshop"):
                    wage = int(wage * 1.2)
                total += wage
        if total == 0:
            return True
        if self.money >= total:
            self.money -= total
            self.workerWages += total
            self.roundCosts += total
            return True
        else:
            self.log(f"⚠️ 工资不足，{total}金币")
            return False

    def pay_maintenance(self):
        cost = self.fixedCost + self.maintenancePenalty
        self.resolve_pirate_hazard()
        if self.money >= cost:
            self.money -= cost
            self.maintenanceCosts += cost
            self.roundCosts += cost
            self.totalCosts += cost
            return True
        else:
            self.money = 0
            self.log("⚠️ 维护费不足，破产")
            return False

    def hire_escort(self):
        if self.pirate_immunity:
            self.log("🛡️ 护航舰队已就位")
            return False
        cost = self.escortCost
        if self.modifierFlags.get("escort_discount"):
            cost = int(cost * (1 - self.modifierFlags["escort_discount"]))
        if self.money < cost:
            self.log(f"❌ 需要{cost}金币才能雇佣护航")
            return False
        self.money -= cost
        self.roundCosts += cost
        self.totalCosts += cost
        self.pirate_immunity = True
        self.log(f"🛡️ 雇佣护航，花费{cost}金币")
        return True

    def resolve_pirate_hazard(self):
        state = self.monsoon_state or {}
        risk = state.get("pirateRisk", 0)
        if risk <= 0:
            return
        if self.pirate_immunity:
            self.log("🛡️ 护航舰队震慑海盗，本程无损")
            return
        if self.modifierFlags.get("pirate_risk_discount"):
            risk *= (1 - self.modifierFlags["pirate_risk_discount"])
        if self.has_module("persian_dome_compass"):
            risk *= 0.7
        if random.random() < risk:
            loss = min(self.money, state.get("pirateLoss", 10))
            self.money -= loss
            self.roundCosts += loss
            self.totalCosts += loss
            self.log(f"🏴‍☠️ 海盗袭扰，损失{loss}金币")

    def end_round(self):
        pre_tax = self.roundRevenue - self.roundCosts - self.maintenanceCosts - self.workerWages
        tax = self.calc_income_tax(pre_tax)
        paid_tax = 0
        if tax > 0 and self.money >= tax:
            paid_tax = tax
            self.money -= tax
            self.incomeTaxPaid += tax
        elif tax > 0 and self.money < tax:
            paid_tax = self.money
            self.incomeTaxPaid += self.money
            self.money = 0
        # Save this round's settlement summary before resetting round counters, for display on the next round's Set Sail transition page
        self.lastRoundSummary = {
            "round": self.currentRound,
            "revenue": self.roundRevenue,
            "costs": self.roundCosts,
            "incomeTax": paid_tax,
            "money": self.money,
            "score": self.score,
        }
        self.modifierFlags = {}
        self.pirate_immunity = False
        self.phase2DemandTags = []
        self.revealedIntel = []
        self.boonChoices = []
        self.roundRevenue = 0
        self.roundCosts = 0
        self.maintenanceCosts = 0
        self.materialCosts = 0
        self.workerWages = 0
        self.currentRound += 1
        if self.currentRound > self.maxRounds:
            self.gameOver = True
            return
        self.phase = 0
        self.purchaseCount = 0
        self.orderCount = 0
        self.resourceCards = []
        self.customerCards = []
        self.purchasedCards.clear()
        self.completedOrders.clear()

    def to_dict(self):
        return {
            "inventory": self.inventory,
            "money": self.money,
            "score": self.score,
            "currentRound": self.currentRound,
            "maxRounds": self.maxRounds,
            "difficulty": self.difficulty,
            "charterEvent": charter_event(self.currentRound, self.max_tier),
            "unlockedResources": self.unlocked_resources(),
            "unlockedProducts": self.unlocked_products(),
            "unlockedPorts": self.unlocked_ports(),
            "unlockedWorkerTypes": self.unlocked_worker_types(),
            "shipLevel": self.shipLevel,
            "equippedModules": self.equippedModules,
            "draftChoices": self.draftChoices,
            "phase": self.phase,
            "resourceCards": self.resourceCards,
            "customerCards": self.customerCards,
            "purchaseCount": self.purchaseCount,
            "orderCount": self.orderCount,
            "purchasedCards": list(self.purchasedCards),
            "completedOrders": list(self.completedOrders),
            "weavers": self.weavers,
            "masterWeavers": self.masterWeavers,
            "sachetMakers": self.sachetMakers,
            "coppersmiths": self.coppersmiths,
            "potters": self.potters,
            "perfumers": self.perfumers,
            "jewelers": self.jewelers,
            "modifierFlags": self.modifierFlags,
            "monsoon_state": self.monsoon_state,
            "pirate_immunity": self.pirate_immunity,
            "escortCost": self.escortCost,
            "intelCost": self.intelCost,
            "revealedIntel": self.revealedIntel,
            "intelRemaining": len(self.phase2DemandTags),
            "boonChoices": self.boonChoices,
            "lastRoundSummary": self.lastRoundSummary,
            "gameOver": self.gameOver,
            "bankrupt": self.bankrupt,
            "fixedCost": self.fixedCost,
            "maintenancePenalty": self.maintenancePenalty,
            "workerWages": self.workerWages,
            "roundRevenue": self.roundRevenue,
            "roundCosts": self.roundCosts,
            "shipUpgradeCost": self.shipUpgradeCost,
            "shipUpgradePenalty": self.shipUpgradePenalty,
            "logs": self.lastLogs[-10:],
            "slot": self.slot          # identity slot
        }

# -------------------- Account storage --------------------
USERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "users.json")

class UserStore:
    """Username + password account store. Each user has its own record, salted and hashed with PBKDF2."""
    def __init__(self, path):
        self.path = path
        self.users = {}
        self.load()

    def load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self.users = json.load(f)
            except Exception:
                self.users = {}

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.users, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    @staticmethod
    def _hash(password, salt):
        return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 100_000).hex()

    def register(self, username, password):
        if not isinstance(username, str) or not (3 <= len(username) <= 20):
            return False, "用户名需为 3-20 个字符"
        if not isinstance(password, str) or len(password) < 6:
            return False, "密码至少 6 位"
        if username in self.users:
            return False, "该用户名已被注册"
        salt = secrets.token_hex(16)
        self.users[username] = {
            "salt": salt,
            "hash": self._hash(password, salt),
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        self.save()
        return True, "注册成功，请登录"

    def verify(self, username, password):
        rec = self.users.get(username)
        if not rec or self._hash(password, rec["salt"]) != rec["hash"]:
            return False, "用户名或密码错误"
        return True, "登录成功"

# -------------------- Shared game session --------------------
class SharedSession:
    """Shared session for two players: both stay in sync on the same round and phase."""
    def __init__(self, user_a, user_b, difficulty=DEFAULT_DIFFICULTY):
        self.players = [user_a, user_b]
        # The agreed difficulty is the session's single source of truth; both fleets and
        # any later restart are built from it, so the two captains can never drift apart.
        self.difficulty = normalize_difficulty(difficulty)
        self.max_tier = difficulty_max_tier(self.difficulty)
        self.games = [PlayerGame(self.difficulty), PlayerGame(self.difficulty)]
        self.games[0].slot = 1
        self.games[1].slot = 2
        self.trade_orders = []
        self.trade_id_counter = 0
        self.trade_ready = [False, False]   # whether each player has clicked ready during the barter phase
        self.ready = set()                  # slots that have clicked "continue" in the current phase
        self.chat_history = []
        self.monsoon_state = MONSOON_STATES[0].copy()
        self.monsoon_cycle_cache = {}
        self.sync_monsoon_state()

    # ---------- Identity ----------
    def slot_of(self, username):
        return self.players.index(username)

    def partner_of(self, username):
        return self.players[1 - self.slot_of(username)]

    # ---------- Synchronized progression ----------
    def _active_phase(self):
        for i in (0, 1):
            if not self.games[i].gameOver:
                return self.games[i].phase
        return self.games[0].phase

    def _set_phase(self, phase):
        # Players in an end state (bankrupt/finished) stay on their own end-game page and no longer follow the session's phase progression
        for g in self.games:
            if not g.gameOver:
                g.phase = phase

    def sync_monsoon_state(self):
        active_game = next((g for g in self.games if not g.gameOver), self.games[0])
        active_round = max(1, min(active_game.currentRound, active_game.maxRounds))
        cycle = (active_round - 1) // 2
        if cycle == 0:
            # Rounds 1-2: keep the original Spring Current opening, identical to existing behavior
            state = MONSOON_TIER0[0]
        else:
            if cycle not in self.monsoon_cycle_cache:
                self.monsoon_cycle_cache[cycle] = random.choice(monsoon_pool(active_round, self.max_tier))
            state = self.monsoon_cycle_cache[cycle]
        self.monsoon_state = state.copy()
        for g in self.games:
            g.set_monsoon_state(self.monsoon_state)

    def gate_complete(self):
        # Bankrupt/finished players count as auto-ready so they never block their partner
        return all((i in self.ready) or self.games[i].gameOver for i in (0, 1))

    def trade_gate_complete(self):
        return all(self.trade_ready[i] or self.games[i].gameOver for i in (0, 1))

    def phase_ready_count(self):
        if self._active_phase() == "trade":
            return sum(1 for i in (0, 1) if self.trade_ready[i] or self.games[i].gameOver)
        return sum(1 for i in (0, 1) if (i in self.ready) or self.games[i].gameOver)

    def advance(self):
        """Once both players are ready, the whole session advances to the next phase together."""
        phase = self._active_phase()
        if phase == 0:
            self.sync_monsoon_state()
            self._set_phase(5)
            # Each player independently draws 4 random Fortunes from the pool; draws are hidden from and different between players
            for g in self.games:
                if not g.gameOver:
                    g.boonChoices = random.sample(boon_pool(g.currentRound, g.max_tier), 4)
        elif phase == 5:
            self._set_phase(1)
            for g in self.games:
                if g.gameOver:
                    continue
                g.resourceCards = []
                for i in range(5):
                    c = g.gen_resource_card()
                    c["id"] = i
                    g.resourceCards.append(c)
                g.phase2DemandTags = random.sample(g.unlocked_resources() + g.unlocked_products(), 5)
                g.revealedIntel = []
                free_intel = g.modifierFlags.get("free_intel", 0)
                if free_intel:
                    g._reveal_intel(free_intel)
        elif phase == 1:
            self._set_phase("trade")
            self.trade_ready = [False, False]
            self.trade_orders = []
        elif phase == "worker_mgmt":
            self._set_phase(2)
            for g in self.games:
                if g.gameOver:
                    continue
                g.customerCards = []
                next_id = 0
                if g.currentRound in (3, 6, 8):
                    o = g.gen_emperor_mandate_order()
                    o["id"] = next_id
                    g.customerCards.append(o)
                    next_id += 1
                order_count = 5 + g.modifierFlags.get("extra_order", 0)
                for i in range(next_id, order_count):
                    o = g.gen_mixed_order()
                    o["id"] = i
                    g.customerCards.append(o)
        elif phase == 2:
            self._set_phase(3)
            for g in self.games:
                if g.gameOver:
                    continue
                g.process_production()
                if not g.pay_wages():
                    g.gameOver = True
                    g.bankrupt = True
                    g.phase = "bankruptcy"
        elif phase == 3:
            for g in self.games:
                if not g.gameOver:
                    g.phase = 4
        elif phase == 4:
            for g in self.games:
                if not g.gameOver:
                    g.end_round()
                    g.phase = "endgame" if g.gameOver else 0
                elif g.bankrupt:
                    g.phase = "bankruptcy"
        self.ready.clear()

    def complete_trade_gate(self):
        self._set_phase("worker_mgmt")
        self.trade_ready = [False, False]
        self.trade_orders = []
        self.ready.clear()

    def restart(self):
        # A restart keeps the difficulty the two captains originally agreed on.
        self.games = [PlayerGame(self.difficulty), PlayerGame(self.difficulty)]
        self.games[0].slot = 1
        self.games[1].slot = 2
        self.trade_orders = []
        self.trade_ready = [False, False]
        self.ready.clear()
        self.monsoon_cycle_cache = {}
        self.sync_monsoon_state()

    # ---------- Waiting hints ----------
    def waiting_message(self, slot):
        game = self.games[slot]
        if game.phase == "trade":
            if not self.trade_ready[slot]:
                return "请点击“准备就绪”以进入工匠管理"
            if not self.trade_gate_complete():
                return "等待对方也点击准备就绪..."
            return None
        if slot in self.ready and not self.gate_complete():
            return "已准备，等待对方点击继续..."
        return None

    # ---------- Barter trades ----------
    def create_trade_order(self, seller_slot, sell_items, buy_items):
        self.trade_id_counter += 1
        order = {
            "id": f"trade_{self.trade_id_counter}",
            "sellerSlot": seller_slot,
            "sell": sell_items,
            "buy": buy_items
        }
        self.trade_orders.append(order)
        return order

    def accept_trade(self, order_id, buyer_slot):
        order = next((o for o in self.trade_orders if o["id"] == order_id), None)
        if not order or order["sellerSlot"] == buyer_slot:
            return False
        seller_game = self.games[order["sellerSlot"]]
        buyer_game = self.games[buyer_slot]
        if not seller_game or not buyer_game:
            return False
        # Check the seller's resources
        for item in order["sell"]:
            if item["type"] == "金币":
                if seller_game.money < item["quantity"]:
                    return False
            else:
                if seller_game.inventory.get(item["type"], 0) < item["quantity"]:
                    return False
        # Check the buyer's resources
        for item in order["buy"]:
            if item["type"] == "金币":
                if buyer_game.money < item["quantity"]:
                    return False
            else:
                if buyer_game.inventory.get(item["type"], 0) < item["quantity"]:
                    return False
        # Execute the swap
        for item in order["sell"]:
            if item["type"] == "金币":
                seller_game.money -= item["quantity"]
                buyer_game.money += item["quantity"]
            else:
                seller_game.inventory[item["type"]] -= item["quantity"]
                buyer_game.inventory[item["type"]] += item["quantity"]
        for item in order["buy"]:
            if item["type"] == "金币":
                buyer_game.money -= item["quantity"]
                seller_game.money += item["quantity"]
            else:
                buyer_game.inventory[item["type"]] -= item["quantity"]
                seller_game.inventory[item["type"]] += item["quantity"]
        self.trade_orders.remove(order)
        seller_game.log("🤝 互市成功！")
        buyer_game.log("🤝 互市成功！")
        return True

    def reject_trade(self, order_id):
        order = next((o for o in self.trade_orders if o["id"] == order_id), None)
        if order:
            self.trade_orders.remove(order)
        return order

    # ---------- Chat ----------
    def add_chat(self, sender, message):
        self.chat_history.append({"from": sender, "message": message})
        if len(self.chat_history) > CHAT_HISTORY_LIMIT:
            self.chat_history.pop(0)

    # ---------- State broadcast ----------
    async def broadcast_state(self):
        for slot in (0, 1):
            uname = self.players[slot]
            ws = ONLINE.get(uname)
            if ws is None:
                continue
            game = self.games[slot]
            other = self.games[1 - slot]
            state = {
                "tradeOrders": self.trade_orders,
                "tradeReady": self.trade_ready,
                "phaseReadyCount": self.phase_ready_count(),
                "yourGame": game.to_dict(),
                "otherGame": other.to_dict(),
                "waitingForOther": self.waiting_message(slot),
                "youReady": slot in self.ready,
                "yourSlot": slot + 1,
                "partnerName": self.players[1 - slot],
                "partnerOnline": self.players[1 - slot] in ONLINE
            }
            await send_json(ws, {"type": "state", "data": state})

# -------------------- Global state --------------------
USERS = UserStore(USERS_FILE)
ONLINE = {}            # username -> websocket
SESSIONS = {}          # username -> SharedSession (both players point to the same session)
PENDING_INVITES = {}   # sender -> {"to": target, "task": asyncio.Task}
LAST_INVITE_AT = {}    # sender -> time.monotonic() timestamp

# -------------------- Send helpers --------------------
async def send_json(ws, obj):
    try:
        await ws.send(json.dumps(obj))
    except Exception:
        pass

async def send_to_user(username, obj):
    ws = ONLINE.get(username)
    if ws is not None:
        await send_json(ws, obj)

async def broadcast_online_users():
    names = list(ONLINE.keys())
    for uname, ws in list(ONLINE.items()):
        await send_json(ws, {"type": "online_users_update", "users": [n for n in names if n != uname]})

# -------------------- Invite system --------------------
async def invite_timeout_task(sender, target):
    try:
        await asyncio.sleep(INVITE_COOLDOWN)
    except asyncio.CancelledError:
        return
    inv = PENDING_INVITES.pop(sender, None)
    if inv and inv["to"] == target:
        await send_to_user(sender, {"type": "invite_timeout", "to": target})
        await send_to_user(target, {"type": "invite_cancelled", "from": sender})

async def handle_send_invite(sender, target, difficulty=DEFAULT_DIFFICULTY):
    difficulty = normalize_difficulty(difficulty)
    if not target or target == sender:
        await send_to_user(sender, {"type": "invite_result", "success": False, "message": "无效的邀请对象"})
        return
    if sender in SESSIONS:
        await send_to_user(sender, {"type": "invite_result", "success": False, "message": "你已在游戏会话中，无法发出邀请"})
        return
    if sender in PENDING_INVITES:
        await send_to_user(sender, {"type": "invite_result", "success": False,
                                    "message": f"你已向 {PENDING_INVITES[sender]['to']} 发出邀请，请等待对方回应或超时"})
        return
    elapsed = time.monotonic() - LAST_INVITE_AT.get(sender, -INVITE_COOLDOWN)
    if elapsed < INVITE_COOLDOWN:
        remain = math.ceil(INVITE_COOLDOWN - elapsed)
        await send_to_user(sender, {"type": "invite_result", "success": False,
                                    "message": f"每分钟只能发出一次邀请，请 {remain} 秒后再试"})
        return
    if target not in ONLINE:
        await send_to_user(sender, {"type": "invite_result", "success": False, "message": f"{target} 不在线，无法邀请"})
        return
    if target in SESSIONS:
        await send_to_user(sender, {"type": "invite_result", "success": False, "message": f"{target} 正在游戏中，无法邀请"})
        return
    LAST_INVITE_AT[sender] = time.monotonic()
    task = asyncio.create_task(invite_timeout_task(sender, target))
    # The proposed difficulty rides with the pending invite so the session is always
    # built from what the invitee actually saw and agreed to, never from a value the
    # responder echoes back.
    PENDING_INVITES[sender] = {"to": target, "task": task, "difficulty": difficulty}
    await send_to_user(target, {"type": "invite_received", "from": sender, "difficulty": difficulty})
    await send_to_user(sender, {"type": "invite_result", "success": True,
                                "message": f"邀请已发送给 {target}，等待回应（{INVITE_COOLDOWN} 秒内有效）"})

async def handle_respond_invite(responder, sender, accept):
    inv = PENDING_INVITES.get(sender)
    if not inv or inv["to"] != responder:
        await send_to_user(responder, {"type": "system_message", "message": "该邀请已失效"})
        return
    PENDING_INVITES.pop(sender, None)
    inv["task"].cancel()
    if not accept:
        await send_to_user(sender, {"type": "invite_rejected", "from": responder})
        return
    if sender not in ONLINE:
        await send_to_user(responder, {"type": "system_message", "message": "对方已离线，邀请失效"})
        return
    if sender in SESSIONS or responder in SESSIONS:
        await send_to_user(responder, {"type": "system_message", "message": "无法建立会话：其中一方已在游戏中"})
        return
    difficulty = normalize_difficulty(inv.get("difficulty"))
    sess = SharedSession(sender, responder, difficulty)
    SESSIONS[sender] = sess
    SESSIONS[responder] = sess
    await send_to_user(sender, {"type": "invite_accepted", "partner": responder, "difficulty": difficulty})
    await send_to_user(responder, {"type": "invite_accepted", "partner": sender, "difficulty": difficulty})
    await broadcast_online_users()
    await sess.broadcast_state()

# -------------------- Chat system --------------------
async def handle_send_chat(sender, message):
    sess = SESSIONS.get(sender)
    if sess is None:
        await send_to_user(sender, {"type": "system_message", "message": "你还没有游戏伙伴，无法发送消息"})
        return
    partner = sess.partner_of(sender)
    if partner not in ONLINE:
        await send_to_user(sender, {"type": "system_message", "message": "对方已离线，无法发送消息"})
        return
    message = str(message).strip()[:500]
    if not message:
        return
    sess.add_chat(sender, message)
    await send_to_user(partner, {"type": "chat_message", "from": sender, "message": message})

# -------------------- In-game actions --------------------
async def handle_game_action(username, data):
    action = data.get("action")
    sess = SESSIONS.get(username)
    if sess is None:
        return
    slot = sess.slot_of(username)
    game = sess.games[slot]
    phase = game.phase
    changed = False

    # Players in an end state (bankrupt/finished) may only perform read-only spectator actions and restart
    if game.gameOver and action not in ("join_game", "restart"):
        return

    if action == "join_game":
        changed = True
    elif action == "startBoon":
        if phase == 0 and slot not in sess.ready:
            sess.ready.add(slot)
            changed = True
            if sess.gate_complete():
                sess.advance()
    elif action == "selectBoon":
        if phase == 5 and slot not in sess.ready:
            # Can only select from the 4 Fortunes dealt to this player this round
            pool = game.boonChoices or BOONS
            boon = next((b for b in pool if b["id"] == data.get("boonId")), None)
            if boon:
                game.apply_boon(boon)
                sess.ready.add(slot)
                changed = True
                if sess.gate_complete():
                    sess.advance()
    elif action == "ready_for_next_phase":
        if phase in (1, "worker_mgmt", 2, 4) and slot not in sess.ready:
            sess.ready.add(slot)
            changed = True
            if sess.gate_complete():
                sess.advance()
    elif action == "purchase":
        if phase == 1:
            card = next((c for c in game.resourceCards if c["id"] == data.get("cardId")), None)
            if card and card["id"] not in game.purchasedCards:
                game.purchase_card(card)
            changed = True
    elif action == "purchaseIntel":
        if phase == 1:
            game.purchase_intel()
            changed = True
    elif action == "setTradeReady":
        if phase == "trade":
            sess.trade_ready[slot] = True
            changed = True
            if sess.trade_gate_complete():
                sess.complete_trade_gate()
    elif action == "createTradeOrder":
        if phase == "trade":
            sell = data.get("sell", [])
            buy = data.get("buy", [])
            sess.create_trade_order(slot, sell, buy)
            changed = True
    elif action == "acceptTrade":
        if phase == "trade":
            sess.accept_trade(data.get("orderId"), slot)
            changed = True
    elif action == "rejectTrade":
        if phase == "trade":
            order = sess.reject_trade(data.get("orderId"))
            if order:
                seller = sess.players[order["sellerSlot"]]
                if seller != username:
                    sell_txt = "、".join(f"{i['type']}×{i['quantity']}" for i in order["sell"])
                    buy_txt = "、".join(f"{i['type']}×{i['quantity']}" for i in order["buy"])
                    await send_to_user(seller, {
                        "type": "system_message",
                        "message": f"❌ 对方拒绝了你的互市提案（出 {sell_txt} ⇄ 换 {buy_txt}）"
                    })
            changed = True
    elif action == "hireWorker":
        if phase == "worker_mgmt" and data.get("workerType") in WAGES:
            game.hire_worker(data["workerType"])
            changed = True
    elif action == "fireWorker":
        if phase == "worker_mgmt" and data.get("workerType") in WAGES:
            game.fire_worker(data["workerType"], data.get("index", -1))
            changed = True
    elif action == "assignTask":
        if phase == "worker_mgmt" and data.get("workerType") in WAGES and data.get("task") in RECIPES:
            game.assign_task(data["workerType"], data["task"])
            changed = True
    elif action == "completeOrder":
        if phase == 2:
            order = next((o for o in game.customerCards if o["id"] == data.get("orderId")), None)
            if order and order["id"] not in game.completedOrders:
                game.complete_order(order)
            changed = True
    elif action == "doMaintenance":
        if phase == 3 and slot not in sess.ready:
            if not game.pay_maintenance():
                game.gameOver = True
                game.bankrupt = True
                game.phase = "bankruptcy"
            sess.ready.add(slot)
            changed = True
            if sess.gate_complete():
                sess.advance()
    elif action == "hireEscort":
        if phase == 3 and slot not in sess.ready:
            game.hire_escort()
            changed = True
    elif action == "upgradeShip":
        if phase == 4 and game.shipLevel < 3:
            cost = game.shipUpgradeCost[game.shipLevel] + game.shipUpgradePenalty
            if game.money >= cost:
                game.money -= cost
                game.shipLevel += 1
            changed = True
    elif action == "draftModules":
        if phase == 4:
            game.start_module_draft()
            changed = True
    elif action == "equipModule":
        if phase == 4:
            idx = data.get("choiceIndex")
            if isinstance(idx, int) and 0 <= idx < len(game.draftChoices):
                mod = game.draftChoices[idx]
                swap_idx = data.get("swapIndex")
                if not (isinstance(swap_idx, int) and 0 <= swap_idx < len(game.equippedModules)):
                    swap_idx = None
                game.equip_module(mod, swap_idx)
            changed = True
    elif action == "cancelModuleDraft":
        if phase == 4:
            game.draftChoices = []
            changed = True
    elif action == "restart":
        # Only allow resetting the whole session once the partner has also finished (settled or bankrupt), keeping both players in sync
        if sess.games[1 - slot].gameOver:
            sess.restart()
            partner = sess.partner_of(username)
            await send_to_user(partner, {"type": "system_message", "message": "对方重新开始了游戏，双方进度已重置"})
            changed = True
        else:
            await send_to_user(username, {"type": "system_message", "message": "需等待对方完成本局后才能重新起航"})

    if changed:
        await sess.broadcast_state()

# -------------------- WebSocket handling --------------------
async def handler(websocket):
    username = None
    try:
        async for raw in websocket:
            try:
                data = json.loads(raw)
            except Exception:
                continue
            action = data.get("action")

            # ---------- Not logged in: only accept register / login ----------
            if username is None:
                if action == "register":
                    ok, msg = USERS.register(str(data.get("username", "")).strip(), str(data.get("password", "")))
                    await send_json(websocket, {"type": "register_result", "success": ok, "message": msg})
                elif action == "login":
                    u = str(data.get("username", "")).strip()
                    p = str(data.get("password", ""))
                    ok, msg = USERS.verify(u, p)
                    if ok and u in ONLINE:
                        ok, msg = False, "该账号已在其他设备登录"
                    await send_json(websocket, {"type": "login_result", "success": ok, "username": u, "message": msg})
                    if ok:
                        username = u
                        ONLINE[u] = websocket
                        await broadcast_online_users()
                        sess = SESSIONS.get(u)
                        if sess is not None:
                            partner = sess.partner_of(u)
                            await send_json(websocket, {"type": "session_resumed", "partner": partner,
                                                        "partnerOnline": partner in ONLINE})
                            await send_to_user(partner, {"type": "partner_status", "username": u, "online": True})
                            await sess.broadcast_state()
                else:
                    await send_json(websocket, {"type": "error", "message": "请先登录"})
                continue

            # ---------- Logged in: lobby / invites / chat / game ----------
            if action == "get_online_users":
                await send_json(websocket, {"type": "online_users", "users": [n for n in ONLINE if n != username]})
            elif action == "send_invite":
                await handle_send_invite(username, str(data.get("to", "")), data.get("difficulty"))
            elif action == "respond_invite":
                await handle_respond_invite(username, str(data.get("from", "")), bool(data.get("accept")))
            elif action == "send_chat":
                await handle_send_chat(username, data.get("message", ""))
            elif action == "get_chat_history":
                sess = SESSIONS.get(username)
                await send_json(websocket, {"type": "chat_history", "history": sess.chat_history if sess else []})
            else:
                await handle_game_action(username, data)
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        if username is not None and ONLINE.get(username) is websocket:
            del ONLINE[username]
            # Cancel this user's pending outgoing invites
            inv = PENDING_INVITES.pop(username, None)
            if inv:
                inv["task"].cancel()
                await send_to_user(inv["to"], {"type": "invite_cancelled", "from": username})
            await broadcast_online_users()
            # Notify the session partner; recycle the session if both players are offline
            sess = SESSIONS.get(username)
            if sess is not None:
                partner = sess.partner_of(username)
                if partner in ONLINE:
                    await send_to_user(partner, {"type": "partner_status", "username": username, "online": False})
                    await sess.broadcast_state()
                else:
                    SESSIONS.pop(username, None)
                    SESSIONS.pop(partner, None)

# -------------------- HTTP static file serving (shares the WebSocket port) --------------------
# Serving static files on the same port as the WebSocket server lets a single ngrok tunnel
# (e.g. ngrok http 8080) expose both the web page and the WebSocket, with automatic
# https/wss adaptation, avoiding browser mixed-content restrictions.
WEB_ROOT = os.path.dirname(os.path.abspath(__file__))

async def process_request(connection, request):
    # Let WebSocket upgrade requests through, to be handled by handler
    if request.headers.get("Upgrade", "").lower() == "websocket":
        return None

    path = request.path.split("?", 1)[0]
    if path in ("/", ""):
        path = "/PortMasters_online.html"
    if path == "/favicon.ico":
        return connection.respond(http.HTTPStatus.NO_CONTENT, "")

    file_path = os.path.normpath(os.path.join(WEB_ROOT, path.lstrip("/")))
    if not (file_path == WEB_ROOT or file_path.startswith(WEB_ROOT + os.sep)) or not os.path.isfile(file_path):
        return connection.respond(http.HTTPStatus.NOT_FOUND, "Not Found")

    content_type, _ = mimetypes.guess_type(file_path)
    with open(file_path, "rb") as f:
        body = f.read()
    return Response(
        http.HTTPStatus.OK, "OK",
        Headers({"Content-Type": content_type or "application/octet-stream",
                 "Content-Length": str(len(body))}),
        body
    )

async def main():
    async with websockets.serve(handler, "0.0.0.0", 8080, process_request=process_request):
        print(f"✅ Server started: web http://0.0.0.0:8080, WebSocket ws://0.0.0.0:8080")
        await asyncio.Future()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Server shut down")
