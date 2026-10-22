from uuid import UUID

from sqlalchemy import select
from sqlmodel import Session

from app.models.address import Address
from app.models.order import Order


def get_address_by_id(session: Session, address_id: UUID) -> Address | None:
    """Get address by ID"""
    return session.get(Address, address_id)


def get_addresses_by_user(session: Session, user_id: UUID) -> list[Address]:
    """Get all addresses for a user"""
    statement = select(Address).where(Address.user_id == user_id)
    result = session.execute(statement)
    return result.scalars().all()  # ✅ Use scalars().all() instead of exec()


def create_address(session: Session, user_id: UUID, address_data: dict) -> Address:
    """Create a new address"""
    address = Address(user_id=user_id, **address_data)
    session.add(address)
    session.commit()
    session.refresh(address)
    return address


def update_address(session: Session, address: Address, address_data: dict) -> Address:
    """Update an address"""
    for key, value in address_data.items():
        setattr(address, key, value)
    session.add(address)
    session.commit()
    session.refresh(address)
    return address


def can_delete_address(session: Session, address_id: UUID) -> tuple[bool, str]:
    """
    Check if address can be deleted.
    Returns: (can_delete, message)
    """
    statement = select(Order).where(
        (Order.shipping_address_id == address_id) | 
        (Order.billing_address_id == address_id)
    )
    result = session.execute(statement)
    orders = result.scalars().all()
    
    if orders:
        order_numbers = [str(o.order_number) for o in orders[:3]]
        message = f"Cannot delete address. It is associated with {len(orders)} order(s)"
        if len(orders) <= 3:
            message += f": {', '.join(order_numbers)}"
        else:
            message += f": {', '.join(order_numbers)} and {len(orders) - 3} more"
        return False, message
    
    return True, "Address can be deleted"


def delete_address(session: Session, address: Address) -> None:
    """Delete an address (only if not used in orders)"""
    statement = select(Order).where(
        (Order.shipping_address_id == address.id) | 
        (Order.billing_address_id == address.id)
    )
    result = session.execute(statement)
    orders = result.scalars().all()
    
    if orders:
        order_numbers = [str(o.order_number) for o in orders[:5]]
        raise ValueError(
            f"Cannot delete address. It is associated with {len(orders)} order(s). "
            f"Order numbers: {', '.join(order_numbers)}"
        )
    
    session.delete(address)
    session.commit()


def set_default_address(session: Session, user_id: UUID, address_id: UUID) -> None:
    """Set an address as default for user"""
    # Remove default from all addresses
    statement = select(Address).where(Address.user_id == user_id)
    result = session.execute(statement)
    addresses = result.scalars().all()
    
    for addr in addresses:
        addr.is_default = False
        session.add(addr)
    
    # Set new default
    address = get_address_by_id(session, address_id)
    if address:
        address.is_default = True
        session.add(address)
    
    session.commit()