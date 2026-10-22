import asyncio
import json
import re

import httpx2
from groq import APIConnectionError, APITimeoutError, APIStatusError, AsyncGroq, Groq
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from app.core.config import settings
from app.core.security import decode_access_token


MAX_RETRY_ATTEMPTS = 2

# Per-LLM-call timeout. 20s proved too aggressive once every call carries
# ~3.5K tokens of fixed overhead (16 tool schemas + system prompt) plus
# history and growing tool results: heavier queries intermittently timed
# out on the thinking model while light ones passed. 60s gives large
# contexts headroom; fast calls are unaffected on either provider.
LLM_TIMEOUT_SECONDS = 60.0

# Output budget. 500 proved too small for reasoning models (gpt-oss counts
# hidden chain-of-thought against it): tool-heavy turns came back with empty
# content, surfacing as "(no response)". 1500 leaves headroom for reasoning
# plus a full reply; output pricing makes the cost negligible.
LLM_MAX_TOKENS = 1500

# Low sampling temperature for consistent tool selection across identical
# questions (same prompt previously sampled different tool paths). Kept above
# zero so final-answer phrasing stays natural.
LLM_TEMPERATURE = 0.2


groq = Groq(
    api_key=settings.GROQ_API_KEY,
    timeout=LLM_TIMEOUT_SECONDS,
    max_retries=0,
)


# ---------------------------------------------------------
# CENTRALIZED LLM PROVIDER SELECTION (env-only switch)
# ---------------------------------------------------------
#
# MCP_LLM_PROVIDER=groq   -> Groq endpoint (default, unchanged behavior)
# MCP_LLM_PROVIDER=gemini -> Gemini via its OpenAI-compatible endpoint
# MCP_LLM_MODEL overrides the provider default model in both cases.
# Both clients expose the same chat.completions.create interface, so the
# tool loop, schemas, history, and retries work unchanged on either.

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
GROQ_DEFAULT_MODEL = "openai/gpt-oss-120b"
GEMINI_DEFAULT_MODEL = "gemini-3.1-flash-lite"


def _check_model_provider_match(provider: str, explicit_model: str) -> None:
    """Fail fast when MCP_LLM_MODEL names a model from the other provider.

    A stale MODEL (e.g. gemini-3.1-flash-lite left over after switching
    PROVIDER to groq) otherwise surfaces as a cryptic mid-chat provider
    error. Custom/fine-tuned names pass through untouched — only the known
    model families of the *other* provider are rejected. Never includes
    keys in the message.
    """
    if not explicit_model:
        return
    lowered = explicit_model.lower()
    # Substring (not prefix) match: provider-qualified names like
    # "openai/gpt-oss-20b" must also trip the guard. These family names are
    # vendor-specific enough that a custom model containing them is almost
    # certainly a stale cross-provider value, not a fine-tune.
    if provider == "groq" and "gemini" in lowered:
        raise RuntimeError(
            f"MCP_LLM_MODEL '{explicit_model}' looks like a Gemini model but "
            "MCP_LLM_PROVIDER is 'groq'; set MCP_LLM_MODEL to a Groq model "
            f"(e.g. '{GROQ_DEFAULT_MODEL}') or unset it to use the default"
        )
    if provider == "gemini" and (
        "gpt-oss" in lowered
        or lowered.startswith(("llama-", "mixtral-", "qwen-"))
        or lowered == GROQ_DEFAULT_MODEL.lower()
    ):
        raise RuntimeError(
            f"MCP_LLM_MODEL '{explicit_model}' looks like a Groq model but "
            "MCP_LLM_PROVIDER is 'gemini'; set MCP_LLM_MODEL to a Gemini model "
            f"(e.g. '{GEMINI_DEFAULT_MODEL}') or unset it to use the default"
        )


def _llm_config() -> tuple[str, str]:
    """Resolve (provider, model) from settings; raise without leaking keys."""
    provider = (settings.MCP_LLM_PROVIDER or "groq").strip().lower()
    if provider not in ("groq", "gemini"):
        raise ValueError(
            f"Unknown MCP_LLM_PROVIDER '{settings.MCP_LLM_PROVIDER}'; use 'groq' or 'gemini'"
        )
    default_model = GEMINI_DEFAULT_MODEL if provider == "gemini" else GROQ_DEFAULT_MODEL
    explicit_model = (settings.MCP_LLM_MODEL or "").strip()
    model = explicit_model or default_model
    _check_model_provider_match(provider, explicit_model)
    if provider == "groq" and not settings.GROQ_API_KEY:
        raise RuntimeError("MCP LLM provider 'groq' needs GROQ_API_KEY to be set")
    if provider == "gemini" and not settings.GEMINI_API_KEY:
        raise RuntimeError("MCP LLM provider 'gemini' needs GEMINI_API_KEY to be set")
    return provider, model


def _active_client():
    """Return the (chat client, model) for the selected provider."""
    provider, model = _llm_config()
    if provider == "gemini":
        from openai import OpenAI

        return (
            OpenAI(
                base_url=GEMINI_BASE_URL,
                api_key=settings.GEMINI_API_KEY,
                timeout=LLM_TIMEOUT_SECONDS,
                max_retries=0,
            ),
            model,
        )
    return groq, model


def _active_async_client():
    """Async client for the selected provider (streaming path only).

    Mirrors _active_client but returns the asyncio flavour so the SSE
    endpoint can stream deltas without bridging a worker thread. Only the
    streaming code path uses this; the non-streaming path (and its tests)
    keep the sync client via _groq_complete.
    """
    provider, model = _llm_config()
    if provider == "gemini":
        from openai import AsyncOpenAI

        return (
            AsyncOpenAI(
                base_url=GEMINI_BASE_URL,
                api_key=settings.GEMINI_API_KEY,
                timeout=LLM_TIMEOUT_SECONDS,
                max_retries=0,
            ),
            model,
            provider,
        )
    return (
        AsyncGroq(
            api_key=settings.GROQ_API_KEY,
            timeout=LLM_TIMEOUT_SECONDS,
            max_retries=0,
        ),
        model,
        provider,
    )


async def main():
    # Resolve once up front: the CLI follows the same MCP_LLM_PROVIDER
    # switch as the server path instead of pinning Groq. Raises here
    # (unknown provider / missing key / model mismatch) before any MCP
    # connection, so a bad env fails fast with a clear message.
    client, model = _active_client()
    provider = (settings.MCP_LLM_PROVIDER or "groq").strip().lower()
    print(f"MCP LLM: provider={provider} model={model}")

    async with Client("http://127.0.0.1:8001/mcp/") as mcp_client:

        # 1. Discover MCP tools
        result = await mcp_client.list_tools()

        tools = []

        for tool in result.tools:
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.input_schema,
                    },
                }
            )

        # 2. Get user request
        user_input = input("\nYou: ")

        messages = [
            {
                "role": "system",
                "content": (
                    "You are an ecommerce agent. "
                    "You have access to tools through an MCP server. "
                    "Determine what information is actually needed before calling tools. "
                    "Use the minimum number of tools necessary. "
                    "Do not call a tool if you already have the required information. "
                    "For multi-step requests, use the result of one tool as input to the next tool. "
                    "Never invent customer IDs, order IDs, statuses, product names, SKUs, "
                    "prices, or other ecommerce data. "
                    "Never guess a product from an order total — product identity "
                    "comes only from get_order items[]. "
                    "After obtaining enough information, stop calling tools and answer the user. "
                    "If a tool returns success=false and retryable=true, "
                    "you may retry the same tool with the same arguments. "
                    "Do not retry non-retryable errors. "

                    "ORDER PRESENTATION: "
                    "When presenting order lists to the user, "
                    "show only Order Number, Status, Payment Status, Grand Total, and Placed At. "
                    "Do not display internal UUID fields such as id or user_id "
                    "unless the user explicitly asks for them. "
                    "Do not expose internal database identifiers unnecessarily. "
                ),
            },
            {
                "role": "user",
                "content": user_input,
            },
        ]

        # Tracks retry attempts for a specific tool + arguments.
        #
        # Example:
        #
        # ("test_failure", "{}") -> 1
        #
        # A successful call removes its retry counter.
        retry_counts = {}

        # 3. Agent loop
        while True:

            print("\nASKING LLM...")

            completion = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                max_tokens=LLM_MAX_TOKENS,
                temperature=LLM_TEMPERATURE,
            )

            assistant_message = completion.choices[0].message

            print("LLM DECISION:")
            print(assistant_message.tool_calls)

            # 4. LLM has finished and does not need another tool
            if not assistant_message.tool_calls:

                print("\nFINAL ANSWER:")
                print(assistant_message.content)

                break

            # 5. Add assistant's tool-call message
            messages.append(
                {
                    "role": "assistant",
                    "content": assistant_message.content,
                    "tool_calls": [
                        _passthrough_tool_call(call, _stripped_arguments_json(call))
                        for call in assistant_message.tool_calls
                    ],
                }
            )

            # 6. Execute every requested tool through MCP
            for call in assistant_message.tool_calls:

                tool_name = call.function.name
                arguments = json.loads(call.function.arguments)

                # -------------------------------------------------
                # APPLICATION-LEVEL DESTRUCTIVE ACTION CHECK
                # -------------------------------------------------
                #
                # The LLM is NOT trusted to decide whether a
                # destructive operation is confirmed.
                #
                # Even if the LLM sends:
                #
                #     confirmed=true
                #
                # we remove that value first.
                #
                # The application asks the actual user for
                # confirmation and controls the final value.
                # -------------------------------------------------

                if tool_name == "cancel_order":

                    # Never trust the LLM's confirmation value.
                    arguments.pop("confirmed", None)

                    print("\n⚠️ DESTRUCTIVE ACTION")
                    print(
                        f"Order {arguments.get('order_id')} "
                        "will be cancelled."
                    )

                    confirmation = input(
                        "Type 'yes' to confirm cancellation: "
                    ).strip().lower()

                    if confirmation != "yes":

                        print("\nCancellation cancelled by user.")

                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": call.id,
                                "content": json.dumps(
                                    {
                                        "success": False,
                                        "error": (
                                            "User did not confirm "
                                            "the cancellation."
                                        ),
                                    }
                                ),
                            }
                        )

                        continue

                    # IMPORTANT:
                    #
                    # This value is controlled by the application,
                    # not by the LLM.
                    arguments["confirmed"] = True

                    print(
                        "\nUser confirmed cancellation."
                    )

                # Create a stable key for this exact operation.
                #
                # Same tool + same arguments = same logical operation.
                retry_key = (
                    tool_name,
                    json.dumps(
                        arguments,
                        sort_keys=True,
                    ),
                )

                retry_count = retry_counts.get(
                    retry_key,
                    0,
                )

                print("\nMCP CALL:")
                print(f"Tool: {tool_name}")
                print(f"Arguments: {arguments}")

                # -------------------------------------------------
                # HARD RETRY LIMIT
                # -------------------------------------------------
                #
                # This prevents the LLM from repeatedly calling
                # the same failed operation forever.
                #
                if retry_count >= MAX_RETRY_ATTEMPTS:

                    print(
                        f"\nBLOCKED: {tool_name} reached "
                        f"the maximum retry limit."
                    )

                    blocked_result = (
                        "Tool execution blocked because "
                        "the maximum retry limit was reached."
                    )

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": blocked_result,
                        }
                    )

                    continue

                # -------------------------------------------------
                # EXECUTE MCP TOOL
                # -------------------------------------------------

                tool_result = await mcp_client.call_tool(
                    tool_name,
                    arguments,
                )

                print("MCP RESULT:")
                print(tool_result.content)

                # Combine all returned text blocks.
                #
                # An MCP tool can return multiple TextContent
                # blocks, so we should not assume only one exists.
                result_text = "\n".join(
                    item.text
                    for item in tool_result.content
                    if hasattr(item, "text")
                )

                # -------------------------------------------------
                # CHECK STRUCTURED TOOL RESULT
                # -------------------------------------------------

                try:
                    result_data = json.loads(result_text)

                    # Tool reported a failure.
                    if result_data.get("success") is False:

                        print("\nTOOL ERROR:")
                        print(result_data.get("error"))

                        # The tool says this failure can be retried.
                        if result_data.get("retryable") is True:

                            retry_counts[retry_key] = (
                                retry_count + 1
                            )

                            print(
                                "This error is retryable."
                            )

                            print(
                                f"Retry attempt: "
                                f"{retry_counts[retry_key]}/"
                                f"{MAX_RETRY_ATTEMPTS}"
                            )

                        else:
                            print(
                                "This error is not retryable."
                            )

                    # Tool succeeded.
                    else:

                        # Clear any previous retry count for this
                        # exact operation.
                        retry_counts.pop(
                            retry_key,
                            None,
                        )

                        print("Tool execution successful.")

                except json.JSONDecodeError:

                    # Not every tool has to return JSON.
                    #
                    # For example, a tool could return plain text.
                    print(
                        "MCP result is not structured JSON."
                    )

                # -------------------------------------------------
                # GIVE MCP RESULT BACK TO LLM
                # -------------------------------------------------

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": result_text,
                    }
                )

            # 7. Loop back to the LLM


# ---------------------------------------------------------
# SERVER-SIDE SINGLE-TURN RUN (used by POST /api/v1/mcp/chat)
# ---------------------------------------------------------
#
# Same Groq model + tool-calling behavior as main() above, but
# non-interactive and bounded: the caller's access JWT travels as an
# HTTP Authorization header on the MCP transport (never as a tool
# argument, never visible to the LLM). The `token` tool parameter is
# stripped from every LLM-facing schema AND from every LLM-supplied
# argument set, so the model cannot see, set, or override auth.

AGENT_MODEL = GROQ_DEFAULT_MODEL
AGENT_MAX_TURNS = 5

AGENT_SYSTEM_PROMPT = (
    "You are an ecommerce agent. "
    "You have access to tools through an MCP server. "
    "Determine what information is actually needed before calling tools. "
    "Use the minimum number of tools necessary. "
    "Do not call a tool if you already have the required information. "
    "For multi-step requests, use the result of one tool as input to the next tool. "
    "Never invent customer IDs, order IDs, statuses, product names, SKUs, "
    "prices, or other ecommerce data. "
    "Never guess a product from an order total, price proximity, or catalog "
    "memory — product identity comes only from a tool result. "
    "After obtaining enough information, stop calling tools and answer the user. "
    "If a tool returns success=false and retryable=true, "
    "you may retry the same tool with the same arguments. "
    "Do not retry non-retryable errors."
)

# Order line-item routing. get_order returns items[] (product_name,
# variant_sku, quantity, unit_price, line_total); list_orders returns
# summary rows only. These rules stop price-based product guessing.
ORDER_ITEMS_GUIDANCE = (
    "Order line-item rules: "
    "any question about which products/SKUs/quantities are in an order "
    "must call get_order with the order number or id and quote "
    "items[].product_name, items[].variant_sku, items[].quantity, "
    "items[].unit_price, and items[].line_total verbatim. "
    "list_orders never contains product names — do not answer product "
    "questions from it; call get_order instead. "
    "If get_order returns no items or an empty items list, say the line "
    "items are not available — never infer a product from grand_total, "
    "item_count, or catalog memory. "
)

# One-shot recovery nudge when a turn finishes with empty content and no
# tool calls (reasoning models can spend the output budget on
# chain-of-thought). Phrased to reuse already-fetched tool results instead
# of starting over.
EMPTY_REPLY_NUDGE = (
    "Your previous reply was empty. Using the information already returned "
    "above, answer the user's original question now in plain human-readable "
    "language without calling any further tools."
)

# Date-relative routing. list_orders has no date parameters, so "today",
# "yesterday", and "this week" resolve by listing recent orders and
# filtering placed_at in context. The server injects the current UTC date
# into the system prompt (see _today_context) so "today" is deterministic
# instead of inferred — this stops both refusals ("tool doesn't support
# date filtering") and invented date-capable tools.
DATE_GUIDANCE = (
    "Date rules: "
    "the current UTC date is given in the system prompt — use it to resolve "
    "relative dates like today, yesterday, or this week. "
    "list_orders accepts from_date and to_date (YYYY-MM-DD): answer date "
    "questions by passing the resolved range directly (e.g. today means "
    "from_date=today and to_date=today), never by listing unfiltered rows. "
    "Never claim date questions cannot be answered, and never invent extra "
    "date-filtering tools. "
)

# Pagination rules for list_orders (supports limit/offset and echoes
# limit, offset, returned_count, total_matching). Appended to the system
# prompt for server-side runs so follow-ups resolve against real context.
PAGINATION_GUIDANCE = (
    "Pagination rules for list_orders: "
    "'Show me 5 orders' means limit=5, offset=0. "
    "An explicit range like 'orders 6 through 10' means offset = first-1 "
    "and limit = last-first+1 (so 6 through 10 is limit=5, offset=5). "
    "'Next N' or 'more' continues the previous page from THIS conversation "
    "with the SAME filters: offset = previous offset + previous limit. "
    "'Previous N' goes back one page: offset = previous offset - previous "
    "limit, floored at 0. "
    "If the user says 'next' or 'more' but there is NO previous page in "
    "this conversation, do NOT invent an offset — ask which page they mean "
    "or start from the first page and say so. "
    "For destructive actions (cancel_order, issue_refund, update_product, "
    "update_product_price, delete_product, adjust_stock): first call the "
    "tool without confirmed to obtain the preview, present the preview to "
    "the user and wait — never set confirmed yourself and never invent a "
    "preview token."
)

# Stock-query routing rules. The inventory tools already filter in SQL;
# these rules keep the model on the single-query path instead of fanning
# out across per-product lookups.
STOCK_ROUTING_GUIDANCE = (
    "Stock routing rules: "
    "low-stock, out-of-stock, running-low, and restock-needed questions "
    "must call list_low_stock_products directly, using the default "
    "threshold unless the user specifies one — do not scan products "
    "individually. "
    "A request for the stock of a specific product or SKU must call "
    "check_stock (or check_product_inventory) first: it resolves exact "
    "SKUs/IDs/slugs and falls back to a word match over product names and "
    "variant SKUs/attributes, flagging inexact hits with match=fuzzy. "
    "Quote a fuzzy hit's variant_sku, attributes, and stock verbatim. "
    "Only when check_stock returns success=false may you fall back to "
    "list_products with a search term plus get_product — and you must try "
    "that before ever telling the user a product is not in the catalog. "
    "If check_stock returns several candidates (match=ambiguous), ask the "
    "user which SKU they mean instead of guessing."
)

# Price-extreme routing. list_products sorts in PostgreSQL, so cheapest /
# most-expensive questions are one precise call — never a page scan and
# never per-product get_product calls for ranking. (Variant price_overrides
# ride along in the row payload for any caveat worth stating.)
PRICE_GUIDANCE = (
    "Price rules: "
    "cheapest, most-expensive, lowest-price, and highest-price questions "
    "must call list_products with sort_by=price and sort_dir=asc (cheapest) "
    "or desc (most-expensive), limit 1 (or N for top-N) — then quote the "
    "row verbatim with its currency code. "
    "Never scan unpaginated pages or call get_product per product to rank. "
)

# Analytics routing rules. Figures arrive precomputed — quote them
# verbatim with their period labels, never recompute or estimate.
ANALYTICS_GUIDANCE = (
    "Analytics routing rules: "
    "totals, revenue, average order value, and period comparisons go to "
    "sales_summary; time series go to sales_trend; product rankings, "
    "categories, slow movers, and declining products go to "
    "product_performance with the matching view — never sum rows in "
    "Python or SQL-side yourself. "
    "Revenue counts settled sales only; day boundaries are UTC. "
    "State comparison periods exactly as echoed (current vs previous). "
    "Month questions need explicit ranges, not presets: 'this month vs "
    "last month' means one sales_summary call with from_date set to the "
    "first of this month through today, plus one with from_date and "
    "to_date covering the full prior month (pass preset=null with explicit "
    "dates, which always win) — then compare the two totals and always "
    "note when a partial month is compared against a full month. "
    "Payment questions go to get_payment_status; refund ledger questions "
    "to list_refunds; unresolved-payment work to list_payment_issues; a "
    "specific refund to get_refund_status. "
    "Quote the live/source field exactly: live means provider-confirmed, "
    "ledger means local records only, stale/unknown means neither — never "
    "present cached or dummy status as verified success."
)

# Response-formatting rules for MCP tool results. The tools return fixed
# structured fields; the model must present them readably instead of
# dumping raw JSON, shifting values between columns, or inventing numbers.
PRESENTATION_GUIDANCE = (
    "When presenting MCP tool results, answer in clear human-readable "
    "language with appropriate labels, not raw JSON. "
    "Choose the fields and detail level from the user's question and the "
    "actual tool results: show every relevant returned field, marking "
    "missing ones -; never omit provided information and never invent values. "
    "For order rows from get_order or list_orders, render one table row "
    "per order with columns in this exact order: row number, order_number, "
    "status, payment_status, grand_total, placed_at. "
    "Copy each value verbatim into its own column. "
    "Format money with two decimals and thousands separators, prefixed by "
    "the currency symbol/code from the currency guidance (never bare $ and "
    "never an assumed currency); plain "
    "counts as whole numbers, and timestamps in a readable "
    "YYYY-MM-DD HH:MM form. "
    "Use a markdown table for multiple rows and a short labeled list for "
    "a single record. "
    "Number rows as offset + row_index + 1 using the echoed offset from the "
    "tool result, so the second page of 5 continues at 6; use page-local "
    "1..N numbering only when no offset is known. "
    "For counts, use only the database-derived total_matching — "
    "never estimate totals. "
    "For refund previews, the labeled breakdown is final: order_total is "
    "the order's grand total, restocking_fee is already retained by the "
    "store inside that calculation, and refund_to_customer is the exact "
    "amount the customer receives — quote all three verbatim and never "
    "subtract the fee from the refund figure again. "
    "For order line items from get_order, list each item as "
    "'product_name × quantity @ unit_price = line_total' with variant_sku "
    "in parentheses; quote every value verbatim from items[] and never "
    "substitute a catalog product or price guess. "
    "Keep answers compact: separate list items, numbered items, and table "
    "rows with single newlines — never blank lines between them, one blank "
    "line only between sections. Variant lists with 3 or more variants "
    "render as a markdown table (SKU | attributes | price | stock), never "
    "as spaced-out bullets."
)
# Encourage batching independent lookups into one assistant turn so they
# execute concurrently instead of across multiple model round trips
# (Groq: "parallel tool use dramatically reduces latency").
PARALLEL_TOOL_GUIDANCE = (
    "Latency rule: when a request needs several INDEPENDENT lookups, request "
    "them together in the same turn as multiple parallel tool calls instead "
    "of one call per turn. Only sequence calls when a later call depends on "
    "an earlier result (for example resolving an order before acting on it). "
)

# Short-term memory of the last successful list_orders page per user
# (JWT subject). Lets stateless follow-ups like "show me the next 5"
# resolve to a real offset. Plain in-process dict: bounded, no new system.
_PAGINATION_MEMORY: dict[str, dict] = {}
_PAGINATION_MEMORY_MAX = 500


def _pagination_user_key(auth_token: str) -> str:
    """Stable per-user memory key from the already-validated JWT (sub email)."""
    try:
        payload = decode_access_token(auth_token or "")
    except Exception:
        payload = None
    sub = (payload or {}).get("sub")
    return f"sub:{sub}" if sub else "anon"


def _remember_pagination(user_key: str, arguments: dict, result: dict) -> None:
    """Record a successful list_orders page; echo values are server truth."""
    if not isinstance(arguments, dict) or not isinstance(result, dict):
        return
    if result.get("success") is not True:
        return
    try:
        entry = {
            "status": arguments.get("status"),
            "payment_status": arguments.get("payment_status"),
            "limit": int(result.get("limit", arguments.get("limit", 0))),
            "offset": int(result.get("offset", arguments.get("offset", 0))),
            "total_matching": int(result.get("total_matching", 0)),
        }
    except (TypeError, ValueError):
        return
    _PAGINATION_MEMORY[user_key] = entry
    while len(_PAGINATION_MEMORY) > _PAGINATION_MEMORY_MAX:
        _PAGINATION_MEMORY.pop(next(iter(_PAGINATION_MEMORY)))


def _pagination_context(user_key: str) -> str | None:
    """Human-readable previous-page context for the LLM, if any exists."""
    entry = _PAGINATION_MEMORY.get(user_key)
    if not entry:
        return None
    filters = []
    if entry.get("status"):
        filters.append(f"status={entry['status']}")
    if entry.get("payment_status"):
        filters.append(f"payment_status={entry['payment_status']}")
    filter_text = ", ".join(filters) if filters else "no filters"
    return (
        "Previous page context (most recent list_orders call in this session): "
        f"{filter_text}, limit={entry['limit']}, offset={entry['offset']}, "
        f"total_matching={entry['total_matching']}. "
        "If the user asks for 'next'/'more' with the same filters, continue "
        "from offset = previous offset + previous limit."
    )


def _with_pagination_context(user_key: str, message: str) -> str:
    """Append previous-page context to the user message, when one exists."""
    context = _pagination_context(user_key)
    text = message.strip()
    return f"{text}\n\n[{context}]" if context else text


# Conversation history carried across /mcp/chat requests (the frontend
# sends prior turns; the server rebuilds Groq messages from them).
# The server stays authoritative: system prompt and tool set always come
# from here, client history is validated, truncated, and capped.
MAX_HISTORY_MESSAGES = 10
MAX_HISTORY_CHARS = 2000
_HISTORY_ROLES = ("user", "assistant", "tool")


def _sanitize_history(raw_history, tool_names: set[str]) -> list[dict]:
    """Rebuild Groq message dicts from untrusted client history.

    Keeps only user/assistant/tool roles (never system/developer), drops
    unknown tool names and malformed entries, pops any `token` argument,
    truncates long contents, and keeps only the most recent window.
    """
    cleaned: list[dict] = []
    if not isinstance(raw_history, (list, tuple)):
        return cleaned
    for item in raw_history:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        if role not in _HISTORY_ROLES:
            continue
        content = item.get("content", "")
        if not isinstance(content, str):
            continue
        content = content.strip()[:MAX_HISTORY_CHARS]
        if role in ("user", "tool"):
            entry: dict = {"role": role, "content": content}
            if role == "tool":
                call_id = item.get("tool_call_id", "")
                if not isinstance(call_id, str) or not call_id.strip():
                    continue
                entry["tool_call_id"] = call_id.strip()[:200]
            if role == "user" and not content:
                continue
            cleaned.append(entry)
            continue
        # Assistant turn: optional tool_calls, validated structurally.
        valid_calls = []
        calls = item.get("tool_calls", [])
        if isinstance(calls, (list, tuple)):
            for call in calls:
                if not isinstance(call, dict):
                    continue
                call_id = call.get("id", "")
                name = call.get("name", "")
                if (
                    not isinstance(call_id, str)
                    or not call_id.strip()
                    or not isinstance(name, str)
                    or name not in tool_names
                ):
                    continue
                arguments = call.get("arguments", {})
                if isinstance(arguments, dict):
                    arguments = dict(arguments)
                    arguments.pop("token", None)
                    try:
                        arguments = json.dumps(arguments)
                    except (TypeError, ValueError):
                        continue
                elif isinstance(arguments, str):
                    try:
                        parsed = json.loads(arguments) if arguments.strip() else {}
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(parsed, dict):
                        continue
                    parsed.pop("token", None)
                    arguments = json.dumps(parsed)
                else:
                    continue
                valid_calls.append(
                    {
                        "id": call_id.strip()[:200],
                        "type": "function",
                        "function": {"name": name, "arguments": arguments[:4000]},
                        # Preserve provider metadata the client echoes back
                        # (e.g. Gemini's extra_content.thought_signature).
                        # Unknown keys are inert data; auth is still stripped
                        # from arguments above, never trusted from here.
                        **{
                            k: v
                            for k, v in call.items()
                            if k not in ("id", "type", "function", "name", "arguments")
                        },
                    }
                )
        entry = {"role": "assistant", "content": content}
        if valid_calls:
            entry["tool_calls"] = valid_calls
        if content or valid_calls:
            cleaned.append(entry)
    # Keep assistant(tool_calls) -> tool(tool_call_id) pairs consistent:
    # drop tool results with no matching call, and calls with no result.
    called_ids = set()
    for entry in cleaned:
        for call in entry.get("tool_calls", []):
            called_ids.add(call["id"])
    answered_ids = {e["tool_call_id"] for e in cleaned if e["role"] == "tool"}
    if called_ids or answered_ids:
        kept = []
        for entry in cleaned:
            if entry["role"] == "assistant" and "tool_calls" in entry:
                entry = dict(entry)
                entry["tool_calls"] = [c for c in entry["tool_calls"] if c["id"] in answered_ids]
                if not entry["tool_calls"] and not entry["content"]:
                    continue
                if not entry["tool_calls"]:
                    entry.pop("tool_calls")
            elif entry["role"] == "tool" and entry["tool_call_id"] not in called_ids:
                continue
            kept.append(entry)
        cleaned = kept
    cleaned = cleaned[-MAX_HISTORY_MESSAGES:]
    return _apply_history_budget(cleaned)


MAX_HISTORY_CHARS_TOTAL = 6000


def _message_size(entry: dict) -> int:
    """Approximate serialized size of one history message."""
    size = len(entry.get("content") or "")
    for call in entry.get("tool_calls", []):
        size += len(call.get("id") or "") + len(
            (call.get("function") or {}).get("arguments") or ""
        )
    return size


def _apply_history_budget(cleaned: list[dict]) -> list[dict]:
    """Enforce the total history budget, dropping OLDEST entries first.

    Assistant(tool_calls) + tool(tool_call_id) pairs are atomic units:
    dropping one side always drops the other, so Groq never sees orphan
    tool messages. The newest turns (including any pending-confirmation
    context) always survive.
    """
    total = sum(_message_size(e) for e in cleaned)
    if total <= MAX_HISTORY_CHARS_TOTAL:
        return cleaned
    # Index tool results by call id for pair-aware eviction.
    by_call_id: dict[str, int] = {}
    for i, entry in enumerate(cleaned):
        if entry["role"] == "tool":
            by_call_id.setdefault(entry["tool_call_id"], i)
    drop: set[int] = set()
    for i, entry in enumerate(cleaned):
        if total <= MAX_HISTORY_CHARS_TOTAL:
            break
        if i in drop:
            continue
        drop.add(i)
        total -= _message_size(entry)
        for call in entry.get("tool_calls", []):
            j = by_call_id.get(call["id"])
            if j is not None and j not in drop:
                drop.add(j)
                total -= _message_size(cleaned[j])
    return [e for i, e in enumerate(cleaned) if i not in drop]


COMPACT_TOOL_CHARS = 3000
COMPACT_TOOL_ROWS = 10


def _compact_tool_text(text: str) -> str:
    """Shrink an oversized tool result for multi-turn history.

    Keeps envelope keys (success, totals, pagination, errors) and the
    first COMPACT_TOOL_ROWS array rows verbatim, then marks what was
    dropped. Small results return byte-identical. Only the stored copy
    is compacted; live parsing still uses the full text.
    """
    if not isinstance(text, str) or len(text) <= COMPACT_TOOL_CHARS:
        return text
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return text[:COMPACT_TOOL_CHARS] + f"\n…[truncated {len(text) - COMPACT_TOOL_CHARS} chars]"
    if not isinstance(data, dict):
        return text[:COMPACT_TOOL_CHARS] + f"\n…[truncated {len(text) - COMPACT_TOOL_CHARS} chars]"
    trimmed = False
    for key in ("orders", "products", "variants"):
        rows = data.get(key)
        if isinstance(rows, list) and len(rows) > COMPACT_TOOL_ROWS:
            data[key] = rows[:COMPACT_TOOL_ROWS]
            data["truncated"] = True
            data["truncated_count"] = len(rows) - COMPACT_TOOL_ROWS
            trimmed = True
    compacted = json.dumps(data)
    if len(compacted) > COMPACT_TOOL_CHARS * 2 and not trimmed:
        return text[:COMPACT_TOOL_CHARS] + f"\n…[truncated {len(text) - COMPACT_TOOL_CHARS} chars]"
    return compacted


def _stripped_arguments_json(call) -> str:
    """Token-stripped arguments JSON for storage in the message history."""
    try:
        arguments = json.loads(call.function.arguments or "{}")
    except (json.JSONDecodeError, AttributeError, TypeError):
        return "{}"
    if not isinstance(arguments, dict):
        return "{}"
    arguments.pop("token", None)
    try:
        return json.dumps(arguments)
    except (TypeError, ValueError):
        return "{}"


def _passthrough_tool_call(call, arguments: str) -> dict:
    """Rebuild one assistant tool-call message, preserving provider metadata.

    Gemini (via the OpenAI-compatible endpoint) attaches signature
    metadata such as ``extra_content.google.thought_signature`` to its
    tool calls, and rejects follow-up requests that drop it. The SDK
    keeps unknown fields (extra="allow"), so dump the original object
    and only override the (token-stripped) arguments — never fabricate,
    never drop. Providers without such metadata (Groq) are unaffected:
    the dump then contains exactly id/type/function.
    """
    try:
        dumped = call.model_dump(mode="json")
        if not isinstance(dumped, dict):
            raise ValueError("unexpected tool-call shape")
        entry = dict(dumped)
    except Exception:
        function = getattr(call, "function", None)
        entry = {
            "id": getattr(call, "id", ""),
            "type": getattr(call, "type", "function"),
            "function": {"name": getattr(function, "name", "")},
        }
    function = entry.get("function")
    function = dict(function) if isinstance(function, dict) else {}
    function["arguments"] = arguments
    entry["function"] = function
    entry.setdefault("type", "function")
    return entry


def _groq_tool_specs(mcp_tools):
    """Groq function specs with the `token` auth param removed."""
    specs = []
    for tool in mcp_tools:
        schema = dict(tool.input_schema or {"type": "object"})
        properties = dict(schema.get("properties") or {})
        properties.pop("token", None)
        required = [r for r in (schema.get("required") or []) if r != "token"]
        parameters = {**schema, "properties": properties}
        if required:
            parameters["required"] = required
        else:
            parameters.pop("required", None)
        specs.append(
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": parameters,
                },
            }
        )
    return specs


def _groq_transient(exc: Exception) -> bool:
    """True for Groq failures worth a retry (rate limit / 5xx / network)."""
    if isinstance(exc, (APITimeoutError, APIConnectionError)):
        return True
    if isinstance(exc, APIStatusError):
        return exc.status_code == 429 or 500 <= exc.status_code < 600
    return False


def _retry_after_seconds(exc: Exception, default: float) -> float:
    """Honor Groq's 'try again in Xs' hint on 429s; else the default."""
    haystacks = [str(exc)]
    body = getattr(exc, "body", None)
    if body is not None:
        haystacks.append(body if isinstance(body, str) else json.dumps(body, default=str))
    response = getattr(exc, "response", None)
    response_text = getattr(response, "text", None)
    if isinstance(response_text, str):
        haystacks.append(response_text)
    try:
        for haystack in haystacks:
            match = re.search(r"try again in ([\d.]+)s", haystack)
            if match:
                return min(max(float(match.group(1)), 0.5), 60.0)
    except (ValueError, TypeError):
        pass
    return default


def _usage_suffix(usage) -> str:
    """Compact token/cache/reasoning usage for latency logging.

    Pass the provider `usage` object (or a completion; its `.usage` is
    unwrapped). Never raises: providers vary in which detail fields they
    return, and logging must not break a successful turn. `cached`
    (prompt cache hits) is the signal to watch for prompt-caching wins.
    """
    try:
        usage = getattr(usage, "usage", usage)
        if usage is None:
            return ""
        prompt = getattr(usage, "prompt_tokens", None)
        out = getattr(usage, "completion_tokens", None)
        cached = None
        details = getattr(usage, "prompt_tokens_details", None)
        if details is not None:
            cached = getattr(details, "cached_tokens", None)
            if cached is None and isinstance(details, dict):
                cached = details.get("cached_tokens")
        reasoning = None
        cdetails = getattr(usage, "completion_tokens_details", None)
        if cdetails is not None:
            reasoning = getattr(cdetails, "reasoning_tokens", None)
            if reasoning is None and isinstance(cdetails, dict):
                reasoning = cdetails.get("reasoning_tokens")
        bits = []
        if prompt is not None:
            bits.append(f"prompt={prompt}")
        if cached is not None:
            bits.append(f"cached={cached}")
        if out is not None:
            bits.append(f"out={out}")
        if reasoning is not None:
            bits.append(f"reasoning={reasoning}")
        return (" tokens[" + " ".join(bits) + "]") if bits else ""
    except Exception:
        return ""


async def _groq_complete(messages, tools, *, stage: str = "initial"):
    """LLM chat call with bounded retries on transient failures.

    Uses the provider selected by MCP_LLM_PROVIDER (Groq by default,
    Gemini via its OpenAI-compatible endpoint). Both clients share the
    chat.completions.create interface, so retries resend the same context
    and a persistent failure surfaces as a 502 instead of a retry storm.

    `stage` (e.g. "turn 3/5") and per-attempt elapsed time are logged and
    included in the final error so timeouts can be traced to the exact
    failing call. Logs carry provider/model/stage/timing only — never
    message content, arguments, or keys.
    """
    import time

    delays = (2.0, 6.0)
    last_exc: Exception | None = None
    client, model = _active_client()
    provider = (settings.MCP_LLM_PROVIDER or "groq").strip().lower()
    started_all = time.monotonic()
    for attempt in range(1 + len(delays)):
        started = time.monotonic()
        try:
            result = await asyncio.to_thread(
                client.chat.completions.create,
                model=model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                parallel_tool_calls=True,
                max_tokens=LLM_MAX_TOKENS,
                temperature=LLM_TEMPERATURE,
            )
            elapsed = time.monotonic() - started
            print(
                f"MCP agent LLM ok: {provider}/{model} {stage} "
                f"attempt {attempt + 1}/{1 + len(delays)} after {elapsed:.1f}s"
                f"{_usage_suffix(getattr(result, 'usage', None))}"
            )
            return result
        except Exception as exc:
            last_exc = exc
            elapsed = time.monotonic() - started
            where = f"{provider}/{model} {stage} attempt {attempt + 1}/{1 + len(delays)} after {elapsed:.1f}s"
            if not _groq_transient(exc):
                print(f"MCP agent LLM failed (not retrying) at {where}: {type(exc).__name__}: {exc}")
                raise RuntimeError(f"LLM request failed at {where}: {exc}") from exc
            if attempt < len(delays):
                wait = _retry_after_seconds(exc, delays[attempt])
                print(
                    f"MCP agent LLM transient failure at {where}, " 
                    f"retrying in {wait}s: {type(exc).__name__}: {exc}"
                )
                await asyncio.sleep(wait)
    print(f"MCP agent LLM retries failed: {type(last_exc).__name__}: {last_exc}")
    total = 1 + len(delays)
    total_elapsed = time.monotonic() - started_all
    raise RuntimeError(
        f"LLM request failed at {stage} (attempt {total}/{total}) "
        f"after {total_elapsed:.1f}s: {last_exc}"
    ) from last_exc


class _StreamedToolCall:
    """Lightweight stand-in for an SDK tool-call object (streaming path).

    `_passthrough_tool_call` reads id/type/function.{name,arguments} via
    attribute access, so replicating just those attributes is enough. No
    provider metadata is available mid-stream (Gemini's thought_signature
    is not emitted in deltas), so Gemini falls back to the plain shape.
    """

    def __init__(self, call_id: str, name: str, arguments: str):
        self.id = call_id
        self.type = "function"
        self.function = _StreamedFunction(name, arguments)


class _StreamedFunction:
    def __init__(self, name: str, arguments: str):
        self.name = name
        self.arguments = arguments


async def _groq_stream(messages, tools, *, stage: str = "initial"):
    """Streaming variant of _groq_complete.

    Yields {"kind": "delta", "text": str} for assistant content as it
    arrives, then a final {"kind": "done", "content", "tool_calls"}.
    Raises RuntimeError on persistent failure (same contract as
    _groq_complete) so callers can map it to a 502 / error event.

    Tool-call deltas are accumulated per `index` (providers split the
    name/arguments across chunks); content deltas are forwarded live.
    """
    import time

    delays = (2.0, 6.0)
    client, model, provider = _active_async_client()
    last_exc: Exception | None = None
    started_all = time.monotonic()
    for attempt in range(1 + len(delays)):
        started = time.monotonic()
        try:
            stream = await client.chat.completions.create(
                model=model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                parallel_tool_calls=True,
                max_tokens=LLM_MAX_TOKENS,
                temperature=LLM_TEMPERATURE,
                stream=True,
            )
        except Exception as exc:
            last_exc = exc
            elapsed = time.monotonic() - started
            where = (
                f"{provider}/{model} {stage} attempt "
                f"{attempt + 1}/{1 + len(delays)} after {elapsed:.1f}s"
            )
            if not _groq_transient(exc):
                print(
                    f"MCP agent LLM stream failed (not retrying) at {where}: "
                    f"{type(exc).__name__}: {exc}"
                )
                raise RuntimeError(f"LLM request failed at {where}: {exc}") from exc
            if attempt < len(delays):
                wait = _retry_after_seconds(exc, delays[attempt])
                print(
                    f"MCP agent LLM stream transient failure at {where}, "
                    f"retrying in {wait}s: {type(exc).__name__}: {exc}"
                )
                await asyncio.sleep(wait)
                continue
            break

        content_parts: list[str] = []
        tool_acc: dict = {}
        usage = None
        try:
            async for chunk in stream:
                chunk_usage = getattr(chunk, "usage", None)
                if chunk_usage is not None:
                    usage = chunk_usage
                choices = getattr(chunk, "choices", None) or []
                if not choices:
                    continue
                delta = getattr(choices[0], "delta", None)
                if delta is None:
                    continue
                piece = getattr(delta, "content", None)
                if piece:
                    content_parts.append(piece)
                    yield {"kind": "delta", "text": piece}
                for tc in getattr(delta, "tool_calls", None) or []:
                    idx = getattr(tc, "index", 0)
                    if idx is None:
                        idx = 0
                    slot = tool_acc.setdefault(idx, {"id": None, "name": "", "args": []})
                    if getattr(tc, "id", None):
                        slot["id"] = tc.id
                    fn = getattr(tc, "function", None)
                    if fn is not None:
                        if getattr(fn, "name", None):
                            slot["name"] = fn.name
                        if getattr(fn, "arguments", None):
                            slot["args"].append(fn.arguments)
        except Exception as exc:
            elapsed = time.monotonic() - started
            print(
                f"MCP agent LLM stream failed mid-stream at "
                f"{provider}/{model} {stage} after {elapsed:.1f}s: "
                f"{type(exc).__name__}: {exc}"
            )
            raise RuntimeError(f"LLM stream failed at {stage}: {exc}") from exc

        tool_calls = [
            _StreamedToolCall(
                slot["id"] or f"call_{idx}",
                slot["name"],
                "".join(slot["args"]) or "{}",
            )
            for idx, slot in sorted(tool_acc.items())
        ]
        elapsed = time.monotonic() - started
        print(
            f"MCP agent LLM stream ok: {provider}/{model} {stage} "
            f"attempt {attempt + 1}/{1 + len(delays)} after {elapsed:.1f}s"
            f"{_usage_suffix(usage)}"
        )
        yield {
            "kind": "done",
            "content": "".join(content_parts),
            "tool_calls": tool_calls,
        }
        return

    total = 1 + len(delays)
    total_elapsed = time.monotonic() - started_all
    print(f"MCP agent LLM stream retries failed: {type(last_exc).__name__}: {last_exc}")
    raise RuntimeError(
        f"LLM request failed at {stage} (attempt {total}/{total}) "
        f"after {total_elapsed:.1f}s: {last_exc}"
    ) from last_exc


def _pending_action_summary(pending_action: dict | None) -> str | None:
    """Deterministic human-readable text for a pending confirmation.

    Used only when the model returns no usable reply text of its own.
    Built strictly from pending_action fields — no LLM call, no invented
    values, no execution. Missing fields degrade gracefully.
    """
    if not isinstance(pending_action, dict):
        return None
    if pending_action.get("tool") == "adjust_stock":
        variant = pending_action.get("variant") or {}
        sku = variant.get("sku") or "this variant"
        try:
            delta = int(pending_action.get("delta", 0))
        except (TypeError, ValueError):
            delta = 0
        try:
            resulting = int(pending_action.get("resulting_stock"))
        except (TypeError, ValueError):
            resulting = None
        signed = f"+{delta}" if delta > 0 else str(delta)
        span = f" ({resulting - delta} → {resulting})" if resulting is not None else ""
        reason = pending_action.get("reason") or ""
        suffix = f" — {reason}" if reason else ""
        return f"Stock adjustment preview: SKU {sku} {signed}{span}{suffix}. Confirm to apply."
    return "A confirmation preview is ready — review the details and confirm to proceed."


# Product cards for the chat UI. Whitelisted fields only (same rule as
# pending_action): the frontend renders thumb + name + price + stock from
# these — never raw tool internals, never LLM-written URLs.
MAX_PRODUCT_CARDS = 4
CARD_TOOLS = {
    "get_order",
    "get_product",
    "list_products",
    "compare_products",
    "check_stock",
    "check_product_inventory",
    "product_performance",
}


def _to_product_card(product: dict | None, stock=None) -> dict | None:
    if not isinstance(product, dict) or not product.get("id"):
        return None
    try:
        stock_int = int(stock) if stock is not None else None
    except (TypeError, ValueError):
        stock_int = None
    return {
        "id": product.get("id"),
        "name": product.get("name"),
        "slug": product.get("slug"),
        "price": product.get("price"),
        "compare_at_price": product.get("compare_at_price"),
        "image_url": product.get("image_url"),
        "stock": stock_int,
        "is_active": product.get("is_active"),
    }


def _card_candidates(tool_name: str, result: dict) -> list[tuple[dict, object]]:
    """(product-dict, stock) pairs worth showing as chat cards."""
    if not isinstance(result, dict) or result.get("success") is not True:
        return []
    if tool_name == "get_order":
        # Order line items resolved to products by the tool (variant ->
        # product -> slug + first image). Already whitelisted/display-only;
        # cap is applied by collect_product_cards below.
        cards = result.get("product_cards")
        if not isinstance(cards, list):
            return []
        return [(c, c.get("stock")) for c in cards if isinstance(c, dict)]
    if tool_name == "get_product":
        product = result.get("product")
        if not isinstance(product, dict):
            return []
        total = None
        try:
            stocks = [
                v.get("stock") for v in (product.get("variants") or [])
                if isinstance(v, dict) and v.get("stock") is not None
            ]
            total = sum(int(s) for s in stocks) or None
        except (TypeError, ValueError):
            total = None
        return [(product, total)]
    if tool_name in ("list_products", "compare_products"):
        products = result.get("products")
        if isinstance(products, list):
            return [(p, None) for p in products[:MAX_PRODUCT_CARDS]]
        return []
    if tool_name == "product_performance":
        # Analytics rows use product_* keys (plus units sold, not stock —
        # never mislabel units as stock, so stock stays None).
        products = result.get("products")
        cards = []
        if isinstance(products, list):
            for r in products[:MAX_PRODUCT_CARDS]:
                if not isinstance(r, dict):
                    continue
                cards.append((
                    {
                        "id": r.get("product_id"),
                        "name": r.get("product_name"),
                        "slug": r.get("product_slug"),
                        "price": r.get("average_price"),
                        "image_url": r.get("image_url"),
                        "is_active": r.get("is_active"),
                    },
                    None,
                ))
        return cards
    if tool_name in ("check_stock", "check_product_inventory"):
        product = result.get("product")
        if isinstance(product, dict):
            variant = result.get("variant")
            stock = None
            if isinstance(variant, dict) and variant.get("stock") is not None:
                stock = variant.get("stock")
            elif result.get("total_stock") is not None:
                stock = result.get("total_stock")
            return [(product, stock)]
    return []


def collect_product_cards(
    tool_name: str,
    result_data: dict,
    product_cards: list,
    seen_card_ids: set,
) -> None:
    """Append chat cards for a successful tool result (mutates in place).

    Call for EVERY successful tool result — never gate on
    requires_confirmation: read-only lookups never set that flag, and
    gating collection on it silently attached zero cards forever.
    """
    if tool_name not in CARD_TOOLS or len(product_cards) >= MAX_PRODUCT_CARDS:
        return
    for product, stock in _card_candidates(tool_name, result_data):
        card = _to_product_card(product, stock)
        if card is None or card["id"] in seen_card_ids:
            continue
        seen_card_ids.add(card["id"])
        product_cards.append(card)
        if len(product_cards) >= MAX_PRODUCT_CARDS:
            break


def _today_context() -> str:
    """Server-authored current-date line so relative dates are deterministic.

    Computed per request (not import time) so long-lived workers never serve
    a stale date. UTC matches the day boundaries used across tools.
    """
    from datetime import datetime, timezone

    return (
        "Current UTC date: "
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}."
    )


# Currency rules. Money-bearing tool results carry top-level `currency`
# (ISO code) and `currency_symbol` fields sourced from the deployment's
# PAYMENT_CURRENCY switch — the same single source the REST displays use.
# This stops the model defaulting to USD: every money figure is labeled
# with the quoted code, never an assumed one. Counts/quantities are not
# money and carry no currency.
CURRENCY_GUIDANCE = (
    "Currency rules: "
    "every money figure in tool results is denominated in the `currency` "
    "code echoed alongside it — quote that code verbatim with each amount "
    "(e.g. 159900.00 INR, never USD unless the echoed code says so). "
    "Use the echoed `currency_symbol` as the display prefix. "
    "Never invent, assume, or convert a currency; if a result somehow lacks "
    "a currency field, state the amount without any currency label rather "
    "than guessing one. "
)


def _currency_context() -> str:
    """Server-authored currency line so money labels track the deployment.

    Computed per request (not import time) so a PAYMENT_CURRENCY switch
    takes effect on restart without prompt edits. Mirrors _today_context.
    """
    from app.core.region import currency_code, currency_symbol

    return (
        "Store currency: "
        f"{currency_code()} ({currency_symbol().strip()})."
    )


_TOOL_STEP_LABELS = {
    "get_order": "Looking up the order…",
    "list_orders": "Listing orders…",
    "cancel_order": "Preparing cancellation…",
    "issue_refund": "Preparing refund…",
    "get_product": "Looking up the product…",
    "list_products": "Searching products…",
    "compare_products": "Comparing products…",
    "update_product": "Preparing product update…",
    "update_product_price": "Preparing price change…",
    "delete_product": "Preparing deactivation…",
    "check_stock": "Checking stock…",
    "check_product_inventory": "Checking inventory…",
    "list_low_stock_products": "Finding low-stock products…",
    "sales_summary": "Computing the sales summary…",
    "sales_trend": "Computing the sales trend…",
    "product_performance": "Analyzing product performance…",
    "get_payment_status": "Checking payment status…",
    "list_refunds": "Listing refunds…",
    "list_payment_issues": "Checking payment issues…",
    "get_refund_status": "Checking refund status…",
    "whoami": "Checking identity…",
    "check_orders_view": "Checking permissions…",
}


def _tool_step_label(name: str) -> str:
    """Short human label for a running tool (chat step chip)."""
    return _TOOL_STEP_LABELS.get(name, "Working…")


async def run_chat_events(
    message: str,
    *,
    auth_token: str,
    mcp_url: str,
    history=None,
    stream: bool = False,
):
    """Run one authenticated agent turn, yielding progress events.

    Event dicts (each has a "type"):
      {"type": "step", "tool", "label"}   a tool is about to execute
      {"type": "token", "text"}           assistant answer delta (stream only)
      {"type": "final", "reply", "tools_used", "product_cards"?, "pending_action"?}
      {"type": "error", "message"}        terminal failure (never both kinds)

    `stream=True` streams the answer through the provider's streaming API;
    `stream=False` (default) uses the proven _groq_complete path unchanged.
    LLM failures raise RuntimeError (mapped to 502 by the JSON endpoint).

    Auth: `auth_token` is sent ONLY as the HTTP Authorization header of
    the MCP transport. Tool calls go out with no token argument, so the
    server resolves identity from ctx.headers via require_mcp_user().

    `history` is the frontend's prior turns (user/assistant/tool dicts).
    It is sanitized by _sanitize_history: the system prompt always stays
    server-authored and client roles are restricted.
    """
    if not message or not message.strip():
        raise ValueError("message is required")
    if not auth_token:
        raise ValueError("auth_token is required")

    user_key = _pagination_user_key(auth_token)

    http_client = httpx2.AsyncClient(
        headers={
            "Authorization": f"Bearer {auth_token}",
            # ngrok free serves a browser-warning interstitial page to
            # non-browser clients unless this header is present. The MCP
            # loopback below calls our own public origin (request.base_url),
            # so without it every tunneled chat turn dies parsing HTML.
            # Harmless everywhere else (plain unknown header).
            "ngrok-skip-browser-warning": "true",
        },
        timeout=30.0,
    )
    # A browser Stop closes this generator mid-yield; without the finally
    # the pooled sockets would leak on every abandoned streamed turn.
    try:
        async for event in _agent_loop(
            message,
            user_key=user_key,
            mcp_url=mcp_url,
            history=history,
            stream=stream,
            http_client=http_client,
        ):
            yield event
    finally:
        await http_client.aclose()


async def _agent_loop(
    message: str,
    *,
    user_key: str,
    mcp_url: str,
    history,
    stream: bool,
    http_client,
):
    """Inner turn loop: owns the MCP session and the LLM/tool exchange."""
    tools_used: list[str] = []
    pending_action: dict | None = None
    product_cards: list[dict] = []
    seen_card_ids: set[str] = set()
    async with Client(streamable_http_client(mcp_url, http_client=http_client)) as mcp_client:
        listed = await mcp_client.list_tools()
        tools = _groq_tool_specs(listed.tools)
        tool_names = {t.name for t in listed.tools}

        # Static, reusable prompt prefix first and dynamic, per-request
        # lines (today's date, store currency) last, so providers that
        # cache prompt prefixes can reuse the bulk of every turn.
        messages = [
            {
                "role": "system",
                "content": AGENT_SYSTEM_PROMPT + " " + CURRENCY_GUIDANCE + " " + DATE_GUIDANCE + " " + PAGINATION_GUIDANCE + " " + PRESENTATION_GUIDANCE + " " + STOCK_ROUTING_GUIDANCE + " " + PRICE_GUIDANCE + " " + ANALYTICS_GUIDANCE + " " + ORDER_ITEMS_GUIDANCE + " " + PARALLEL_TOOL_GUIDANCE + " " + _today_context() + " " + _currency_context(),
            },
            *_sanitize_history(history, tool_names),
            {"role": "user", "content": _with_pagination_context(user_key, message)},
        ]
        retry_counts: dict = {}
        final_text = ""
        empty_retry_used = False

        import time

        run_started = time.monotonic()

        async def _turn_events(stage: str):
            """Yield token deltas, then one private _result with content/calls."""
            if not stream:
                completion = await _groq_complete(messages, tools, stage=stage)
                msg = completion.choices[0].message
                yield {
                    "kind": "_result",
                    "content": msg.content,
                    "tool_calls": msg.tool_calls,
                }
                return
            async for ev in _groq_stream(messages, tools, stage=stage):
                if ev["kind"] == "delta":
                    yield ev
                elif ev["kind"] == "done":
                    yield {
                        "kind": "_result",
                        "content": ev["content"],
                        "tool_calls": ev["tool_calls"],
                    }

        for turn in range(1, AGENT_MAX_TURNS + 1):
            turn_started = time.monotonic()
            stage = f"turn {turn}/{AGENT_MAX_TURNS}"
            assistant_content = None
            assistant_tool_calls = None
            async for ev in _turn_events(stage):
                if ev["kind"] == "delta":
                    yield {"type": "token", "text": ev["text"]}
                elif ev["kind"] == "_result":
                    assistant_content = ev["content"]
                    assistant_tool_calls = ev["tool_calls"]

            if (
                not assistant_tool_calls
                and not (assistant_content or "").strip()
                and not empty_retry_used
            ):
                # Blank finish (reasoning models can spend the output
                # budget on chain-of-thought): one nudge retry asking for
                # a plain-language answer instead of surfacing
                # "(no response)". If the retry also blanks or calls
                # tools, normal handling below applies.
                empty_retry_used = True
                print(f"MCP agent empty reply at turn {turn}, nudging once")
                messages.append({"role": "user", "content": EMPTY_REPLY_NUDGE})
                assistant_content = None
                assistant_tool_calls = None
                async for ev in _turn_events("empty-retry"):
                    if ev["kind"] == "delta":
                        yield {"type": "token", "text": ev["text"]}
                    elif ev["kind"] == "_result":
                        assistant_content = ev["content"]
                        assistant_tool_calls = ev["tool_calls"]

            if not assistant_tool_calls:
                final_text = assistant_content or ""
                break

            calls = list(assistant_tool_calls)
            messages.append(
                {
                    "role": "assistant",
                    "content": assistant_content,
                    "tool_calls": [
                        _passthrough_tool_call(call, _stripped_arguments_json(call))
                        for call in calls
                    ],
                }
            )

            # Prepare every call first (parse + strip auth + retry guard)
            # so independent calls can run concurrently.
            prepared = []
            for call in calls:
                tool_name = call.function.name
                try:
                    arguments = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError:
                    arguments = {}
                if not isinstance(arguments, dict):
                    arguments = {}
                # Defense in depth: auth never rides in tool arguments,
                # even if the model invents the parameter.
                arguments.pop("token", None)
                retry_key = (tool_name, json.dumps(arguments, sort_keys=True))
                prepared.append(
                    {
                        "call": call,
                        "name": tool_name,
                        "arguments": arguments,
                        "retry_key": retry_key,
                        "blocked": retry_counts.get(retry_key, 0) >= MAX_RETRY_ATTEMPTS,
                    }
                )

            executable = [p for p in prepared if not p["blocked"]]
            for p in executable:
                yield {
                    "type": "step",
                    "tool": p["name"],
                    "label": _tool_step_label(p["name"]),
                }

            gathered: list = []
            if executable:
                # Independent lookups run together (one model round trip).
                gathered = await asyncio.gather(
                    *(
                        mcp_client.call_tool(p["name"], p["arguments"])
                        for p in executable
                    ),
                    return_exceptions=True,
                )
            result_by_call = {id(p): g for p, g in zip(executable, gathered)}

            # Append tool messages in the original call order.
            for p in prepared:
                call = p["call"]
                if p["blocked"]:
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": (
                                "Tool execution blocked because the maximum "
                                "retry limit was reached."
                            ),
                        }
                    )
                    continue

                tool_name = p["name"]
                retry_key = p["retry_key"]
                tool_result = result_by_call.get(id(p))
                if isinstance(tool_result, BaseException):
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": json.dumps(
                                {"success": False, "error": f"Tool error: {tool_result}"}
                            ),
                        }
                    )
                    continue

                tools_used.append(tool_name)
                result_text = "\n".join(
                    item.text for item in tool_result.content if hasattr(item, "text")
                )
                result_data = None
                try:
                    result_data = json.loads(result_text)
                    if not isinstance(result_data, dict):
                        # Valid JSON but not an object (array/scalar) — never
                        # let .get() below turn it into a 500; degrade to a
                        # plain tool error the model can react to instead.
                        result_data = {
                            "success": False,
                            "error": "Tool returned an unexpected shape",
                        }
                    if result_data.get("success") is False:
                        if result_data.get("retryable") is True:
                            retry_counts[retry_key] = retry_counts.get(retry_key, 0) + 1
                    else:
                        retry_counts.pop(retry_key, None)
                        if tool_name == "list_orders":
                            _remember_pagination(user_key, p["arguments"], result_data)
                        if result_data.get("requires_confirmation") is True:
                            # Latest pending destructive preview, surfaced to
                            # the caller so the UI can offer explicit buttons.
                            # Shapes differ per tool; pass through only the
                            # whitelisted preview fields (never raw internals).
                            order = result_data.get("order")
                            order = order if isinstance(order, dict) else {}
                            pending_action = {
                                "tool": tool_name,
                                "order_id": order.get("id"),
                                "order_number": order.get("order_number"),
                                "status": order.get("status"),
                                "preview_token": result_data.get("preview_token"),
                                "expires_in_minutes": result_data.get("expires_in_minutes"),
                            }
                            if tool_name == "cancel_order":
                                pending_action["cancel_implications"] = result_data.get(
                                    "cancel_implications"
                                )
                            if tool_name == "issue_refund":
                                pending_action["amount"] = result_data.get("amount")
                                pending_action["reason"] = result_data.get("reason")
                                pending_action["requires_approval"] = result_data.get(
                                    "requires_approval"
                                )
                                pending_action["order_total"] = result_data.get("order_total")
                                pending_action["refund_to_customer"] = result_data.get(
                                    "refund_to_customer"
                                )
                                pending_action["restocking_fee"] = result_data.get(
                                    "restocking_fee"
                                )
                                pending_action["additional_fee_at_execution"] = result_data.get(
                                    "additional_fee_at_execution"
                                )
                            if tool_name in (
                                "update_product",
                                "update_product_price",
                                "delete_product",
                                "adjust_stock",
                            ):
                                pending_action["product"] = result_data.get("product")
                                pending_action["variant"] = result_data.get("variant")
                                pending_action["changes"] = result_data.get("changes")
                                pending_action["delta"] = result_data.get("delta")
                                pending_action["resulting_stock"] = result_data.get(
                                    "resulting_stock"
                                )
                                pending_action["reason"] = result_data.get("reason")
                                pending_action["consequence"] = result_data.get("consequence")
                        # Product cards for the chat UI (see collect_product_cards:
                        # deliberately outside requires_confirmation — read
                        # lookups never set that flag).
                        collect_product_cards(tool_name, result_data, product_cards, seen_card_ids)
                except json.JSONDecodeError:
                    pass
                # Card display rows (e.g. get_order product_cards) are consumed
                # above by collect_product_cards. Strip them from the
                # model-facing copy: they are UI-only (image URLs, ids) and
                # would otherwise ride along in every later history turn.
                llm_text = result_text
                if isinstance(result_data, dict) and "product_cards" in result_data:
                    llm_text = json.dumps(
                        {k: v for k, v in result_data.items() if k != "product_cards"}
                    )
                messages.append(
                    {"role": "tool", "tool_call_id": call.id, "content": _compact_tool_text(llm_text)}
                )
            turn_elapsed = time.monotonic() - turn_started
            print(
                f"MCP agent turn {turn}/{AGENT_MAX_TURNS} done after "
                f"{turn_elapsed:.1f}s "
                f"(tools this turn: {len(calls)})"
            )
            # Loop back to the LLM for the next turn.

        print(f"MCP agent run done after {time.monotonic() - run_started:.1f}s")
        result: dict = {
            "reply": final_text.strip()
            or _pending_action_summary(pending_action)
            or "(no response)",
            "tools_used": tools_used,
        }
        if pending_action is not None:
            result["pending_action"] = pending_action
        if product_cards:
            result["product_cards"] = product_cards
        yield {"type": "final", **result}


async def run_chat(
    message: str, *, auth_token: str, mcp_url: str, history=None
) -> dict:
    """Non-streaming entry point: drain run_chat_events into the final dict.

    Kept stable for existing callers (the JSON endpoint and tests):
    returns {"reply", "tools_used"} plus optional pending_action/cards, and
    raises (ValueError/RuntimeError) exactly as before.
    """
    result: dict | None = None
    async for event in run_chat_events(
        message, auth_token=auth_token, mcp_url=mcp_url, history=history, stream=False
    ):
        if event.get("type") == "error":
            raise RuntimeError(event.get("message") or "Agent failed")
        if event.get("type") == "final":
            result = {k: v for k, v in event.items() if k != "type"}
    if result is None:
        raise RuntimeError("Agent produced no final response")
    return result


if __name__ == "__main__":
    asyncio.run(main())