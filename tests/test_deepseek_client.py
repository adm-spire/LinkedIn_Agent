import httpx
import pytest
from openai import APIStatusError

from app.config import ProfileConfig
from app.llm.deepseek_client import (
    DeepSeekClient,
    FatalLLMError,
    LLMError,
    build_user_prompt,
)
from app.pipeline.normalize import normalize_job


class _Message:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content):
        self.message = _Message(content)


class _Response:
    def __init__(self, content):
        self.choices = [_Choice(content)]


class _FakeCompletions:
    def __init__(self, content=None, exc=None):
        self.content = content
        self.exc = exc
        self.calls = 0

    def create(self, **_kwargs):
        self.calls += 1
        if self.exc:
            raise self.exc
        return _Response(self.content)


class _FakeChat:
    def __init__(self, completions):
        self.completions = completions


class _FakeClient:
    def __init__(self, completions):
        self.chat = _FakeChat(completions)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr("app.llm.deepseek_client.time.sleep", lambda *_: None)


def _client(completions):
    c = DeepSeekClient.__new__(DeepSeekClient)
    c.client = _FakeClient(completions)
    c.model = "deepseek-chat"
    c.max_retries = 0
    return c


def _job():
    return normalize_job(
        {"title": "AI Engineer", "company": "Acme", "url": "https://x/1", "description": "Python LLM"}
    )


def test_valid_response_parsed():
    completions = _FakeCompletions(
        '{"match": true, "score": 90, "reason": "good", "matching_skills": ["Python"], "missing_skills": []}'
    )
    result = _client(completions).match_job(ProfileConfig(skills=["Python"]), _job())
    assert result.match is True
    assert result.score == 90
    assert result.model == "deepseek-chat"


def test_invalid_schema_raises_llm_error():
    completions = _FakeCompletions('{"match": true, "score": 999}')
    with pytest.raises(LLMError):
        _client(completions).match_job(ProfileConfig(), _job())


def test_malformed_json_retries_then_raises():
    completions = _FakeCompletions("not json")
    client = _client(completions)
    client.max_retries = 2
    with pytest.raises(LLMError):
        client.match_job(ProfileConfig(), _job())
    assert completions.calls == 3


def test_api_error_raises_llm_error():
    completions = _FakeCompletions(exc=RuntimeError("boom"))
    with pytest.raises(LLMError):
        _client(completions).match_job(ProfileConfig(), _job())


def test_no_sleep_after_final_attempt(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("app.llm.deepseek_client.time.sleep", sleeps.append)
    completions = _FakeCompletions("not json")
    client = _client(completions)
    client.max_retries = 2
    with pytest.raises(LLMError):
        client.match_job(ProfileConfig(), _job())
    assert completions.calls == 3
    assert len(sleeps) == 2


def _api_status_error(status_code: int) -> APIStatusError:
    request = httpx.Request("POST", "https://api.deepseek.com/chat/completions")
    response = httpx.Response(status_code, request=request)
    return APIStatusError("api error", response=response, body=None)


def test_fatal_status_raises_immediately_without_retry():
    completions = _FakeCompletions(exc=_api_status_error(401))
    client = _client(completions)
    client.max_retries = 2
    with pytest.raises(FatalLLMError):
        client.match_job(ProfileConfig(), _job())
    assert completions.calls == 1


def test_fatal_error_is_llm_error_subclass():
    assert issubclass(FatalLLMError, LLMError)


def test_non_fatal_status_retries_then_raises():
    completions = _FakeCompletions(exc=_api_status_error(500))
    client = _client(completions)
    client.max_retries = 2
    with pytest.raises(LLMError):
        client.match_job(ProfileConfig(), _job())
    assert completions.calls == 3


def test_prompt_marks_job_as_untrusted():
    prompt = build_user_prompt(ProfileConfig(), _job())
    assert "untrusted data" in prompt.lower()
    assert "AI Engineer" in prompt
