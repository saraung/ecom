import re
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Header, Query, Request
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field
from groq import Groq
from sqlmodel import Session, select
from app.core.config import settings
from app.api.deps import SessionDep, get_current_user
from app.services.chat_session import issue_session, owned_session, allow_request, MAX_HISTORY, MAX_REPLY
from app.services.rag_service import get_rag_response
from app.models.product import Product

router = APIRouter(prefix="/chat", tags=["ChatBot"])

# ✅ Initialize Groq client
client = Groq(
    api_key=settings.GROQ_API_KEY, timeout=20.0, max_retries=0,
)

def build_system_prompt() -> str:
    """Support prompt with LIVE policy numbers (never hardcoded).

    Restocking fees, shipping threshold/cost, COD limits/fee and the
    support phone all come from store settings + regional config, so the
    assistant quotes today's values in the deployment's currency.
    Falls back to code defaults when the DB is unreachable.
    """
    from app.core.region import currency_code, format_money, tax_label
    from app.core.store_settings import get_store_settings
    from app.core.config import settings as _settings

    try:
        store = get_store_settings()
    except Exception:
        store = None

    def _num(value, default):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    restocking_confirmed = _num(getattr(store, "restocking_fee_confirmed", 5.0), 5.0)
    restocking_processing = _num(
        getattr(store, "restocking_fee_processing", 15.0), 15.0
    )
    free_ship = _num(getattr(store, "free_shipping_threshold", 1000.0), 1000.0)
    ship_cost = _num(getattr(store, "shipping_cost", 50.0), 50.0)
    cod_fee = _num(getattr(store, "cod_fee", 50.0), 50.0)
    cod_min = _num(getattr(store, "cod_min_order_value", 0.0), 0.0)
    cod_max = _num(getattr(store, "cod_max_order_value", 10000.0), 10000.0)
    support_phone = _settings.STORE_SUPPORT_PHONE or "support line"
    _ = tax_label, currency_code  # labels available to future prompt edits

    return f"""You are a friendly customer support assistant for an e-commerce store.

## Your Role
Help customers with product questions, shipping, and orders.
Keep answers short (2-3 sentences), friendly, and helpful.

## What You CAN Help With
- Product information and availability
- Shipping costs and delivery times
- Order status (redirect to human agent)
- COD availability and limits

## What You CANNOT Help With (Redirect to Human Agent)
- Returns and refunds - we don't have a return policy yet
- Order cancellations - please contact support
- Damaged or missing items - please contact support
- Account issues - please contact support

## Cancellation Policy
- Orders can be cancelled BEFORE shipping
- Online orders: {restocking_confirmed:g}% restocking fee ({restocking_processing:g}% while processing)
- Once SHIPPED → CANNOT cancel

## Shipping Policy
- Free shipping on orders above {format_money(free_ship)}
- Standard: {format_money(ship_cost)} (3-5 days)

## COD Policy
- Available for orders between {format_money(cod_min)} and {format_money(cod_max)}
- COD fee: {format_money(cod_fee)}

## IMPORTANT RULES
1. If a customer asks about returns or refunds, say:
   "I don't have information about returns yet. Please contact our support team at support@store.com or call {support_phone}."

2. If a customer asks about a specific brand or product NOT in our store, say:
   "Sorry, we don't have [brand] products right now. Would you like to see our available products?"

3. ONLY provide information that is explicitly stated in these policies.

4. If you don't know something, say:
   "I don't have that information right now. Let me connect you with a human agent!"
"""


SYSTEM_PROMPT = build_system_prompt()

PRODUCT_KEYWORDS = [
    "product", "item", "buy", "price", "shop", "available", 
    "stock", "show me", "find", "top", "best", "recommend",
    "cheap", "affordable", "expensive", "cost", "worth",
    "suggestion", "offer", "deal", "discount", "sale"
]

# ✅ Only policies that actually exist
POLICY_KEYWORDS = [
    "shipping", "delivery", "cod", "cancel", "cancellation"
]

optional_bearer = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def optional_chat_user(session: SessionDep, token: str | None = Depends(optional_bearer)):
    # Invalid/disabled/revoked authenticated sessions never downgrade to guests.
    return get_current_user(session, token) if token else None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str = Field(min_length=1, max_length=1000)

# ✅ Cache product names for quick lookup
_product_names_cache = None
_product_names_cache_time = None

def get_product_names(session: Session) -> list[str]:
    """Get all product names from database (cached)"""
    global _product_names_cache, _product_names_cache_time
    
    if _product_names_cache is not None and _product_names_cache_time is not None:
        if (datetime.now() - _product_names_cache_time).seconds < 300:
            return _product_names_cache
    
    statement = select(Product.name).where(Product.is_active == True)
    products = session.exec(statement).all()
    _product_names_cache = [p.lower() for p in products]
    _product_names_cache_time = datetime.now()
    return _product_names_cache

def is_product_query(message: str, session: Session) -> bool:
    """Check if message is asking about a product"""
    message_lower = message.lower()
    message_words = set(message_lower.split())
    
    product_names = get_product_names(session)
    for name in product_names:
        if name in message_lower:
            return True
        name_words = set(name.split())
        if name_words.intersection(message_words):
            return True
    
    for keyword in PRODUCT_KEYWORDS:
        if keyword in message_lower:
            return True
    
    return False

@router.post("/session")
def create_chat_session(session: SessionDep, request: Request, owner=Depends(optional_chat_user)):
    allow_request(session, request, owner, "session")
    return {"session_id": issue_session(session, owner)}


@router.post("")
def chat(req: ChatRequest, session: SessionDep, request: Request, owner=Depends(optional_chat_user)):
    message = req.message.strip()
    if not message:
        return {"reply": "Please type a message 🙂"}
    owned_session(session, req.session_id, owner)
    allow_request(session, request, owner, "message")
    try:
        conversation = owned_session(session, req.session_id, owner, lock=True)
        history = conversation.history[-MAX_HISTORY:]
        is_policy_query = any(keyword in message.lower() for keyword in POLICY_KEYWORDS)
        if not is_policy_query and is_product_query(message, session):
            reply = get_rag_response(message, session, history)
        else:
            messages = [{"role": "system", "content": build_system_prompt()}, *history[-5:],
                        {"role": "user", "content": message}]
            completion = client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=messages,
                max_tokens=500,
                temperature=0.7,
            )
            reply = completion.choices[0].message.content
        reply = str(reply or "Sorry, I could not generate a reply.")[:MAX_REPLY]
        conversation.history = [*history, {"role": "user", "content": message},
                                {"role": "assistant", "content": reply}][-MAX_HISTORY:]
        session.add(conversation)
        session.commit()
        return {"reply": reply}
    except HTTPException:
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        print("Chatbot error:", e)
        raise HTTPException(503, "Chat is temporarily unavailable; please try again")

@router.get("/history")
def get_history(session: SessionDep, request: Request,
                session_id: str | None = Query(default=None, min_length=1, max_length=1000),
                x_chat_session: str | None = Header(default=None, max_length=1000), owner=Depends(optional_chat_user)):
    session_id = x_chat_session or session_id
    owned_session(session, session_id, owner)
    allow_request(session, request, owner, "history")
    return owned_session(session, session_id, owner).history

@router.delete("/history")
def clear_history(session: SessionDep, request: Request,
                  session_id: str | None = Query(default=None, min_length=1, max_length=1000),
                  x_chat_session: str | None = Header(default=None, max_length=1000), owner=Depends(optional_chat_user)):
    session_id = x_chat_session or session_id
    owned_session(session, session_id, owner)
    allow_request(session, request, owner, "history")
    row = owned_session(session, session_id, owner, lock=True)
    row.history = []
    session.add(row)
    session.commit()
    return {"message": "History cleared"}
