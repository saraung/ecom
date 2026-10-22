"""Thin authenticated MCP-agent chat endpoint (first real connection).

Auth/RBAC: reuses the existing REST chain only —
  app/api/deps.py:get_current_user (JWT -> User, session validity)
  app/api/deps.py:TokenPayload + _assert_admin_audience (admin audience)
Per-tool RBAC (e.g. orders.view on get_order) is enforced inside the MCP
tools themselves; this endpoint adds no permission system of its own.

The caller's raw access JWT (same token get_current_user validated) is
forwarded to the MCP server as an HTTP Authorization header by
app/mcp/agent.py:run_chat. It is never placed in tool arguments and the
LLM never sees it (the `token` param is stripped from LLM schemas/args).
"""

import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, TokenPayload, _assert_admin_audience, oauth2_scheme
from app.core.config import settings
from app.mcp.agent import run_chat, run_chat_events 

router = APIRouter(prefix="/mcp", tags=["MCP Agent"])


class McpHistoryToolCall(BaseModel):
    """One client-reported assistant tool call (validated server-side)."""

    id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=100)
    arguments: Any = None


class McpHistoryMessage(BaseModel):
    """One prior chat turn. Roles are restricted: never system/developer."""

    role: Literal["user", "assistant", "tool"]
    content: str = Field(default="", max_length=8000)
    tool_calls: list[McpHistoryToolCall] = Field(default_factory=list, max_length=10)
    tool_call_id: str = Field(default="", max_length=200)


class McpChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[McpHistoryMessage] = Field(default_factory=list, max_length=20)


class McpChatResponse(BaseModel):
    reply: str
    tools_used: list[str] = []
    pending_action: dict | None = None
    product_cards: list[dict] = []


def resolve_mcp_url(request_base_url: str) -> str:
    """Loopback origin for the agent's internal MCP hop.

    Defaults to our own request origin (correct on localhost). Behind
    tunnels/proxies with a public Host, MCP_LOOPBACK_URL pins it local
    so the hop never traverses the tunnel edge.
    """
    override = (settings.MCP_LOOPBACK_URL or "").strip()
    if override:
        from urllib.parse import urlparse

        parts = urlparse(override if "://" in override else f"http://{override}")
        if parts.scheme == "https" and (parts.hostname or "") in (
            "localhost",
            "127.0.0.1",
            "::1",
        ):
            raise ValueError(
                "MCP_LOOPBACK_URL uses https:// for a localhost target, but "
                "local uvicorn serves plain HTTP — use http://127.0.0.1:8001/mcp/"
            )
        return override.rstrip("/") + "/"
    base = request_base_url if request_base_url.endswith("/") else request_base_url + "/"
    return f"{base}mcp/"


def llm_group_detail(eg: BaseExceptionGroup) -> str | None:
    """Unwrap an anyio task-group error; return LLM-failure detail, if any.

    The MCP client runs inside an anyio task group, which wraps errors
    raised in its body (e.g. run_chat's RuntimeError on LLM failure) in
    an ExceptionGroup. A contained LLM failure still maps to 502.
    """
    flat: list[BaseException] = list(eg.exceptions)
    llm_errors: list[str] = []
    while flat:
        err = flat.pop()
        if isinstance(err, BaseExceptionGroup):
            flat.extend(err.exceptions)
        elif isinstance(err, RuntimeError):
            llm_errors.append(str(err))
    return "; ".join(llm_errors) if llm_errors else None


@router.post("/chat", response_model=McpChatResponse)
async def mcp_chat(
    data: McpChatRequest,
    request: Request,
    user: CurrentUser,
    payload: TokenPayload,
    token: str = Depends(oauth2_scheme),
) -> McpChatResponse:
    _ = user
    _assert_admin_audience(payload)

    # Same process serves /mcp, so loop back to our own origin instead of
    # hardcoding a host/port. request.base_url ends with "/".
    mcp_url = resolve_mcp_url(str(request.base_url))

    try:
        result = await run_chat(
            data.message,
            auth_token=token,
            mcp_url=mcp_url,
            history=[item.model_dump() for item in data.history],
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
    except BaseExceptionGroup as eg:
        # anyio wraps errors raised inside the MCP client's task group.
        # Log every sub-exception server-side: the group repr alone
        # ("1 sub-exception") never says what actually failed.
        detail = llm_group_detail(eg)
        sub = "; ".join(
            f"{type(e).__name__}: {e}" for e in getattr(eg, "exceptions", [])
        )
        print(f"❌ MCP transport failed [{mcp_url}]: {sub or eg}")
        if detail is not None:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail=detail
            ) from eg
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Agent transport failed",
        ) from eg
    return McpChatResponse(
        reply=result["reply"],
        tools_used=result["tools_used"],
        pending_action=result.get("pending_action"),
        product_cards=result.get("product_cards") or [],
    )


def _sse_frame(event: dict) -> str:
    """Serialize one agent event as an SSE frame.

    `event:` carries the discriminator so the client can dispatch without
    parsing JSON twice; `data:` is the full event object.
    """
    return (
        f"event: {event.get('type', 'message')}\n"
        f"data: {json.dumps(event, default=str)}\n\n"
    )


@router.post("/chat/stream")
async def mcp_chat_stream(
    data: McpChatRequest,
    request: Request,
    user: CurrentUser,
    payload: TokenPayload,
    token: str = Depends(oauth2_scheme),
) -> StreamingResponse:
    """Streaming twin of POST /mcp/chat (Server-Sent Events).

    Auth/RBAC identical to the JSON endpoint: the same JWT chain runs
    before the response starts, so an unauthenticated caller still gets a
    normal 401/403. Per-tool RBAC stays inside the MCP tools.

    Frames: `step` (tool starting), `token` (answer delta), then exactly
    one of `final` (reply + optional cards/pending_action) or `error`.
    Axios-style buffering proxies are disabled via X-Accel-Buffering.
    """
    _ = user
    _assert_admin_audience(payload)
    mcp_url = resolve_mcp_url(str(request.base_url))

    async def event_stream():
        try:
            async for event in run_chat_events(
                data.message,
                auth_token=token,
                mcp_url=mcp_url,
                history=[item.model_dump() for item in data.history],
                stream=True,
            ):
                yield _sse_frame(event)
        except ValueError as exc:
            yield _sse_frame({"type": "error", "message": str(exc)})
        except RuntimeError as exc:
            yield _sse_frame({"type": "error", "message": str(exc)})
        except BaseExceptionGroup as eg:
            detail = llm_group_detail(eg)
            print(f"❌ MCP stream failed [{mcp_url}]: {eg}")
            yield _sse_frame(
                {"type": "error", "message": detail or "Agent transport failed"}
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


class McpCancelRequest(BaseModel):
    order_id: str = Field(min_length=1, max_length=100)
    preview_token: str = Field(min_length=1, max_length=2000)
    reason: str = Field(default="", max_length=500)


@router.post("/cancel", response_model=dict)
async def mcp_cancel(
    data: McpCancelRequest,
    user: CurrentUser,
    payload: TokenPayload,
    token: str = Depends(oauth2_scheme),
) -> dict:
    """Execute a button-confirmed MCP order cancellation.

    The click alone authorizes nothing: the tool re-resolves the caller
    from the session JWT, re-checks orders.update, validates the signed
    preview (same user/order/status, unexpired), re-locks the row, and
    re-validates state before the shared service commits.
    """
    _ = user
    _assert_admin_audience(payload)
    from app.mcp.tools.orders import cancel_order as cancel_order_tool

    result = await cancel_order_tool(
        order_id=data.order_id,
        reason=data.reason,
        preview_token=data.preview_token,
        confirmed=True,
        ctx=None,
        token=token,
    )
    if result.get("success") is not True:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("error", "Cancellation failed"),
        )
    return result


class McpRefundRequest(BaseModel):
    order_id: str = Field(min_length=1, max_length=100)
    amount: str | None = Field(default=None, max_length=20)
    reason: str = Field(default="", max_length=500)
    preview_token: str = Field(min_length=1, max_length=2000)


@router.post("/refund", response_model=dict)
async def mcp_refund(
    data: McpRefundRequest,
    user: CurrentUser,
    payload: TokenPayload,
    token: str = Depends(oauth2_scheme),
) -> dict:
    """Execute a button-confirmed MCP refund.

    The click alone authorizes nothing: the tool re-resolves the caller
    from the session JWT, re-checks orders.refund, validates the signed
    preview (same user/order/amount/reason/basis, unexpired), recomputes
    the refundable balance, and executes through request_admin_refund
    (role limits, approval staging, ledger idempotency, PSP handling).
    """
    _ = user
    _assert_admin_audience(payload)
    from app.mcp.tools.orders import issue_refund as issue_refund_tool

    result = await issue_refund_tool(
        order_id=data.order_id,
        amount=data.amount,
        reason=data.reason,
        preview_token=data.preview_token,
        confirmed=True,
        ctx=None,
        token=token,
    )
    if result.get("success") is not True:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("error", "Refund failed"),
        )
    return result


def _mcp_write_error(result: dict, fallback: str) -> None:
    if result.get("success") is not True:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("error", fallback),
        )


class McpProductUpdateRequest(BaseModel):
    product_id: str = Field(min_length=1, max_length=200)
    changes: dict = Field(default_factory=dict)
    preview_token: str = Field(min_length=1, max_length=2000)


@router.post("/products/update", response_model=dict)
async def mcp_product_update(
    data: McpProductUpdateRequest,
    user: CurrentUser,
    payload: TokenPayload,
    token: str = Depends(oauth2_scheme),
) -> dict:
    """Execute a button-confirmed MCP product edit.

    The click alone authorizes nothing: the tool re-resolves the caller
    from the session JWT, re-checks products.update, validates the signed
    preview (same user/target/exact changes/fingerprint, unexpired),
    re-locks the row, and re-validates before the repo function commits.
    """
    _ = user
    _assert_admin_audience(payload)
    from app.mcp.tools.products import update_product as update_product_tool

    result = await update_product_tool(
        product_id=data.product_id,
        changes=data.changes,
        preview_token=data.preview_token,
        confirmed=True,
        ctx=None,
        token=token,
    )
    _mcp_write_error(result, "Product update failed")
    return result


class McpProductPriceRequest(BaseModel):
    product_id: str = Field(min_length=1, max_length=200)
    price: Any = None
    compare_at_price: Any = None
    variant_id: str | None = Field(default=None, max_length=200)
    preview_token: str = Field(min_length=1, max_length=2000)


@router.post("/products/price", response_model=dict)
async def mcp_product_price(
    data: McpProductPriceRequest,
    user: CurrentUser,
    payload: TokenPayload,
    token: str = Depends(oauth2_scheme),
) -> dict:
    """Execute a button-confirmed MCP price change (same guarantees as above)."""
    _ = user
    _assert_admin_audience(payload)
    from app.mcp.tools.products import update_product_price as price_tool

    result = await price_tool(
        product_id=data.product_id,
        price=data.price,
        compare_at_price=data.compare_at_price,
        variant_id=data.variant_id,
        preview_token=data.preview_token,
        confirmed=True,
        ctx=None,
        token=token,
    )
    _mcp_write_error(result, "Price update failed")
    return result


class McpProductDeleteRequest(BaseModel):
    product_id: str = Field(min_length=1, max_length=200)
    preview_token: str = Field(min_length=1, max_length=2000)


@router.post("/products/delete", response_model=dict)
async def mcp_product_delete(
    data: McpProductDeleteRequest,
    user: CurrentUser,
    payload: TokenPayload,
    token: str = Depends(oauth2_scheme),
) -> dict:
    """Execute a button-confirmed MCP product deactivation (soft-delete only)."""
    _ = user
    _assert_admin_audience(payload)
    from app.mcp.tools.products import delete_product as delete_product_tool

    result = await delete_product_tool(
        product_id=data.product_id,
        preview_token=data.preview_token,
        confirmed=True,
        ctx=None,
        token=token,
    )
    _mcp_write_error(result, "Product deletion failed")
    return result


class McpStockAdjustRequest(BaseModel):
    variant_id: str = Field(min_length=1, max_length=200)
    delta: int
    reason: str = Field(min_length=1, max_length=500)
    preview_token: str = Field(min_length=1, max_length=2000)


@router.post("/inventory/adjust", response_model=dict)
async def mcp_stock_adjust(
    data: McpStockAdjustRequest,
    user: CurrentUser,
    payload: TokenPayload,
    token: str = Depends(oauth2_scheme),
) -> dict:
    """Execute a button-confirmed MCP stock adjustment (same guarantees)."""
    _ = user
    _assert_admin_audience(payload)
    from app.mcp.tools.inventory import adjust_stock as adjust_stock_tool

    result = await adjust_stock_tool(
        variant_id=data.variant_id,
        delta=data.delta,
        reason=data.reason,
        preview_token=data.preview_token,
        confirmed=True,
        ctx=None,
        token=token,
    )
    _mcp_write_error(result, "Stock adjustment failed")
    return result
