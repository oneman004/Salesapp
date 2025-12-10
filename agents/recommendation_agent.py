# agents/recommendation_agent.py
from typing import Dict, Any, List
import random
from .base_agent import BaseAgent, Task, TaskResult, ErrorDetail, NextAction

# lightweight product catalog + related SKUs for demo
_PRODUCT_CATALOG = {
    "TSHIRT-RED-XL": {"name": "Red T-Shirt XL", "category": "apparel", "price": 799, "related": ["HAT-BLK", "TSHIRT-BLUE-M"]},
    "TSHIRT-BLUE-M": {"name": "Blue T-Shirt M", "category": "apparel", "price": 749, "related": ["HAT-BLK"]},
    "JEANS-BLK-32": {"name": "Black Jeans 32", "category": "apparel", "price": 1999, "related": ["BELT-BRN", "HAT-BLK"]},
    "HAT-BLK": {"name": "Black Cap", "category": "accessory", "price": 399, "related": ["TSHIRT-RED-XL"]},
    "BELT-BRN": {"name": "Brown Belt", "category": "accessory", "price": 499, "related": []},
}

# to check inventory we import the InventoryAgent class (same process-level instance recommended by orchestrator)
# the orchestrator should pass an inventory client or keep same instance; for demo we'll allow optional client in payload
class RecommendationAgent(BaseAgent):
    name = "recommendation"

    def __init__(self):
        pass

    def handle(self, task: Task) -> TaskResult:
        t = task.type
        if t == "RECOMMEND_FOR_CART":
            return self._for_cart(task)
        if t == "RECOMMEND_ALTERNATIVES":
            return self._alternatives(task)
        return TaskResult(
            task_id=task.task_id,
            agent=self.name,
            status="failed",
            errors=[ErrorDetail(code="UNSUPPORTED_TASK", message=f"Unsupported: {t}", details={})]
        )

    def _for_cart(self, task: Task) -> TaskResult:
        # payload: {"cart": [{"sku":"...","qty":n}], "user_profile": {...}, "inventory_client": optional_instance}
        cart = task.payload.get("cart", [])
        user_profile = task.payload.get("user_profile", {})
        inventory_client = task.payload.get("inventory_client")  # orchestrator can pass a Python object (InventoryAgent instance)
        # Collect top related SKUs (simple union of related lists)
        related_scores: Dict[str, float] = {}
        for item in cart:
            sku = item.get("sku")
            catalog = _PRODUCT_CATALOG.get(sku)
            if not catalog: continue
            for rel in catalog.get("related", []):
                related_scores[rel] = related_scores.get(rel, 0) + 1.0

        # Boost by simple heuristics: if user likes accessories, prefer accessory category
        pref = user_profile.get("preference_category")
        if pref:
            for sku in list(related_scores.keys()):
                if _PRODUCT_CATALOG.get(sku, {}).get("category") == pref:
                    related_scores[sku] *= 1.2

        # Build candidate list sorted
        candidates = sorted(related_scores.items(), key=lambda kv: kv[1], reverse=True)
        results = []
        for sku, score in candidates:
            entry = _PRODUCT_CATALOG.get(sku)
            # check inventory if client present
            available = True
            available_qty = None
            if inventory_client:
                # call inventory client programmatically
                inv_task = Task(
                    task_id=f"inv_check_{sku}",
                    agent="inventory",
                    type="INVENTORY_CHECK",
                    session_id=task.session_id,
                    customer_id=task.customer_id,
                    payload={"items": [{"sku": sku, "qty": 1}]},
                )
                inv_res = inventory_client.handle(inv_task)
                if inv_res.status != "success":
                    available = False
                else:
                    available_qty = inv_res.payload["items"][0].get("available_qty")
            results.append({
                "sku": sku,
                "name": entry["name"],
                "price": entry["price"],
                "score": score,
                "available": available,
                "available_qty": available_qty
            })

        # If no candidates, fallback to category-based suggestions
        if not results:
            # simple fallback: top-selling (random demo)
            fallback = random.sample(list(_PRODUCT_CATALOG.keys()), k=min(2, len(_PRODUCT_CATALOG)))
            for sku in fallback:
                entry = _PRODUCT_CATALOG[sku]
                results.append({"sku": sku, "name": entry["name"], "price": entry["price"], "score": 0.1, "available": True})

        return TaskResult(
            task_id=task.task_id,
            agent=self.name,
            status="success",
            payload={"recommendations": results}
        )

    def _alternatives(self, task: Task) -> TaskResult:
        # payload: {"sku":"...","inventory_client": optional}
        sku = task.payload.get("sku")
        inventory_client = task.payload.get("inventory_client")
        if not sku:
            return TaskResult(
                task_id=task.task_id,
                agent=self.name,
                status="failed",
                errors=[ErrorDetail(code="MISSING_SKU", message="sku is required", details={})]
            )
        # simple alternative search: same category or related in catalog
        alt_candidates = []
        source = _PRODUCT_CATALOG.get(sku)
        if not source:
            return TaskResult(
                task_id=task.task_id,
                agent=self.name,
                status="failed",
                errors=[ErrorDetail(code="SKU_NOT_IN_CATALOG", message=f"{sku} not found", details={})]
            )
        # first try explicit related
        for r in source.get("related", []):
            alt_candidates.append(r)
        # then same category items
        for k, v in _PRODUCT_CATALOG.items():
            if v["category"] == source["category"] and k != sku:
                alt_candidates.append(k)
        # dedupe
        seen = set()
        alts = []
        for a in alt_candidates:
            if a in seen: continue
            seen.add(a)
            entry = _PRODUCT_CATALOG.get(a)
            available = True
            if inventory_client:
                inv_task = Task(
                    task_id=f"inv_check_alt_{a}",
                    agent="inventory",
                    type="INVENTORY_CHECK",
                    session_id=task.session_id,
                    customer_id=task.customer_id,
                    payload={"items": [{"sku": a, "qty": 1}]}
                )
                inv_res = inventory_client.handle(inv_task)
                available = (inv_res.status == "success")
            alts.append({"sku": a, "name": entry["name"], "price": entry["price"], "available": available})
        return TaskResult(
            task_id=task.task_id,
            agent=self.name,
            status="success",
            payload={"alternatives": alts}
        )

# quick demo main
if __name__ == "__main__":
    from base_agent import Task
    import uuid
    ra = RecommendationAgent()
    cart = [{"sku": "TSHIRT-RED-XL", "qty": 1}]
    t = Task(task_id=str(uuid.uuid4()), agent="recommendation", type="RECOMMEND_FOR_CART", session_id="s1", customer_id="c1", payload={"cart": cart, "user_profile": {"preference_category": "accessory"}})
    print(ra.handle(t))
