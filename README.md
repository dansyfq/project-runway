# Runway

**How much lease you have left, and what it buys you.**

Capstone project for the AI Champions Bootcamp 2026 (Project Type 2), by Team Runway: Lynn Koh, Leong Soon Poh,
Danish Syafiq and Max How.

Runway helps HDB resale buyers understand one rule that keeps catching people out. Since May 2019, how much CPF you
can put towards a flat depends on whether its lease will last until the youngest buyer turns 95. If it won't, CPF use
and the HDB loan are both scaled down. Runway works this out for your own ages and flat, shows what a shorter lease
costs in each town you're considering, and explains the result in plain English with the official rule quoted.

Runway is a Streamlit app: `app.py` is the Streamlit host, and the whole interface (`runway_game/index.html`) is a
custom Streamlit component that it runs full-window and exchanges messages with.

## What's in the app

The interface in `runway_game/index.html` is the approved design hand-off, running full-window inside Streamlit. One left navigation (Home, Map, Shortlist, Trends, Ask, More, Log in) is on every screen: a fixed sidebar on wide screens, a drawer behind the menu button on phones. Every screen has its own address (`/`, `/map`, `/shortlist`, `/trends`, `/ask`, `/more`, and `/details`, `/text-size`, `/about`, `/methodology` (the old `/how-it-works` still opens it), `/sources`, `/faq`, `/timeline`, `/case-study`, `/lease-explorer`, `/insights`, `/privacy`, `/terms` under More), so reloads, shared links and Back/Forward work; addresses carry page names only, never anything you type. Every inner page has a breadcrumb back to Home, the navigation has a site search (pages, FAQ questions and towns, in the browser only), and an unknown address opens Home with a "Page not found" notice.

| Screen | What it does |
|---|---|
| **Home page** | Landing page, Ask Runway first: a question box (**Ask Runway** asks it on the Ask page) beside one worked example that quotes the official document, the age-95 rule calculator, what a shorter lease costs by town, and the required notice. Green and beige palette, the device's system font (Anton only for the RUNWAY wordmark), as set out in `DESIGN.md`. **Log in** in the navigation opens the login (admin or user) over the page. |
| **Setup** | Youngest buyer's age, rough CPF, first town. No names or NRIC. A labelled Singpass demo (made-up people, not connected to Singpass) shows how these could be filled in for you; see `docs/singpass-integration.md`. |
| **Map** (use case 1) | Town map: every HDB block, MRT lines and the flats sold in Jul–Sep 2026. Tap a diamond for the verdict, runway bar, CPF you can use and cash you need. Keep, Why?, Next flat. **Find by budget** ranks towns and flat types by how many recent sales your cash and CPF cover; **Filters** narrow the diamonds by flat type, price, cash and CPF verdict. |
| **Flat result** | Opened from a diamond. A price check against similar recent sales (same town and flat type, lease within 5 years, last 12 months, from `runway/price_check.py`); Buyer's Stamp Duty, HDB fees and the grants you may get once you add income and household details; an HDB loan beside a bank loan at a rate you type, with the 30% income cap; and what the lease means for whoever buys from you in 5 to 20 years. Every figure names its document in `data/corpus/`. |
| **Shortlist** | Kept flats recalculated for your details, two or three of them side by side in a table, a printable summary, CSV download, and a Towns checked grid of the 26 towns with Wikimedia Commons photos. |
| **Trends** | Public price charts, no login or setup needed. Compare median resale price or price per sqm by town since 1990 (up to 5 places, by flat type and period), and what remaining lease does to price. Numbers are built from `data/resale.parquet` by `runway/trends.py`; each chart has a table view. |
| **Ask** (use case 2) | Answers from 32 official documents with sources, "Why?" for a flat, chat summary, **Download this chat** (a text file with the date, the notice, each answer's sources and the summary, made in the browser), a **Your questions** list that jumps to each answer, read-aloud, and document upload that suggests towns. A question that gives an age, a lease or a price is worked out with Runway's calculator tools (`runway/agent.py`: lease check, HDB loan length, Buyer's Stamp Duty), which Claude calls instead of doing sums; every figure in the answer must come from the passages, the question or a tool result. Answers, read-aloud and voice input in English, Chinese, Malay or Tamil (official quotes and figures stay in English; the rest of the interface is English). Helpful / Not helpful under each AI answer: a vote writes one line to the server log and to `data/feedback.jsonl` where the disk is writable, with the question kept only if it has no personal details. |
| **Lease explorer** (use case 3, `/lease-explorer`) | CPF use for every age of the youngest buyer and every lease left, as one chart, with sliders for your own case: CPF share, HDB loan limit and the lease needed for full CPF. Worked out in the browser (tested against `runway/cpf_rules.py`); "Ask Runway about this flat" sends the case to Ask. |
| **Insights** (admin only, `/insights`) | Answer votes and the questions marked Not helpful, the latest eval run including retrieval by search mode, every document and its passage count, and AI calls against the hourly cap (`runway/insights.py`). The server checks the admin role again, so a `user` or guest is refused. |
| **More** | Your details (with a reset), text size, About Us (with the required notice), Methodology (the Ask pipeline, the rules, a requirements checklist and the flowcharts; it was How it works), Sources and credits, an FAQ whose answers each cite one document in `data/corpus/`, a buying timeline (`/timeline`) from the HFE letter to completion with a source for every step, a case study worked out live from the Trends data, the Lease explorer, the Privacy Policy and the Terms; for `admin`, the admin tools and Insights. Visitors browse as guests and see short versions; logging in as `user` or `admin` shows the full About Us and Methodology. |

Python (`runway/bridge.py`) checks logins and roles, sends the map data after the home page loads, and answers questions
(`runway/rag.py` + `runway/llm.py`). The map's calculator runs in the browser and is tested against
`runway/cpf_rules.py` so both give the same numbers. The AI never calculates; an explanation with a number
the calculator didn't produce is replaced by a plain template.

## Run it locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # then add your ANTHROPIC_API_KEY
python scripts/seed_users.py                                  # optional: more logins (see below)
streamlit run app.py
```

Without an `ANTHROPIC_API_KEY` the app still works: calculations, charts and document search run as normal, and Ask
Runway shows the matching official passages instead of an AI answer.

Ask Runway uses Claude through the Anthropic API: `claude-sonnet-5-5` by default, or the model named in
`ANTHROPIC_MODEL` (for example `claude-haiku-5-5`, which costs far less per answer). The key comes from
[console.anthropic.com](https://console.anthropic.com); a Claude subscription does not include one. Documents are found by
hybrid search: BM25 keywords and a FAISS vector store (cosine similarity over `BAAI/bge-small-en-v1.5` embeddings, run
locally with fastembed), merged by weighted reciprocal rank fusion (k = 60). A question in Chinese, Malay or Tamil is put
into English by the model first. `python eval/run_eval.py` compares the three search modes on the same questions
(keywords / vectors / hybrid, right document first: 15 / 18 / 17 of 19; in the top 3: 18 / 19 / 19). The pipeline is
built on LangChain's core interfaces (`runway/chain.py`): the search is a LangChain retriever returning Documents, and
every prompt is a `ChatPromptTemplate`; the model call stays on the Anthropic SDK for its tool loop and beta options.

The FAISS index for the committed documents is in `data/index/` (about 0.5 MB; rebuild it with
`python -m runway.vector` after changing `data/corpus/`). An uploaded or changed document is embedded when the
search is rebuilt and saved to `data/runtime/index/`. The embedding model (about 65 MB) downloads from Hugging Face on
the first start and adds about 180 MB of memory. Until it is ready, or if it can't load, the vectors fall back to TF-IDF term
vectors, and setting `VECTOR_BACKEND = "tfidf"` (Secrets or environment) keeps them there and skips the model.

## Accounts and roles

Anyone can use Runway as a guest, without an account. Two accounts are built in:

| Account | Role | What it can do |
|---|---|---|
| `admin` | admin | Everything `user` can, plus the admin tools: upload or replace Ask documents; edit About Us, Methodology, the Privacy Policy, Terms and the FAQ; and the Insights page (`/insights`) |
| `user` | user | Ask questions and use everything a guest can, and read the full About Us and Methodology. No admin tools, and no Insights |

Only salted PBKDF2 hashes (600,000 rounds) of their passwords are in the repo, in `BUILTIN_USERS` in
`runway/auth.py`. The passwords are long random strings handed over separately; they are not in the repo.
The server keeps the role in the session at login and checks it for every admin message (`runway/bridge.py`), so
`user` is refused an upload, an edit or the Insights data even if the browser sends the message. Five wrong passwords pause a username for a minute.

Accounts in Secrets (`[auth.users]`) work as before and win over a built-in account of the same name:

```toml
BUILTIN_ACCOUNTS = "admin,user"   # the default; "user" turns the built-in admin off, "" turns both off
[auth.users]
reviewer = "pbkdf2_sha256$..."                          # just a hash: admin (for admin or user, that account's role)
alice = { hash = "pbkdf2_sha256$...", role = "user" }   # role "admin" or "user"
```

So the existing `reviewer` login keeps the admin tools, and a hash under `admin` gives the built-in admin a new
password. `scripts/seed_users.py` writes the hashes; it takes the accounts from, in order:

1. the `RUNWAY_DEMO_USERS` environment variable (`name:password`), or
2. `demo_accounts.local.toml` (gitignored), or
3. a generated `reviewer` account with a random password, saved to `demo_accounts.local.toml`.

It writes only a salted PBKDF2 hash to `.streamlit/secrets.toml` (also gitignored). For a deployed app, paste that
file's contents into **Streamlit Community Cloud > App settings > Secrets**. Use `--rotate` for a new password.

### Admin tools

A logged-in account sees a green **Admin view** or **User view** pill on every screen. Admin also gets an
**Admin tools** group in More:

- **Upload Ask documents**: a PDF, web page (HTML), Markdown or text file (up to 6 MB) becomes a document in
  `data/corpus/`, added or replacing one, and Ask Runway searches it from the next question.
- **Edit pages**: About Us and Methodology (full and public versions), Privacy Policy and Terms have an
  *Edit this page* button; the FAQ has an editor to add, change or remove questions. *Restore* puts back the built text.
- **Insights** (`/insights`): answer votes and the questions marked Not helpful, the latest eval run, every document
  and its passage count, and AI calls this hour (`runway/insights.py`). A guest or `user` who opens it is asked to log in as admin.

The server checks the admin role for every change (`runway/bridge.py`) and cleans edited page HTML to plain
formatting and links. A change takes effect at once. Streamlit Community Cloud wipes the app's disk on every redeploy,
so Runway keeps changes elsewhere (`runway/store.py`), in this order:

1. **Neon (Postgres)**, when `DATABASE_URL` is set: page edits, the FAQ, uploaded documents and answer votes. The app
   creates its two tables (`runway_files`, `runway_feedback`) itself and puts the files back after every restart.
2. **Cloudflare R2**, when the four `R2_*` settings are set: the original file of each upload (`uploads/<slug>/...`).
3. Without Neon, a **GitHub token** commits each change (`data/content.json`, `data/corpus/<slug>.md`) to the repo.

```toml
DATABASE_URL = "postgresql://...neon.tech/neondb?sslmode=require"   # Neon: Connect > connection string
R2_ACCOUNT_ID = "..."            # Cloudflare: R2 > API tokens (Object Read & Write, this bucket only)
R2_ACCESS_KEY_ID = "..."
R2_SECRET_ACCESS_KEY = "..."
R2_BUCKET = "runway-uploads"
```

Or, instead of Neon, a GitHub token:

```toml
GITHUB_TOKEN = "github_pat_..."   # fine-grained token: this repository only, Contents: Read and write
# GITHUB_REPO = "dansyfq/project-runway"   # the defaults
# GITHUB_BRANCH = "main"
```

Each commit redeploys the app. Without a token, changes last until the app next restarts.

## Deploy (Streamlit Community Cloud)

1. Push this repo to GitHub.
2. At [share.streamlit.io](https://share.streamlit.io), create an app from the repo, branch `main`, main file
   `app.py`, Python 3.12, and set the custom subdomain `runway-hdb` (app URL: https://runway-hdb.streamlit.app).
3. Paste the contents of your local `.streamlit/secrets.toml` (the `ANTHROPIC_API_KEY` line first, then the `[auth.users]` hashes: a key placed below `[auth.users]` is read as a
   username and the AI stays off) into the app's
   Secrets.

## API and model usage

- **API.** Ask Runway calls Claude through the Anthropic API (the `anthropic` Python SDK) from `runway/llm.py`, on
  the server only; the browser never talks to Anthropic.
- **Model.** `claude-sonnet-5-5` by default (`DEFAULT_CHAT_MODEL` in `runway/config.py`), or the model named in
  `ANTHROPIC_MODEL`, for example `claude-haiku-5-5`.
- **Secrets.** `ANTHROPIC_API_KEY` and, optionally, `ANTHROPIC_MODEL`, read from Streamlit secrets first, then from
  environment variables (`runway/config.py`).
- **Settings.** `max_tokens` 16,000 (the model's thinking counts towards it; the prompts keep answers short), effort
  `low`, a 40-second timeout and one retry (`MAX_TOKENS`, `EFFORT` in `runway/llm.py`). With the calculator tools, at
  most 3 model turns and no new turn after 75 seconds per question (`MAX_STEPS`, `DEADLINE_SECONDS` in `runway/agent.py`).
- **Rate cap.** At most 300 AI calls an hour for the whole app (`AI_CALLS_PER_HOUR` in `runway/llm.py`), since guests
  can ask without an account. Past the cap, Ask falls back as below.
- **What is sent.** For an answer: the question, up to six recent chat turns, the youngest buyer's age if set, the
  answer language, the 5 retrieved passages and the definitions of Runway's 3 calculator tools and its price lookup; when Claude calls a tool,
  its result (worked out on Runway's server from figures the visitor typed) goes back too. "Why?" sends one flat's calculator figures and the rule passages; "Sum
  up this chat" sends the chat (the last 12 turns are used); a question in Chinese, Malay or Tamil is first sent alone to
  be put into English for the search. Never sent: files a visitor opens on Ask (read in the browser only), questions
  with an NRIC, phone number or email (stopped in the browser and again on the server), and income or household details.
- **Prompts.** The system prompts (answer, "Why?", summary, translation for search) and the question screening are in
  `runway/llm.py`.
- **Fallbacks.** No key, the hourly cap reached or an API error: Ask shows the matching official passages, "Why?" a
  plain template and the summary a list of the questions asked. An answer with a figure that is not in the passages, the
  question, the chat or a tool result is replaced by the passages too. A request the model declines is re-run on Anthropic's fallback model
  (`fallbacks="default"`, beta `server-side-fallback-2026-07-01`).
- **Search.** Document search makes no API call and needs no key: BM25 keywords and a FAISS vector store of
  `BAAI/bge-small-en-v1.5` embeddings, made on Runway's server with fastembed (the model, about 65 MB, is downloaded from
  Hugging Face on first start), with TF-IDF vectors as the stand-in (`runway/rag.py`, `runway/vector.py`; see Run it locally, above).
- **Voice.** Read-aloud uses the edge-tts package (Microsoft's free online neural voices, no key) in
  `runway/voicepack.py`: the server sends the text being read, never the visitor's voice. If it fails, the device's own
  voices read the answer.

## Project layout

```
app.py                 Streamlit host: full-window interface + message loop
runway_game/index.html the interface (from design/runway-mockup.html in the hand-off)
runway_game/assets/    home page photos (Wikimedia Commons, credited on the page)
DESIGN.md              colours, type, spacing and copy rules for the interface
runway/bridge.py       sign-in, ask, why, summary, trends, towns, town_photo and nav (page URL) messages
runway/cpf_rules.py    age-95 rule, CPF share, HDB loan limit, loan tenure (Python reference)
runway/costs.py        stamp duty, HDB fees, grants, HDB and bank loan under the income cap
runway/price_check.py  one flat's price per sqm against similar recent sales
runway/rag.py          chunking and hybrid search (BM25 keywords + vector store, reciprocal rank fusion)
runway/vector.py       the FAISS vector store: bge-small embeddings, saved in data/index/ (TF-IDF fallback in rag.py)
runway/chain.py        LangChain layer: the search as a retriever (Documents), prompt templates to Anthropic messages
runway/llm.py          prompts, question screening, number guard, Claude calls and the tool loop (Anthropic API)
runway/agent.py        the tools Ask's AI can call (lease check, loan length, stamp duty, and the price lookup)
runway/insights.py     the admin-only Insights page: votes, eval by search mode, documents, AI use
runway/auth.py         built-in accounts, roles, password hashing and checks
runway/game_data.py    map data and town photos; town list and one photo at a time for the home page
runway/trends.py       price trends by town and by lease left, built from resale.parquet (Trends tab)
runway/content.py      admin edits to page text and the FAQ, and uploaded Ask documents
runway/store.py        lasting storage for those edits and for votes (Neon database, Cloudflare R2 files)
runway/voicepack.py    Singapore voice pack for read-aloud (edge-tts)
runway/config.py       settings (Streamlit secrets, then environment) and defaults
scripts/               build_dataset, refresh_data (monthly), fetch_town_photos, seed_users, to_corpus
.github/workflows/     monthly data refresh: rebuilds the dataset and opens a pull request for a person to merge
data/game/             towns, Jul-Sep 2026 sales, blocks, roads, MRT, amenities
data/photos/           26 town photos + credits (scripts/fetch_town_photos.py)
data/corpus/           32 official documents with source URLs
data/index/            FAISS index of their passages (python -m runway.vector)
data/resale.parquet    HDB resale transactions since 1990 (Trends and the price check; refreshed monthly)
eval/, tests/          evaluation questions and the pytest suite
```

## Checks

```bash
pytest                 # includes a check that the map's calculator matches cpf_rules.py (needs Node.js)
python eval/run_eval.py   # retrieval, calculator, decline checks (+ LLM answers if a key is set)
```

The CPF formula reproduces every official worked example: MND's May 2019 Annex B (age 25 with 55 / 65 / 75 years
left gives 70% / 90% / 100%) and CPF Board's FAQ.

The lease premium by town (`pct` in `data/game/map.json`) is the % change in price per sqm for one extra year of
lease. Method, as in the proposal's Table 1: within one town and flat type, fit `log(price per sqm) = a + b * remaining
lease` by least squares; `exp(b) - 1` is the premium. It is a market pattern, not a cause: it does not adjust for floor
level, size, model or condition. The values in `map.json` came from the design hand-off and no script in this repo
rebuilds them (`scripts/refresh_data.py` leaves them alone). `runway/lease_data.py` implemented the same method for the
proposal's Table 1; it was removed because the app never called it, and the last commit that has it is `2f9f31b`.

## Data and licences

- HDB resale flat prices, [data.gov.sg](https://data.gov.sg/collections/189/view), Singapore Open Data Licence.
  Rebuild `data/resale.parquet` with `python scripts/build_dataset.py <folder with the 5 CSVs>`, or run
  `python scripts/refresh_data.py` to download the five files and rebuild in one step.
- **Monthly refresh.** The "Data refresh" GitHub workflow runs `refresh_data.py` on the 3rd of each month, runs the
  tests and opens a pull request with the new `data/resale.parquet` and `data/dataset_meta.json`. It never pushes to
  `main`, so nothing deploys until the pull request is merged. It needs the repository setting "Allow GitHub Actions
  to create and approve pull requests". Trends and the home page figures follow the new data; the map's Jul–Sep 2026
  sales and each town's lease effect stay as they are, because `data/game/` came from the design hand-off and has no
  build script. The transaction count in this file is as at Sep 2026.
- Rules documents: public pages from CPF Board, HDB, MND, MOM, IRAS and CEA, retrieved 16 Oct 2026. Each file in
  `data/corpus/` records its source URL.
