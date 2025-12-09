# agents/loyalty_agent/loyalty_agent.py

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class CustomerProfile:
    id: str
    name: str
    loyalty_tier: str       # "BRONZE", "SILVER", "GOLD", "PLATINUM"
    available_points: int
    lifetime_value: float


@dataclass
class CartItem:
    sku: str
    name: str
    category: str
    price: float
    quantity: int


@dataclass
class Cart:
    items: List[CartItem]


@dataclass
class Promotion:
    id: str
    code: Optional[str]
    type: str               # "PERCENTAGE" or "FLAT"
    value: float
    min_cart_value: Optional[float]
    description: str
    source: str             # "AUTO" or "COUPON"


def calculate_cart_total(cart: Cart) -> float:
    return sum(item.price * item.quantity for item in cart.items)


def apply_promo_amount(amount: float, promo: Promotion) -> float:
    if promo.type == "PERCENTAGE":
        return amount * (promo.value / 100)
    elif promo.type == "FLAT":
        return min(amount, promo.value)
    return 0.0


def tier_bonus_percentage(tier: str) -> float:
    mapping = {
        "BRONZE": 0,
        "SILVER": 2,
        "GOLD": 5,
        "PLATINUM": 10
    }
    return mapping.get(tier.upper(), 0)


class LoyaltyOffersAgent:
    def __init__(self, point_rate: float = 0.1):
        self.point_rate = point_rate  # 1 point = ₹0.1

    def get_best_offer(
        self,
        customer: CustomerProfile,
        cart: Cart,
        promotions: List[Promotion],
        manual_coupon: Optional[str] = None,
    ):
        base_total = calculate_cart_total(cart)

        auto_promos = [p for p in promotions if p.source == "AUTO"]
        coupon_promo = next(
            (p for p in promotions if p.source == "COUPON" and p.code == manual_coupon),
            None
        )

        scenarios = []

        # Scenario 1: only auto promos
        scenarios.append(
            self._evaluate_scenario(base_total, customer, auto_promos)
        )

        # Scenario 2: manual coupon promo
        if coupon_promo:
            scenarios.append(
                self._evaluate_scenario(base_total, customer, [coupon_promo])
            )

        best = max(scenarios, key=lambda s: s["total_savings"])
        return best

    def _evaluate_scenario(self, base_total, customer, promos: List[Promotion]):
        current = base_total
        applied_promos = []

        for p in promos:
            saved = apply_promo_amount(current, p)
            if saved <= 0:
                continue
            current -= saved
            applied_promos.append({
                "id": p.id,
                "description": p.description,
                "saved": saved
            })

        # Tier bonus
        tb = tier_bonus_percentage(customer.loyalty_tier)
        if tb > 0:
            saved = current * (tb / 100)
            current -= saved
            applied_promos.append({
                "id": f"TIER_{customer.loyalty_tier}",
                "description": f"{customer.loyalty_tier} tier bonus {tb}%",
                "saved": saved
            })

        # Redeem points
        max_redeemable = customer.available_points * self.point_rate
        redeemed = min(current, max_redeemable)
        used_points = int(redeemed / self.point_rate)

        final_price = current - redeemed
        total_savings = base_total - final_price

        return {
            "base_total": base_total,
            "final_price": final_price,
            "total_savings": total_savings,
            "applied_promotions": applied_promos,
            "points_used": used_points,
            "amount_from_points": redeemed,
            "message": (
                f"You saved ₹{total_savings:.0f}. "
                f"Final payable: ₹{final_price:.0f} "
                f"(used {used_points} points)."
            )
        }
