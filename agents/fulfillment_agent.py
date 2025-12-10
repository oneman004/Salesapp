# agents/fulfillment_agent.py
from typing import Any, Dict
from datetime import datetime, timedelta, timezone
import uuid
from .base_agent import BaseAgent, Task, TaskResult, ErrorDetail, NextAction

class FulfillmentAgent(BaseAgent):
    name = "fulfillment"

    def __init__(self):
        # in-memory fulfillment records: fulfillment_id -> details
        self._fulfillments: Dict[str, Dict[str, Any]] = {}
        # simple list of stores with capacity (for click-and-collect)
        self._stores = {
            "STORE_1": {"city": "Bangalore", "capacity": 20},
            "STORE_2": {"city": "Mumbai", "capacity": 10},
            "WAREHOUSE": {"city": "Warehouse", "capacity": 100}
        }

    def handle(self, task: Task) -> TaskResult:
        t = task.type
        if t == "FULFILLMENT_CREATE":
            return self._create(task)
        if t == "FULFILLMENT_UPDATE_STATUS":
            return self._update_status(task)
        if t == "FULFILLMENT_CANCEL":
            return self._cancel(task)
        if t == "FULFILLMENT_GET":
            return self._get(task)
        return TaskResult(task_id=task.task_id, agent=self.name, status="failed",
                          errors=[ErrorDetail(code="UNSUPPORTED_TASK", message=f"Unsupported: {t}", details={})])

    def _create(self, task: Task) -> TaskResult:
        payload = task.payload or {}
        order_id = payload.get("order_id")
        mode = payload.get("mode", "ship_to_home")  # ship_to_home | click_and_collect
        address = payload.get("address", {})
        items = payload.get("items", [])
        inventory_confirmed = payload.get("inventory_confirmation", False)

        if not order_id or not items:
            return TaskResult(task_id=task.task_id, agent=self.name, status="failed",
                              errors=[ErrorDetail(code="MISSING_FIELDS", message="order_id and items required", details={})])

        if not inventory_confirmed:
            return TaskResult(task_id=task.task_id, agent=self.name, status="failed",
                              errors=[ErrorDetail(code="INVENTORY_NOT_CONFIRMED", message="Inventory must be confirmed before fulfillment", details={})],
                              next_actions=[NextAction(type="CALL_AGENT", message="Ask InventoryAgent to confirm or reserve stock.", data={"agent":"inventory"})])

        fid = f"ful_{uuid.uuid4().hex[:8]}"
        if mode == "ship_to_home":
            city = (address.get("city") or "").lower()
            # simple ETA rules
            if city in {"bengaluru", "bangalore", "mumbai", "delhi", "kolkata"}:
                eta_days = 2
            else:
                eta_days = 4
            eta_date = (datetime.now(timezone.utc).date() + timedelta(days=eta_days)).isoformat()
            slot = "10:00-14:00"
            record = {
                "fulfillment_id": fid,
                "order_id": order_id,
                "mode": "ship_to_home",
                "status": "SCHEDULED",
                "eta": eta_date,
                "slot": slot,
                "store_id": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "items": items
            }
            self._fulfillments[fid] = record
            return TaskResult(task_id=task.task_id, agent=self.name, status="success",
                              payload=record,
                              next_actions=[NextAction(type="NOTIFY_CUSTOMER", message=f"Your order will be delivered by {eta_date} between {slot}.")])

        if mode == "click_and_collect":
            # select a store (prefer store_id in payload)
            store_id = payload.get("store_id")
            if not store_id:
                # choose a store that has capacity
                store_id = next((s for s, v in self._stores.items() if v["capacity"] > 0), None)
                if store_id is None:
                    return TaskResult(task_id=task.task_id, agent=self.name, status="failed",
                                      errors=[ErrorDetail(code="NO_STORE_AVAILABLE", message="No store available for pickup", details={})])
            # decrement store capacity (simple)
            self._stores[store_id]["capacity"] -= 1
            ready_date = (datetime.utcnow().date() + timedelta(days=1)).isoformat()
            slot = "16:00-21:00"
            record = {
                "fulfillment_id": fid,
                "order_id": order_id,
                "mode": "click_and_collect",
                "status": "READY_SOON",
                "eta": ready_date,
                "slot": slot,
                "store_id": store_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "items": items
            }
            self._fulfillments[fid] = record
            return TaskResult(task_id=task.task_id, agent=self.name, status="success",
                              payload=record,
                              next_actions=[NextAction(type="NOTIFY_CUSTOMER", message=f"Your order will be ready for pickup at {store_id} by {ready_date}, between {slot}.")])

        return TaskResult(task_id=task.task_id, agent=self.name, status="failed",
                          errors=[ErrorDetail(code="UNSUPPORTED_MODE", message=f"Unsupported mode: {mode}", details={})])

    def _update_status(self, task: Task) -> TaskResult:
        fid = task.payload.get("fulfillment_id")
        new_status = task.payload.get("status")
        if not fid or fid not in self._fulfillments:
            return TaskResult(task_id=task.task_id, agent=self.name, status="failed",
                              errors=[ErrorDetail(code="FULFILLMENT_NOT_FOUND", message="fulfillment_id invalid", details={})])

        self._fulfillments[fid]["status"] = new_status
        self._fulfillments[fid]["updated_at"] = datetime.utcnow().isoformat()
        return TaskResult(task_id=task.task_id, agent=self.name, status="success", payload=self._fulfillments[fid])

    def _cancel(self, task: Task) -> TaskResult:
        fid = task.payload.get("fulfillment_id")
        reason = task.payload.get("reason", "customer_request")
        if not fid or fid not in self._fulfillments:
            return TaskResult(task_id=task.task_id, agent=self.name, status="failed",
                              errors=[ErrorDetail(code="FULFILLMENT_NOT_FOUND", message="fulfillment_id invalid", details={})])

        record = self._fulfillments[fid]
        record["status"] = "CANCELLED"
        record["cancel_reason"] = reason
        record["cancelled_at"] = datetime.utcnow().isoformat()
        # if click-and-collect, release store capacity
        if record.get("mode") == "click_and_collect" and record.get("store_id"):
            sid = record["store_id"]
            if sid in self._stores:
                self._stores[sid]["capacity"] += 1
        return TaskResult(task_id=task.task_id, agent=self.name, status="success", payload=record,
                          next_actions=[NextAction(type="NOTIFY_CUSTOMER", message="Your delivery has been cancelled.")] )

    def _get(self, task: Task) -> TaskResult:
        fid = task.payload.get("fulfillment_id")
        if not fid:
            return TaskResult(task_id=task.task_id, agent=self.name, status="success", payload={"fulfillments": list(self._fulfillments.values())})
        if fid not in self._fulfillments:
            return TaskResult(task_id=task.task_id, agent=self.name, status="failed", errors=[ErrorDetail(code="FULFILLMENT_NOT_FOUND", message="No fulfillment found", details={})])
        return TaskResult(task_id=task.task_id, agent=self.name, status="success", payload=self._fulfillments[fid])
