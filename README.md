**An application focused on analyzing the trading value of Riven Mods using data from Warframe Market, a fan-run Warframe trading platform. The project evaluates Riven parameters to estimate market value and compare the cost-effectiveness of purchasing unveiled Rivens versus gambling on veiled Rivens, including high-value “god rolls.”**

---

### Terminology 
*(Warframe is not as mainstream as games like Fortnite, so some terms may be unfamiliar.)*

### 1. Riven Mod

A **Riven Mod** is a special type of weapon modification in *Warframe* that becomes unique to a single weapon once revealed.
Each Riven can roll a combination of **positive and negative stats**, such as increased critical damage or reduced zoom.

Riven Mods originate as **veiled Rivens** and must have their challenge completed before the weapon it applies to is revealed.
Before unveiling, the exact weapon is unknown, **only the weapon class is shown.**


**Riven classes include:**

- Rifle
- Shotgun
- Pistol
- Melee
- Archgun
- Kitgun
- Zaw
- Companion Weapon

---

### 2. Riven Mod (Unveiled)

An **unveiled Riven Mod** is a Riven that has had it's challenge completed and is now bound to a specific weapon (e.g., Torid Riven Mod).

Once unveiled:

The weapon is permanently revealed

The Riven’s stats can be rerolled using **Kuva**

**Kuva** is an in-game resource used to reroll a Riven Mod's randomized attributes

The Riven can be traded (subject to Mastery Rank requirements)

| Veiled Riven Mod| Unveiled Riven Mod |
|-----------------|--------------------|
| ![Veiled Riven Mod](images/riven_veiled.png) | ![Unveiled Riven Mod](images/riven_unveiled.png) |

*Images © Digital Extremes Ltd. Used for educational and illustrative purposes.*

---

### Instructions

#### Prerequisites
- **Python 3.14** — [python.org](https://www.python.org/downloads/)
- **Node.js** (v18+) — [nodejs.org](https://nodejs.org/)

#### 1. Start the Backend
```bash
cd backend
pip install flask requests
python main.py
```
The Flask API will start on `http://localhost:5000`.

#### 2. Start the Frontend
```bash
cd frontend
npm install
npm run dev
```
The Vite dev server will start on `http://localhost:8080` and proxy API requests to the backend.

#### 3. Use the App
Open `http://localhost:8080` in your browser, select your filters, and search for Riven auctions.

