"""Purchase-time copies consumed without mutating account/address records."""

ADDRESS_FIELDS = ("label", "line1", "line2", "city", "state", "postal_code", "country", "is_default")
CUSTOMER_FIELDS = ("full_name", "username", "email", "phone")


def customer_snapshot(user):
    return {"id": str(user.id), **{field: getattr(user, field) for field in CUSTOMER_FIELDS}}


def address_snapshot(address, user):
    return {"id": str(address.id), **{field: getattr(address, field) for field in ADDRESS_FIELDS},
            "full_name": user.full_name, "phone": user.phone}


def order_details(order):
    """The existing nested response shape, with purchase-time values."""
    customer = order.customer_details
    result = {"user": None, "shipping_address": None, "billing_address": None}
    if customer is not None:
        result["user"] = {"id": str(customer.id), **{
            field: getattr(customer, field) for field in ("full_name", "email", "phone")}}
    for kind in ("shipping", "billing"):
        address = getattr(order, f"{kind}_details")
        if address is not None:
            result[f"{kind}_address"] = {"id": str(address.id), **{
                field: getattr(address, field) for field in ADDRESS_FIELDS},
                "full_name": getattr(customer, "full_name", None),
                "phone": getattr(customer, "phone", None)}
    return result
