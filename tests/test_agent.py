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
