# agents/loyalty_agent.py
from typing import Dict, Any
from .base_agent import BaseAgent, Task, TaskResult, ErrorDetail, NextAction
import math

class LoyaltyAgent(BaseAgent):
    name = "loyalty"

    def __init__(self):
        # simple in-memory ledger: customer_id -> points
        self._points = {
            "cust_001": 1200,
            "cust_002": 50
        }
        # simple tier config (for demonstration)
        self._tiers = {
            "silver": {"multiplier": 1.0, "min": 0},
            "gold": {"multiplier": 1.2, "min": 1000},
            "platinum": {"multiplier": 1.5, "min": 5000}
        }

    def handle(self, task: Task) -> TaskResult:
        t = task.type
        if t == "LOYALTY_CALCULATE":
            return self._calculate(task)
        if t == "LOYALTY_REDEEM":
            return self._redeem(task)
        if t == "LOYALTY_ISSUE":
            return self._issue(task)
        if t == "LOYALTY_GET":
            return self._get_balance(task)
        return TaskResult(
            task_id=task.task_id,
            agent=self.name,
            status="failed",
            errors=[ErrorDetail(code="UNSUPPORTED_TASK", message=f"Unsupported: {t}", details={})]
        )

    def _get_balance(self, task: Task) -> TaskResult:
        cid = task.customer_id
        balance = self._points.get(cid, 0)
        return TaskResult(task_id=task.task_id, agent=self.name, status="success", payload={"points": balance})

    def _calculate(self, task: Task) -> TaskResult:
        # payload: {"customer_id":..., "order_amount": 1000, "use_points": true/false}
        amount = float(task.payload.get("order_amount", 0))
        cid = task.customer_id or task.payload.get("customer_id")

        if amount <= 0:
            return TaskResult(task_id=task.task_id, agent=self.name, status="failed",
                              errors=[ErrorDetail(code="INVALID_AMOUNT", message="order_amount must be > 0", details={})])

        points = self._points.get(cid, 0)
        # rule: 100 points -> ₹1 discount (demo)
        redeemable_value = math.floor(points / 100)
        max_redeemable = min(redeemable_value, int(amount))  # don't allow negative payment
        # build payload with options
        payload = {
            "order_amount": amount,
            "customer_points": points,
            "max_redeemable_value_in_inr": max_redeemable,
            "suggested_redeem": 0 if points < 100 else min(max_redeemable, int(amount*0.2))  # suggest up to 20% via points
        }
        return TaskResult(task_id=task.task_id, agent=self.name, status="success", payload=payload)

    def _redeem(self, task: Task) -> TaskResult:
        # payload: {"amount_to_redeem": 10, "order_id": "..."}
        cid = task.customer_id or task.payload.get("customer_id")
        amount_to_redeem = int(task.payload.get("amount_to_redeem", 0))
        if amount_to_redeem <= 0:
            return TaskResult(task_id=task.task_id, agent=self.name, status="failed",
                              errors=[ErrorDetail(code="INVALID_REDEEM", message="amount_to_redeem must be > 0", details={})])

        points_needed = amount_to_redeem * 100
        current = self._points.get(cid, 0)
        if current < points_needed:
            return TaskResult(task_id=task.task_id, agent=self.name, status="failed",
                              errors=[ErrorDetail(code="INSUFFICIENT_POINTS", message="Not enough points", details={"available_points": current})],
                              next_actions=[NextAction(type="ASK_CUSTOMER", message="You don't have enough points. Would you like to use a different payment method?")])

        self._points[cid] = current - points_needed
        return TaskResult(task_id=task.task_id, agent=self.name, status="success",
                          payload={"redeemed_value_in_inr": amount_to_redeem, "remaining_points": self._points[cid]})

    def _issue(self, task: Task) -> TaskResult:
        # payload: {"order_id": "...", "order_amount": 1000, "rule": "default"}
        cid = task.customer_id or task.payload.get("customer_id")
        amount = float(task.payload.get("order_amount", 0))
        if amount <= 0:
            return TaskResult(task_id=task.task_id, agent=self.name, status="failed",
                              errors=[ErrorDetail(code="INVALID_AMOUNT", message="order_amount must be > 0", details={})])
        # simple issue rule: 1% of order_amount in INR -> points (1 INR = 100 points)
        points_earned = int(amount * 1 * 100)  # e.g., ₹100 -> 10000 points (demo scale - fine for hackathon)
        self._points[cid] = self._points.get(cid, 0) + points_earned
        return TaskResult(task_id=task.task_id, agent=self.name, status="success",
                          payload={"issued_points": points_earned, "new_balance": self._points[cid]})
