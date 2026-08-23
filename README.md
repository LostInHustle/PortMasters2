# ⚓ PortMasters 2

> 🌐 **Bilingual Documentation** | [🇨🇳 查看中文文档](README_zh-CN.md)

---

## 📖 1. Overview

Welcome back to the Maritime Silk Road! PortMasters 2 takes the series online. Two to five captains sail one shared voyage, always on the same round and the same phase. You compete for renown, yet you also barter goods, gold and information with each other along the way. Draw a fortune from the Navigator's Compass, buy rumors from the brokers, fit your flagship with modules, and keep enough cash on hand for wages, upkeep and taxes through every voyage (8 rounds on Easy, 12 on Standard, 16 on Hard). The richer reputation wins.

What's new since PortMasters 1:

- 🌐 Online play for two to five captains, with accounts, a lobby, invitations, open rooms, chat and reconnection.
- 🤝 A barter phase where everyone in the room trades goods and gold freely. An offer can go out openly to the whole room, or be addressed to one captain, in which case only that captain sees it and only that captain can take it.
- 🧭 Fortunes: each round the Navigator's Compass deals every captain a private hand of 4 random buffs, and you lock in one.
- 🗣️ The Broker's Whisper: pay for intel, and every clue turns into a guaranteed order later that round.
- 🔧 Ship modules: draft and install up to 3 of them, from the Smuggler's Hold to the Overdrive Engine.
- 👑 Emperor Mandates: at set milestones of the voyage an imperial commission appears in the Trade phase, a large golden order worth far more than an ordinary one. The last one of the voyage is marked out as the closing commission.
- 👀 A spectator window, so a bankrupt captain can still watch the other captains finish the voyage. You can also open it on any captain at any time from the roster on the right, which makes it easy to see what a trading partner is short of before you make them an offer.
- 🔔 Notices for everything that happens to your fleet, each one with its own close button, plus a clear all control when several arrive at once.
- 🌍 The whole interface is available in English (the default) and Simplified Chinese. Switch any time with the 🌐 button.
- ⚖️ Three difficulty modes that form a ladder. Easy (8 rounds) keeps the voyage on the founding set of goods for a gentler game; Standard (12 rounds) opens the full trade at a brisker pace with no corrupt brokers; Hard (16 rounds) is the full challenge with the corrupt broker hazard on. Whoever sends the invitation or opens the room picks the level, and every session starts on Easy unless it is changed.
- 🗺️ The Silk Road Charter: the trade network expands in two waves, the "New Maritime Edict" and then "Ten Thousand Kingdoms Trade", adding 4 new resources, 4 new products, 4 new artisan types, 4 new ports (9 total), 6 new Fortunes, 6 new ship modules and 4 new Trade Winds (8 total). The waves arrive on Standard (Rounds 4 and 8) and Hard (Rounds 6 and 10); on Easy the voyage stays on the founding set the whole way through and these waves never arrive.

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
5. Invite someone from the lobby, or open a room for two to five captains and wait for them to join. Choose the difficulty for the session (Easy by default), and once it is accepted the shared voyage begins. 🌊

> 💡 The whole game is one Python file and one HTML file. There is nothing to build and no bundler in the way, which is exactly why this edition is nice to poke at.

### ⚙️ Settings the server reads from the environment

Both are optional. Leave them unset and everything behaves exactly as it always has.

| Variable          | What it does                                                                                |
| :---------------- | :------------------------------------------------------------------------------------------ |
| `PORT`            | The port to listen on. Defaults to 8080. Hosting platforms assign this, so let them set it. |
| `USERS_FILE_PATH` | Where accounts are stored. Defaults to a `users.json` sitting next to `server.py`.          |

---

## ☁️ 3. Playing Over the Internet

### 🔌 Option A: a tunnel, for a quick game tonight

The page and the WebSocket share a single port, so one tunnel carries the whole game with https and wss handled for you:

```bash
ngrok http 8080
```

Send the address it prints to your friends. Nothing else to configure. The tunnel closes when you close it, which makes this the right choice for a one off session.

### 🚂 Option B: Railway, for something that stays up

`railway.json` tells Railway everything it needs, so a deploy is mostly clicking through:

1. Push the repository to GitHub.
2. In Railway, create a project and pick **Deploy from GitHub repo**, then choose that repository.
3. Railway reads `railway.json`, installs `websockets` from `requirements.txt`, and starts `server.py`. It assigns a port through the `PORT` variable, which the server picks up on its own.
4. Under **Settings**, open **Networking** and choose **Generate Domain**. That public address is the game. Share it and you are done.

Because both the page and the WebSocket live on that one domain, there is no second address to configure anywhere and no mixed content to work around.

**Keeping accounts between deploys.** Railway rebuilds the container on every deploy and wipes its filesystem with it, so an accounts file sitting next to the script would take every registered captain with it. To keep them:

1. Add a **Volume** to the service and mount it at `/data`.
2. Add a variable `USERS_FILE_PATH` with the value `/data/users.json`.

Accounts then live on the volume and survive redeploys. Voyages in progress are held in memory by design and always end when the process restarts, so plan deploys for when nobody is mid voyage.

---

## 🎮 4. Gameplay Mechanics

A game lasts **8 voyages** (rounds) on Easy, **12** on Standard or **16** on Hard, and each voyage runs through **8 phases**. No phase advances until every captain confirms.

| Phase           | Description                                                                                                                                                                                                                     |
| :-------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **⚓ Set Sail** | Confirm the start of the round. From round 2 on, this page also recaps how the previous round went.                                                                                                                             |
| **🧭 Fortune**  | The compass deals you 4 of the 8 fortunes at random. Every captain gets a different hand. Lock one; it lasts this round only.                                                                                                   |
| **🛒 Procure**  | Buy materials and goods from the supply cards (5 on Easy; on Standard and Hard the hand grows to 8 when Tier 1 opens and 11 when Tier 2 opens). The Broker's Whisper panel sits at the top and sells intel about coming demand. |
| **🤝 Barter**   | Trade with the room. Post an offer like "I give this for that" and it settles the moment someone accepts. Send it to everyone, or address it to one captain so only they can see and take it.                                   |
| **👥 Artisans** | Hire or dismiss artisans and hand out production tasks. Materials are consumed right away.                                                                                                                                      |
| **📦 Trade**    | Deliver port orders from your stock. Clues you bought show up here as guaranteed orders marked 🗣️, and on milestone rounds an 👑 Emperor Mandate appears, worth several ordinary orders.                                        |
| **🔧 Upkeep**   | Production arrives and wages are paid on their own. Then you pay 15 gold of fleet upkeep. If you cannot, your fleet goes bankrupt.                                                                                              |
| **🚢 Shipyard** | Upgrade the ship if you like (levels 0 to 3), draft modules, then end the voyage.                                                                                                                                               |

### ⚖️ Difficulty Modes

The difficulties form a ladder, and the game always starts on Easy unless someone chooses otherwise.

- **🌱 Easy** is the shorter 8 round voyage and keeps the whole game on the founding set of goods. You trade the three starting raw materials of Hemp Cloth, Silk and Tea, craft the four starter products, and hire from the first three artisan guilds, together with only the fortunes, ship modules, ports and trade winds that belong to them. The board never grows crowded, so there is plenty of room to learn the rhythm of each round.
- **⚖️ Standard** is the 12 round middle rung and opens the full trade, but with no corrupt brokers. The Silk Road Charter brings in Tier 1 at Round 4 and Tier 2 at Round 8, so you get every good, port and artisan at a brisker pace than Hard, with pirate raids that bite a little harder than Easy. It suits captains who know the basics and want a real challenge without committing to the long Hard voyage.
- **🔥 Hard** is the longer 16 round voyage and opens the full trade. It plays exactly like the Silk Road Charter progression described below, bringing in the remaining raw materials, products, foreign ports, specialist artisans and the richer fortunes, modules and trade winds as the rounds go on. The first five rounds stay as relaxed as Easy mode, then there is far more to manage and the competition for cargo space and coin is much fiercer. Pirate raids and escort fees both scale with your wealth, and on the hard route some brokers are corrupt and secretly tip off pirates when you buy a whisper, raising your raid chance and making the escort call at Upkeep a real gamble.

The difficulty is settled before a voyage begins. Whoever sends the invitation or opens the room chooses the level, and an invited captain sees a short explanation of what it changes and confirms it before the session starts. Everyone therefore always plays the same voyage at the same difficulty, and a restart keeps that difficulty.

### 🗺️ When the two expansion waves arrive

Anything marked _(New Maritime Edict)_ or _(Ten Thousand Kingdoms Trade)_ below joins the game when that wave lands, and the two waves land at different points depending on the difficulty:

| Difficulty  | New Maritime Edict | Ten Thousand Kingdoms Trade |
| :---------- | :----------------- | :-------------------------- |
| 🌱 Easy     | never              | never                       |
| ⚖️ Standard | Round 4            | Round 8                     |
| 🔥 Hard     | Round 6            | Round 10                    |

On Easy the voyage stays on the founding set from the first round to the last, so nothing marked below ever appears.

### 📦 Resources

Raw materials:

- `Hemp Cloth` 🧶, the everyday fabric for simple clothes.
- `Silk` 👘, the fine stuff behind the luxury goods.
- `Tea Leaves` 🍵, what gives a sachet its scent.
- `Porcelain Clay` 🧱, the fine clay behind celadon ware _(New Maritime Edict)_.
- `Copper Ore` ⛏️, hammered into mirrors and fittings _(New Maritime Edict)_.
- `Spices` 🌶️, the fragrant cargo of the southern seas _(Ten Thousand Kingdoms Trade)_.
- `Pearls` 🦪, lustrous treasures from southern waters _(Ten Thousand Kingdoms Trade)_.

Finished goods:

- `Hemp Garb` 👔 takes 2 Hemp Cloth (Weaver). Base value 15, sells around 30 to 42.
- `Cloth Tunic` 👕 takes 2 Hemp Cloth and 1 Silk (Weaver). Base value 35, sells around 50 to 65.
- `Fine Brocade` 👗 takes 3 Silk (Master Weaver only). Base value 60, sells around 70 to 90.
- `Scented Sachet` 🌸 takes 1 Silk and 2 Tea (Sachet Maker only). Base value 80, sells around 95 to 120.
- `Bronze Mirror` 🪞 takes 3 Copper Ore (Coppersmith). Base value 45, sells around 55 to 72 _(New Maritime Edict)_.
- `Celadon Porcelain` 🏺 takes 3 Porcelain Clay (Potter). Base value 65, sells around 78 to 100 _(New Maritime Edict)_.
- `Foreign Perfume Oil` 🧴 takes 2 Spices and 1 Silk (Perfumer only). Base value 85, sells around 100 to 130 _(Ten Thousand Kingdoms Trade)_.
- `Pearl Necklace` 📿 takes 2 Pearls and 1 Silk (Jeweler only). Base value 105, sells around 125 to 160 _(Ten Thousand Kingdoms Trade)_.

### 👷 Artisan System

- **Weavers** 👩‍🔧 craft Hemp Garb and Cloth Tunics. Wage: 8 gold a round.
- **Master Weavers** 👩‍🎨 also craft Fine Brocade. Wage: 12 gold a round.
- **Sachet Makers** 🌸 are the only ones who can make Sachets. Wage: 20 gold a round.
- **Coppersmiths** 🪞 craft Bronze Mirrors. Wage: 12 gold a round _(New Maritime Edict)_.
- **Potters** 🏺 craft Celadon Porcelain. Wage: 14 gold a round _(New Maritime Edict)_.
- **Perfumers** 🧴 are the only ones who can make Foreign Perfume Oil. Wage: 18 gold a round _(Ten Thousand Kingdoms Trade)_.
- **Jewelers** 📿 are the only ones who can make Pearl Necklaces. Wage: 24 gold a round _(Ten Thousand Kingdoms Trade)_.
- Once an artisan has produced 2 items in total, they become **skilled** ⭐ and make 2 per task at the same wage.
- Hiring costs nothing up front; wages come out automatically at Upkeep. Letting an idle artisan go costs one wage in severance.

### 🧭 Fortunes (a private hand of 4 each round, pick 1)

| Fortune                                                 | Effect                                                                |
| :------------------------------------------------------ | :-------------------------------------------------------------------- |
| 🌬️ Silk Road Tailwind                                   | Shipping for silk and finished goods is halved this round             |
| 🌊 Favorable Tides                                      | Base shipping costs 4 gold less                                       |
| ✨ Merchant's Charm                                     | Everything you buy costs about 15% less                               |
| 🔨 Artisan's Inspiration                                | Every worker makes one extra item                                     |
| 💰 Emergency Loan                                       | 40 gold, right now                                                    |
| 📜 Tax Exemption                                        | Income tax falls to 5%                                                |
| 🧶 Hemp Monopoly                                        | Hemp Cloth costs 2 gold less per unit                                 |
| 🎓 Apprentice Legacy                                    | This round's artisan wages are halved                                 |
| 🔮 Farsight _(New Maritime Edict)_                      | Gain 1 free Broker's Whisper clue this round                          |
| 🏮 Porcelain & Bronze Consortium _(New Maritime Edict)_ | Celadon Porcelain and Bronze Mirror orders pay 15% more this round    |
| 🧾 Frontier Tariff Relief _(New Maritime Edict)_        | VAT on finished goods deliveries is halved this round                 |
| 💎 Treasures from Afar _(Ten Thousand Kingdoms Trade)_  | Foreign Perfume Oil and Pearl Necklace orders pay 15% more this round |
| 🛡️ Deep Sea Escort Pact _(Ten Thousand Kingdoms Trade)_ | Escort hiring costs half price and pirate risk is halved this round   |
| 🛍️ Merchants Converge _(Ten Thousand Kingdoms Trade)_   | 1 extra order appears in the Trade phase this round                   |

### 🔧 Ship Modules (draft 3, install 1; slots equal your ship level)

| Module                                                             | Effect                                                                                                    |
| :----------------------------------------------------------------- | :-------------------------------------------------------------------------------------------------------- |
| 🏴‍☠️ Smuggler's Hold                                                 | Purchases cost 15% less, but income tax rises 20%                                                         |
| 🏗️ Bulk Rigging                                                    | Each item ships 1 gold cheaper; ship upgrades cost 15 gold more                                           |
| 🛠️ Artisan's Workshop                                              | Workers make one extra item; wages rise 20%                                                               |
| 📒 Hidden Ledger                                                   | Income tax is figured on profit after VAT, but each delivery carries a 15% chance of a 20 gold audit fine |
| 🐍 Silk Monopoly                                                   | Silk ships for free, and silk product orders pay 20% more                                                 |
| 🕵️ Broker's Network                                                | Whispers cost just 2 gold and reveal 2 clues at a time                                                    |
| ♻️ Salvage Crane                                                   | A 30% chance your shipping fee comes back on delivery                                                     |
| ⚡ Overdrive Engine                                                | Shipping costs 5 gold less; upkeep costs 10 gold more                                                     |
| 🎫 Trade Bureau Token _(New Maritime Edict)_                       | Orders for new trade route goods (Porcelain Clay, Copper Ore and their products) pay 10% more             |
| 🔥 Kiln Cellar _(New Maritime Edict)_                              | Porcelain Clay and Copper Ore purchase price −2 gold per unit                                             |
| 📡 Ocean Going Interpreter _(New Maritime Edict)_                  | Each Broker's Whisper purchase reveals 1 extra clue at no added cost                                      |
| 🪪 Foreign Quarter Guild Pass _(Ten Thousand Kingdoms Trade)_      | Spices and Pearls purchase price −3 gold per unit                                                         |
| 🧿 Persian Dome Compass _(Ten Thousand Kingdoms Trade)_            | Pirate risk reduced by 30%                                                                                |
| ⛵ Fleet of Ten Thousand Treasures _(Ten Thousand Kingdoms Trade)_ | Shipping for Foreign Perfume Oil and Pearl Necklace is 3 gold cheaper per item                            |

### 💰 Taxes & Finance

- **VAT**: about 5% of the profit on finished goods, taken automatically when you deliver.
- **Income tax**: about 10% of the round's net profit (5% under a Tax Exemption), taken at the end of the round.
- **Shipping**: 2 gold per item, less 5 gold for every ship level and any fortune discount, and never below 5 gold on that much alone. Modules go further and can take it under that floor, all the way to nothing: Bulk Rigging shaves a gold off every item, the Overdrive Engine takes 5 off the total, and Silk Monopoly ships silk for free. The Trade board shows the exact figure your fleet will be charged for each order, with every one of those already counted, so the number you read is the number you pay.
- **Upkeep**: a flat 15 gold a round (some modules raise it), paid by hand during the Upkeep phase. Miss it and your game is over.

### 🌐 Multiplayer

- **Accounts**: a username and a password. Passwords are stored salted and hashed in `users.json`.
- **Invitations and rooms**: invitations go out one per minute from the lobby and expire after 60 seconds; alternatively you can open a room for two to five captains that others join freely. Either way the difficulty is chosen up front, and an invited captain confirms it in the invitation window before the voyage starts.
- **Staying in sync**: every captain shares the round and the phase. The "Ready n / N" chip shows how many have confirmed. A bankrupt player counts as ready and never holds the others up.
- **Barter**: an offer is open to the room by default and anyone but its author can take it. Address it to one captain instead and only that captain sees it, so a deal you have already talked through in chat cannot be sniped by a third party.
- **Bankruptcy and spectating**: a bankrupt captain stays on the settlement page and can open the live 👀 spectator window to watch any other captain play on. The same window opens on any captain at any time by clicking them in the roster on the right, so you can size up a trading partner before making an offer. It updates live and never interrupts what you were reading.
- **Reconnection**: sessions live on the server, and a successful login leaves a token in the browser, so refreshing the page or coming back later puts you straight back where you were without retyping a password. A voyage is only recycled once every captain has been offline for a grace period.
- **Restart**: once every game has ended, any captain can reset the table for a new run.

---

## ⌨️ 5. Controls

### ⚡ Keyboard Shortcuts

| Key     | Action                                             |
| :------ | :------------------------------------------------- |
| `F1`    | Open the game manual                               |
| `Esc`   | Close dialogs, the spectator window, or chat       |
| `Enter` | Send a chat message (while typing in the chat box) |

### 🖱️ Mouse Usage

- Click buttons to act: buy, trade, hire, upgrade, ready up.
- The 🌐 button (in the header, on the login page, or in the lobby) switches between English and 中文 whenever you like.
- Hover over underlined labels for an explanation. Panels scroll when their content runs long.

---

## 💡 6. Strategy Tips

1. Mind your cash before anything else. Wages and upkeep come due every single round, and the "Due This Round" box on the left does the math for you.
2. Whispers are money in the bank. Every clue becomes a real order for that exact item at that exact port. With the Broker's Network module the intel is almost free.
3. Barter instead of buying. The roster panel shows exactly what each other fleet is missing and what it hoards. A good swap beats the market price.
4. Finished goods carry the margins. A sachet sells for 95 to 120 gold while flipping raw materials earns pocket change. Just remember the VAT.
5. Upgrade the ship early. The discount pays for itself over many deliveries, so aim for level 1 or 2 by the middle rounds.
6. Pick the fortune that matches your plan: the Charm for a buying round, Inspiration for a production round, the Loan when you are about to go under.

---

## 🏆 7. Game End & Rankings

After the final voyage (8 rounds on Easy, 12 on Standard, 16 on Hard), each captain receives a final rating based on **renown**, the running total of net profit from delivered orders.

A longer voyage with richer goods earns far more renown, so each difficulty has its own thresholds.

| Rank Title                    | Easy renown | Standard renown | Hard renown |
| :---------------------------- | :---------- | :-------------- | :---------- |
| 👑 Sovereign of the Silk Road | ≥ 1200      | ≥ 3000          | ≥ 6000      |
| 🏆 Maritime Trade Tycoon      | ≥ 800       | ≥ 2000          | ≥ 4000      |
| ⭐ Accomplished Merchant      | ≥ 600       | ≥ 1500          | ≥ 3000      |
| 👍 Competent Merchant         | ≥ 400       | ≥ 1000          | ≥ 2000      |
| 🌊 Novice Merchant            | < 400       | < 1000          | < 2000      |

---

## 🛡️ 8. Troubleshooting

- **"Port 8080 already in use"**: something else has the port. Stop it, or start the server on another one with `PORT=8090 python server.py`.
- **"This account is already logged in on another device"**: one connection per account. Close the other tab or device first.
- **A button does nothing**: nine times out of ten you are waiting for another captain. Check "Ready n / N" at the bottom and give them a nudge over 💬.
- **A captain dropped**: the session is safe on the server, and they just need to log back in. Chat and trades wait until then.
- **The server restarted**: accounts survive in `users.json`, but running voyages live in memory and are gone. Start a fresh session.
- **Connection trouble over the internet**: the page and the WebSocket have to share one https origin. A tunnel over the single port (`ngrok http 8080`) does that, and so does a Railway deploy, which gives you one domain serving both.
- **Accounts vanished after a deploy**: the host wiped the container filesystem. Mount a volume and point `USERS_FILE_PATH` at a file on it, as described in the Railway section above.

---

## 👤 9. Credits & License

- **Developers**: `Joe Zhou, Aaron Zhu`
- **Version**: `PortMasters 2 v1.0.0rc1 preview`
- **Files**: `server.py` holds the whole server, `PortMasters_online.html` holds the whole client, and `railway.json` describes the deploy. That is the entire project.
- **Language Support**: English (default) and Simplified Chinese, switchable inside the game
- **License**: MIT License. Use it, change it, share it, for personal or commercial projects.
- New to the series? [PortMasters 1](https://lostinhustle.github.io/PortMasters/PortMasters_Web_Edition/PortMasters_v1.4.0) is a gentler, single player place to start.

---

## 🌟 Quick Reference

- **Launch**: `python server.py`, then open `http://localhost:8080`
- **Put it online**: `ngrok http 8080` for tonight, or deploy to Railway with the included `railway.json` for something that stays up
- **Difficulty**: every session starts on Easy; whoever sends the invitation or opens the room can step up to Standard or Hard for the full trade, and an invited captain confirms it before the voyage begins
- **Core Loop**: Set Sail → Fortune → Procure → Barter → Artisans → Trade → Upkeep → Shipyard
- **Best Sellers**: Scented Sachets and Fine Brocade (mind the VAT!)
- **Sure Money**: buy whispers, and equip the Broker's Network
- **Bankruptcy Warning**: if gold cannot cover wages and upkeep at settlement, you are out (though you can spectate!)
- **Win Condition**: reach the top Sovereign rating, which is renown of 1200+ on Easy, 3000+ on Standard, or 6000+ on Hard

---

🌊 _Fair winds and following seas, Captains!_ 🏴‍☠️
