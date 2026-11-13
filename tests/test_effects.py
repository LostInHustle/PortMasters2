"""Effect matrix for every boon, ship module, Broker's Whisper path, monsoon, mandate and
special rule in server.py.

Every assertion checks the thing the player actually receives: gold moved, inventory moved,
a counter charged, or the exact figure the server stamps for display. Where an effect is
supposed to change a price, the test buys or delivers and compares the balance delta, not
just the advertised number.

Run from the repository root:

    python3 -m unittest discover -s tests -v
"""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server as srv  # noqa: E402

MODULE_BY_ID = {
    m["id"]: m for m in srv.MODULES_TIER0 + srv.MODULES_TIER1 + srv.MODULES_TIER2
}
BOON_BY_ID = {b["id"]: b for b in srv.BOONS_TIER0 + srv.BOONS_TIER1 + srv.BOONS_TIER2}


def neutral_weather():
    return {
        "id": "test_calm",
        "name": "calm",
        "icon": "",
        "desc": "",
        "rewardPorts": [],
        "rewardMultiplier": 1.0,
        "resource": None,
        "purchaseMultiplier": 1.0,
        "pirateRisk": 0.0,
    }


def new_game(difficulty="standard", money=100, round_no=1):
    g = srv.PlayerGame(difficulty)
    g.money = money
    g.currentRound = round_no
    g.set_monsoon_state(neutral_weather())
    return g


def give(g, **items):
    for item, qty in items.items():
        g.inventory[item] = qty


def equip(g, module_id, ship_level=3):
    g.shipLevel = ship_level
    mod = MODULE_BY_ID[module_id]
    assert g.equip_module(mod), f"could not equip {module_id}"


def apply(g, boon_id):
    g.apply_boon(BOON_BY_ID[boon_id])


def mk_order(resources, reward, is_product=False, oid=1, port="泉州港"):
    return {
        "id": oid,
        "demandPort": port,
        "resources": [{"type": t, "required": q} for t, q in resources],
        "reward": reward,
        "totalItems": sum(q for _, q in resources),
        "isProductOrder": is_product,
        "fromIntel": False,
        "kind": "normal",
    }


def mk_card(resources, oid=1, port="泉州港"):
    rows = [{"type": t, "quantity": q, "price": p} for t, q, p in resources]
    return {
        "id": oid,
        "port": port,
        "resources": rows,
        "totalCost": sum(r["quantity"] * r["price"] for r in rows),
        "isProductCard": False,
    }


class BoonEffects(unittest.TestCase):
    def test_silk_wind_halves_silk_and_silk_woven_goods_shipping(self):
        g = new_game()
        apply(g, "silk_wind")
        give(g, 丝绸=10)
        self.assertTrue(g.complete_order(mk_order([("丝绸", 10)], 100)))
        self.assertEqual(g.roundCosts, 10)  # 20 base, halved
        self.assertEqual(g.money, 190)

        other = new_game()
        apply(other, "silk_wind")
        give(other, 茶叶=10)
        self.assertTrue(other.complete_order(mk_order([("茶叶", 10)], 100)))
        self.assertEqual(other.roundCosts, 20)  # not silk

    def test_favorable_tides_takes_four_off_every_order(self):
        g = new_game()
        apply(g, "favorable_tides")
        give(g, 茶叶=10)
        self.assertTrue(g.complete_order(mk_order([("茶叶", 10)], 100)))
        self.assertEqual(g.roundCosts, 16)
        self.assertEqual(g.money, 184)

    def test_merchant_charm_charges_85_percent(self):
        g = new_game()
        apply(g, "merchant_charm")
        card = mk_card([("茶叶", 2, 30)])
        self.assertEqual(g.get_card_final_cost(card), 51)
        self.assertTrue(g.purchase_card(card))
        self.assertEqual(g.money, 49)
        self.assertEqual(g.roundCosts, 51)
        self.assertEqual(g.inventory["茶叶"], 5)

    def test_emergency_loan_pays_40(self):
        g = new_game()
        apply(g, "emergency_loan")
        self.assertEqual(g.money, 140)

    def test_tax_shelter_cuts_the_rate_to_five_percent(self):
        g = new_game()
        apply(g, "tax_shelter")
        self.assertEqual(g.calc_income_tax(1000), 50)

    def test_hemp_monopoly_discounts_each_bolt(self):
        g = new_game()
        apply(g, "hemp_monopoly")
        card = mk_card([("麻布", 3, 5)])
        g.resourceCards = [card]
        shown = g.resource_cards_for_client()[0]
        self.assertEqual(shown["resources"][0]["discountedPrice"], 3)
        self.assertEqual(shown["finalCost"], 9)
        self.assertTrue(g.purchase_card(card))
        self.assertEqual(g.money, 91)
        self.assertEqual(g.inventory["麻布"], 11)

    def test_master_apprentice_halves_artisan_wages_not_one_time_hire(self):
        g = new_game()
        apply(g, "master_apprentice")
        self.assertTrue(g.hire_worker("weaver"))
        self.assertEqual(g.estimated_wages(), 4)
        self.assertTrue(g.pay_wages())
        self.assertEqual(g.money, 96)
        self.assertEqual(g.workerWages, 4)
        self.assertEqual(g.roundCosts, 4)

    def test_artisan_inspiration_adds_one_item_per_worker(self):
        g = new_game()
        apply(g, "artisan_inspiration")
        g.hire_worker("weaver")
        self.assertTrue(g.assign_task("weaver", "麻衣"))
        g.process_production()
        self.assertEqual(g.inventory["麻衣"], 2)
        self.assertEqual(g.inventory["麻布"], 6)

    def test_farsight_reveals_a_free_clue_when_cards_are_dealt(self):
        sess = srv.GameSession("solo")
        sess.start()
        g = sess.games[0]
        g.phase = 5
        apply(g, "farsight")
        money = g.money
        sess.advance()
        self.assertEqual(g.phase, 1)
        self.assertEqual(len(g.revealedIntel), 1)
        self.assertEqual(g.money, money)  # free means free
        self.assertEqual(len(g.resourceCards), 5)

    def test_porcelain_bronze_guild_boosts_porcelain_and_bronze_orders(self):
        g = new_game()
        apply(g, "porcelain_bronze_guild")
        give(g, 青瓷器=1, 紫铜镜=1)
        self.assertTrue(
            g.complete_order(mk_order([("青瓷器", 1)], 100, is_product=True))
        )
        # VAT 2, then reward 98 * 1.15 = 112 (truncated), shipping 5
        self.assertEqual(g.roundRevenue, 112)
        self.assertEqual(g.money, 207)

        other = new_game()
        apply(other, "porcelain_bronze_guild")
        give(other, 茶叶=1)
        self.assertTrue(other.complete_order(mk_order([("茶叶", 1)], 100)))
        self.assertEqual(other.roundRevenue, 100)

    def test_frontier_tariff_relief_halves_product_vat(self):
        g = new_game()
        apply(g, "frontier_tariff_relief")
        give(g, 青瓷器=2)
        self.assertTrue(
            g.complete_order(mk_order([("青瓷器", 2)], 200, is_product=True))
        )
        # 100 per unit, taxable 56, VAT 2 then halved to 1, so 2 total instead of 4
        self.assertEqual(g.vatPaid, 2)
        self.assertEqual(g.roundRevenue, 198)

    def test_exotic_treasures_boosts_silk_perfume_and_pearls(self):
        g = new_game()
        apply(g, "exotic_treasures")
        give(g, 蕃香脂=1)
        self.assertTrue(
            g.complete_order(mk_order([("蕃香脂", 1)], 100, is_product=True))
        )
        self.assertEqual(g.roundRevenue, 112)  # VAT 2 then 98 * 1.15

    def test_deep_sea_escort_pact_halves_fee_and_risk(self):
        g = new_game(money=340)
        apply(g, "deep_sea_escort_pact")
        state = neutral_weather()
        state["pirateRisk"] = 0.4
        g.set_monsoon_state(state)
        self.assertEqual(g.escort_cost(), 17)  # 34 halved
        self.assertAlmostEqual(g.effective_pirate_risk(), 0.2)
        self.assertTrue(g.hire_escort())
        self.assertEqual(g.money, 323)
        self.assertEqual(g.roundCosts, 17)
        self.assertEqual(g.effective_pirate_risk(), 0.0)

    def test_merchants_converge_adds_one_trade_order(self):
        sess = srv.GameSession("solo")
        sess.start()
        g = sess.games[0]
        g.phase = "worker_mgmt"
        apply(g, "merchants_converge")
        sess.advance()
        self.assertEqual(g.phase, 2)
        self.assertEqual(len(g.customerCards), 6)  # 5 base orders plus 1

        plain = srv.GameSession("solo2")
        plain.start()
        p = plain.games[0]
        p.phase = "worker_mgmt"
        plain.advance()
        self.assertEqual(len(p.customerCards), 5)

    def test_boons_replace_each_other_and_never_alias_the_shared_table(self):
        g = new_game()
        apply(g, "silk_wind")
        apply(g, "tax_shelter")
        self.assertNotIn("transport_silk_discount", g.modifierFlags)
        self.assertEqual(g.calc_income_tax(1000), 50)

        original = dict(BOON_BY_ID["merchant_charm"]["modifiers"])
        apply(g, "merchant_charm")
        g.modifierFlags["purchase_discount"] = 0.99
        self.assertEqual(BOON_BY_ID["merchant_charm"]["modifiers"], original)


class ModuleEffects(unittest.TestCase):
    def test_smugglers_hold_cuts_purchases_and_raises_income_tax(self):
        g = new_game()
        equip(g, "smugglers_hold")
        card = mk_card([("茶叶", 2, 50)])
        self.assertEqual(g.get_card_final_cost(card), 85)
        self.assertTrue(g.purchase_card(card))
        self.assertEqual(g.money, 15)
        self.assertEqual(g.calc_income_tax(1000), 120)

    def test_bulk_hauler_and_overdrive_engine_change_shipping_and_upgrade_cost(self):
        g = new_game()
        equip(g, "bulk_hauler", ship_level=1)
        self.assertEqual(g.shipUpgradePenalty, 15)
        self.assertEqual(g.calc_transport_cost(10), 5)  # 20 - 5 ship level - 10 items
        self.assertEqual(g.calc_transport_cost(3), 2)  # floor 5, then minus 3 items

        self.assertTrue(g.equip_module(MODULE_BY_ID["overdrive_engine"], swap_idx=0))
        self.assertEqual(g.shipUpgradePenalty, 0)
        self.assertEqual(g.maintenancePenalty, 10)
        self.assertEqual(g.calc_transport_cost(10), 10)  # 20 - 5 ship level - 5 engine

    def test_artisans_workshop_adds_output_and_wage_cost(self):
        g = new_game()
        equip(g, "artisans_workshop")
        g.hire_worker("weaver")
        g.assign_task("weaver", "麻衣")
        g.process_production()
        self.assertEqual(g.inventory["麻衣"], 2)
        self.assertEqual(g.effective_wage("weaver"), 9)  # 8 * 1.2
        self.assertEqual(g.effective_wage("jeweler"), 28)  # 24 * 1.2
        self.assertTrue(g.pay_wages())
        self.assertEqual(g.money, 91)

    def test_tax_evasion_halves_both_taxes_and_can_fine(self):
        g = new_game()
        equip(g, "tax_evasion")
        give(g, 青瓷器=2)
        self.assertEqual(g.calc_vat("青瓷器", 100), 1)  # 2 halved
        self.assertEqual(g.calc_income_tax(1000), 50)
        with mock.patch("random.random", return_value=0.14):
            self.assertTrue(
                g.complete_order(mk_order([("青瓷器", 2)], 200, is_product=True))
            )
        self.assertEqual(g.money, 100 - 5 + 198 - 20)

    def test_tax_evasion_audit_can_miss(self):
        g = new_game()
        equip(g, "tax_evasion")
        give(g, 茶叶=1)
        with mock.patch("random.random", return_value=0.15):
            self.assertTrue(g.complete_order(mk_order([("茶叶", 1)], 100)))
        self.assertEqual(g.money, 195)  # 100 - 5 shipping + 100 reward, no fine

    def test_silk_monopoly_ships_silk_free_and_boosts_only_silk_products(self):
        g = new_game()
        equip(g, "silk_monopoly")
        give(g, 丝绸=10)
        self.assertEqual(g.calc_transport_cost(10, has_silk=True), 0)
        self.assertTrue(g.complete_order(mk_order([("丝绸", 10)], 100)))
        self.assertEqual(g.roundCosts, 0)
        self.assertEqual(g.roundRevenue, 100)  # raw silk gets no income bonus

        product = new_game()
        equip(product, "silk_monopoly")
        give(product, 绫罗绸缎=1)
        self.assertTrue(
            product.complete_order(mk_order([("绫罗绸缎", 1)], 100, is_product=True))
        )
        # VAT 3, then 97 * 1.2 = 116
        self.assertEqual(product.roundRevenue, 116)

        perfume = new_game()
        equip(perfume, "silk_monopoly")
        give(perfume, 蕃香脂=1)
        self.assertTrue(
            perfume.complete_order(mk_order([("蕃香脂", 1)], 100, is_product=True))
        )
        self.assertEqual(perfume.roundRevenue, 117)  # VAT 2, then 98 * 1.2
        self.assertEqual(perfume.roundCosts, 5)  # it is not in the free shipping family

        porcelain = new_game()
        equip(porcelain, "silk_monopoly")
        give(porcelain, 青瓷器=1)
        self.assertTrue(
            porcelain.complete_order(mk_order([("青瓷器", 1)], 100, is_product=True))
        )
        self.assertEqual(porcelain.roundRevenue, 98)  # no silk product bonus

    def test_brokers_network_cuts_whisper_cost_and_doubles_clues(self):
        g = new_game()
        equip(g, "brokers_network")
        self.assertEqual(g.intelCost, 2)
        g.phase2DemandTags = ["麻布", "丝绸", "茶叶", "瓷土"]
        self.assertTrue(g.purchase_intel())
        self.assertEqual(g.money, 98)
        self.assertEqual(len(g.revealedIntel), 2)
        self.assertEqual(len(g.phase2DemandTags), 2)

        g.equip_module(MODULE_BY_ID["kiln_cellar"], swap_idx=0)
        self.assertEqual(g.intelCost, 5)

    def test_salvage_crane_refunds_shipping_on_a_lucky_roll(self):
        g = new_game()
        equip(g, "salvage_crane")
        give(g, 麻布=2)
        with mock.patch("random.random", return_value=0.29):
            self.assertTrue(g.complete_order(mk_order([("麻布", 2)], 100)))
        self.assertEqual(
            g.money, 200
        )  # 100 start, shipping 5 charged then refunded, 100 reward
        self.assertEqual(g.roundCosts, 5)
        self.assertEqual(g.score, 95)

        unlucky = new_game()
        equip(unlucky, "salvage_crane")
        give(unlucky, 麻布=2)
        with mock.patch("random.random", return_value=0.30):
            self.assertTrue(unlucky.complete_order(mk_order([("麻布", 2)], 100)))
        self.assertEqual(unlucky.money, 195)

    def test_overdrive_engine_raises_upkeep(self):
        g = new_game()
        equip(g, "overdrive_engine")
        self.assertEqual(g.maintenancePenalty, 10)
        self.assertTrue(g.pay_maintenance())
        self.assertEqual(g.money, 75)
        self.assertEqual(g.maintenanceCosts, 25)
        self.assertEqual(g.roundCosts, 25)

    def test_bureau_token_pays_on_new_route_goods_in_any_position(self):
        product = new_game()
        equip(product, "bureau_token")
        give(product, 青瓷器=1)
        self.assertTrue(
            product.complete_order(mk_order([("青瓷器", 1)], 100, is_product=True))
        )
        self.assertEqual(product.roundRevenue, 107)  # VAT 2, then 98 * 1.1

        raw = new_game()
        equip(raw, "bureau_token")
        give(raw, 瓷土=2)
        self.assertTrue(raw.complete_order(mk_order([("瓷土", 2)], 100)))
        self.assertEqual(raw.roundRevenue, 110)

        mixed = new_game()
        equip(mixed, "bureau_token")
        give(mixed, 茶叶=1, 铜矿=1)
        self.assertTrue(mixed.complete_order(mk_order([("茶叶", 1), ("铜矿", 1)], 100)))
        self.assertEqual(mixed.roundRevenue, 110)  # copper second still qualifies

        unrelated = new_game()
        equip(unrelated, "bureau_token")
        give(unrelated, 茶叶=2)
        self.assertTrue(unrelated.complete_order(mk_order([("茶叶", 2)], 100)))
        self.assertEqual(unrelated.roundRevenue, 100)

        tier_two = new_game()
        equip(tier_two, "bureau_token")
        give(tier_two, 珠链=1)
        self.assertTrue(
            tier_two.complete_order(mk_order([("珠链", 1)], 100, is_product=True))
        )
        self.assertEqual(tier_two.roundRevenue, 99)  # VAT 1, no new route bonus

    def test_kiln_cellar_discounts_porcelain_clay_and_copper_ore_only(self):
        g = new_game()
        equip(g, "kiln_cellar")
        card = mk_card([("瓷土", 2, 4), ("铜矿", 1, 10), ("丝绸", 1, 8)])
        g.resourceCards = [card]
        shown = g.resource_cards_for_client()[0]
        self.assertEqual([r["discountedPrice"] for r in shown["resources"]], [2, 8, 8])
        self.assertEqual(shown["finalCost"], 20)  # 26 total minus 6 flat discount
        self.assertTrue(g.purchase_card(card))
        self.assertEqual(g.money, 80)

    def test_ocean_relay_adds_a_third_clue(self):
        g = new_game()
        equip(g, "ocean_relay")
        g.phase2DemandTags = ["麻布", "丝绸", "茶叶", "瓷土"]
        self.assertTrue(g.purchase_intel())
        self.assertEqual(len(g.revealedIntel), 2)
        self.assertEqual(g.money, 95)

    def test_foreign_quarter_pass_discounts_spices_and_pearls(self):
        g = new_game()
        equip(g, "foreign_quarter_pass")
        card = mk_card([("香料", 1, 10), ("珍珠", 1, 20), ("麻布", 1, 5)])
        self.assertEqual(g.get_card_final_cost(card), 29)  # 35 minus 6
        g.resourceCards = [card]
        shown = g.resource_cards_for_client()[0]
        self.assertEqual([r["discountedPrice"] for r in shown["resources"]], [7, 17, 5])

    def test_persian_dome_compass_cuts_risk_thirty_percent(self):
        g = new_game()
        equip(g, "persian_dome_compass")
        state = neutral_weather()
        state["pirateRisk"] = 0.4
        g.set_monsoon_state(state)
        self.assertAlmostEqual(g.effective_pirate_risk(), 0.28)

    def test_fleet_of_treasures_discounts_each_treasure_item(self):
        g = new_game()
        equip(g, "fleet_of_treasures", ship_level=1)
        order = mk_order([("蕃香脂", 2), ("珠链", 1), ("丝绸", 7)], 100)
        self.assertEqual(
            g.calc_transport_cost(10, True, order["resources"]), 6
        )  # 15 minus 9

    def test_module_draft_requires_a_slot_persists_batch_and_rerolls_once(self):
        g = new_game()
        self.assertFalse(g.start_module_draft())
        g.shipLevel = 1
        self.assertTrue(g.start_module_draft())
        first = [m["id"] for m in g.draftChoices]
        self.assertEqual(len(first), 3)
        self.assertEqual(len(set(first)), 3)
        self.assertTrue(
            all(m["id"] in [x["id"] for x in srv.MODULES_TIER0] for m in g.draftChoices)
        )

        g.draftOpen = False
        self.assertTrue(g.start_module_draft())
        self.assertEqual(
            [m["id"] for m in g.draftChoices], first
        )  # same batch, no free reroll

        self.assertTrue(g.reroll_module_draft())
        self.assertFalse(g.reroll_module_draft())
        self.assertTrue(g.equip_module(MODULE_BY_ID[g.draftChoices[0]["id"]]))
        self.assertFalse(g.draftOpen)
        self.assertTrue(g.has_module(g.equippedModules[0]["id"]))


class Combinations(unittest.TestCase):
    def test_purchase_stack_applies_percent_flat_then_smugglers(self):
        g = new_game()
        apply(g, "merchant_charm")
        equip(g, "kiln_cellar")
        equip(g, "smugglers_hold")
        card = mk_card([("瓷土", 2, 8), ("铜矿", 1, 12)])
        self.assertEqual(g.get_card_final_cost(card), 14)  # 28 -> 23 -> 17 -> 14
        self.assertTrue(g.purchase_card(card))
        self.assertEqual(g.money, 86)
        self.assertEqual(g.roundCosts, 14)

    def test_transport_stack_combines_level_boons_and_modules(self):
        g = new_game()
        g.shipLevel = 1
        apply(g, "silk_wind")
        g.modifierFlags["transport_flat_discount"] = 4  # both boons active at once
        self.assertEqual(
            g.calc_transport_cost(10, has_silk=True), 5
        )  # 20-5-4=11, halved

        bulk = new_game()
        bulk.shipLevel = 1
        apply(bulk, "silk_wind")
        bulk.modifierFlags["transport_flat_discount"] = 4
        equip(bulk, "bulk_hauler", ship_level=1)
        self.assertEqual(
            bulk.calc_transport_cost(10, has_silk=True), 0
        )  # 5 minus 10 items

        fleet = new_game()
        equip(fleet, "fleet_of_treasures", ship_level=1)
        order = mk_order([("蕃香脂", 2), ("珠链", 1), ("丝绸", 7)], 100)
        self.assertEqual(fleet.calc_transport_cost(10, True, order["resources"]), 6)
        over = new_game()
        equip(over, "overdrive_engine", ship_level=1)
        order2 = mk_order([("蕃香脂", 2), ("珠链", 1), ("丝绸", 7)], 100)
        self.assertEqual(over.calc_transport_cost(10, True, order2["resources"]), 10)

    def test_tax_stack_applies_override_smugglers_then_ledger(self):
        g = new_game()
        apply(g, "tax_shelter")
        equip(g, "smugglers_hold")
        equip(g, "tax_evasion")
        self.assertEqual(g.calc_income_tax(1000), 30)  # 50 -> 60 -> 30

    def test_wage_stack_applies_workshop_then_apprentice(self):
        g = new_game()
        equip(g, "artisans_workshop")
        apply(g, "master_apprentice")
        g.hire_worker("weaver")
        g.hire_worker("weaver")
        g.hire_worker("master")
        self.assertEqual(g.effective_wage("weaver"), 4)  # 8 * 1.2 = 9, halved to 4
        self.assertEqual(g.effective_wage("master"), 7)  # 12 * 1.2 = 14, halved
        self.assertEqual(g.estimated_wages(), 15)
        self.assertTrue(g.pay_wages())
        self.assertEqual(g.money, 85)

    def test_production_stack_adds_boon_and_workshop_on_top_of_skill(self):
        g = new_game()
        equip(g, "artisans_workshop")
        apply(g, "artisan_inspiration")
        g.hire_worker("weaver")
        g.assign_task("weaver", "麻衣")
        g.process_production()
        self.assertEqual(g.inventory["麻衣"], 3)  # base 1 + boon 1 + workshop 1
        # The worker crossed two items produced and is now skilled.
        g.assign_task("weaver", "麻衣")
        g.process_production()
        self.assertEqual(g.inventory["麻衣"], 7)  # 3 + (2 + 1 + 1)

    def test_reward_stack_multiplies_in_order_and_truncates(self):
        g = new_game()
        equip(g, "silk_monopoly")
        apply(g, "exotic_treasures")
        give(g, 蕃香脂=1)
        self.assertTrue(
            g.complete_order(mk_order([("蕃香脂", 1)], 100, is_product=True))
        )
        # VAT 2 -> 98 * 1.2 = 117 * 1.15 = 134
        self.assertEqual(g.roundRevenue, 134)
        self.assertEqual(g.money, 229)  # 100 - 5 shipping + 134

    def test_silk_monopoly_does_not_stack_on_porcelain_even_with_bureau_token(self):
        g = new_game()
        equip(g, "silk_monopoly")
        equip(g, "bureau_token")
        give(g, 青瓷器=1)
        self.assertTrue(
            g.complete_order(mk_order([("青瓷器", 1)], 100, is_product=True))
        )
        self.assertEqual(g.roundRevenue, 107)  # VAT 2 then only bureau 1.1
        self.assertEqual(g.roundCosts, 5)

    def test_intel_stack_charges_two_and_reveals_three(self):
        g = new_game()
        equip(g, "brokers_network")
        equip(g, "ocean_relay")
        g.phase2DemandTags = ["麻布", "丝绸", "茶叶", "瓷土", "铜矿"]
        self.assertTrue(g.purchase_intel())
        self.assertEqual(g.money, 98)
        self.assertEqual(len(g.revealedIntel), 3)
        self.assertEqual(len(g.phase2DemandTags), 2)

    def test_risk_stack_applies_pact_then_compass(self):
        g = new_game()
        apply(g, "deep_sea_escort_pact")
        equip(g, "persian_dome_compass")
        state = neutral_weather()
        state["pirateRisk"] = 0.5
        g.set_monsoon_state(state)
        self.assertAlmostEqual(g.effective_pirate_risk(), 0.175)  # 0.5 * 0.5 * 0.7


class BrokerWhisper(unittest.TestCase):
    def test_clue_becomes_a_real_order_with_matching_good_and_port(self):
        g = new_game()
        g.phase2DemandTags = ["麻布", "丝绸", "茶叶"]
        with mock.patch.object(
            srv, "choice", side_effect=lambda arr: arr[0]
        ), mock.patch.object(srv, "rand", return_value=2):
            self.assertTrue(g.purchase_intel())
            clue = g.revealedIntel[0]
            self.assertEqual(clue["item"], "麻布")
            self.assertEqual(clue["port"], "泉州港")
            self.assertEqual(g.money, 95)

            order = g.gen_mixed_order()
            self.assertTrue(order["fromIntel"])
            self.assertEqual(order["demandPort"], clue["port"])
            self.assertEqual(order["resources"][0]["type"], clue["item"])
            self.assertTrue(clue["used"])

            other = g.gen_mixed_order()
            self.assertFalse(other.get("fromIntel", False))

    def test_whisper_fails_without_tags_or_gold(self):
        g = new_game(money=3)
        g.phase2DemandTags = ["麻布"]
        self.assertFalse(g.purchase_intel())
        self.assertEqual(g.money, 3)

        g.money = 100
        g.phase2DemandTags = []
        self.assertFalse(g.purchase_intel())
        self.assertEqual(g.money, 100)

    def test_hard_mode_corruption_stacks_and_easy_mode_never_corrupts(self):
        hard = new_game("hard")
        hard.phase2DemandTags = ["麻布", "丝绸", "茶叶"]
        with mock.patch("random.random", return_value=0.0):
            self.assertTrue(hard.purchase_intel())
            self.assertTrue(hard.purchase_intel())
        self.assertAlmostEqual(hard.broker_pirate_risk, 0.4)
        self.assertAlmostEqual(hard.effective_pirate_risk(), 0.4)

        easy = new_game("easy")
        easy.phase2DemandTags = ["麻布", "丝绸"]
        with mock.patch("random.random", return_value=0.0):
            self.assertTrue(easy.purchase_intel())
        self.assertEqual(easy.broker_pirate_risk, 0.0)


class MonsoonsAndMandates(unittest.TestCase):
    def test_every_monsoon_actually_moves_its_price_and_reward(self):
        self.assertEqual(len(srv.MONSOON_STATES), 8)
        g = new_game()
        for state in srv.MONSOON_STATES:
            with self.subTest(state=state["id"]):
                g.set_monsoon_state(state)
                port = state["rewardPorts"][0]
                self.assertEqual(
                    g.env_reward(port, 100), round(100 * state["rewardMultiplier"])
                )
                neutral_port = next(
                    p for p in srv.PORTS_TIER0 if p not in state["rewardPorts"]
                )
                self.assertEqual(g.env_reward(neutral_port, 100), 100)
                self.assertEqual(
                    g.env_purchase_price(state["resource"], 100),
                    round(100 * state["purchaseMultiplier"]),
                )
                other_item = "珍珠" if state["resource"] != "珍珠" else "麻布"
                self.assertEqual(g.env_purchase_price(other_item, 100), 100)
                self.assertAlmostEqual(g.pirate_threat(), state["pirateRisk"])

    def test_pirate_raid_takes_its_tier_share_and_escort_prevents_it(self):
        g = new_game("easy", money=100)
        state = neutral_weather()
        state["pirateRisk"] = 0.5
        g.set_monsoon_state(state)
        with mock.patch("random.random", return_value=0.0):
            g.pay_maintenance()
        self.assertEqual(g.money, 100 - 15 - 15)  # 15 percent raid plus 15 upkeep
        self.assertEqual(g.roundCosts, 30)

        safe = new_game("easy", money=100)
        safe.set_monsoon_state(state)
        self.assertTrue(safe.hire_escort())
        with mock.patch("random.random", return_value=0.0):
            safe.pay_maintenance()
        self.assertEqual(safe.money, 100 - 10 - 15)

    def test_every_emperor_mandate_is_generated_on_its_scheduled_round(self):
        for difficulty, cfg in srv.DIFFICULTIES.items():
            for round_no, size in cfg["mandates"].items():
                with self.subTest(difficulty=difficulty, round_no=round_no):
                    g = new_game(difficulty, round_no=round_no)
                    order = g.gen_emperor_mandate_order(size)
                    tpl = srv.EMPEROR_MANDATE_TEMPLATES[size]
                    self.assertEqual(order["kind"], "EmperorMandate")
                    self.assertEqual(order["demandPort"], tpl["port"])
                    self.assertEqual(
                        order["resources"],
                        [dict(r) for r in tpl["resources"]],
                    )
                    self.assertEqual(order["reward"], tpl["reward"])
                    self.assertEqual(
                        order["isFinalMandate"], round_no == max(cfg["mandates"])
                    )

    def test_trade_phase_deals_the_mandate_alongside_normal_orders(self):
        sess = srv.GameSession("solo")
        sess.start()
        g = sess.games[0]
        g.currentRound = 3  # easy schedule has a mandate here
        g.phase = "worker_mgmt"
        sess.advance()
        self.assertEqual(g.customerCards[0]["kind"], "EmperorMandate")
        self.assertFalse(g.customerCards[0]["isFinalMandate"])
        self.assertEqual(len(g.customerCards), 5)

    def test_charter_announces_only_the_round_a_tier_opens(self):
        self.assertEqual(
            srv.charter_event(4, srv.DIFFICULTIES["standard"]["tier_unlock"])["id"],
            "tier1",
        )
        self.assertEqual(
            srv.charter_event(8, srv.DIFFICULTIES["standard"]["tier_unlock"])["id"],
            "tier2",
        )
        self.assertIsNone(
            srv.charter_event(5, srv.DIFFICULTIES["standard"]["tier_unlock"])
        )
        self.assertIsNone(srv.charter_event(4, srv.DIFFICULTIES["easy"]["tier_unlock"]))

    def test_phase_option_count_widens_with_each_tier(self):
        easy = srv.DIFFICULTIES["easy"]["tier_unlock"]
        standard = srv.DIFFICULTIES["standard"]["tier_unlock"]
        self.assertEqual(srv.phase_option_count(1, easy), 5)
        self.assertEqual(srv.phase_option_count(4, standard), 8)
        self.assertEqual(srv.phase_option_count(8, standard), 11)


class DisplayMatchesCharge(unittest.TestCase):
    def test_printed_purchase_price_is_the_gold_actually_taken(self):
        g = new_game()
        apply(g, "merchant_charm")
        equip(g, "kiln_cellar")
        equip(g, "smugglers_hold")
        card = mk_card([("瓷土", 2, 8), ("铜矿", 1, 12)])
        g.resourceCards = [card]
        shown = g.resource_cards_for_client()[0]
        before = g.money
        self.assertTrue(g.purchase_card(card))
        self.assertEqual(before - g.money, shown["finalCost"])
        self.assertEqual(shown["finalCost"], 14)
        self.assertEqual(
            [r["discountedPrice"] * r["quantity"] for r in shown["resources"]],
            [12, 10],
        )  # the percentage discount is shown on the card total, not on each line

    def test_printed_shipping_is_the_gold_actually_taken(self):
        g = new_game()
        g.shipLevel = 1
        apply(g, "favorable_tides")
        equip(g, "bulk_hauler", ship_level=1)
        give(g, 茶叶=10)
        order = mk_order([("茶叶", 10)], 77)
        g.customerCards = [order]
        shown = g.customer_cards_for_client()[0]
        self.assertEqual(shown["transportCost"], 1)
        before = g.money
        self.assertTrue(g.complete_order(shown))
        self.assertEqual(g.money - before, 77 - shown["transportCost"])
        self.assertEqual(g.roundCosts, 1)

    def test_printed_wages_are_the_gold_actually_taken(self):
        g = new_game()
        equip(g, "artisans_workshop")
        apply(g, "master_apprentice")
        g.hire_worker("weaver")
        g.hire_worker("master")
        preview = g.to_dict()["estimatedWages"]
        before = g.money
        self.assertTrue(g.pay_wages())
        self.assertEqual(before - g.money, preview)
        self.assertEqual(preview, 11)  # 4 + 7

    def test_printed_escort_fee_is_the_gold_actually_taken(self):
        g = new_game(money=340)
        apply(g, "deep_sea_escort_pact")
        preview = g.to_dict()["escortCost"]
        before = g.money
        self.assertTrue(g.hire_escort())
        self.assertEqual(before - g.money, preview)
        self.assertEqual(preview, 17)

    def test_printed_upgrade_price_includes_every_module_penalty(self):
        g = new_game(money=500)
        equip(g, "bulk_hauler", ship_level=1)
        data = g.to_dict()
        self.assertEqual(data["shipUpgradePenalty"], 15)
        self.assertEqual(
            data["shipUpgradeCost"][g.shipLevel] + data["shipUpgradePenalty"], 40
        )
        g.equip_module(MODULE_BY_ID["overdrive_engine"], swap_idx=0)
        data = g.to_dict()
        self.assertEqual(data["shipUpgradePenalty"], 0)
        self.assertEqual(
            data["shipUpgradeCost"][g.shipLevel] + data["shipUpgradePenalty"], 25
        )


class BarterAndSharedRules(unittest.TestCase):
    def test_barter_moves_both_sides_resources(self):
        sess = srv.GameSession("a")
        sess.players.append("b")
        sess.start()
        a, b = sess.games
        order = sess.create_trade_order(
            0, [{"type": "麻布", "quantity": 2}], [{"type": "金币", "quantity": 10}]
        )
        self.assertTrue(sess.accept_trade(order["id"], 1))
        self.assertEqual(a.money, 110)
        self.assertEqual(a.inventory["麻布"], 6)
        self.assertEqual(b.money, 90)
        self.assertEqual(b.inventory["麻布"], 10)
        self.assertEqual(sess.trade_orders, [])

    def test_barter_merges_duplicate_entries_and_rejects_the_overflow(self):
        sess = srv.GameSession("a")
        sess.players.append("b")
        sess.start()
        a, b = sess.games
        a.inventory["麻布"] = 5
        order = sess.create_trade_order(
            0,
            [{"type": "麻布", "quantity": 5}, {"type": "麻布", "quantity": 5}],
            [{"type": "金币", "quantity": 10}],
        )
        self.assertEqual(len(order["sell"]), 1)
        self.assertEqual(order["sell"][0]["quantity"], 10)
        self.assertFalse(sess.accept_trade(order["id"], 1))
        self.assertEqual(a.inventory["麻布"], 5)

    def test_income_tax_base_counts_each_round_cost_once(self):
        g = new_game(money=100)
        g.roundRevenue = 1000
        g.roundCosts = 400  # already includes wages and maintenance
        g.workerWages = 50
        g.maintenanceCosts = 100
        g.end_round()
        self.assertEqual(g.incomeTaxPaid, 60)  # 10 percent of 600, not of 450
        self.assertEqual(g.money, 40)
        self.assertEqual(g.lastRoundSummary["incomeTax"], 60)

    def test_income_tax_is_zero_on_a_losing_round(self):
        g = new_game(money=100)
        g.roundRevenue = 100
        g.roundCosts = 200
        g.end_round()
        self.assertEqual(g.incomeTaxPaid, 0)
        self.assertEqual(g.money, 100)

    def test_score_counts_net_reward_after_vat_and_shipping(self):
        g = new_game()
        give(g, 青瓷器=2)
        self.assertTrue(
            g.complete_order(mk_order([("青瓷器", 2)], 200, is_product=True))
        )
        self.assertEqual(g.vatPaid, 4)
        self.assertEqual(g.roundRevenue, 196)
        self.assertEqual(g.roundCosts, 5)
        self.assertEqual(g.score, 191)


if __name__ == "__main__":
    unittest.main()
