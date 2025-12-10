# agents/payment_agent.py
import uuid
from typing import Dict, Any
from datetime import datetime, timezone
from .base_agent import BaseAgent, Task, TaskResult, ErrorDetail, NextAction

class PaymentAgent(BaseAgent):
    name = "payment"

    def __init__(self):
        # simple in-memory ledger: tx_id -> record
        self._transactions: Dict[str, Dict[str, Any]] = {}
        # mock saved cards (customer_id -> list of cards)
        self._saved_cards = {
            "cust_001": [{"card_number": "4111111111111112", "token": "tok_card_1112", "expiry": "12/26"}]
        }

    def handle(self, task: Task) -> TaskResult:
        t = task.type
        if t == "PAYMENT_AUTHORIZE":
            return self._authorize(task)
        if t == "PAYMENT_CAPTURE":
            return self._capture(task)
        if t == "PAYMENT_REFUND":
            return self._refund(task)
        if t == "PAYMENT_STATUS":
            return self._status(task)
        return TaskResult(
            task_id=task.task_id,
            agent=self.name,
            status="failed",
            errors=[ErrorDetail(code="UNSUPPORTED_TASK", message=f"Unsupported task type: {t}", details={})]
        )

    # -------------------------
    # Authorization (mock)
    # -------------------------
    def _authorize(self, task: Task) -> TaskResult:
        payload = task.payload or {}
        amount = payload.get("amount")
        payment = payload.get("payment", {})  # { method: 'card'|'upi'|'gift_card'|'pos', ... }

        if amount is None or amount <= 0:
            return TaskResult(task_id=task.task_id, agent=self.name, status="failed",
                              errors=[ErrorDetail(code="INVALID_AMOUNT", message="Amount must be > 0", details={"amount": amount})])

        method = payment.get("method")
        if method == "card":
            return self._authorize_card(task, amount, payment)
        if method == "upi":
            return self._authorize_upi(task, amount, payment)
        if method == "gift_card":
            return self._authorize_gift_card(task, amount, payment)
        if method == "pos":
            return self._authorize_pos(task, amount, payment)
        return TaskResult(task_id=task.task_id, agent=self.name, status="failed",
                          errors=[ErrorDetail(code="UNSUPPORTED_METHOD", message=f"Unsupported payment method: {method}", details={})],
                          next_actions=[NextAction(type="ASK_CUSTOMER", message="Supported methods: card, upi, gift_card, pos")])

    def _authorize_card(self, task: Task, amount: float, payment: Dict[str, Any]) -> TaskResult:
        card_number = payment.get("card_number", "")
        token = payment.get("token")  # prefer token if passed
        cid = task.customer_id

        last4 = card_number[-4:] if card_number else (token[-4:] if token else "0000")
        tx_id = f"tx_{uuid.uuid4().hex[:8]}"

        # Basic validation rules for demo
        if card_number and len(card_number) < 12:
            return TaskResult(task_id=task.task_id, agent=self.name, status="failed",
                              errors=[ErrorDetail(code="INVALID_CARD", message="Card number too short", details={"card_number": card_number})],
                              next_actions=[NextAction(type="ASK_CUSTOMER", message="Please re-enter card details.")])

        # Demo rule: last4 '0000' => decline - insufficient funds
        if last4 == "0000":
            return TaskResult(task_id=task.task_id, agent=self.name, status="failed",
                              errors=[ErrorDetail(code="INSUFFICIENT_FUNDS", message="Card declined - insufficient funds", details={"last4": last4})],
                              next_actions=[NextAction(type="ASK_CUSTOMER", message="Your card was declined. Would you like to try UPI or another card?")])

        # Demo: even last digit -> success; odd -> random decline
        try:
            decision_even = int(last4[-1]) % 2 == 0
        except Exception:
            decision_even = True

        if decision_even:
            auth_id = f"auth_{tx_id}"
            self._transactions[tx_id] = {
                "tx_id": tx_id, "auth_id": auth_id, "method": "card", "last4": last4,
                "amount": amount, "status": "AUTHORIZED", "created_at": datetime.now(timezone.utc).isoformat()
            }
            return TaskResult(task_id=task.task_id, agent=self.name, status="success",
                              payload={"tx_id": tx_id, "auth_id": auth_id, "method": "card", "amount": amount})
        else:
            return TaskResult(task_id=task.task_id, agent=self.name, status="failed",
                              errors=[ErrorDetail(code="CARD_DECLINED", message="Issuer declined the card", details={"last4": last4})],
                              next_actions=[NextAction(type="ASK_CUSTOMER", message="Card was declined. Try another payment method?")])

    def _authorize_upi(self, task: Task, amount: float, payment: Dict[str, Any]) -> TaskResult:
        upi_id = payment.get("upi_id", "")
        tx_id = f"tx_{uuid.uuid4().hex[:8]}"

        if "@" not in upi_id:
            return TaskResult(task_id=task.task_id, agent=self.name, status="failed",
                              errors=[ErrorDetail(code="INVALID_UPI", message="UPI id looks invalid", details={"upi_id": upi_id})],
                              next_actions=[NextAction(type="ASK_CUSTOMER", message="Please check the UPI ID.")])

        # demo: if upi contains 'fail' -> immediate failure; else send collect (pending)
        if "fail" in upi_id:
            return TaskResult(task_id=task.task_id, agent=self.name, status="failed",
                              errors=[ErrorDetail(code="UPI_FAILURE", message="UPI collect failed", details={"upi_id": upi_id})],
                              next_actions=[NextAction(type="ASK_CUSTOMER", message="UPI failed. Try another method?")])

        auth_id = f"auth_{tx_id}"
        self._transactions[tx_id] = {
            "tx_id": tx_id, "auth_id": auth_id, "method": "upi", "upi_id": upi_id,
            "amount": amount, "status": "PENDING", "created_at": datetime.now(timezone.utc).isoformat()
        }
        return TaskResult(task_id=task.task_id, agent=self.name, status="pending",
                          payload={"tx_id": tx_id, "auth_id": auth_id, "method": "upi", "status": "COLLECT_REQUEST_SENT"},
                          next_actions=[NextAction(type="ASK_CUSTOMER", message=f"UPI collect request sent to {upi_id}. Please approve to continue.")])

    def _authorize_gift_card(self, task: Task, amount: float, payment: Dict[str, Any]) -> TaskResult:
        card_code = payment.get("card_code", "")
        # demo: allow mock_balance in payment payload for testing
        balance = int(payment.get("mock_balance", 1000))
        if balance < amount:
            return TaskResult(task_id=task.task_id, agent=self.name, status="failed",
                              errors=[ErrorDetail(code="INSUFFICIENT_GIFT_BALANCE", message="Gift card balance too low", details={"balance": balance})],
                              next_actions=[NextAction(type="ASK_CUSTOMER", message="Gift card low. Pay remainder via another method?")])
        tx_id = f"tx_{uuid.uuid4().hex[:8]}"
        auth_id = f"auth_{tx_id}"
        self._transactions[tx_id] = {"tx_id": tx_id, "auth_id": auth_id, "method": "gift_card", "amount": amount, "status": "AUTHORIZED", "created_at": datetime.now(timezone.utc).isoformat()}
        return TaskResult(task_id=task.task_id, agent=self.name, status="success",
                          payload={"tx_id": tx_id, "auth_id": auth_id, "method": "gift_card", "amount": amount})

    def _authorize_pos(self, task: Task, amount: float, payment: Dict[str, Any]) -> TaskResult:
        terminal = payment.get("terminal_id", "POS_1")
        tx_id = f"tx_{uuid.uuid4().hex[:8]}"
        auth_id = f"auth_{tx_id}"
        self._transactions[tx_id] = {"tx_id": tx_id, "auth_id": auth_id, "method": "pos", "terminal": terminal, "amount": amount, "status": "AUTHORIZED", "created_at": datetime.now(timezone.utc).isoformat()}
        return TaskResult(task_id=task.task_id, agent=self.name, status="success",
                          payload={"tx_id": tx_id, "auth_id": auth_id, "method": "pos", "amount": amount})

    # -------------------------
    # Capture, Refund, Status
    # -------------------------
    def _capture(self, task: Task) -> TaskResult:
        auth_id = task.payload.get("auth_id")
        # find tx
        found = None
        for tx in self._transactions.values():
            if tx.get("auth_id") == auth_id:
                found = tx
                break
        if not found:
            return TaskResult(task_id=task.task_id, agent=self.name, status="failed",
                              errors=[ErrorDetail(code="AUTH_NOT_FOUND", message="Authorization not found", details={"auth_id": auth_id})])

        if found["status"] == "CAPTURED":
            return TaskResult(task_id=task.task_id, agent=self.name, status="success", payload={"message": "Already captured", "tx": found})

        # For pending UPI, allow capture only if status was AUTHORIZED (for demo, we'll set pending->captured on capture)
        found["status"] = "CAPTURED"
        found["captured_at"] = datetime.now(timezone.utc).isoformat()
        return TaskResult(task_id=task.task_id, agent=self.name, status="success", payload={"capture_id": f"cap_{found['tx_id']}", "tx": found})

    def _refund(self, task: Task) -> TaskResult:
        tx_id = task.payload.get("tx_id")
        amount = task.payload.get("amount")
        tx = self._transactions.get(tx_id)
        if not tx:
            return TaskResult(task_id=task.task_id, agent=self.name, status="failed",
                              errors=[ErrorDetail(code="TX_NOT_FOUND", message="Transaction not found", details={"tx_id": tx_id})])
        # demo: refund allowed if captured
        tx_status = tx.get("status")
        if tx_status not in ("CAPTURED", "AUTHORIZED"):
            return TaskResult(task_id=task.task_id, agent=self.name, status="failed",
                              errors=[ErrorDetail(code="REFUND_NOT_ALLOWED", message=f"Cannot refund tx in status {tx_status}", details={})])
        ref_id = f"ref_{uuid.uuid4().hex[:8]}"
        tx.setdefault("refunds", []).append({"refund_id": ref_id, "amount": amount or tx.get("amount"), "refunded_at": datetime.utcnow().isoformat()})
        return TaskResult(task_id=task.task_id, agent=self.name, status="success", payload={"refund_id": ref_id, "tx_id": tx_id})

    def _status(self, task: Task) -> TaskResult:
        tx_id = task.payload.get("tx_id")
        tx = None
        if tx_id:
            tx = self._transactions.get(tx_id)
        else:
            # accept auth_id lookup
            auth_id = task.payload.get("auth_id")
            tx = next((t for t in self._transactions.values() if t.get("auth_id") == auth_id), None)
        if not tx:
            return TaskResult(task_id=task.task_id, agent=self.name, status="failed",
                              errors=[ErrorDetail(code="TX_NOT_FOUND", message="Transaction not found", details={})])
        return TaskResult(task_id=task.task_id, agent=self.name, status="success", payload={"tx": tx})
