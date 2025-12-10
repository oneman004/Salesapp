# tests/test_flow.py
import uuid
from agents.app.orchestrator import orchestrator

def test_successful_checkout():
    cart = [{"sku":"TSHIRT-RED-XL","qty":1,"price":799}]
    customer_id = "cust_001"
    payment = {"method":"card","card_number":"4111111111111112"}
    address = {"line1":"Addr","city":"Bangalore","pincode":"560001"}
    res = orchestrator.checkout_flow(cart=cart, customer_id=customer_id, payment_payload=payment, address=address)
    assert res["status"] == "success"
    assert "order_id" in res
