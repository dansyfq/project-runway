# Runway

**How much lease you have left, and what it buys you.**

Capstone project for the AI Champions Bootcamp 2026 (Project Type 2), by Team Runway: Lynn Koh, Leong Soon Poh,
Danish Syafiq and Max How.

Runway helps HDB resale buyers understand one rule that keeps catching people out. Since May 2019, how much CPF you
can put towards a flat depends on whether its lease will last until the youngest buyer turns 95. If it won't, CPF use
and the HDB loan are both scaled down. Runway works this out for your own ages and flat, shows what a shorter lease
costs in each town you're considering, and explains the result in plain English with the official rule quoted.

## What's in the app

| Page | What it does |
|---|---|
| **Map** (use case 1) | Town Safari: every flat sold in a town in Jul–Sep 2026 on a OneMap base map, coloured by how much CPF the buyer could use. Tap one for the verdict card, runway bar, CPF you can use, cash you need and more numbers. |
| **Shortlist** | Kept flats recalculated for your details, saved as a CSV file, and town stamps. |
| **Ask** (use case 2) | RAG assistant over 32 official CPF Board, HDB, MND/MOM, IRAS and CEA documents. Cites sources, sums up the chat, declines advice and prompt-injection attempts. |
| **Your details** | Youngest buyer's age, other buyer's age, rough CPF and first town. No names or NRIC. |
| **About Us** | Notice (required disclaimer), scope, objectives, features, data sources, credits, team. |
| **How it works** | Data flow, one flowchart per use case, lease effect by town, test results, data caveats. |

The LLM explains; it never calculates. All figures come from `runway/cpf_rules.py` and `runway/lease_data.py`.
Explanations containing a number the code didn't produce are thrown away and replaced by a plain template.

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
app.py                 entry point: login gate and page navigation
app_pages/             the five pages
runway/cpf_rules.py    age-95 rule, CPF share, HDB loan limit, loan tenure
runway/lease_data.py   lease premium per town (log-linear least squares)
runway/rag.py          chunking, BM25 + embedding search, reciprocal rank fusion
runway/llm.py          prompts, question screening, number guard, OpenAI calls
runway/auth.py         password hashing and checks
scripts/               build_dataset.py, to_corpus.py, seed_users.py
data/resale.parquet    986,090 HDB resale transactions (1990 to Sep 2026)
data/corpus/           32 official documents with source URLs
eval/                  28 test questions and the evaluation script
tests/                 pytest suite (rules, data, retrieval, LLM guards, auth, app smoke tests)
```

## Checks

```bash
pytest                 # 66 tests
python eval/run_eval.py   # retrieval, calculator, decline checks (+ LLM answers if a key is set)
```

The CPF formula reproduces every official worked example: MND's May 2019 Annex B (age 25 with 55 / 65 / 75 years
left gives 70% / 90% / 100%) and CPF Board's FAQ. The lease premium reproduces the proposal's Table 1 from the data.

## Data and licences

- HDB resale flat prices, [data.gov.sg](https://data.gov.sg/collections/189/view), Singapore Open Data Licence.
  Rebuild `data/resale.parquet` with `python scripts/build_dataset.py <folder with the 5 CSVs>`.
- Rules documents: public pages from CPF Board, HDB, MND, MOM, IRAS and CEA, retrieved 16 Oct 2026. Each file in
  `data/corpus/` records its source URL.
