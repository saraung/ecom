# tests/test_mcp_agent_stream.py
"""Streaming agent path (fully mocked: no Groq, no MCP server, no DB).

Covers run_chat_events event ordering (step -> token -> final), the
non-streaming wrapper contract preserved by run_chat, parallel tool
execution, and the SSE frame serializer used by POST /mcp/chat/stream.
"""
import asyncio
import inspect
import json
from types import SimpleNamespace

import pytest
from groq.resources.chat.completions import AsyncCompletions

from app.core.config import settings

settings.ENVIRONMENT = "test"  # keep the APScheduler sweep out of tests

from fastapi.testclient import TestClient  # noqa: E402

import app.api.v1.mcp as mcp_api  # noqa: E402
import app.mcp.agent as agent_mod  # noqa: E402
from app.api.deps import get_current_user  # noqa: E402
from app.api.v1.mcp import _sse_frame  # noqa: E402
from app.main import app  # noqa: E402
from app.mcp.agent import run_chat, run_chat_events  # noqa: E402

TOOLS = [
    SimpleNamespace(
        name="list_orders",
        description="List order summaries",
        input_schema={"type": "object", "properties": {"limit": {"type": "integer"}}},
    ),
    SimpleNamespace(
        name="get_order",
        description="Get an order",
        input_schema={"type": "object", "properties": {"order_id": {"type": "string"}}},
    ),
]


class FakeMCPClient:
    instances = []

    def __init__(self, *args, **kwargs):
        self.calls = []
        self.handler = lambda name, args: {"success": True}
        FakeMCPClient.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def list_tools(self):
        return SimpleNamespace(tools=TOOLS)

    async def call_tool(self, name, arguments):
        self.calls.append((name, dict(arguments)))
        return SimpleNamespace(
            content=[SimpleNamespace(text=json.dumps(self.handler(name, arguments)))]
        )


def _tool_call(call_id, name, args):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=json.dumps(args)),
    )


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    monkeypatch.setattr(agent_mod, "Client", FakeMCPClient)
    FakeMCPClient.instances.clear()
    agent_mod._PAGINATION_MEMORY.clear()
    yield
    agent_mod._PAGINATION_MEMORY.clear()


def run(coro):
    return asyncio.run(coro)


def script_stream(monkeypatch, scripts):
    """Queue of stream scripts; each is a list of ('delta'|'done', ...)."""

    async def fake_stream(messages, tools, stage="initial"):
        script = scripts.pop(0)
        for item in script:
            if item[0] == "delta":
                yield {"kind": "delta", "text": item[1]}
            elif item[0] == "done":
                yield {"kind": "done", "content": item[1], "tool_calls": item[2]}

    monkeypatch.setattr(agent_mod, "_groq_stream", fake_stream)


async def _collect(message):
    events = []
    async for ev in run_chat_events(
        message, auth_token="tok", mcp_url="http://x/mcp/", stream=True
    ):
        events.append(ev)
    return events


def test_stream_event_order_step_then_tokens_then_final(monkeypatch):
    script_stream(
        monkeypatch,
        [
            # Turn 1: the model asks for a tool (no user-facing text).
            [("done", "", [_tool_call("c0", "list_orders", {"limit": 5})])],
            # Turn 2: the answer streams token by token, no more tools.
            [("delta", "Here are "), ("delta", "5 orders."), ("done", "Here are 5 orders.", [])],
        ],
    )

    async def go():
        def patched_init(self, *a, **k):
            self.calls = []
            self.handler = lambda name, args: {"success": True, "orders": []}
            FakeMCPClient.instances.append(self)

        monkeypatch.setattr(FakeMCPClient, "__init__", patched_init)
        return await _collect("show 5 orders")

    events = run(go())
    kinds = [e["type"] for e in events]
    assert kinds == ["step", "token", "token", "final"]
    assert events[0]["tool"] == "list_orders" and events[0]["label"]
    assert "".join(e["text"] for e in events if e["type"] == "token") == "Here are 5 orders."
    final = events[-1]
    assert final["reply"] == "Here are 5 orders."
    assert final["tools_used"] == ["list_orders"]


def test_stream_parallel_tools_single_step_phase(monkeypatch):
    script_stream(
        monkeypatch,
        [
            [
                (
                    "done",
                    "",
                    [
                        _tool_call("c0", "list_orders", {"limit": 5}),
                        _tool_call("c1", "get_order", {"order_id": "ORD-1"}),
                    ],
                )
            ],
            [("delta", "done"), ("done", "done", [])],
        ],
    )

    async def go():
        def patched_init(self, *a, **k):
            self.calls = []
            self.handler = lambda name, args: {"success": True}
            FakeMCPClient.instances.append(self)

        monkeypatch.setattr(FakeMCPClient, "__init__", patched_init)
        return await _collect("orders and order")

    events = run(go())
    steps = [e for e in events if e["type"] == "step"]
    assert {s["tool"] for s in steps} == {"list_orders", "get_order"}
    assert events[-1]["tools_used"] == ["list_orders", "get_order"]


def test_stream_runtime_error_propagates(monkeypatch):
    async def boom(messages, tools, stage="initial"):
        raise RuntimeError("LLM request failed")
        yield  # pragma: no cover - marks this as an async generator

    monkeypatch.setattr(agent_mod, "_groq_stream", boom)
    with pytest.raises(RuntimeError):
        run(_collect("hi"))


def test_run_chat_wrapper_uses_non_stream_complete(monkeypatch):
    # run_chat must stay on _groq_complete (stream=False) for callers/tests.
    def groq_turn(content=None, calls=()):
        tool_calls = [
            SimpleNamespace(id=f"c{i}", function=SimpleNamespace(name=n, arguments=json.dumps(a)))
            for i, (n, a) in enumerate(calls)
        ]
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=tool_calls))]
        )

    responses = [groq_turn("hello there")]

    async def fake_complete(messages, tools, stage="initial"):
        return responses.pop(0)

    monkeypatch.setattr(agent_mod, "_groq_complete", fake_complete)
    res = run(run_chat("hi", auth_token="tok", mcp_url="http://x/mcp/"))
    assert res == {"reply": "hello there", "tools_used": []}


def test_groq_stream_only_passes_sdk_supported_kwargs(monkeypatch):
    """Regression for the prod break: _groq_stream once passed
    stream_options, which groq 1.7.0's AsyncCompletions.create does not
    accept, so every streamed turn died on a TypeError at turn 1.

    Drives the real _groq_stream against a fake async client that records
    the kwargs, then asserts each one exists on the installed SDK method.
    """
    accepted = set(inspect.signature(AsyncCompletions.create).parameters)
    captured = {}

    class _EmptyStream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    class _FakeCompletions:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return _EmptyStream()

    class _FakeClient:
        def __init__(self):
            self.chat = SimpleNamespace(completions=_FakeCompletions())

    monkeypatch.setattr(
        agent_mod, "_active_async_client",
        lambda: (_FakeClient(), "test-model", "groq"),
    )

    async def go():
        events = []
        async for ev in agent_mod._groq_stream(
            [{"role": "user", "content": "hi"}], []
        ):
            events.append(ev)
        return events

    events = run(go())
    assert events and events[-1]["kind"] == "done"
    unsupported = set(captured) - accepted
    assert not unsupported, f"unsupported kwargs sent to groq: {unsupported}"


def test_sse_frame_format():
    frame = _sse_frame({"type": "token", "text": "hi\n"})
    assert frame.startswith("event: token\ndata: ")
    assert frame.endswith("\n\n")
    payload = json.loads(frame.split("data: ", 1)[1].strip())
    assert payload == {"type": "token", "text": "hi\n"}


def test_stream_endpoint_sse_and_error_frames(monkeypatch):
    # A single TestClient context: the MCP session manager's lifespan may
    # only run once per app instance, so both scenarios share one client.
    calls = {"n": 0}

    async def fake_events(message, *, auth_token, mcp_url, history, stream):
        assert stream is True
        calls["n"] += 1
        if calls["n"] == 1:
            yield {"type": "step", "tool": "list_orders", "label": "Looking up orders"}
            yield {"type": "token", "text": "Hi"}
            yield {
                "type": "final",
                "reply": "Hi",
                "tools_used": ["list_orders"],
                "product_cards": [],
            }
        else:
            raise RuntimeError("LLM request failed")

    monkeypatch.setattr(mcp_api, "run_chat_events", fake_events)
    monkeypatch.setattr(mcp_api, "_assert_admin_audience", lambda payload: None)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="test")
    try:
        # NOT a context manager: TestClient only runs app lifespan inside
        # `with`, and starting it here would run the MCP session manager
        # (which may only start once per process) and break sibling tests
        # that also boot the app.
        client = TestClient(app)
        ok = client.post(
            "/api/v1/mcp/chat/stream",
            json={"message": "hi", "history": []},
            headers={"Authorization": "Bearer test-token"},
        )
        assert ok.status_code == 200
        assert ok.headers["content-type"].startswith("text/event-stream")
        assert ok.headers.get("x-accel-buffering") == "no"
        assert "event: step" in ok.text
        assert "event: token" in ok.text
        assert "event: final" in ok.text
        assert '"reply": "Hi"' in ok.text

        err = client.post(
            "/api/v1/mcp/chat/stream",
            json={"message": "hi", "history": []},
            headers={"Authorization": "Bearer test-token"},
        )
        assert err.status_code == 200
        assert "event: error" in err.text
        assert "LLM request failed" in err.text
    finally:
        app.dependency_overrides.clear()
