import chromadb
from chromadb.utils import embedding_functions
from groq import Groq
from sqlmodel import Session
from app.core.config import settings
from datetime import datetime, timedelta
from uuid import UUID
from decimal import Decimal
import re
from app.core.region import format_money

# ✅ Use SentenceTransformerEmbeddingFunction
try:
    from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2
    embed_fn = ONNXMiniLM_L6_V2()
    print("✅ Using ONNX embedding (lightweight)")
except (ImportError, AttributeError):
    embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )
    print("✅ Using SentenceTransformer embedding")

# ✅ Initialize Groq client
groq_client = Groq(
    api_key=settings.GROQ_API_KEY, timeout=20.0, max_retries=0,
)

# Initialize ChromaDB
_chroma_client = None
_last_sync = None
SYNC_INTERVAL = 300  # 5 minutes

def get_chroma_client():
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path=settings.CHROMA_DB_PATH)
    return _chroma_client

def get_collection():
    client = get_chroma_client()
    try:
        return client.get_collection("products")
    except:
        return client.create_collection(
            name="products",
            embedding_function=embed_fn
        )

def flatten_product(product) -> str:
    """Convert product to natural language for embedding"""
    variants = product.variants or []
    variant_info = ""
    
    if variants:
        prices = []
        for v in variants:
            if v.price_override is not None:
                prices.append(float(v.price_override))
            elif product.price is not None:
                prices.append(float(product.price))
        
        if prices:
            min_price = min(prices)
            max_price = max(prices)
            
            if min_price == max_price:
                variant_info = f"Price: {format_money(min_price)}. "
            else:
                variant_info = f"Prices range from {format_money(min_price)} to {format_money(max_price)}. "
            
            variant_details = []
            for v in variants:
                price = float(v.price_override) if v.price_override is not None else float(product.price)
                attrs = v.attributes or {}
                color = attrs.get('color', '')
                storage = attrs.get('storage', '')
                if color and storage:
                    variant_details.append(f"{storage} {color} - {format_money(price)}")
                elif storage:
                    variant_details.append(f"{storage} - {format_money(price)}")
                elif color:
                    variant_details.append(f"{color} - {format_money(price)}")
                else:
                    variant_details.append(f"{format_money(price)}")
            
            if variant_details and len(variant_details) > 1:
                variant_info += f"Variants: {'; '.join(variant_details)}. "
    
    description = product.description or ""
    return f"{product.name}. {description} {variant_info}".strip()

def ingest_all_products(session: Session) -> int:
    """Sync all products to ChromaDB"""
    from app.models.product import Product
    from sqlmodel import select
    
    statement = select(Product).where(Product.is_active == True)
    products = session.exec(statement).all()
    
    collection = get_collection()
    
    try:
        existing_ids = collection.get()["ids"]
        if existing_ids:
            collection.delete(ids=existing_ids)
    except:
        pass
    
    if not products:
        return 0
    
    documents = []
    metadatas = []
    ids = []
    
    for product in products:
        doc = flatten_product(product)
        documents.append(doc)
        
        prices = []
        for v in (product.variants or []):
            if v.price_override is not None:
                prices.append(float(v.price_override))
            elif product.price is not None:
                prices.append(float(product.price))
        
        min_price = min(prices) if prices else float(product.price or 0)
        
        metadatas.append({
            "product_id": str(product.id),
            "name": product.name,
            "price_min": float(min_price),
        })
        ids.append(str(product.id))
    
    collection.add(
        documents=documents,
        metadatas=metadatas,
        ids=ids
    )
    
    return len(products)

def ensure_products_synced(session: Session):
    global _last_sync
    
    if _last_sync is None or (datetime.now() - _last_sync) > timedelta(seconds=SYNC_INTERVAL):
        try:
            count = ingest_all_products(session)
            _last_sync = datetime.now()
            print(f"✅ RAG synced: {count} products")
        except Exception as e:
            print(f"⚠️ RAG sync failed: {e}")

def delete_product_from_rag(product_id: UUID) -> bool:
    collection = get_collection()
    try:
        collection.delete(ids=[str(product_id)])
        return True
    except:
        return False

def get_sync_status() -> dict:
    global _last_sync
    collection = get_collection()
    try:
        product_count = len(collection.get()["ids"])
    except:
        product_count = 0
    return {
        "is_synced": _last_sync is not None,
        "last_sync": _last_sync.isoformat() if _last_sync else None,
        "product_count": product_count,
    }

def search_products(query: str, session: Session, top_k: int = 3) -> str:
    """Search products using semantic similarity with partial match fallback"""
    collection = get_collection()
    
    # ✅ Try semantic search first
    try:
        results = collection.query(
            query_texts=[query],
            n_results=top_k
        )
        
        if results['documents'] and results['documents'][0]:
            formatted = []
            for doc, meta in zip(results['documents'][0], results['metadatas'][0]):
                price_info = f" ({format_money(meta.get('price_min', 0))})" if meta.get('price_min') else ""
                formatted.append(f"- {doc}{price_info}")
            return "\n".join(formatted)
    except Exception as e:
        print(f"Semantic search error: {e}")
    
    # ✅ Fallback: Try partial match on product names from database
    try:
        from app.models.product import Product
        from sqlmodel import select
        
        statement = select(Product).where(
            Product.is_active == True,
            Product.name.ilike(f"%{query}%")
        ).limit(top_k)
        products = session.exec(statement).all()
        
        if products:
            formatted = []
            for p in products:
                prices = []
                for v in (p.variants or []):
                    if v.price_override is not None:
                        prices.append(float(v.price_override))
                    elif p.price is not None:
                        prices.append(float(p.price))
                price = min(prices) if prices else float(p.price or 0)
                formatted.append(f"- {p.name} ({format_money(price)})")
            return "\n".join(formatted)
    except Exception as e:
        print(f"Partial match search error: {e}")
    
    return "No products found."

def get_rag_response(user_query: str, session: Session, history: list = None) -> str:
    """Main RAG chat function with conversation history"""
    ensure_products_synced(session)
    
    # ✅ Get the last mentioned product from history (for follow-up questions)
    last_product_name = None
    
    if history and len(history) > 0:
        # Look for product mentions in assistant responses
        for msg in reversed(history):
            if msg["role"] == "assistant":
                # Match patterns like "Apple Watch Series 9", "iPhone 15 Pro Max", etc.
                product_match = re.search(r'([A-Za-z0-9\s]+?)(?:\s*[–-]|\s*is available|\s*starts at|\s*range from|\s*price)', msg["content"])
                if product_match:
                    potential_name = product_match.group(1).strip()
                    # Verify it's a real product
                    from app.models.product import Product
                    from sqlmodel import select
                    stmt = select(Product).where(Product.name.ilike(f"%{potential_name}%")).limit(1)
                    product = session.exec(stmt).first()
                    if product:
                        last_product_name = product.name
                        break
        
        # If it's a follow-up question, use the last product
        followup_keywords = ["that", "it", "this", "those", "these", "of that", "for that", "price of", "cost of"]
        is_followup = any(keyword in user_query.lower() for keyword in followup_keywords)
        
        if is_followup and last_product_name:
            # Search specifically for the last mentioned product
            context = search_products(last_product_name, session)
            if context and context != "No products found.":
                # Use the full query with product context
                user_query = f"{last_product_name} {user_query}"
    
    rating_keywords = ["highest rated", "best rated", "top rated", "rating", "ratings", "review", "reviews", "popular", "best selling"]
    if any(keyword in user_query.lower() for keyword in rating_keywords):
        from app.models.product import Product
        from sqlmodel import select
        statement = select(Product).where(Product.is_active == True).limit(5)
        products = session.exec(statement).all()
        
        if products:
            product_list = []
            for p in products:
                prices = []
                for v in (p.variants or []):
                    if v.price_override is not None:
                        prices.append(float(v.price_override))
                    elif p.price is not None:
                        prices.append(float(p.price))
                price = min(prices) if prices else float(p.price or 0)
                product_list.append(f"- {p.name} ({format_money(price)})")
            
            return f"I don't have ratings or reviews for our products yet. However, here are our available products:\n" + "\n".join(product_list)
        else:
            return "I don't have ratings data yet, and I couldn't find any products in our catalog."
    
    # ✅ Pass session to search_products
    context = search_products(user_query, session)
    
    if not context or context == "No products found." or context.strip() == "":
        from app.models.product import Product
        from sqlmodel import select
        statement = select(Product).where(Product.is_active == True).limit(10)
        products = session.exec(statement).all()
        
        if products:
            product_list = []
            for p in products:
                prices = []
                for v in (p.variants or []):
                    if v.price_override is not None:
                        prices.append(float(v.price_override))
                    elif p.price is not None:
                        prices.append(float(p.price))
                price = min(prices) if prices else float(p.price or 0)
                product_list.append(f"- {p.name} ({format_money(price)})")
            context = "Here are our available products:\n" + "\n".join(product_list)
        else:
            return "I couldn't find any products in our catalog. Please check back later!"
    
    # ✅ Build conversation history for context
    history_context = ""
    if history and len(history) > 0:
        history_context = "\n".join([f"{msg['role']}: {msg['content']}" for msg in history[-6:]])
    
    RAG_PROMPT = f"""You are a friendly customer support assistant for an e-commerce store.

## YOUR ONLY JOB
Answer the user's question using ONLY the product information provided below.

## AVAILABLE PRODUCTS (ONLY THESE EXIST IN OUR STORE)
{context}

## CONVERSATION HISTORY (for understanding follow-up questions)
{history_context if history_context else "No previous conversation."}

## CRITICAL RULES
1. ONLY mention products from the list above
2. If the user asks about a product NOT in the list, say: "Sorry, we don't have that product. Here are our available products: [list]"
3. Use the EXACT prices shown in the list
4. NEVER invent products, prices, or features
5. NEVER claim a product is "highest-rated", "best-selling", or "most popular" - you have no ratings data
6. Keep responses short (2-3 sentences)
7. Be consistent - if you said a product doesn't exist, don't mention it later
8. Use conversation history to understand follow-up questions like "price of that?" or "lowest price?"

User question: {user_query}

Your response:"""

    try:
        completion = groq_client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {"role": "system", "content": "You are a strict product assistant. You can ONLY talk about products explicitly listed in the user's message. Use the exact prices provided. You have NO ratings, reviews, or sales data."},
                {"role": "user", "content": RAG_PROMPT}
            ],
            max_tokens=500,
            temperature=0.1,
        )
        return completion.choices[0].message.content
    except Exception as e:
        print(f"RAG API error: {e}")
        return f"Here are our available products:\n\n{context}\n\nWould you like more details about any specific product?"
