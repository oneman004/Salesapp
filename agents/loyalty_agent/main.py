# agents/loyalty_agent/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional

from loyalty_agent import (
    LoyaltyOffersAgent,
    CustomerProfile,
    CartItem,
    Cart,
    Promotion,
)

app = FastAPI()
agent = LoyaltyOffersAgent()

# ✅ CORS so that web-app (localhost:3000 etc.) can call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # hackathon demo ke liye thik hai
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Request Schemas ---------- #

class CustomerIn(BaseModel):
    id: str
    name: str
    loyalty_tier: str
    available_points: int
    lifetime_value: float


class CartItemIn(BaseModel):
    sku: str
    name: str
    category: str
    price: float
    quantity: int


class PromotionIn(BaseModel):
    id: str
    code: Optional[str] = None
    type: str
    value: float
    min_cart_value: Optional[float] = None
    description: str
    source: str


class LoyaltyRequest(BaseModel):
    customer: CustomerIn
    cart_items: List[CartItemIn]
    promotions: List[PromotionIn]
    manual_coupon: Optional[str] = None


@app.post("/loyalty/apply-offers")
def apply_offers(payload: LoyaltyRequest):
    customer = CustomerProfile(
        id=payload.customer.id,
        name=payload.customer.name,
        loyalty_tier=payload.customer.loyalty_tier,
        available_points=payload.customer.available_points,
        lifetime_value=payload.customer.lifetime_value,
    )

    cart = Cart(
        items=[
            CartItem(
                sku=i.sku,
                name=i.name,
                category=i.category,
                price=i.price,
                quantity=i.quantity,
            )
            for i in payload.cart_items
        ]
    )

    promotions = [
        Promotion(
            id=p.id,
            code=p.code,
            type=p.type,
            value=p.value,
            min_cart_value=p.min_cart_value,
            description=p.description,
            source=p.source,
        )
        for p in payload.promotions
    ]

    result = agent.get_best_offer(
        customer=customer,
        cart=cart,
        promotions=promotions,
        manual_coupon=payload.manual_coupon,
    )

    return result
