# agents/post_purchase_agent.py
from typing import Dict, Any
from datetime import datetime, timedelta
from .base_agent import BaseAgent, Task, TaskResult, ErrorDetail, NextAction
import uuid

class PostPurchaseAgent(BaseAgent):
    name = "post_purchase"

    def __init__(self):
        # in-memory records: return_id -> details
        self._returns = {}
        self._feedback = []

    def handle(self, task: Task) -> TaskResult:
        t = task.type
        if t == "RETURNS_INITIATE":
            return self._initiate_return(task)
        if t == "RETURNS_STATUS":
            return self._status(task)
        if t == "FEEDBACK_SUBMIT":
            return self._feedback_submit(task)
        if t == "WARRANTY_CHECK":
            return self._warranty_check(task)
        return TaskResult(task_id=task.task_id, agent=self.name, status="failed",
                          errors=[ErrorDetail(code="UNSUPPORTED_TASK", message=f"Unsupported: {t}", details={})])

    def _initiate_return(self, task: Task) -> TaskResult:
        # payload: {"order_id": "...", "items":[{"sku":"..","qty":1}], "reason": "defective"}
        order_id = task.payload.get("order_id")
        items = task.payload.get("items", [])
        reason = task.payload.get("reason", "customer_request")
        if not order_id or not items:
            return TaskResult(task_id=task.task_id, agent=self.name, status="failed",
                              errors=[ErrorDetail(code="MISSING_FIELDS", message="order_id and items required", details={})])

        rid = f"ret_{uuid.uuid4().hex[:8]}"
        est_process_days = 3
        self._returns[rid] = {
            "return_id": rid,
            "order_id": order_id,
            "items": items,
            "reason": reason,
            "status": "INITIATED",
            "created_at": datetime.utcnow().isoformat(),
            "expected_complete_at": (datetime.utcnow() + timedelta(days=est_process_days)).isoformat()
        }
        return TaskResult(task_id=task.task_id, agent=self.name, status="success",
                          payload={"return_id": rid, "status": "INITIATED", "expected_complete_at": self._returns[rid]["expected_complete_at"]},
                          next_actions=[NextAction(type="NOTIFY_CUSTOMER", message=f"Return initiated (id: {rid}). We'll process it within {est_process_days} days.")])

    def _status(self, task: Task) -> TaskResult:
        rid = task.payload.get("return_id")
        if not rid or rid not in self._returns:
            return TaskResult(task_id=task.task_id, agent=self.name, status="failed",
                              errors=[ErrorDetail(code="INVALID_RETURN_ID", message="return_id invalid", details={})])
        return TaskResult(task_id=task.task_id, agent=self.name, status="success", payload=self._returns[rid])

    def _feedback_submit(self, task: Task) -> TaskResult:
        # payload: {"order_id":"...", "rating":5, "comments":"..."}
        feedback = {
            "order_id": task.payload.get("order_id"),
            "rating": int(task.payload.get("rating", 0)),
            "comments": task.payload.get("comments", ""),
            "customer_id": task.customer_id,
            "created_at": datetime.utcnow().isoformat()
        }
        self._feedback.append(feedback)
        return TaskResult(task_id=task.task_id, agent=self.name, status="success", payload={"saved": True})

    def _warranty_check(self, task: Task) -> TaskResult:
        # payload: {"sku":"...", "purchase_date":"2024-01-01"} -> demo: 1-year warranty
        purchase_date = task.payload.get("purchase_date")
        sku = task.payload.get("sku")
        if not purchase_date or not sku:
            return TaskResult(task_id=task.task_id, agent=self.name, status="failed",
                              errors=[ErrorDetail(code="MISSING_FIELDS", message="sku and purchase_date required", details={})])
        # naive parse YYYY-MM-DD
        try:
            from datetime import datetime
            pd = datetime.fromisoformat(purchase_date)
        except Exception as e:
            return TaskResult(task_id=task.task_id, agent=self.name, status="failed",
                              errors=[ErrorDetail(code="INVALID_DATE", message="purchase_date must be ISO YYYY-MM-DD", details={})])
        warranty_period_days = 365
        expires = pd + timedelta(days=warranty_period_days)
        is_valid = expires > datetime.utcnow()
        return TaskResult(task_id=task.task_id, agent=self.name, status="success",
                          payload={"sku": sku, "warranty_valid": is_valid, "warranty_expires_on": expires.isoformat()})
