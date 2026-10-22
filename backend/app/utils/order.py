from datetime import datetime


def generate_order_number() -> str:
    """Generate unique order number: ORD-2026-001"""
    year = datetime.now().year
    month = datetime.now().month
    day = datetime.now().day
    
    # Get last order number and increment
    # For now, simple timestamp-based
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"ORD-{timestamp}"