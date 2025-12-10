# app/demo_run.py
from .orchestrator import orchestrator
from fastapi import FastAPI
import uuid
app = FastAPI()
def run_demo():
    cart = [{"sku":"TSHIRT-RED-XL","qty":1,"price":799}]
    customer_id = "cust_001"
    payment = {"method":"card","card_number":"4111111111111112"}  # even last digit => success in mock
    address = {"line1":"Flat 101","city":"Bangalore","pincode":"560001"}

    res = orchestrator.checkout_flow(cart=cart, customer_id=customer_id, payment_payload=payment, address=address)
    print("Demo checkout result:")
    import json
    print(json.dumps(res, indent=2))

if __name__ == "__main__":
    run_demo()
