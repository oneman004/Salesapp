from dataclasses import dataclass
from typing import List, Optional, Dict
from datetime import datetime, timedelta


# ---------- Data Models ---------- #

@dataclass
class OrderItem:
    sku: str
    name: str
    quantity: int
    price: float


@dataclass
class Order:
    order_id: str
    customer_id: str
    placed_at: datetime
    status: str               # "PLACED", "SHIPPED", "DELIVERED", "CANCELLED"
    items: List[OrderItem]
    total_amount: float
    shipment_id: Optional[str] = None


@dataclass
class Shipment:
    shipment_id: str
    order_id: str
    carrier: str
    tracking_number: str
    status: str               # "IN_TRANSIT", "OUT_FOR_DELIVERY", "DELIVERED"
    expected_delivery: datetime
    last_updated: datetime


@dataclass
class ReturnRequest:
    return_id: str
    order_id: str
    customer_id: str
    created_at: datetime
    reason: str
    status: str               # "PENDING", "APPROVED", "REJECTED"
    message: str


@dataclass
class Feedback:
    feedback_id: str
    order_id: str
    customer_id: str
    rating: int
    comment: Optional[str]
    created_at: datetime


# ---------- Mock "database" (in-memory) ---------- #

class MockDB:
    def __init__(self):
        now = datetime.utcnow()

        self.orders: Dict[str, Order] = {
            "ORD123": Order(
                order_id="ORD123",
                customer_id="CUST001",
                placed_at=now - timedelta(days=5),
                status="DELIVERED",
                items=[
                    OrderItem(sku="TSHIRT_01", name="Graphic T-Shirt", quantity=1, price=799),
                    OrderItem(sku="JEANS_02", name="Slim Fit Jeans", quantity=1, price=1999),
                ],
                total_amount=2798,
                shipment_id="SHIP123",
            ),
            "ORD456": Order(
                order_id="ORD456",
                customer_id="CUST001",
                placed_at=now - timedelta(days=35),
                status="DELIVERED",
                items=[
                    OrderItem(sku="SHOES_05", name="Sneakers", quantity=1, price=2999),
                ],
                total_amount=2999,
                shipment_id="SHIP456",
            ),
        }

        self.shipments: Dict[str, Shipment] = {
            "SHIP123": Shipment(
                shipment_id="SHIP123",
                order_id="ORD123",
                carrier="ABFRL Logistics",
                tracking_number="TRK123",
                status="DELIVERED",
                expected_delivery=now - timedelta(days=2),
                last_updated=now - timedelta(days=2),
            ),
            "SHIP456": Shipment(
                shipment_id="SHIP456",
                order_id="ORD456",
                carrier="ABFRL Logistics",
                tracking_number="TRK456",
                status="DELIVERED",
                expected_delivery=now - timedelta(days=30),
                last_updated=now - timedelta(days=30),
            ),
        }

        self.returns: Dict[str, ReturnRequest] = {}
        self.feedbacks: Dict[str, Feedback] = {}

    def generate_return_id(self) -> str:
        return f"RET{len(self.returns) + 1:03d}"

    def generate_feedback_id(self) -> str:
        return f"FDB{len(self.feedbacks) + 1:03d}"


# ---------- Post-Purchase Support Agent ---------- #

class PostPurchaseAgent:
    """
    Worker agent that handles:
    - order tracking
    - returns / exchanges
    - feedback capture
    """

    def __init__(self, db: Optional[MockDB] = None, return_window_days: int = 30):
        self.db = db or MockDB()
        self.return_window_days = return_window_days

    # ----- 1. Track Order / Shipment ----- #

    def track_order(self, order_id: str, customer_id: str):
        order = self.db.orders.get(order_id)
        if not order or order.customer_id != customer_id:
            return {
                "success": False,
                "message": "Order not found for this customer.",
            }

        shipment = self.db.shipments.get(order.shipment_id) if order.shipment_id else None

        response = {
            "success": True,
            "order_id": order.order_id,
            "order_status": order.status,
            "placed_at": order.placed_at.isoformat(),
            "total_amount": order.total_amount,
            "items": [item.__dict__ for item in order.items],
        }

        if shipment:
            response["shipment"] = {
                "shipment_id": shipment.shipment_id,
                "carrier": shipment.carrier,
                "tracking_number": shipment.tracking_number,
                "status": shipment.status,
                "expected_delivery": shipment.expected_delivery.isoformat(),
                "last_updated": shipment.last_updated.isoformat(),
            }

        # Friendly message for conversational UI
        if shipment:
            response["summary_message"] = (
                f"Order {order.order_id} is {order.status.lower()}. "
                f"Shipment status: {shipment.status.replace('_', ' ').title()} "
                f"via {shipment.carrier}."
            )
        else:
            response["summary_message"] = (
                f"Order {order.order_id} is currently {order.status.lower()}."
            )

        return response

    # ----- 2. Create Return Request ----- #

    def create_return_request(self, order_id: str, customer_id: str, reason: str):
        order = self.db.orders.get(order_id)
        if not order or order.customer_id != customer_id:
            return {
                "success": False,
                "message": "Order not found for this customer.",
            }

        # Check return window
        now = datetime.utcnow()
        days_since = (now - order.placed_at).days

        if days_since > self.return_window_days:
            msg = (
                f"This order was placed {days_since} days ago. "
                f"Our return window is {self.return_window_days} days, "
                "so we unfortunately cannot process a return."
            )
            return {
                "success": False,
                "message": msg,
                "eligible": False,
                "days_since_order": days_since,
            }

        return_id = self.db.generate_return_id()
        req = ReturnRequest(
            return_id=return_id,
            order_id=order_id,
            customer_id=customer_id,
            created_at=now,
            reason=reason,
            status="APPROVED",  # for demo we auto-approve
            message="Return approved. Please drop the product at nearest store or schedule a pickup.",
        )
        self.db.returns[return_id] = req

        return {
            "success": True,
            "return_id": return_id,
            "status": req.status,
            "message": req.message,
            "order_id": order_id,
        }

    # ----- 3. Submit Feedback ----- #

    def submit_feedback(self, order_id: str, customer_id: str, rating: int, comment: Optional[str]):
        if rating < 1 or rating > 5:
            return {
                "success": False,
                "message": "Rating must be between 1 and 5.",
            }

        order = self.db.orders.get(order_id)
        if not order or order.customer_id != customer_id:
            return {
                "success": False,
                "message": "Order not found for this customer.",
            }

        feedback_id = self.db.generate_feedback_id()
        fb = Feedback(
            feedback_id=feedback_id,
            order_id=order_id,
            customer_id=customer_id,
            rating=rating,
            comment=comment,
            created_at=datetime.utcnow(),
        )
        self.db.feedbacks[feedback_id] = fb

        # You can later use this in analytics / product quality loops

        return {
            "success": True,
            "feedback_id": feedback_id,
            "message": "Thanks for your feedback! It really helps us improve.",
        }
