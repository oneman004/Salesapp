# agents/inventory_agent.py
import threading
from typing import Dict, Any, List
from datetime import datetime, timezone
from .base_agent import BaseAgent, Task, TaskResult, ErrorDetail, NextAction

_lock = threading.Lock()

class InventoryAgent(BaseAgent):
    name = "inventory"

    def __init__(self):
        # simple in-memory stock: sku -> {"qty": int, "locations": {...}}
        # location model is optional for demo (store-level availability)
        self._stock: Dict[str, Dict[str, Any]] = {
            "TSHIRT-RED-XL": {"qty": 10, "locations": {"STORE_1": 5, "WAREHOUSE": 5}},
            "TSHIRT-BLUE-M": {"qty": 0, "locations": {"STORE_1": 0, "WAREHOUSE": 0}},
            "JEANS-BLK-32": {"qty": 6, "locations": {"STORE_2": 6}},
            "HAT-BLK": {"qty": 15, "locations": {"WAREHOUSE": 15}},
        }
        # reservations store reservation_id -> details
        self._reservations: Dict[str, Dict[str, Any]] = {}

    def handle(self, task: Task) -> TaskResult:
        t = task.type
        if t == "INVENTORY_CHECK":
            return self._check(task)
        if t == "INVENTORY_RESERVE":
            return self._reserve(task)
        if t == "INVENTORY_RELEASE":
            return self._release(task)
        if t == "INVENTORY_GET":
            return self._get(task)
        else:
            return TaskResult(
                task_id=task.task_id,
                agent=self.name,
                status="failed",
                errors=[ErrorDetail(code="UNSUPPORTED_TASK", message=f"Unsupported: {t}", details={})]
            )

    def _check(self, task: Task) -> TaskResult:
        # payload: {"items": [{"sku":"...", "qty": n}], "preferred_store": "STORE_1" (optional)}
        items = task.payload.get("items", [])
        preferred_store = task.payload.get("preferred_store")
        response_items = []
        for it in items:
            sku = it.get("sku")
            qty = int(it.get("qty", 1))
            stock_entry = self._stock.get(sku)
            if not stock_entry:
                response_items.append({"sku": sku, "available": False, "available_qty": 0})
                continue
            available_qty = stock_entry.get("qty", 0)
            # If preferred store is given, check store-level first
            if preferred_store and preferred_store in stock_entry.get("locations", {}):
                loc_qty = stock_entry["locations"][preferred_store]
                # report store qty and total qty
                response_items.append({
                    "sku": sku,
                    "available": (loc_qty >= qty) or (available_qty >= qty),
                    "available_qty": available_qty,
                    "store_qty": loc_qty
                })
            else:
                response_items.append({
                    "sku": sku,
                    "available": available_qty >= qty,
                    "available_qty": available_qty
                })

        all_available = all(ri["available"] for ri in response_items)
        status = "success" if all_available else "failed"
        next_actions = []
        if not all_available:
            # ask inventory confirmation or fallback to store pickup
            next_actions.append(NextAction(
                type="CALL_AGENT",
                message="Some items are out of stock. Ask Inventory/Recommendation for alternatives.",
                data={"agent": "recommendation", "reason": "inventory_low"}
            ))
        return TaskResult(
            task_id=task.task_id,
            agent=self.name,
            status=status,
            payload={"items": response_items}
        )

    def _reserve(self, task: Task) -> TaskResult:
        # payload: {"order_id":"...","items":[{"sku":"...","qty":n}],"hold_for_minutes":30}
        order_id = task.payload.get("order_id")
        items = task.payload.get("items", [])
        hold = int(task.payload.get("hold_for_minutes", 30))
        if not order_id or not items:
            return TaskResult(
                task_id=task.task_id,
                agent=self.name,
                status="failed",
                errors=[ErrorDetail(code="MISSING_FIELDS", message="order_id & items required", details={})]
            )

        # first verify availability atomically
        with _lock:
            for it in items:
                sku = it["sku"]
                qty = int(it["qty"])
                if sku not in self._stock or self._stock[sku]["qty"] < qty:
                    return TaskResult(
                        task_id=task.task_id,
                        agent=self.name,
                        status="failed",
                        errors=[ErrorDetail(code="INSUFFICIENT_STOCK", message=f"SKU {sku} insufficient", details={"sku": sku})],
                        next_actions=[NextAction(type="CALL_AGENT", message="Ask inventory manager to restock", data={"sku": sku})]
                    )
            # reduce stock and create reservation
            reservation_ts = int(datetime.now(timezone.utc).timestamp())
            reservation_id = f"res_{order_id}_{reservation_ts}"
            for it in items:
                sku = it["sku"]
                qty = int(it["qty"])
                self._stock[sku]["qty"] -= qty
                # try to decrement from locations if present (prefer warehouse)
                # simple algorithm: decrement warehouse first
                locs = self._stock[sku].get("locations", {})
                for loc in sorted(locs.keys()):
                    if locs[loc] >= qty:
                        locs[loc] -= qty
                        break
                    else:
                        consumed = locs[loc]
                        qty -= consumed
                        locs[loc] = 0
                # store back
                self._stock[sku]["locations"] = locs

            self._reservations[reservation_id] = {
                "order_id": order_id,
                "items": items,
                "expires_in_minutes": hold,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
        return TaskResult(
            task_id=task.task_id,
            agent=self.name,
            status="success",
            payload={"reservation_id": reservation_id, "reserved_items": items, "hold_for_minutes": hold}
        )

    def _release(self, task: Task) -> TaskResult:
        # payload: {"reservation_id": "..."} -> return stock back
        rid = task.payload.get("reservation_id")
        if not rid or rid not in self._reservations:
            return TaskResult(
                task_id=task.task_id,
                agent=self.name,
                status="failed",
                errors=[ErrorDetail(code="INVALID_RESERVATION", message="reservation missing or invalid", details={"reservation_id": rid})]
            )
        details = self._reservations.pop(rid)
        items = details["items"]
        with _lock:
            for it in items:
                sku = it["sku"]
                qty = int(it["qty"])
                if sku not in self._stock:
                    self._stock[sku] = {"qty": qty, "locations": {}}
                else:
                    self._stock[sku]["qty"] += qty
                    # for simplicity add back to WAREHOUSE
                    locs = self._stock[sku].setdefault("locations", {})
                    locs["WAREHOUSE"] = locs.get("WAREHOUSE", 0) + qty
        return TaskResult(
            task_id=task.task_id,
            agent=self.name,
            status="success",
            payload={"released_reservation": rid}
        )

    def _get(self, task: Task) -> TaskResult:
        # payload may be {"sku":"..."} or empty to list all
        sku = task.payload.get("sku")
        if sku:
            entry = self._stock.get(sku)
            if not entry:
                return TaskResult(
                    task_id=task.task_id,
                    agent=self.name,
                    status="failed",
                    errors=[ErrorDetail(code="SKU_NOT_FOUND", message=f"SKU {sku} not found", details={})]
                )
            return TaskResult(
                task_id=task.task_id,
                agent=self.name,
                status="success",
                payload={"sku": sku, "entry": entry}
            )
        else:
            return TaskResult(
                task_id=task.task_id,
                agent=self.name,
                status="success",
                payload={"stock": self._stock}
            )

# For quick manual demo:
if __name__ == "__main__":
    from base_agent import Task
    import uuid
    a = InventoryAgent()
    t = Task(task_id=str(uuid.uuid4()), agent="inventory", type="INVENTORY_CHECK", session_id="s1", customer_id=None, payload={"items":[{"sku":"TSHIRT-RED-XL","qty":2}]})
    print(a.handle(t))
