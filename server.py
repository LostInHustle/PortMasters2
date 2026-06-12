#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PortMasters 多人联机服务器 v4（账号版）
- 账号系统：注册 / 登录（用户名+密码，按用户分别持久化存储于 users.json）
- 在线大厅：登录即在线，实时广播在线玩家列表；断线即离线
- 邀请系统：每位玩家每分钟只能发出一次邀请，60 秒未响应自动超时；
  对方可接受（双方进入共享会话）或拒绝（发起方收到拒绝提示）
- 共享会话：8 回合 × 每回合 4 个阶段，双方始终处于同一回合同一阶段，
  通过“继续 (n / 2)”机制同步推进
- 互市阶段需双方都点击“准备就绪”才同步进入工匠管理
- 聊天系统：会话双方在线时可互发消息，离线时禁止发送
- 网页与 WebSocket 共用同一端口 8080（便于单条 ngrok 隧道穿透并支持 wss）
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

# -------------------- 常量 --------------------
RESOURCES = ["麻布", "丝绸", "茶叶"]
PRODUCTS = ["麻衣", "布衣", "绫罗绸缎", "香囊"]
PORTS = ["泉州港", "广州港", "宁波港", "扬州港", "杭州港"]

RECIPES = {
    "麻衣": {"materials": {"麻布": 2}, "value": 15, "worker_type": "weaver"},
    "布衣": {"materials": {"麻布": 2, "丝绸": 1}, "value": 35, "worker_type": "weaver"},
    "绫罗绸缎": {"materials": {"丝绸": 3}, "value": 60, "worker_type": "master"},
    "香囊": {"materials": {"丝绸": 1, "茶叶": 2}, "value": 80, "worker_type": "sachet_maker"}
}

COMMODITIES = {
    "麻布": {"ports": ["泉州港", "宁波港"], "basePrice": (3, 6)},
    "丝绸": {"ports": ["杭州港", "扬州港"], "basePrice": (6, 10)},
    "茶叶": {"ports": ["广州港", "泉州港"], "basePrice": (10, 14)}
}

PRODUCT_PRICES = {
    "麻衣": (30, 42), "布衣": (50, 65),
    "绫罗绸缎": (70, 90), "香囊": (95, 120)
}

RESOURCE_PROBS = {"麻布": 0.4, "丝绸": 0.35, "茶叶": 0.25}
WAGES = {"weaver": 8, "master": 12, "sachet_maker": 20}

BOONS = [
    {"id": "silk_wind", "name": "丝路顺风", "icon": "🌬️", "desc": "本回合丝绸及成品运费减半。", "modifiers": {"transport_silk_discount": 0.5}},
    {"id": "favorable_tides", "name": "顺风顺水", "icon": "🌊", "desc": "本回合基础运费减4金币。", "modifiers": {"transport_flat_discount": 4}},
    {"id": "merchant_charm", "name": "商贾魅力", "icon": "✨", "desc": "本回合采购85折优惠。", "modifiers": {"purchase_discount": 0.15}},
    {"id": "artisan_inspiration", "name": "匠人灵感", "icon": "🔨", "desc": "本回合所有工人多生产1件。", "modifiers": {"worker_bonus_production": 1}},
    {"id": "emergency_loan", "name": "紧急钱庄", "icon": "💰", "desc": "立即获得40金币。", "modifiers": {"instant_gold": 40}},
    {"id": "tax_shelter", "name": "免税令", "icon": "📜", "desc": "本回合所得税率降至5%。", "modifiers": {"income_tax_override": 0.05}},
    {"id": "hemp_monopoly", "name": "麻布专营", "icon": "🧶", "desc": "麻布采购单价降低2金币。", "modifiers": {"hemp_price_reduction": 2}},
    {"id": "master_apprentice", "name": "学徒传承", "icon": "🎓", "desc": "本回合雇佣工资减半。", "modifiers": {"hire_discount": 0.5}}
]

INVITE_COOLDOWN = 60          # 邀请冷却 / 超时时间（秒）
CHAT_HISTORY_LIMIT = 200      # 每个会话保留的聊天记录条数

# -------------------- 工具函数 --------------------
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

# -------------------- PlayerGame 类 --------------------
class PlayerGame:
    def __init__(self):
        self.inventory = {"麻布": 8, "丝绸": 5, "茶叶": 3, "麻衣": 0, "布衣": 0, "绫罗绸缎": 0, "香囊": 0}
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
        self.weavers = []
        self.masterWeavers = []
        self.sachetMakers = []
        self.fixedCost = 15
        self.shipLevel = 0
        self.shipUpgradeCost = [15, 25, 40]
        self.shipUpgradePenalty = 0
        self.maintenancePenalty = 0
        self.phase = 0          # 0:welcome, 5:boon, 1:purchase, 'trade':互市, 'worker_mgmt':工匠, 2:贸易, 3:维护, 4:船坞
        self.resourceCards = []
        self.customerCards = []
        self.purchasedCards = set()
        self.completedOrders = set()
        self.purchaseCount = 0
        self.orderCount = 0
        self.gameOver = False
        self.modifierFlags = {}
        self.phase2DemandTags = []
        self.revealedIntel = []
        self.intelCost = 5
        self.intelOrderUsed = False
        self.equippedModules = []
        self.lastLogs = []
        # 注入 slot 信息（由 SharedSession 设置）
        self.slot = None

    def log(self, msg):
        self.lastLogs.append(msg)
        if len(self.lastLogs) > 100:
            self.lastLogs.pop(0)

    # ---------- 费用计算 ----------
    def calc_transport_cost(self, total_items, has_silk=False):
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
        if self.has_module("smugglers_hold"):
            cost = int(cost * 0.85)
        return max(0, cost)

    def get_hire_cost(self, wtype):
        wage = WAGES[wtype]
        if self.modifierFlags.get("hire_discount"):
            wage = int(wage * 0.5)
        return wage

    # ---------- 卡牌生成 ----------
    def gen_raw_order(self, filter=None):
        num = rand(1, 3)
        resources = []
        available = RESOURCES[:]
        port = choice(PORTS)
        total = 0
        if filter and filter in RESOURCES:
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
        reward = base + rand(10, 25)
        return {"demandPort": port, "resources": resources, "reward": reward, "totalItems": total, "isProductOrder": False}

    def gen_product_order(self, filter=None):
        product = filter if (filter in PRODUCTS) else choice(PRODUCTS)
        req = rand(1, 3)
        port = choice(PORTS)
        base_price = rand(*PRODUCT_PRICES[product])
        return {"demandPort": port, "resources": [{"type": product, "required": req}], "reward": base_price * req, "totalItems": req, "isProductOrder": True}

    def gen_mixed_order(self):
        if self.revealedIntel and not self.intelOrderUsed:
            intel = choice(self.revealedIntel)
            self.intelOrderUsed = True
            if intel["item"] in RESOURCES:
                return self.gen_raw_order(intel["item"])
            if intel["item"] in PRODUCTS:
                return self.gen_product_order(intel["item"])
        return self.gen_raw_order() if random.random() < 0.5 else self.gen_product_order()

    def gen_resource_card(self):
        if random.random() < 0.3:
            return self.gen_product_purchase_card()
        num = rand(1, 3)
        resources = []
        available = list(RESOURCE_PROBS.keys())
        probs = list(RESOURCE_PROBS.values())
        port = choice(PORTS)
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
            resources.append({"type": chosen, "quantity": qty, "price": price})
        total = sum(r["quantity"] * r["price"] for r in resources)
        return {"port": port, "resources": resources, "totalCost": total, "isProductCard": False}

    def gen_product_purchase_card(self):
        product = choice(PRODUCTS)
        qty = rand(1, 2)
        port = choice(PORTS)
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
        return {
            "port": port,
            "resources": [{
                "type": product, "quantity": qty, "price": unit_price,
                "materialCost": mat_cost, "materialDetails": " + ".join(details)
            }],
            "totalCost": unit_price * qty,
            "isProductCard": True
        }

    # ---------- 核心动作 ----------
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
        transport = self.calc_transport_cost(order["totalItems"], has_silk)
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

    def hire_worker(self, wtype):
        wage = self.get_hire_cost(wtype)
        if self.money < wage:
            self.log("❌ 资金不足，无法雇佣")
            return False
        lst = {"weaver": self.weavers, "master": self.masterWeavers, "sachet_maker": self.sachetMakers}[wtype]
        lst.append({"task": None, "progress": 0, "producedCount": 0, "isSkilled": False})
        self.log(f"👥 雇佣了新工匠（{wtype}）")
        return True

    def fire_worker(self, wtype, idx):
        lst = {"weaver": self.weavers, "master": self.masterWeavers, "sachet_maker": self.sachetMakers}[wtype]
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
        lst = {"weaver": self.weavers, "master": self.masterWeavers, "sachet_maker": self.sachetMakers}[wtype]
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
        all_lists = [
            (self.weavers, "weaver"),
            (self.masterWeavers, "master"),
            (self.sachetMakers, "sachet_maker")
        ]
        for lst, wtype in all_lists:
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
        for lst, wtype in [(self.weavers, "weaver"), (self.masterWeavers, "master"), (self.sachetMakers, "sachet_maker")]:
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

    def end_round(self):
        pre_tax = self.roundRevenue - self.roundCosts - self.maintenanceCosts - self.workerWages
        tax = self.calc_income_tax(pre_tax)
        if tax > 0 and self.money >= tax:
            self.money -= tax
            self.incomeTaxPaid += tax
        elif tax > 0 and self.money < tax:
            self.incomeTaxPaid += self.money
            self.money = 0
        self.modifierFlags = {}
        self.phase2DemandTags = []
        self.revealedIntel = []
        self.intelOrderUsed = False
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
            "shipLevel": self.shipLevel,
            "equippedModules": self.equippedModules,
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
            "modifierFlags": self.modifierFlags,
            "intelCost": self.intelCost,
            "revealedIntel": self.revealedIntel,
            "gameOver": self.gameOver,
            "fixedCost": self.fixedCost,
            "maintenancePenalty": self.maintenancePenalty,
            "workerWages": self.workerWages,
            "roundRevenue": self.roundRevenue,
            "roundCosts": self.roundCosts,
            "shipUpgradeCost": self.shipUpgradeCost,
            "shipUpgradePenalty": self.shipUpgradePenalty,
            "logs": self.lastLogs[-10:],
            "slot": self.slot          # 身份槽位
        }

# -------------------- 账号存储 --------------------
USERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "users.json")

class UserStore:
    """用户名 + 密码账号库。每个用户一条独立记录，PBKDF2 加盐存储。"""
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

# -------------------- 共享游戏会话 --------------------
class SharedSession:
    """两名玩家的共享会话：双方始终同步处于同一回合同一阶段。"""
    def __init__(self, user_a, user_b):
        self.players = [user_a, user_b]
        self.games = [PlayerGame(), PlayerGame()]
        self.games[0].slot = 1
        self.games[1].slot = 2
        self.trade_orders = []
        self.trade_id_counter = 0
        self.trade_ready = [False, False]   # 互市阶段双方是否点了准备
        self.ready = set()                  # 当前阶段已点击“继续”的槽位
        self.chat_history = []

    # ---------- 身份 ----------
    def slot_of(self, username):
        return self.players.index(username)

    def partner_of(self, username):
        return self.players[1 - self.slot_of(username)]

    # ---------- 同步推进 ----------
    def _active_phase(self):
        for i in (0, 1):
            if not self.games[i].gameOver:
                return self.games[i].phase
        return self.games[0].phase

    def _set_phase(self, phase):
        for g in self.games:
            g.phase = phase

    def gate_complete(self):
        # 已破产/已结束的玩家视为自动准备，避免阻塞对方
        return all((i in self.ready) or self.games[i].gameOver for i in (0, 1))

    def trade_gate_complete(self):
        return all(self.trade_ready[i] or self.games[i].gameOver for i in (0, 1))

    def phase_ready_count(self):
        if self._active_phase() == "trade":
            return sum(1 for i in (0, 1) if self.trade_ready[i] or self.games[i].gameOver)
        return sum(1 for i in (0, 1) if (i in self.ready) or self.games[i].gameOver)

    def advance(self):
        """双方都准备好后，整个会话同步进入下一阶段。"""
        phase = self._active_phase()
        if phase == 0:
            self._set_phase(5)
        elif phase == 5:
            self._set_phase(1)
            for g in self.games:
                g.resourceCards = []
                for i in range(5):
                    c = g.gen_resource_card()
                    c["id"] = i
                    g.resourceCards.append(c)
        elif phase == 1:
            self._set_phase("trade")
            self.trade_ready = [False, False]
            self.trade_orders = []
        elif phase == "worker_mgmt":
            self._set_phase(2)
            for g in self.games:
                g.customerCards = []
                for i in range(5):
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
        elif phase == 3:
            self._set_phase(4)
        elif phase == 4:
            for g in self.games:
                if not g.gameOver:
                    g.end_round()
                g.phase = "endgame" if g.gameOver else 0
        self.ready.clear()

    def complete_trade_gate(self):
        self._set_phase("worker_mgmt")
        self.trade_ready = [False, False]
        self.trade_orders = []
        self.ready.clear()

    def restart(self):
        self.games = [PlayerGame(), PlayerGame()]
        self.games[0].slot = 1
        self.games[1].slot = 2
        self.trade_orders = []
        self.trade_ready = [False, False]
        self.ready.clear()

    # ---------- 等待提示 ----------
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

    # ---------- 互市订单 ----------
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
        # 检查卖方资源
        for item in order["sell"]:
            if item["type"] == "金币":
                if seller_game.money < item["quantity"]:
                    return False
            else:
                if seller_game.inventory.get(item["type"], 0) < item["quantity"]:
                    return False
        # 检查买方资源
        for item in order["buy"]:
            if item["type"] == "金币":
                if buyer_game.money < item["quantity"]:
                    return False
            else:
                if buyer_game.inventory.get(item["type"], 0) < item["quantity"]:
                    return False
        # 执行交换
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
        self.trade_orders = [o for o in self.trade_orders if o["id"] != order_id]

    # ---------- 聊天 ----------
    def add_chat(self, sender, message):
        self.chat_history.append({"from": sender, "message": message})
        if len(self.chat_history) > CHAT_HISTORY_LIMIT:
            self.chat_history.pop(0)

    # ---------- 状态广播 ----------
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
                "yourSlot": slot + 1,
                "partnerName": self.players[1 - slot],
                "partnerOnline": self.players[1 - slot] in ONLINE
            }
            await send_json(ws, {"type": "state", "data": state})

# -------------------- 全局状态 --------------------
USERS = UserStore(USERS_FILE)
ONLINE = {}            # username -> websocket
SESSIONS = {}          # username -> SharedSession（两名玩家指向同一会话）
PENDING_INVITES = {}   # sender -> {"to": target, "task": asyncio.Task}
LAST_INVITE_AT = {}    # sender -> time.monotonic() 时间戳

# -------------------- 发送工具 --------------------
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

# -------------------- 邀请系统 --------------------
async def invite_timeout_task(sender, target):
    try:
        await asyncio.sleep(INVITE_COOLDOWN)
    except asyncio.CancelledError:
        return
    inv = PENDING_INVITES.pop(sender, None)
    if inv and inv["to"] == target:
        await send_to_user(sender, {"type": "invite_timeout", "to": target})
        await send_to_user(target, {"type": "invite_cancelled", "from": sender})

async def handle_send_invite(sender, target):
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
    PENDING_INVITES[sender] = {"to": target, "task": task}
    await send_to_user(target, {"type": "invite_received", "from": sender})
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
    sess = SharedSession(sender, responder)
    SESSIONS[sender] = sess
    SESSIONS[responder] = sess
    await send_to_user(sender, {"type": "invite_accepted", "partner": responder})
    await send_to_user(responder, {"type": "invite_accepted", "partner": sender})
    await broadcast_online_users()
    await sess.broadcast_state()

# -------------------- 聊天系统 --------------------
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

# -------------------- 游戏内动作 --------------------
async def handle_game_action(username, data):
    action = data.get("action")
    sess = SESSIONS.get(username)
    if sess is None:
        return
    slot = sess.slot_of(username)
    game = sess.games[slot]
    phase = game.phase
    changed = False

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
            boon = next((b for b in BOONS if b["id"] == data.get("boonId")), None)
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
            sess.reject_trade(data.get("orderId"))
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
            sess.ready.add(slot)
            changed = True
            if sess.gate_complete():
                sess.advance()
    elif action == "upgradeShip":
        if phase == 4 and game.shipLevel < 3:
            cost = game.shipUpgradeCost[game.shipLevel] + game.shipUpgradePenalty
            if game.money >= cost:
                game.money -= cost
                game.shipLevel += 1
            changed = True
    elif action == "restart":
        # 仅当对方也已结束（结算完毕或破产）时才允许重置整个会话，保证双方同步
        if sess.games[1 - slot].gameOver:
            sess.restart()
            partner = sess.partner_of(username)
            await send_to_user(partner, {"type": "system_message", "message": "对方重新开始了游戏，双方进度已重置"})
            changed = True
        else:
            await send_to_user(username, {"type": "system_message", "message": "需等待对方完成本局后才能重新起航"})

    if changed:
        await sess.broadcast_state()

# -------------------- WebSocket 处理 --------------------
async def handler(websocket):
    username = None
    try:
        async for raw in websocket:
            try:
                data = json.loads(raw)
            except Exception:
                continue
            action = data.get("action")

            # ---------- 未登录：只接受注册 / 登录 ----------
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

            # ---------- 已登录：大厅 / 邀请 / 聊天 / 游戏 ----------
            if action == "get_online_users":
                await send_json(websocket, {"type": "online_users", "users": [n for n in ONLINE if n != username]})
            elif action == "send_invite":
                await handle_send_invite(username, str(data.get("to", "")))
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
            # 取消该用户发出的待处理邀请
            inv = PENDING_INVITES.pop(username, None)
            if inv:
                inv["task"].cancel()
                await send_to_user(inv["to"], {"type": "invite_cancelled", "from": username})
            await broadcast_online_users()
            # 通知会话伙伴；若双方都已离线则回收会话
            sess = SESSIONS.get(username)
            if sess is not None:
                partner = sess.partner_of(username)
                if partner in ONLINE:
                    await send_to_user(partner, {"type": "partner_status", "username": username, "online": False})
                    await sess.broadcast_state()
                else:
                    SESSIONS.pop(username, None)
                    SESSIONS.pop(partner, None)

# -------------------- HTTP 静态文件服务（与 WebSocket 共用同一端口） --------------------
# 说明：将静态文件服务并入 WebSocket 端口，便于通过单条 ngrok 隧道（如 ngrok http 8080）
# 同时穿透网页与 WebSocket，并自动适配 https/wss，避免浏览器混合内容限制。
WEB_ROOT = os.path.dirname(os.path.abspath(__file__))

async def process_request(connection, request):
    # WebSocket 升级请求放行，交由 handler 处理
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
        print(f"✅ 服务器启动：网页 http://0.0.0.0:8080 ，WebSocket ws://0.0.0.0:8080")
        await asyncio.Future()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("服务器关闭")
