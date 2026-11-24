"""Ask Runway's calculator tools (runway/agent.py) and the tool loop in runway/llm.py."""

import json
from types import SimpleNamespace

import pytest

import runway.llm as llm_mod
from runway import agent
from runway.cpf_rules import check_lease, max_loan_tenure
from runway.costs import stamp_duty
from runway.llm import LLM
from runway.rag import Chunk

SOURCE = Chunk(0, "cpf-faq-lease-not-covering-95", "CPF FAQ", "CPF Board", "https://www.cpf.gov.sg", "2026-10-16",
               "Lease", "CPF usage is pro-rated if the lease does not cover the youngest buyer to age 95.")


def test_lease_tool_returns_the_calculators_figures():
    out, err = agent.run("cpf_lease_check", {"youngest_age": 25, "remaining_lease_years": 65})
    data, c = json.loads(out), check_lease(25, 65)
    assert not err and data["cpf_usable_percent_of_valuation_limit"] == agent.figure(c.cpf_share * 100) == "90"
    assert data["hdb_loan_limit_percent"] == "67.5" and data["lease_ends_when_youngest_is"] == "90"
    assert data["covers_youngest_to_95"] is False and data["lease_needed_for_full_cpf"] == "70"


def test_tenure_and_stamp_duty_tools():
    out, _ = agent.run("hdb_loan_tenure", {"buyer_ages": [50, 50], "remaining_lease_years": 80})
    assert json.loads(out)["longest_hdb_loan_years"] == agent.figure(max_loan_tenure([50, 50], 80)) == "15"
    out, _ = agent.run("buyers_stamp_duty", {"price": 500000})
    assert json.loads(out)["buyers_stamp_duty"] == f"${round(stamp_duty(500000)):,}"


@pytest.mark.parametrize(("name", "args"), [
    ("cpf_lease_check", {"youngest_age": 12, "remaining_lease_years": 60}),  # too young to buy
    ("cpf_lease_check", {"youngest_age": True, "remaining_lease_years": 60}),
    ("cpf_lease_check", {"youngest_age": 30, "remaining_lease_years": 150}),
    ("hdb_loan_tenure", {"buyer_ages": [], "remaining_lease_years": 60}),
    ("buyers_stamp_duty", {"price": -5}),
    ("delete_everything", {}),
    ("cpf_lease_check", "not an object"),
])
def test_tools_reject_bad_inputs_as_errors_not_crashes(name, args):
    out, err = agent.run(name, args)
    assert err and "error" in json.loads(out)


def test_tools_are_strict_with_closed_schemas():
    for tool in agent.TOOLS:
        assert tool["strict"] and tool["input_schema"]["additionalProperties"] is False
        assert set(tool["input_schema"]["required"]) == set(tool["input_schema"]["properties"])


def scripted(*turns):
    """A fake client that plays back one response per call and records every request."""
    calls, replies = [], list(turns)

    def create(**kw):
        calls.append(kw)
        return replies.pop(0)

    bot = LLM.__new__(LLM)
    bot.chat_model = "test"
    bot._client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
    return bot, calls


def tool_turn(name, args, id_="t1"):
    return SimpleNamespace(stop_reason="tool_use", content=[
        SimpleNamespace(type="thinking", thinking=""),
        SimpleNamespace(type="tool_use", id=id_, name=name, input=args)])


def text_turn(text):
    return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=text)])


def test_answer_calls_the_calculator_and_may_quote_its_figures():
    bot, calls = scripted(tool_turn("cpf_lease_check", {"youngest_age": 25, "remaining_lease_years": 65}),
                          text_turn("Runway's calculator says CPF can pay 90% and the HDB loan limit is 67.5% [1]."))
    result = bot.answer("I'm 25 and the flat has 65 years left. How much CPF can I use?", [SOURCE])
    assert result.error is None and "67.5%" in result.text  # 67.5 is in no passage or question: it came from the tool
    assert calls[0]["tools"] == agent.TOOLS
    sent = calls[1]["messages"]
    assert sent[-2]["role"] == "assistant" and sent[-2]["content"][0].type == "thinking"  # turn sent back unchanged
    result_block = sent[-1]["content"][0]
    assert result_block["type"] == "tool_result" and result_block["tool_use_id"] == "t1" and not result_block["is_error"]


def test_a_figure_from_neither_the_tools_nor_the_passages_is_still_caught():
    bot, _ = scripted(tool_turn("cpf_lease_check", {"youngest_age": 25, "remaining_lease_years": 65}),
                      text_turn("You can use 88% [1]."))
    result = bot.answer("I'm 25 and the flat has 65 years left. How much CPF can I use?", [SOURCE])
    assert result.error == llm_mod.INVENTED_FIGURE and result.text == llm_mod.offline_answer([SOURCE])


def test_tool_loop_stops_after_max_steps():
    bot, calls = scripted(*[tool_turn("buyers_stamp_duty", {"price": 500000}, f"t{i}") for i in range(agent.MAX_STEPS)])
    result = bot.answer("What stamp duty is due on a $500,000 flat?", [SOURCE])
    assert result.error and "tool steps" in result.error and len(calls) == agent.MAX_STEPS


def test_each_tool_turn_spends_the_hourly_budget(monkeypatch):
    from collections import deque

    monkeypatch.setattr(llm_mod, "AI_CALLS_PER_HOUR", 1)
    monkeypatch.setattr(llm_mod, "_calls", deque())
    bot, calls = scripted(tool_turn("buyers_stamp_duty", {"price": 500000}), text_turn("unused"))
    result = bot.answer("What stamp duty is due on a $500,000 flat?", [SOURCE])
    assert result.error == llm_mod.AI_BUSY and len(calls) == 1


def test_a_tool_cannot_launder_a_figure_the_user_never_gave():
    """The model puts 80000 into a tool's input to make "$80,000" pass the guard: the call is refused, the figure is caught."""
    bot, calls = scripted(tool_turn("buyers_stamp_duty", {"price": 80000}),
                          text_turn("You get a grant of $80,000 [1]."))
    result = bot.answer("What grant do I get?", [SOURCE])
    refused = calls[1]["messages"][-1]["content"][0]
    assert refused["is_error"] and "figures the user gave" in refused["content"]
    assert result.error == llm_mod.INVENTED_FIGURE


def test_tool_inputs_may_use_figures_from_earlier_questions():
    bot, calls = scripted(tool_turn("cpf_lease_check", {"youngest_age": 25, "remaining_lease_years": 65.0}),
                          text_turn("CPF can pay 90% [1]."))
    history = [{"role": "user", "content": "I'm 25."}, {"role": "assistant", "content": "Noted [1]."}]
    result = bot.answer("The flat has 65 years left. How much CPF?", [SOURCE], history=history)
    assert not calls[1]["messages"][-1]["content"][0]["is_error"] and result.error is None


def test_input_numbers_reads_every_figure():
    assert agent.input_numbers({"buyer_ages": [30, 32], "remaining_lease_years": 61.5, "x": True}) == {"30", "32", "61.5"}


def test_no_passages_means_no_ai_call():
    bot, calls = scripted(text_turn("unused"))
    result = bot.answer("What is the HDB loan limit?", [])
    assert calls == [] and result.text == llm_mod.offline_answer([])


# ---- the price lookup (Trends' figures) ----

TRENDS = {  # the part of runway.trends.build_trends() output the lookup reads
    "towns": ["Bedok", "Kallang / Whampoa"], "types": ["3 ROOM", "4 ROOM", "5 ROOM", "EXECUTIVE"],
    "since_month": "2024-10", "last_month": "2026-09",
    "lease_psm": {"3 ROOM": {}, "5 ROOM": {}, "EXECUTIVE": {},
                  "4 ROOM": {"Bedok": [5842, 5848, 6671, 7368, 9711, 9409], "Kallang / Whampoa": [None] * 6}},
}
ASK = {"town": "Bedok", "flat_type": "4-room", "remaining_lease_years": 55}


@pytest.fixture
def trends_data(monkeypatch):
    import runway.trends

    monkeypatch.setattr(runway.trends, "load_trends", lambda: TRENDS)


def test_price_lookup_returns_trends_figures_and_the_gap(trends_data):
    out, err = agent.run("price_by_lease", ASK)
    data = json.loads(out)
    assert not err and data["lease_band_years"] == "50 to 59" and data["median_price_per_sqm_in_this_band"] == "$5,848"
    assert data["compared_with_lease_band_years"] == "80 to 89" and data["median_price_per_sqm_in_compared_band"] == "$9,711"
    assert data["percent_difference"] == "40" and data["this_band_price_is"] == "lower"  # (9711 - 5848) / 9711 = 39.8%
    assert data["sales_window"] == "October 2024 to September 2026" and "Trends" in data["source"]
    assert "calculator" not in data["source"] and "not the lease alone" in data["how_to_say_it"]


def test_price_lookup_for_a_long_lease_compares_with_the_short_band(trends_data):
    data = json.loads(agent.run("price_by_lease", {**ASK, "remaining_lease_years": 85})[0])
    assert data["lease_band_years"] == "80 to 89" and data["compared_with_lease_band_years"] == "50 to 59"
    assert data["percent_difference"] == "66" and data["this_band_price_is"] == "higher"  # (5848 - 9711) / 5848 = -66.1%
    assert json.loads(agent.run("price_by_lease", {**ASK, "town": "BEDOK", "remaining_lease_years": 95})[0])["percent_difference"] == "61"


@pytest.mark.parametrize("args", [
    {**ASK, "town": "Nowhere"},                    # not a town Trends has
    {**ASK, "flat_type": "2-room"},                # not a flat type Trends has
    {**ASK, "remaining_lease_years": 0},           # no lease left
    {**ASK, "remaining_lease_years": 150},
    {**ASK, "remaining_lease_years": True},
    {**ASK, "town": None},
    {**ASK, "town": "Kallang / Whampoa"},          # every band too thin: no median to give
])
def test_price_lookup_errors_instead_of_guessing(trends_data, args):
    out, err = agent.run("price_by_lease", args)
    assert err and "error" in json.loads(out) and "$" not in out


def test_answer_may_quote_the_price_lookup(trends_data):
    bot, calls = scripted(tool_turn("price_by_lease", ASK),
                          text_turn("In Bedok, 4-room flats with 50 to 59 years of lease left sold for a median $5,848 per sqm, "
                                    "40% lower than the $9,711 for 80 to 89 years left (October 2024 to September 2026). These are "
                                    "different flats, so it is a market pattern, not the lease alone [1]."))
    result = bot.answer("What does 55 years of lease left do to the price of a 4-room flat in Bedok?", [SOURCE])
    assert result.error is None and "$5,848" in result.text  # 5,848 is in no passage or question: it came from the tool
    assert any(t["name"] == "price_by_lease" for t in calls[0]["tools"])
    assert "price_by_lease" in llm_mod.ANSWER_SYSTEM and "never guess it" in llm_mod.ANSWER_SYSTEM
    block = calls[1]["messages"][-1]["content"][0]
    assert not block["is_error"] and "Trends" in block["content"]


def test_a_price_not_in_the_lookup_is_still_caught(trends_data):
    bot, _ = scripted(tool_turn("price_by_lease", ASK), text_turn("Flats there cost about $6,200 per sqm [1]."))
    result = bot.answer("What does 55 years of lease left do to the price of a 4-room flat in Bedok?", [SOURCE])
    assert result.error == llm_mod.INVENTED_FIGURE


def test_the_price_lookup_only_takes_a_lease_the_user_gave(trends_data):
    bot, calls = scripted(tool_turn("price_by_lease", {**ASK, "remaining_lease_years": 65}), text_turn("unused [1]"))
    bot.answer("What does 55 years of lease left do to the price of a 4-room flat in Bedok?", [SOURCE])
    refused = calls[1]["messages"][-1]["content"][0]
    assert refused["is_error"] and "figures the user gave" in refused["content"]


# ---- asking for the flat type or lease instead of letting the AI guess ----

TOWNS = ["Ang Mo Kio", "Bedok", "Clementi", "Yishun"]


def needs(question, earlier=()):
    return agent.lease_price_needs(question, list(earlier), TOWNS)


def test_a_vague_lease_price_question_asks_for_both_details():
    reply = needs("What does a shorter lease do to HDB resale prices in Bedok?")
    assert "in Bedok" in reply and "flat type" in reply and "years of lease" in reply
    assert "3-room, 4-room, 5-room or Executive" in reply and "55 years of lease left" in reply


def test_it_asks_only_for_what_is_missing():
    only_type = needs("How does 55 years of lease affect prices in Bedok?")
    assert only_type and "flat type" in only_type and "years of lease are left" not in only_type
    only_years = needs("How does lease affect the price of a 4-room flat in Bedok?")
    assert only_years and "how many years of lease" in only_years and "flat type (3-room" not in only_years
    assert "flat" in only_type.lower() and "years" in only_years.lower()  # a reply written like the example passes the topic filter


def test_details_given_earlier_in_the_chat_count():
    assert needs("What does a shorter lease do to prices in Bedok?", ["I'm looking at a 4-room flat with 55 years left"]) is None
    only = needs("What does a shorter lease do to prices in Bedok?", ["I'm looking at a 4-room flat"])
    assert only and "how many years of lease" in only


@pytest.mark.parametrize("question", [
    "What does 55 years of lease left do to the price of a 4-room flat in Bedok?",  # everything is there
    "Why do short leases cost more in Clementi than Yishun?",                       # a "why" question: answered from the documents
    "What does a shorter lease do to HDB resale prices?",                           # no town
    "What does a shorter lease do to prices in Bedok and Yishun?",                  # two towns
    "Can I use CPF for a short lease flat in Bedok?",                               # not about price
    "What is the price of a flat in Bedok?",                                        # not about lease
    "How is the HDB loan affected by a short lease in Bedok?",                      # not about price
    "I'm 30 and the flat has 55 years left. How much CPF can I use?",
])
def test_other_questions_are_left_to_the_ai(question):
    assert needs(question) is None


def test_a_town_name_inside_another_word_is_not_a_town():
    assert agent.lease_price_needs("What does a shorter lease do to prices in Bedokland?", [], TOWNS) is None


def price_needs(question, earlier=()):
    return agent.price_ask_needs(question, list(earlier), TOWNS)


def test_a_plain_price_question_asks_for_the_lease():
    reply = price_needs("What is the latest HDB resale price for a 4-room flat in Bedok?")
    assert "in Bedok" in reply and "how many years of lease are left" in reply and "flat type" not in reply
    assert "the town" not in reply


def test_a_price_question_with_nothing_given_asks_for_town_type_and_lease():
    reply = price_needs("What is the average resale price?")
    assert "the town" in reply and "flat type" in reply and "years of lease" in reply


def test_a_price_question_with_everything_given_goes_on_to_the_price_lookup():
    assert price_needs("What is the price of a 4-room flat in Bedok with 60 years of lease left?") is None
    assert price_needs("And what about the price of a flat?", ["4-room in Bedok, 60 years of lease left"]) is None


def test_rules_and_comparison_questions_that_mention_a_price_are_left_alone():
    for q in ("How is the loan limit worked out from the purchase price?", "How much stamp duty do I pay on a $600,000 flat?",
              "What is the minimum occupation period?", "Compare resale prices in Bedok and Yishun",
              "Why do resale prices fall with lease?"):
        assert price_needs(q) is None, q
