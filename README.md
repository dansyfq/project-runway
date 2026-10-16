# Runway

**How much lease you have left, and what it buys you.**

Capstone project for the AI Champions Bootcamp 2026 (Project Type 2), by Team Runway: Lynn Koh, Leong Soon Poh,
Danish Syafiq and Max How.

Runway helps HDB resale buyers understand one rule that keeps catching people out. Since May 2019, how much CPF you
can put towards a flat depends on whether its lease will last until the youngest buyer turns 95. If it won't, CPF use
and the HDB loan are both scaled down. Runway works this out for your own ages and flat, shows what a shorter lease
costs in each town you're considering, and explains the result in plain English with the official rule quoted.

## What's in the app

The interface in `runway_game/index.html` is the approved design hand-off, running full-window inside Streamlit:

| Screen | What it does |
|---|---|
| **Sign in** | Username and password, checked in Python against hashed passwords in Streamlit secrets. |
| **Setup** | Youngest buyer's age, rough CPF, first town. No names or NRIC. |
| **Map** (use case 1) | Town Safari: every HDB block, MRT lines and the flats sold in Jul–Sep 2026. Tap a diamond for the verdict, runway bar, CPF you can use and cash you need. Keep, Why?, Next flat. |
| **Shortlist** | Kept flats recalculated for your details, CSV download, and 26 town stamps with Wikimedia Commons photos. |
| **Ask** (use case 2) | Answers from 32 official documents with sources, "Why?" for a flat, chat summary, read-aloud, and document upload that suggests towns. |
| **More** | Your details, text size, About Us (with the required notice), How it works (flowcharts), Sources and credits. The `demo` account sees short versions; `reviewer` and `lecturer` see the full ones. |

Python (`runway/bridge.py`) handles sign-in, sends the map data only after sign-in, and answers questions
(`runway/rag.py` + `runway/llm.py`). The map's calculator runs in the browser and is tested against
`runway/cpf_rules.py` so both give the same numbers. The AI never calculates; an explanation with a number
the calculator didn't produce is replaced by a plain template.

## Run it locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # then add your OPENAI_API_KEY
python scripts/seed_users.py                                  # creates demo logins (see below)
streamlit run app.py
```

Without an `OPENAI_API_KEY` the app still works: calculations, charts and keyword search run as normal, and Ask
Runway shows the matching official passages instead of an AI answer.

## Logins

No usernames or passwords are stored in this repository. `scripts/seed_users.py` creates accounts from, in order:

1. the `RUNWAY_DEMO_USERS` environment variable (`name:password,name2:password2`), or
2. `demo_accounts.local.toml` (gitignored), or
3. three generated accounts with random passwords, saved to `demo_accounts.local.toml`.

It writes only salted PBKDF2 hashes to `.streamlit/secrets.toml` (also gitignored). For a deployed app, paste that
file's contents into **Streamlit Community Cloud > App settings > Secrets**. Use `--rotate` to issue new passwords.

## Deploy (Streamlit Community Cloud)

1. Push this repo to GitHub.
2. At [share.streamlit.io](https://share.streamlit.io), create an app from the repo, branch `main`, main file
   `app.py`, Python 3.12, and set the custom subdomain `runway-hdb` (app URL: https://runway-hdb.streamlit.app).
3. Paste the contents of your local `.streamlit/secrets.toml` (OpenAI key and `[auth.users]` hashes) into the app's
   Secrets.

## Project layout

```
app.py                 Streamlit host: full-window interface + message loop
runway_game/index.html the interface (from design/runway-mockup.html in the hand-off)
runway/bridge.py       sign-in, ask, why, summary messages
runway/cpf_rules.py    age-95 rule, CPF share, HDB loan limit, loan tenure (Python reference)
runway/rag.py          chunking, BM25 + embedding search, reciprocal rank fusion
runway/llm.py          prompts, question screening, number guard, OpenAI calls
runway/auth.py         password hashing and checks
runway/game_data.py    map data and town photos sent after sign-in
data/game/             towns, Jul-Sep 2026 sales, blocks, roads, MRT, amenities
data/photos/           26 town photos + credits (scripts/fetch_town_photos.py)
data/corpus/           32 official documents with source URLs
data/resale.parquet    986,090 HDB resale transactions (offline analysis)
eval/, tests/          evaluation questions and the pytest suite
```

## Checks

```bash
pytest                 # includes a check that the map's calculator matches cpf_rules.py (needs Node.js)
python eval/run_eval.py   # retrieval, calculator, decline checks (+ LLM answers if a key is set)
```

The CPF formula reproduces every official worked example: MND's May 2019 Annex B (age 25 with 55 / 65 / 75 years
left gives 70% / 90% / 100%) and CPF Board's FAQ. The lease premium reproduces the proposal's Table 1 from the data.

## Data and licences

- HDB resale flat prices, [data.gov.sg](https://data.gov.sg/collections/189/view), Singapore Open Data Licence.
  Rebuild `data/resale.parquet` with `python scripts/build_dataset.py <folder with the 5 CSVs>`.
- Rules documents: public pages from CPF Board, HDB, MND, MOM, IRAS and CEA, retrieved 16 Oct 2026. Each file in
  `data/corpus/` records its source URL.
