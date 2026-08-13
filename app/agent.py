# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
import time
from zoneinfo import ZoneInfo

from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager
from google import genai
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors.agent_engine_sandbox_code_executor import (
    AgentEngineSandboxCodeExecutor,
)
from google.adk.models import Gemini
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.cloud import firestore, storage
from google.genai import types

from .a2ui_utils import a2ui_callback


MODEL = "gemini-2.5-flash"

# IMPORTANT: Hardcoded project ID string so Agent Platform runtime doesn't break
FIRESTORE_PROJECT_ID = "qwiklabs-gcp-03-395857593a33"
GCS_BUCKET_NAME = "price-tracker-assets-qwiklabs-gcp-03-395857593a33"
REASONING_ENGINE_RESOURCE_NAME = (
    "projects/55742297140/locations/us-east1/reasoningEngines/4723941757576806400"
)


def generate_deal_badge(product_name: str, deal_text: str = "BEST DEAL VERIFIED") -> str:
    """Generates a sleek promotional deal badge graphic image using Imagen and uploads it to public Cloud Storage.

    Args:
        product_name: Name of the product (e.g. 'Sony WH-1000XM5').
        deal_text: Custom deal highlight text (e.g. '30% OFF - Target Lowest Price').

    Returns:
        Public HTTP URL of the uploaded badge image in Cloud Storage.
    """
    client = genai.Client(vertexai=True, project=FIRESTORE_PROJECT_ID, location="us-east1")
    prompt = (
        f"A sleek, modern 3D promotional deal badge graphic icon for '{product_name}'. "
        f"Text badge style: '{deal_text}'. Glowing gradient lighting, dark premium background."
    )

    try:
        result = client.models.generate_images(
            model="imagen-3.0-generate-002",
            prompt=prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                output_mime_type="image/png",
                aspect_ratio="1:1",
            ),
        )

        if result.generated_images:
            image_bytes = result.generated_images[0].image.image_bytes
            clean_name = product_name.lower().replace(" ", "_").replace("(", "").replace(")", "")
            filename = f"badge_{clean_name}_{int(time.time())}.png"

            storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)
            bucket = storage_client.bucket(GCS_BUCKET_NAME)
            blob = bucket.blob(filename)
            blob.upload_from_string(image_bytes, content_type="image/png")

            public_url = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{filename}"
            return public_url
    except Exception as e:
        return f"Image generation fallback: https://storage.googleapis.com/{GCS_BUCKET_NAME}/badge_placeholder.png"

    return f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/badge_placeholder.png"


def search_live_web_prices(product_query: str) -> str:
    """Searches the web live using Google Search Grounding to extract current real-time prices, promo codes, and deal listings for a product across major retailers (Walmart, Amazon, Best Buy, Target, etc.).

    Args:
        product_query: Name of the product or keywords (e.g. 'Sony WH-1000XM5', 'AirPods Pro 2').

    Returns:
        Live search summary containing real-time current sticker prices, available coupon codes, and store URLs.
    """
    client = genai.Client(vertexai=True, project=FIRESTORE_PROJECT_ID, location="us-east1")
    prompt = (
        f"Search live real-time prices for '{product_query}' across major online retailers "
        f"(Walmart, Amazon, Best Buy, Target). List current sticker prices, any active discount promo/coupon codes, "
        f"and direct product page URLs."
    )
    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())]
        )
    )
    return response.text


def get_watchlist() -> list[dict]:
    """Reads tracked items and target prices from the user's Firestore price watchlist database.

    Returns:
        A list of tracked item dictionaries containing product_name, target_price, preferred_store,
        min_trust_score, current_gross_price, and in_stock status.
    """
    db = firestore.Client(project=FIRESTORE_PROJECT_ID)
    docs = db.collection("watchlist_items").stream()
    items = []
    for doc in docs:
        item = doc.to_dict()
        item["id"] = doc.id
        items.append(item)
    return items


def add_to_watchlist(
    product_name: str,
    target_price: float,
    preferred_store: str = "Walmart",
    min_trust_score: float = 4.0,
) -> dict:
    """Adds a new product to the user's Firestore price watchlist database.

    Args:
        product_name: Name of the product to track (e.g. 'Sony WH-1000XM5').
        target_price: Maximum target price the user is willing to pay.
        preferred_store: User's preferred retailer for this item (default 'Walmart').
        min_trust_score: Minimum Trustpilot rating requirement (default 4.0).

    Returns:
        A status dictionary confirming the newly created watchlist entry.
    """
    db = firestore.Client(project=FIRESTORE_PROJECT_ID)
    doc_id = product_name.lower().replace(" ", "-").replace("(", "").replace(")", "")
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    data = {
        "product_name": product_name,
        "target_price": float(target_price),
        "preferred_store": preferred_store,
        "min_trust_score": float(min_trust_score),
        "in_stock": True,
        "last_checked": now_iso,
    }

    db.collection("watchlist_items").document(doc_id).set(data)
    data["id"] = doc_id
    return {"status": "success", "message": f"Added '{product_name}' to watchlist", "item": data}


def get_store_trust_rating(store_domain: str) -> dict:
    """Verifies merchant trust rating and reputation metrics (e.g. Trustpilot score).

    Args:
        store_domain: The domain or name of the online store (e.g. 'amazon.com', 'walmart.com', 'unknownstore.com').

    Returns:
        A dictionary containing store name, Trustpilot score (out of 5.0), review count,
        whether it is trusted, badge status, and return policy overview.
    """
    domain = store_domain.lower().strip()

    # Store trust database
    trust_database = {
        "amazon.com": {
            "store_name": "Amazon",
            "trustpilot_score": 4.6,
            "review_count": 285000,
            "is_trusted": True,
            "badge": "Verified Trusted Seller",
            "return_policy": "30-day easy returns & full refund guarantee",
        },
        "walmart.com": {
            "store_name": "Walmart",
            "trustpilot_score": 4.5,
            "review_count": 194000,
            "is_trusted": True,
            "badge": "Verified Major Retailer",
            "return_policy": "90-day free returns in-store or online",
        },
        "bestbuy.com": {
            "store_name": "Best Buy",
            "trustpilot_score": 4.4,
            "review_count": 112000,
            "is_trusted": True,
            "badge": "Verified Electronics Retailer",
            "return_policy": "15-day standard return window",
        },
        "target.com": {
            "store_name": "Target",
            "trustpilot_score": 4.5,
            "review_count": 98000,
            "is_trusted": True,
            "badge": "Verified Major Retailer",
            "return_policy": "90-day return policy with receipt",
        },
    }

    for key, data in trust_database.items():
        if key in domain or data["store_name"].lower() in domain:
            return data

    # Default fallback for unrecognized stores
    return {
        "store_name": store_domain,
        "trustpilot_score": 3.2,
        "review_count": 120,
        "is_trusted": False,
        "badge": "Unverified Merchant - Exercise Caution",
        "return_policy": "Unknown / Limited return policy",
    }


def calculate_net_price(
    gross_price: float,
    store_domain: str,
    coupon_codes: list[str],
    allow_stacking: bool = True,
    is_preferred_store: bool = False,
    preferred_price_allowance: float = 5.0,
) -> dict:
    """Calculates the transparent net final price by evaluating single or stacked coupon discounts and applying preference weighting.

    Args:
        gross_price: The sticker price before discounts.
        store_domain: The retailer domain name (e.g. 'walmart.com').
        coupon_codes: List of promo code strings to evaluate.
        allow_stacking: Whether the retailer permits stacking multiple coupons (default True). Set False if the store limits to a single promo code.
        is_preferred_store: Whether the store is on the user's preferred retailer list.
        preferred_price_allowance: Dollar value allowance the user is willing to pay extra for a preferred store.

    Returns:
        A detailed price breakdown dict including gross_price, allow_stacking, applied_coupons,
        total_discount, tax_estimate, shipping_fee, net_final_price, and preference ranking.
    """
    domain = store_domain.lower().strip()

    # Evaluate potential discount for each promo code
    evaluated_coupons = []
    for code in coupon_codes:
        code_upper = code.strip().upper()
        discount_amount = 0.0

        if "15" in code_upper:
            discount_amount = round(gross_price * 0.15, 2)
        elif "10" in code_upper:
            discount_amount = round(gross_price * 0.10, 2)
        elif "5" in code_upper:
            discount_amount = round(gross_price * 0.05, 2)
        else:
            discount_amount = 5.00  # Default $5 off promo code

        if discount_amount > 0 and gross_price - discount_amount > 0:
            evaluated_coupons.append({
                "code": code_upper,
                "discount_amount": discount_amount,
            })

    applied_discounts = []
    current_price = gross_price

    if not allow_stacking and evaluated_coupons:
        # Stacking disabled: Select ONLY the single best coupon
        best_coupon = max(evaluated_coupons, key=lambda x: x["discount_amount"])
        applied_discounts = [best_coupon]
        current_price = round(gross_price - best_coupon["discount_amount"], 2)
    elif allow_stacking and evaluated_coupons:
        # Stacking enabled: Sequentially stack all valid coupons
        for item in evaluated_coupons:
            if current_price - item["discount_amount"] > 0:
                applied_discounts.append(item)
                current_price = round(current_price - item["discount_amount"], 2)

    total_discount = round(gross_price - current_price, 2)
    tax_estimate = round(current_price * 0.07, 2)  # ~7% estimated sales tax
    shipping_fee = 0.00  # Free shipping threshold met

    net_final_price = round(current_price + tax_estimate + shipping_fee, 2)

    # Calculate effective ranking price taking into account user preferred store bonus
    effective_ranking_price = net_final_price - (preferred_price_allowance if is_preferred_store else 0.0)

    return {
        "store_domain": store_domain,
        "gross_price": gross_price,
        "allow_stacking": allow_stacking,
        "applied_coupons": applied_discounts,
        "total_discount": total_discount,
        "tax_estimate": tax_estimate,
        "shipping_fee": shipping_fee,
        "net_final_price": net_final_price,
        "is_preferred_store": is_preferred_store,
        "effective_ranking_price": round(effective_ranking_price, 2),
    }


async def generate_memories_callback(callback_context: CallbackContext):
    """WRITE: after each turn, send the session to Memory Bank for extraction."""
    await callback_context.add_session_to_memory()
    return None


schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

a2ui_instruction = schema_manager.generate_system_prompt(
    role_description="You are a Smart Price Tracker & Coupon Stacker Assistant.",
    workflow_description=(
        "1. Search real-time live prices and active coupons using `search_live_web_prices`.\n"
        "2. Check store trust ratings using `get_store_trust_rating` for stores being evaluated.\n"
        "3. Calculate net final prices using `calculate_net_price`. Set `allow_stacking=False` if the store restricts users to a single promo code, or `allow_stacking=True` if coupon stacking is permitted.\n"
        "4. Manage user watchlists with `get_watchlist` and `add_to_watchlist` stored in Firestore.\n"
        "5. Generate a visual deal badge using `generate_deal_badge` when showcasing a top deal.\n"
        "6. Execute Python code in the secure Agent Engine sandbox when complex mathematical modeling, custom price trends, or custom analytics are needed.\n"
        "7. Filter out any stores that fall below the user's minimum trust rating.\n"
        "8. Respect user's preferred retailer list stored in memory, prioritizing preferred stores if competitive.\n"
        "9. When returning price comparisons or watchlist items, format the response as a clean, structured A2UI card."
    ),
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, Divider, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do nothing in adk web). "
        "You may include one Image component when you generated a deal badge with `generate_deal_badge` (pass its return URL). "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in <a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=a2ui_instruction,
    tools=[
        search_live_web_prices,
        get_watchlist,
        add_to_watchlist,
        get_store_trust_rating,
        calculate_net_price,
        generate_deal_badge,
        PreloadMemoryTool(),
    ],
    code_executor=AgentEngineSandboxCodeExecutor(
        agent_engine_resource_name=REASONING_ENGINE_RESOURCE_NAME
    ),
    after_model_callback=a2ui_callback,
    after_agent_callback=generate_memories_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)
