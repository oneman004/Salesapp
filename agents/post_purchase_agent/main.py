from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from post_purchase_agent import PostPurchaseAgent

app = FastAPI(title="Post Purchase Support Agent")

# allow calls from web-app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # dev/demo only
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

agent = PostPurchaseAgent()


# ---------- Request Schemas ---------- #

class TrackOrderRequest(BaseModel):
    order_id: str
    customer_id: str


class ReturnRequestIn(BaseModel):
    order_id: str
    customer_id: str
    reason: str


class FeedbackRequest(BaseModel):
    order_id: str
    customer_id: str
    rating: int
    comment: Optional[str] = None


# ---------- Endpoints ---------- #

@app.post("/postpurchase/track-order")
def track_order(payload: TrackOrderRequest):
    return agent.track_order(
        order_id=payload.order_id,
        customer_id=payload.customer_id,
    )


@app.post("/postpurchase/request-return")
def request_return(payload: ReturnRequestIn):
    return agent.create_return_request(
        order_id=payload.order_id,
        customer_id=payload.customer_id,
        reason=payload.reason,
    )


@app.post("/postpurchase/feedback")
def submit_feedback(payload: FeedbackRequest):
    return agent.submit_feedback(
        order_id=payload.order_id,
        customer_id=payload.customer_id,
        rating=payload.rating,
        comment=payload.comment,
    )
