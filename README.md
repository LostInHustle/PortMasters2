# ⚓ PortMasters 2

> 🌐 **Bilingual Documentation** | [🇨🇳 查看中文文档](README_zh-CN.md)

---

## 📖 1. Overview
Welcome back to the Maritime Silk Road! PortMasters 2 takes the series online. Two captains sail one shared voyage, always on the same round and the same phase. You compete for renown, yet you also barter goods, gold and information with each other along the way. Draw a fortune from the Navigator's Compass, buy rumors from the brokers, fit your flagship with modules, and keep enough cash on hand for wages, upkeep and taxes through every voyage (8 rounds in Easy mode, 16 in Hard). The richer reputation wins.

What's new since PortMasters 1:
- 🌐 Online play for two, with accounts, a lobby, invitations, chat and reconnection.
- 🤝 A barter phase where you and your partner trade goods and gold freely.
- 🧭 Fortunes: each round the Navigator's Compass deals every captain a private hand of 4 random buffs, and you lock in one.
- 🗣️ The Broker's Whisper: pay for intel, and every clue turns into a guaranteed order later that round.
- 🔧 Ship modules: draft and install up to 3 of them, from the Smuggler's Hold to the Overdrive Engine.
- 👀 A spectator window, so a bankrupt captain can still watch the partner finish the voyage.
- 🌍 The whole interface is available in English (the default) and Simplified Chinese. Switch any time with the 🌐 button.
- ⚖️ Two difficulty modes. Easy keeps the voyage on the founding set of goods for a gentler game, while Hard opens the full trade through the Silk Road Charter. The inviting captain picks the level and the other confirms it, and every session starts on Easy unless it is changed.
- 🗺️ The Silk Road Charter: at Round 6 ("New Maritime Edict") and Round 10 ("Ten Thousand Kingdoms Trade"), the trade network expands in two waves, 4 new resources, 4 new products, 4 new artisan types, 4 new ports (9 total), 6 new Fortunes, 6 new ship modules and 4 new Trade Winds (8 total) join the game. Rounds 1-5 play exactly as before. This progression is the Hard mode experience, which runs for 16 rounds; in Easy mode the 8 round voyage stays on the founding set the whole way through and these waves do not arrive.

---

## 🛠️ 2. Installation & Running

### ✅ Prerequisites
- Python 3.10 or newer on the machine that hosts the game.
- One library: `websockets` (listed in `requirements.txt`).
- Windows, macOS or Linux. The players themselves only need a modern browser.

### 🚀 Steps to Run
1. Download or clone the project folder.
2. Install the dependency:
   ```bash
   pip install -r requirements.txt
   ```
3. Start the server:
   ```bash
   python server.py
   ```
4. Each player opens **http://localhost:8080** in a browser (on a LAN, use the host machine's address and port 8080), registers an account and logs in.
5. Invite someone from the lobby. Choose the difficulty for the session (Easy by default), and once they have read what it means and accepted, the shared voyage begins. 🌊

> 💡 Playing over the internet: the page and the WebSocket share port 8080, so a single tunnel such as `ngrok http 8080` carries the whole game, https and wss included.

---

## 🎮 3. Gameplay Mechanics

A game lasts **8 voyages** (rounds) in Easy mode or **16** in Hard mode, and each voyage runs through **8 phases**. No phase advances until both captains confirm.

| Phase | Description |
|:---|:---|
| **⚓ Set Sail** | Confirm the start of the round. From round 2 on, this page also recaps how the previous round went. |
| **🧭 Fortune** | The compass deals you 4 of the 8 fortunes at random. Your partner gets a different hand. Lock one; it lasts this round only. |
| **🛒 Procure** | Buy materials and goods from the supply cards (5 in Easy mode; in Hard mode the hand grows to 8 once the first charter wave opens at Round 6 and to 11 once the second opens at Round 10). The Broker's Whisper panel sits at the top and sells intel about coming demand. |
| **🤝 Barter** | Trade with your partner. Post an offer like "I give this for that" and it settles the moment they accept. |
| **👥 Artisans** | Hire or dismiss artisans and hand out production tasks. Materials are consumed right away. |
| **📦 Trade** | Deliver port orders from your stock. Clues you bought show up here as guaranteed orders marked 🗣️. |
| **🔧 Upkeep** | Production arrives and wages are paid on their own. Then you pay 15 gold of fleet upkeep. If you cannot, your fleet goes bankrupt. |
| **🚢 Shipyard** | Upgrade the ship if you like (levels 0 to 3), draft modules, then end the voyage. |

### ⚖️ Difficulty Modes
Every session is played at one of two difficulties, and the game always starts on Easy unless someone chooses otherwise.

- **🌱 Easy** is the shorter 8 round voyage and keeps the whole game on the founding set of goods. You trade the three starting raw materials of Hemp Cloth, Silk and Tea, craft the four starter products, and hire from the first three artisan guilds, together with only the fortunes, ship modules, ports and trade winds that belong to them. The board never grows crowded, so there is plenty of room to learn the rhythm of each round.
- **🔥 Hard** is the longer 16 round voyage and opens the full trade. It plays exactly like the Silk Road Charter progression described below, bringing in the remaining raw materials, products, foreign ports, specialist artisans and the richer fortunes, modules and trade winds as the rounds go on. The first five rounds stay as relaxed as Easy mode, then there is far more to manage and the competition for cargo space and coin is much fiercer.

The difficulty is agreed before a voyage begins. When you invite another captain you choose the level, and they see a short explanation of what it changes and confirm it before the session starts. Both captains therefore always play the same voyage at the same difficulty, and a restart keeps that difficulty.

### 📦 Resources
Raw materials:
- `Hemp Cloth` 🧶, the everyday fabric for simple clothes.
- `Silk` 👘, the fine stuff behind the luxury goods.
- `Tea Leaves` 🍵, what gives a sachet its scent.
- `Porcelain Clay` 🧱, the fine clay behind celadon ware *(New Maritime Edict, Round 6+)*.
- `Copper Ore` ⛏️, hammered into mirrors and fittings *(New Maritime Edict, Round 6+)*.
- `Spices` 🌶️, the fragrant cargo of the southern seas *(Ten Thousand Kingdoms Trade, Round 10+)*.
- `Pearls` 🦪, lustrous treasures from southern waters *(Ten Thousand Kingdoms Trade, Round 10+)*.

Finished goods:
- `Hemp Garb` 👔 takes 2 Hemp Cloth (Weaver). Base value 15, sells around 30 to 42.
- `Cloth Tunic` 👕 takes 2 Hemp Cloth and 1 Silk (Weaver). Base value 35, sells around 50 to 65.
- `Fine Brocade` 👗 takes 3 Silk (Master Weaver only). Base value 60, sells around 70 to 90.
- `Scented Sachet` 🌸 takes 1 Silk and 2 Tea (Sachet Maker only). Base value 80, sells around 95 to 120.
- `Bronze Mirror` 🪞 takes 3 Copper Ore (Coppersmith). Base value 45, sells around 55 to 72 *(New Maritime Edict, Round 6+)*.
- `Celadon Porcelain` 🏺 takes 3 Porcelain Clay (Potter). Base value 65, sells around 78 to 100 *(New Maritime Edict, Round 6+)*.
- `Foreign Perfume Oil` 🧴 takes 2 Spices and 1 Silk (Perfumer only). Base value 85, sells around 100 to 130 *(Ten Thousand Kingdoms Trade, Round 10+)*.
- `Pearl Necklace` 📿 takes 2 Pearls and 1 Silk (Jeweler only). Base value 105, sells around 125 to 160 *(Ten Thousand Kingdoms Trade, Round 10+)*.

### 👷 Artisan System
- **Weavers** 👩‍🔧 craft Hemp Garb and Cloth Tunics. Wage: 8 gold a round.
- **Master Weavers** 👩‍🎨 also craft Fine Brocade. Wage: 12 gold a round.
- **Sachet Makers** 🌸 are the only ones who can make Sachets. Wage: 20 gold a round.
- **Coppersmiths** 🪞 craft Bronze Mirrors. Wage: 12 gold a round *(New Maritime Edict, Round 6+)*.
- **Potters** 🏺 craft Celadon Porcelain. Wage: 14 gold a round *(New Maritime Edict, Round 6+)*.
- **Perfumers** 🧴 are the only ones who can make Foreign Perfume Oil. Wage: 18 gold a round *(Ten Thousand Kingdoms Trade, Round 10+)*.
- **Jewelers** 📿 are the only ones who can make Pearl Necklaces. Wage: 24 gold a round *(Ten Thousand Kingdoms Trade, Round 10+)*.
- Once an artisan has produced 2 items in total, they become **skilled** ⭐ and make 2 per task at the same wage.
- Hiring costs nothing up front; wages come out automatically at Upkeep. Letting an idle artisan go costs one wage in severance.

### 🧭 Fortunes (a private hand of 4 each round, pick 1)
| Fortune | Effect |
|:---|:---|
| 🌬️ Silk Road Tailwind | Shipping for silk and finished goods is halved this round |
| 🌊 Favorable Tides | Base shipping costs 4 gold less |
| ✨ Merchant's Charm | Everything you buy costs about 15% less |
| 🔨 Artisan's Inspiration | Every worker makes one extra item |
| 💰 Emergency Loan | 40 gold, right now |
| 📜 Tax Exemption | Income tax falls to 5% |
| 🧶 Hemp Monopoly | Hemp Cloth costs 2 gold less per unit |
| 🎓 Apprentice Legacy | Hiring wages are halved |
| 🔮 Farsight *(Round 6+)* | Gain 1 free Broker's Whisper clue this round |
| 🏮 Porcelain & Bronze Consortium *(Round 6+)* | Celadon Porcelain and Bronze Mirror orders pay 15% more this round |
| 🧾 Frontier Tariff Relief *(Round 6+)* | VAT on finished-goods deliveries is halved this round |
| 💎 Treasures from Afar *(Round 10+)* | Foreign Perfume Oil and Pearl Necklace orders pay 15% more this round |
| 🛡️ Deep-Sea Escort Pact *(Round 10+)* | Escort hiring costs half price and pirate risk is halved this round |
| 🛍️ Merchants Converge *(Round 10+)* | 1 extra order appears in the Trade phase this round |

### 🔧 Ship Modules (draft 3, install 1; slots equal your ship level)
| Module | Effect |
|:---|:---|
| 🏴‍☠️ Smuggler's Hold | Purchases cost 15% less, but income tax rises 20% |
| 🏗️ Bulk Rigging | Each item ships 1 gold cheaper; ship upgrades cost 15 gold more |
| 🛠️ Artisan's Workshop | Workers make one extra item; wages rise 20% |
| 📒 Hidden Ledger | Income tax is figured on profit after VAT, but each delivery carries a 15% chance of a 20 gold audit fine |
| 🐍 Silk Monopoly | Silk ships for free, and silk product orders pay 20% more |
| 🕵️ Broker's Network | Whispers cost just 2 gold and reveal 2 clues at a time |
| ♻️ Salvage Crane | A 30% chance your shipping fee comes back on delivery |
| ⚡ Overdrive Engine | Shipping costs 5 gold less; upkeep costs 10 gold more |
| 🎫 Trade Bureau Token *(Round 6+)* | Orders for new trade-route goods (Porcelain Clay, Copper Ore and their products) pay 10% more |
| 🔥 Kiln Cellar *(Round 6+)* | Porcelain Clay and Copper Ore purchase price −2 gold per unit |
| 📡 Ocean-Going Interpreter *(Round 6+)* | Each Broker's Whisper purchase reveals 1 extra clue at no added cost |
| 🪪 Foreign Quarter Guild Pass *(Round 10+)* | Spices and Pearls purchase price −3 gold per unit |
| 🧿 Persian Dome Compass *(Round 10+)* | Pirate risk reduced by 30% |
| ⛵ Fleet of Ten-Thousand Treasures *(Round 10+)* | Shipping for Foreign Perfume Oil and Pearl Necklace is 3 gold cheaper per item |

### 💰 Taxes & Finance
- **VAT**: about 5% of the profit on finished goods, taken automatically when you deliver.
- **Income tax**: about 10% of the round's net profit (5% under a Tax Exemption), taken at the end of the round.
- **Shipping**: 2 gold per item, less 5 gold per ship level and any fortune discounts, but never below 5 gold.
- **Upkeep**: a flat 15 gold a round (some modules raise it), paid by hand during the Upkeep phase. Miss it and your game is over.

### 🌐 Multiplayer
- **Accounts**: a username and a password. Passwords are stored salted and hashed in `users.json`.
- **Invitations**: one per minute from the lobby, and each expires after 60 seconds. When you invite someone you also choose the session difficulty, and they confirm it in the invitation window before the voyage starts.
- **Staying in sync**: both captains share the round and the phase. The "Ready n / 2" chip shows who has confirmed. A bankrupt player counts as ready and never holds the partner up.
- **Bankruptcy and spectating**: a bankrupt captain stays on the settlement page and can open the live 👀 spectator window to watch the partner play on.
- **Reconnection**: sessions live on the server, so logging back in puts you right where you were. A session is only thrown away once both players are offline.
- **Restart**: when both games have ended, either captain can reset the table for a new run.

---

## ⌨️ 4. Controls

### ⚡ Keyboard Shortcuts
| Key | Action |
|:---|:---|
| `F1` | Open the game manual |
| `Esc` | Close dialogs, the spectator window, or chat |
| `Enter` | Send a chat message (while typing in the chat box) |

### 🖱️ Mouse Usage
- Click buttons to act: buy, trade, hire, upgrade, ready up.
- The 🌐 button (in the header, on the login page, or in the lobby) switches between English and 中文 whenever you like.
- Hover over underlined labels for an explanation. Panels scroll when their content runs long.

---

## 💡 5. Strategy Tips
1. Mind your cash before anything else. Wages and upkeep come due every single round, and the "Due This Round" box on the left does the math for you.
2. Whispers are money in the bank. Every clue becomes a real order for that exact item at that exact port. With the Broker's Network module the intel is almost free.
3. Barter instead of buying. The partner panel shows exactly what the other fleet is missing and what it hoards. A good swap beats the market price.
4. Finished goods carry the margins. A sachet sells for 95 to 120 gold while flipping raw materials earns pocket change. Just remember the VAT.
5. Upgrade the ship early. The discount pays for itself over many deliveries, so aim for level 1 or 2 by the middle rounds.
6. Pick the fortune that matches your plan: the Charm for a buying round, Inspiration for a production round, the Loan when you are about to go under.

---

## 🏆 6. Game End & Rankings

After the final voyage (8 rounds in Easy mode, 16 in Hard), each captain receives a final rating based on **renown**, the running total of net profit from delivered orders.

A 16 round Hard voyage earns far more renown than an 8 round Easy one, so each difficulty has its own thresholds.

| Rank Title | Easy renown | Hard renown |
|:---|:---|:---|
| 👑 Sovereign of the Silk Road | ≥ 1200 | ≥ 6000 |
| 🏆 Maritime Trade Tycoon | ≥ 800 | ≥ 4000 |
| ⭐ Accomplished Merchant | ≥ 600 | ≥ 3000 |
| 👍 Competent Merchant | ≥ 400 | ≥ 2000 |
| 🌊 Novice Merchant | < 400 | < 2000 |

---

## 🛡️ 7. Troubleshooting
- **"Port 8080 already in use"**: something else has the port. Stop it, or change the port number in `server.py`.
- **"This account is already logged in on another device"**: one connection per account. Close the other tab or device first.
- **A button does nothing**: nine times out of ten you are waiting for your partner. Check "Ready n / 2" at the bottom and give them a nudge over 💬.
- **Your partner dropped**: the session is safe on the server, and they just need to log back in. Chat and trades wait until then.
- **The server restarted**: accounts survive in `users.json`, but running voyages live in memory and are gone. Start a fresh session.
- **Connection trouble over the internet**: tunnel the one port (`ngrok http 8080`) so the page and the WebSocket share a single https origin.

---

## 👤 8. Credits & License
- **Developers**: `Joe Zhou, Aaron Zhu`
- **Version**: `PortMasters 2 v1.0.0a4 preview`
- **Language Support**: English (default) and Simplified Chinese, switchable inside the game
- **License**: MIT License. Use it, change it, share it, for personal or commercial projects.
- New to the series? [PortMasters 1](https://lostinhustle.github.io/PortMasters/PortMasters_Web_Edition/PortMasters_v1.4.0) is a gentler, single player place to start.

---

## 🌟 Quick Reference
- **Launch**: `python server.py`, then open `http://localhost:8080`
- **Difficulty**: every session starts on Easy; the inviting captain can choose Hard for the full trade, and the other captain confirms it before the voyage begins
- **Core Loop**: Set Sail → Fortune → Procure → Barter → Artisans → Trade → Upkeep → Shipyard
- **Best Sellers**: Scented Sachets and Fine Brocade (mind the VAT!)
- **Sure Money**: buy whispers, and equip the Broker's Network
- **Bankruptcy Warning**: if gold cannot cover wages and upkeep at settlement, you are out (though you can spectate!)
- **Win Condition**: reach the top Sovereign rating, which is renown of 1200 or more in Easy mode and 6000 or more in Hard

---
🌊 *Fair winds and following seas, Captains!* 🏴‍☠️
