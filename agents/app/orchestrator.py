# app/orchestrator.py
import uuid
from typing import Dict, Any
from fastapi import FastAPI, HTTPException
import uvicorn

# import agents
from ..inventory_agent import InventoryAgent
from ..recommendation_agent import RecommendationAgent
from ..payment_agent import PaymentAgent
from ..fulfillment_agent import FulfillmentAgent
from ..loyalty_agent import LoyaltyAgent
from ..post_purchase_agent import PostPurchaseAgent
from ..base_agent import Task

app = FastAPI(title="Sales Orchestrator Demo")

class SalesOrchestrator:
    def __init__(self):
        self.inventory = InventoryAgent()
        self.recommendation = RecommendationAgent()
        self.payment = PaymentAgent()
        self.fulfillment = FulfillmentAgent()
        self.loyalty = LoyaltyAgent()
        self.post_purchase = PostPurchaseAgent()

    def checkout_flow(self, cart: list, customer_id: str, payment_payload: dict, address: dict, prefer_store: str = None):
        session_id = str(uuid.uuid4())
        order_id = f"order_{uuid.uuid4().hex[:8]}"
        # 1) Inventory check
        inv_task = Task(task_id=str(uuid.uuid4()), agent="inventory", type="INVENTORY_CHECK", session_id=session_id, customer_id=customer_id, payload={"items": cart, "preferred_store": prefer_store})
        inv_res = self.inventory.handle(inv_task)
        if inv_res.status != "success":
            return {"status": "failed", "reason": "inventory_unavailable", "inventory": inv_res.payload}

        # 2) Suggest recommendations (non-blocking)
        rec_task = Task(task_id=str(uuid.uuid4()), agent="recommendation", type="RECOMMEND_FOR_CART", session_id=session_id, customer_id=customer_id, payload={"cart": cart, "user_profile": {}, "inventory_client": self.inventory})
        rec_res = self.recommendation.handle(rec_task)

        # 3) Loyalty calculate (optional) -> see if user wants to redeem (not auto)
        loy_calc = None
        loy_task = Task(task_id=str(uuid.uuid4()), agent="loyalty", type="LOYALTY_CALCULATE", session_id=session_id, customer_id=customer_id, payload={"order_amount": sum(item.get("price", 0)*item.get("qty",1) for item in cart)})
        loy_res = self.loyalty.handle(loy_task)
        if loy_res.status == "success":
            loy_calc = loy_res.payload

        # 4) Reserve inventory
        res_task = Task(task_id=str(uuid.uuid4()), agent="inventory", type="INVENTORY_RESERVE", session_id=session_id, customer_id=customer_id, payload={"order_id": order_id, "items": cart})
        reserve_res = self.inventory.handle(res_task)
        if reserve_res.status != "success":
            return {"status": "failed", "reason": "reserve_failed", "detail": reserve_res.errors}

        # 5) Authorize / capture payment
        pay_task = Task(task_id=str(uuid.uuid4()), agent="payment", type="PAYMENT_AUTHORIZE", session_id=session_id, customer_id=customer_id, payload={"amount": sum(item.get("price",0)*item.get("qty",1) for item in cart), "payment": payment_payload})
        pay_res = self.payment.handle(pay_task)
        if pay_res.status == "failed":
            # release reservation
            self.inventory.handle(Task(task_id=str(uuid.uuid4()), agent="inventory", type="INVENTORY_RELEASE", session_id=session_id, customer_id=customer_id, payload={"reservation_id": reserve_res.payload.get("reservation_id")}))
            return {"status":"failed","reason":"payment_failed","detail": pay_res.errors, "next_actions": pay_res.next_actions}

        # handle pending (eg UPI waiting)
        if pay_res.status == "pending":
            # return pending info to client so it can wait/notify (demo)
            return {"status":"pending", "payment": pay_res.payload, "next_actions": pay_res.next_actions}

        # On success, capture (we mock capture)
        capture_task = Task(task_id=str(uuid.uuid4()), agent="payment", type="PAYMENT_CAPTURE", session_id=session_id, customer_id=customer_id, payload={"auth_id": pay_res.payload.get("auth_id")})
        capture_res = self.payment.handle(capture_task)
        if capture_res.status != "success":
            # ideally release reservation & rollback payment if needed
            return {"status":"failed","reason":"capture_failed","detail": capture_res.errors}

        # 6) Create fulfillment
        ful_task = Task(task_id=str(uuid.uuid4()), agent="fulfillment", type="FULFILLMENT_CREATE", session_id=session_id, customer_id=customer_id, payload={"order_id": order_id, "mode": "ship_to_home", "address": address, "items": cart, "inventory_confirmation": True})
        ful_res = self.fulfillment.handle(ful_task)
        if ful_res.status != "success":
            # in production: trigger manual ops
            return {"status":"failed","reason":"fulfillment_failed","detail": ful_res.errors}

        # 7) Issue loyalty points after order success
        loy_issue_task = Task(task_id=str(uuid.uuid4()), agent="loyalty", type="LOYALTY_ISSUE", session_id=session_id, customer_id=customer_id, payload={"order_id": order_id, "order_amount": sum(item.get("price",0)*item.get("qty",1) for item in cart)})
        loy_issue_res = self.loyalty.handle(loy_issue_task)

        # 8) Post-purchase record / notify
        # store order record (for demo return order_id and payload)
        result = {
            "status":"success",
            "order_id": order_id,
            "inventory": inv_res.payload,
            "recommendations": rec_res.payload if rec_res.status=="success" else {},
            "payment": capture_res.payload,
            "fulfillment": ful_res.payload,
            "loyalty": loy_issue_res.payload if loy_issue_res.status=="success" else {},
        }
        return result

orchestrator = SalesOrchestrator()

@app.post("/checkout")
def checkout_endpoint(payload: Dict[str, Any]):
    """
    Expected JSON payload:
    {
      "customer_id": "cust_001",
      "cart": [{"sku":"TSHIRT-RED-XL","qty":1,"price":799}],
      "payment": {"method":"card","card_number":"4111111111111111"},
      "address": {"line1":"...", "city":"Bangalore", "pincode":"560001"}
    }
    """
    try:
        customer_id = payload["customer_id"]
        cart = payload["cart"]
        payment = payload["payment"]
        address = payload.get("address", {})
    except KeyError:
        raise HTTPException(status_code=400, detail="Missing required fields: customer_id, cart, payment")

    res = orchestrator.checkout_flow(cart=cart, customer_id=customer_id, payment_payload=payment, address=address)
    return res

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
