import pytest

from app.browser.guards import (
    BudgetExceeded,
    BudgetState,
    UNTRUSTED_CLOSE,
    UNTRUSTED_OPEN,
    detect_login_wall,
    is_allowed_navigation,
    select_allowed_tools,
    truncate,
    wrap_untrusted,
)
from app.config import McpConfig


def test_select_allowed_tools_keeps_navigation_caps():
    names = [
        "browser_navigate",
        "browser_snapshot",
        "browser_click",
        "browser_scroll",
        "browser_press_key",
        "browser_wait_for",
    ]
    assert select_allowed_tools(names) == names


def test_select_allowed_tools_drops_dangerous_caps():
    names = [
        "browser_navigate",
        "browser_type",
        "browser_fill_form",
        "browser_evaluate",
        "browser_file_upload",
        "browser_tab_new",
        "browser_drag",
        "browser_select_option",
    ]
    assert select_allowed_tools(names) == ["browser_navigate"]


def test_navigation_prefix_guard():
    assert is_allowed_navigation("https://www.linkedin.com/jobs/view/1/")
    assert is_allowed_navigation("https://www.linkedin.com/jobs/search/?keywords=x")
    assert not is_allowed_navigation("https://www.linkedin.com/feed/")
    assert not is_allowed_navigation("https://evil.com/jobs/")
    assert not is_allowed_navigation("")


def test_truncate_and_wrap():
    assert truncate("abc", 10) == "abc"
    assert "truncated" in truncate("abcdef", 3)
    wrapped = wrap_untrusted("page text")
    assert UNTRUSTED_OPEN in wrapped and UNTRUSTED_CLOSE in wrapped
    assert "page text" in wrapped


def test_detect_login_wall():
    assert detect_login_wall("Page URL: https://www.linkedin.com/checkpoint/challenge/x")
    assert detect_login_wall("Please complete this security verification to continue")
    assert detect_login_wall("Page URL: https://www.linkedin.com/login")
    assert not detect_login_wall(
        "AI Engineer at Acme. Full-time. Apply now. https://www.linkedin.com/jobs/view/1/"
    )


def _limits(**overrides):
    data = {
        "max_steps_per_query": 3,
        "max_llm_calls_per_query": 2,
        "max_llm_calls_per_run": 4,
        "max_tool_calls_per_query": 2,
        "max_total_tokens_per_run": 100,
        "max_wall_clock_s_per_query": 60,
    }
    data.update(overrides)
    return McpConfig(**data)


def test_budget_steps():
    budget = BudgetState(_limits())
    budget.start_query()
    for _ in range(3):
        budget.register_step()
    with pytest.raises(BudgetExceeded):
        budget.register_step()


def test_budget_llm_per_query_and_run():
    budget = BudgetState(_limits())
    budget.start_query()
    budget.register_llm_call()
    budget.register_llm_call()
    with pytest.raises(BudgetExceeded):
        budget.register_llm_call()

    run_budget = BudgetState(_limits(max_llm_calls_per_query=10, max_llm_calls_per_run=2))
    run_budget.start_query()
    run_budget.register_llm_call()
    run_budget.register_llm_call()
    with pytest.raises(BudgetExceeded):
        run_budget.register_llm_call()


def test_budget_tool_calls_and_tokens():
    budget = BudgetState(_limits())
    budget.start_query()
    budget.register_tool_call()
    budget.register_tool_call()
    with pytest.raises(BudgetExceeded):
        budget.register_tool_call()

    tokens = BudgetState(_limits(max_total_tokens_per_run=10))
    tokens.register_tokens(6)
    with pytest.raises(BudgetExceeded):
        tokens.register_tokens(6)


def test_budget_deadline():
    budget = BudgetState(_limits(max_wall_clock_s_per_query=60))
    budget.start_query()
    budget.deadline = 0.0
    with pytest.raises(BudgetExceeded):
        budget.check_deadline()
