# Singpass for Runway: what it could do, and the demo

Written 18 Nov 2026 from Singpass's public developer documents (linked below). Runway is **not** connected to Singpass.
The "Singpass demo" in the app is a mock-up with made-up people, to show what a real connection could look like.

## The idea

Today a visitor types their age, CPF balance, income and a few household details. With Singpass's **Myinfo**, a visitor
could agree to share those figures instead, and Runway would fill them in. The rest of the app would not change:
the same calculators run on the same fields.

## How a real sign-in works

1. The visitor taps "Log in with Singpass". Runway sends them to Singpass (OpenID Connect, authorization code flow).
2. They approve in the Singpass app (a QR code on a computer, or a direct hand-off on a phone).
3. For Myinfo data, Singpass shows a consent screen listing what Runway asks for. The visitor agrees to share it.
4. Runway's server swaps the code for the data, signed and encrypted for Runway. The browser never sees the keys.
5. Singpass requires apps to follow its FAPI 2.0 version of the login by 31 Dec 2026.

## What Myinfo could give Runway, and where it would go

| Myinfo data (from the data catalog) | Runway field | Used for |
|---|---|---|
| Date of birth (sometimes only year and month) | Youngest buyer's age (`S.age`) | The age-95 rule, loan length |
| CPF Ordinary Account balance (Citizens and PRs; can be negative) | CPF Ordinary Account (`S.oa`) | Cash needed at the start |
| Income from the latest tax assessment | Household income (`S.inc`) | HDB loan income cap, grants |
| Marital status | Buying as (`S.hh`) | Couple or single (35 or over) |
| HDB ownership (dates of purchase and transfer) | First-timer or not (`S.first`) | Grants |
| Citizenship / residential status | Citizenship (`S.cit`) | Grant rules, quotas |

Check each row against the current data catalog before any real build. Date of birth, the CPF balance, the tax
assessment income and the HDB ownership dates were confirmed in Singpass's documents; marital status and citizenship are
standard Myinfo fields that we did not look up one by one. A "housing grant history" field was not found, so ownership
alone may not settle first-timer status, which HDB decides under its own rules.

Notes: Myinfo gives a date of birth, not an age, so Runway works the age out. It returns only the signed-in person,
so a partner's age and income would need their own sign-in or typing. CPF contribution history (up to 15 months of
employer contributions) is also available. We found no Myinfo field for CPF housing withdrawals.

## Other uses worth considering

- **Estimate monthly CPF coming in** from the contribution history, to show how long until the cash gap closes.
- **Check the second buyer too**: each buyer signs in separately, and the app uses the younger age.
- **Residency and quota rules**: citizenship and residential status could flag the SPR quota or grant differences.
- **Singles scheme**: marital status plus age could say at once whether the singles rules apply.
- **Save a shortlist to an account.** This is the one to be careful with: it means storing data, which the app
  deliberately avoids today (no names, no NRIC, nothing kept in the browser except the dark-mode choice).

## Who can actually use it

- **Singpass Login and Myinfo** need access to the Singpass Developer Portal and a Singapore-registered organisation
  (government or private sector). The documents do not mention students or individuals as developers.
- **sgID** (the open developer ID from GovTech) lets a developer register after signing in with Singpass, but general
  use is limited to the `openid` and `name` scopes. Date of birth and similar scopes need a separate request.
- **Testing**: the developer portal offers a staging environment with test personas, and the community project
  MockPass imitates Singpass for local development (unofficial).

So a student project is unlikely to get a live connection. Even with one, CPF and income data would need approval
for each scope, and a clear reason to ask for it.

## Privacy

A real build would follow data minimisation: ask only for what each calculation needs, say why, and let the visitor
untick items (the demo does this). Singpass data can include the NRIC number; Runway would have to discard it at once and never
log it. Runway's current promise (no NRIC, no names) would need rewording in the Privacy page before any real use.

## What the demo does

- **Open to everyone.** The "Skip the typing?" card appears for every visitor, with or without a reviewer login. It is a
  labelled mock-up ("Demonstration only", made-up people, nothing sent anywhere).
- It appears on the age step and on **More > Your details**.
- Three made-up people (A, B and C). The visitor picks one, sees a consent screen with a tick box for each item, and
  taps "Share selected details". Runway fills in only the ticked items.
- It never contacts Singpass, shows no Singpass branding, asks for no password and sends nothing. What it fills in is kept only in the open tab (session storage), like anything else typed into Your details, and is forgotten when the tab closes.
- Filled-in values flow through the same calculators: verdicts, income cap, grants, shortlist, Ask.
- "Reset my details" clears everything the demo filled in.

Code: `SPD`, `SPD_ITEMS`, `spdFill` and `openSingpassDemo` in `runway_game/index.html`. Tests: `tests/test_singpass_demo.py`.

## Sources

- [Singpass developer docs: pre-requisites for onboarding](https://docs.developer.singpass.gov.sg/docs/getting-started/pre-requisites-for-onboarding)
- [Myinfo data catalog](https://docs.developer.singpass.gov.sg/docs/data-catalog-myinfo)
- [Myinfo: CPF contribution history (up to 15 months)](https://docs.developer.singpass.gov.sg/docs/data-catalog-myinfo/understanding-the-data/cpf-contribution-history-up-to-15-months)
- [Singpass: invoke the authorization endpoint](https://docs.developer.singpass.gov.sg/singpass-developer-docs/getting-started/custom-integration/invoke-authorization-endpoint)
- [Singpass: getting access to the developer portal (FAPI 2.0 notice)](https://docs.developer.singpass.gov.sg/docs/singpass-developer-portal-sdp/getting-access)
- [Myinfo test personas](https://docs.developer.singpass.gov.sg/docs/testing/myinfo-test-personas)
- [sgID developer docs: register your application](https://docs.id.gov.sg/introduction/getting-started/register-your-application)
- [sgID data catalog](https://docs.id.gov.sg/data-catalog)
- [MockPass (unofficial mock server)](https://github.com/opengovsg/mockpass)
