import asyncio

import pytest
from langchain.agents.middleware.types import ModelRequest, ToolCallRequest
from langchain_core.messages import AIMessage, ToolMessage

from app.browser.guards import (
    BudgetState,
    LoginWallError,
    UNTRUSTED_OPEN,
)
from app.browser.mcp_scraper import (
    McpScraper,
    _GuardMiddleware,
    _tokens_from_response,
    _unwrap_exception,
    parse_cards_json,
)
from app.browser.search import expand_searches
from app.config import McpConfig, Secrets, load_config


def _limits(**overrides):
    data = {
        "max_steps_per_query": 5,
        "max_llm_calls_per_query": 5,
        "max_llm_calls_per_run": 10,
        "max_tool_calls_per_query": 5,
        "max_total_tokens_per_run": 1000,
        "max_wall_clock_s_per_query": 60,
        "min_delay_s": 0.0,
        "max_delay_s": 0.0,
    }
    data.update(overrides)
    return McpConfig(**data)


def _request(name, args):
    return ToolCallRequest(
        tool_call={"name": name, "args": args, "id": "c1"},
        tool=None,
        state={},
        runtime=None,
    )


def _handler(content):
    async def handler(_request):
        return ToolMessage(content=content, tool_call_id="c1", name="browser_snapshot")

    return handler


def test_rejects_non_allowlisted_tool():
    mw = _GuardMiddleware(BudgetState(_limits()), {"browser_navigate"})
    out = asyncio.run(
        mw.awrap_tool_call(_request("browser_type", {"text": "x"}), _handler("ran"))
    )
    assert "not available" in out.content


def test_rejects_disallowed_navigation():
    budget = BudgetState(_limits())
    mw = _GuardMiddleware(budget, {"browser_navigate"})
    out = asyncio.run(
        mw.awrap_tool_call(
            _request("browser_navigate", {"url": "https://evil.com/"}), _handler("nav")
        )
    )
    assert "rejected" in out.content.lower()
    assert budget.rejected_navigations == 1


def test_allowed_tool_wraps_untrusted_content():
    mw = _GuardMiddleware(BudgetState(_limits()), {"browser_snapshot"})
    out = asyncio.run(
        mw.awrap_tool_call(_request("browser_snapshot", {}), _handler("job page text"))
    )
    assert UNTRUSTED_OPEN in out.content
    assert "job page text" in out.content


def test_login_wall_raises():
    mw = _GuardMiddleware(BudgetState(_limits()), {"browser_snapshot"})
    with pytest.raises(LoginWallError):
        asyncio.run(
            mw.awrap_tool_call(
                _request("browser_snapshot", {}),
                _handler("Page URL: https://www.linkedin.com/checkpoint/challenge/x"),
            )
        )


def test_parse_cards_json_drops_invalid_and_offsite():
    content = (
        '{"jobs": ['
        '{"title": "AI Engineer", "company": "Acme", '
        '"url": "https://www.linkedin.com/jobs/view/1/"},'
        '{"title": "x", "company": "y", "url": "https://evil.com/1"},'
        '{"title": "no company", "url": "https://www.linkedin.com/jobs/view/2/"}'
        "]}"
    )
    cards = parse_cards_json(content)
    assert len(cards) == 1
    assert cards[0]["title"] == "AI Engineer"


def test_parse_cards_json_handles_garbage():
    assert parse_cards_json("not json at all") == []


def test_parse_cards_json_keeps_urlless_cards_with_fallback():
    content = (
        '{"jobs": [{"title": "AI Engineer", "company": "Acme", '
        '"location": "Chennai (On-site)", '
        '"posted_text": "Posted 10 hours ago"}]}'
    )
    cards = parse_cards_json(
        content, fallback_url="https://www.linkedin.com/jobs/search/?keywords=ai"
    )
    assert len(cards) == 1
    assert cards[0]["url"] == "https://www.linkedin.com/jobs/search/?keywords=ai"
    assert cards[0]["location"] == "Chennai (On-site)"


class _EmptyResponse:
    result: list = []


def test_convergence_withdraws_tools_near_budget():
    limits = _limits(max_steps_per_query=3, max_tool_calls_per_query=10)
    budget = BudgetState(limits)
    budget.start_query()
    budget.steps_query = 2  # one step from the wall
    mw = _GuardMiddleware(budget, set())
    seen = {}

    async def handler(request):
        seen["tools"] = request.tools
        seen["tool_choice"] = request.tool_choice
        return _EmptyResponse()

    request = ModelRequest(
        model=None,
        messages=[],
        system_message=None,
        tool_choice="auto",
        tools=[object()],
        response_format=None,
        state={},
        runtime=None,
        model_settings={},
    )
    asyncio.run(mw.awrap_model_call(request, handler))
    assert seen["tools"] == []
    assert seen["tool_choice"] == "none"


def test_tokens_from_response():
    msg = AIMessage(
        content="x", usage_metadata={"total_tokens": 42, "input_tokens": 1, "output_tokens": 41}
    )

    class _Resp:
        result = [msg]

    assert _tokens_from_response(_Resp()) == 42


class _FakeAgent:
    def __init__(self, content):
        self.content = content
        self.configs = []

    async def ainvoke(self, state, config=None):
        self.configs.append(config)
        return {"messages": [AIMessage(content=self.content)]}


def test_run_query_agent_parses_and_sets_recursion_limit():
    config = load_config()
    scraper = McpScraper(config, Secrets(deepseek_api_key="x"))
    scraper.budget.start_query()
    agent = _FakeAgent(
        '{"jobs": [{"title": "AI", "company": "Acme", '
        '"url": "https://www.linkedin.com/jobs/view/1/"}]}'
    )
    search = expand_searches(config.search)[0]
    cards = asyncio.run(scraper._run_query_agent(agent, search))
    assert cards[0]["title"] == "AI"
    assert agent.configs[0]["recursion_limit"] >= 4


def test_unwrap_exception():
    inner = LoginWallError("wall")
    nested = ExceptionGroup("outer", [ExceptionGroup("mid", [inner])])
    assert _unwrap_exception(nested) is inner


def test_collect_unwraps_exception_group(monkeypatch):
    config = load_config()
    scraper = McpScraper(config, Secrets(deepseek_api_key="x"))

    async def boom():
        raise ExceptionGroup("g", [LoginWallError("wall")])

    monkeypatch.setattr(scraper, "_collect_async", boom)
    with pytest.raises(LoginWallError):
        scraper.collect()


def test_run_query_recursion_limit_formula():
    config = load_config()
    config.mcp.max_steps_per_query = 10
    config.mcp.max_llm_calls_per_query = 7
    scraper = McpScraper(config, Secrets(deepseek_api_key="x"))
    agent = _FakeAgent('{"jobs": []}')
    search = expand_searches(config.search)[0]
    asyncio.run(scraper._run_query_agent(agent, search))
    # LangGraph counts model + tool super-steps; limit must exceed 2 * budget calls.
    assert agent.configs[0]["recursion_limit"] == 2 * 7 + 6
