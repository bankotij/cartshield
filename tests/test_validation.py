import pytest
from pydantic import ValidationError
from app.api.schemas import CheckoutRequest

BASE = {"customer_id": "cust", "items": [{"sku": "item", "quantity": 1}], "payment_method": "card", "total_amount": 10}

@pytest.mark.parametrize("change", [{"items": []}, {"total_amount": float("inf")}, {"total_amount": float("nan")}, {"total_amount": 0}, {"customer_id": ""}, {"payment_method": ""}, {"items": [{"sku": "", "quantity": 1}]}])
def test_invalid_checkout_never_reaches_the_worker(change):
    with pytest.raises(ValidationError):
        CheckoutRequest(**(BASE | change))

def test_valid_checkout_keeps_failure_modes_optional():
    request = CheckoutRequest(**BASE)
    assert request.total_amount == 10
    assert request.payment_mode.value == "none"
