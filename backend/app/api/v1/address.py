from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.api.deps import SessionDep, CurrentUser
from app.models.user import User
from app.repositories import address as address_repo
from app.schemas.address import AddressCreate, AddressRead, AddressUpdate


router = APIRouter(prefix="/addresses", tags=["Addresses"])


@router.get("", response_model=list[AddressRead])
def get_addresses(
    session: SessionDep,
    current_user: CurrentUser,
):
    """Get all addresses for current user"""
    addresses = address_repo.get_addresses_by_user(session, current_user.id)
    
    # ✅ Explicitly convert to AddressRead - this fixes the issue
    return [
        AddressRead(
            id=addr.id,
            user_id=addr.user_id,
            label=addr.label,
            line1=addr.line1,
            line2=addr.line2,
            city=addr.city,
            state=addr.state,
            postal_code=addr.postal_code,
            country=addr.country,
            is_default=addr.is_default,
            created_at=addr.created_at,
        )
        for addr in addresses
    ]


@router.post("", response_model=AddressRead, status_code=status.HTTP_201_CREATED)
def create_address(
    address_data: AddressCreate,
    session: SessionDep,
    current_user: CurrentUser,
):
    """Create a new address"""
    address = address_repo.create_address(
        session,
        current_user.id,
        address_data.model_dump()
    )
    
    return AddressRead(
        id=address.id,
        user_id=address.user_id,
        label=address.label,
        line1=address.line1,
        line2=address.line2,
        city=address.city,
        state=address.state,
        postal_code=address.postal_code,
        country=address.country,
        is_default=address.is_default,
        created_at=address.created_at,
    )


@router.put("/{address_id}", response_model=AddressRead)
def update_address(
    address_id: UUID,
    address_data: AddressUpdate,
    session: SessionDep,
    current_user: CurrentUser,
):
    """Update an address"""
    address = address_repo.get_address_by_id(session, address_id)
    if not address:
        raise HTTPException(status_code=404, detail="Address not found")
    
    if address.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    updated = address_repo.update_address(
        session,
        address,
        address_data.model_dump(exclude_unset=True)
    )
    
    return AddressRead(
        id=updated.id,
        user_id=updated.user_id,
        label=updated.label,
        line1=updated.line1,
        line2=updated.line2,
        city=updated.city,
        state=updated.state,
        postal_code=updated.postal_code,
        country=updated.country,
        is_default=updated.is_default,
        created_at=updated.created_at,
    )


@router.delete("/{address_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_address(
    address_id: UUID,
    session: SessionDep,
    current_user: CurrentUser,
):
    """Delete an address"""
    address = address_repo.get_address_by_id(session, address_id)
    if not address:
        raise HTTPException(status_code=404, detail="Address not found")
    
    if address.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    can_delete, message = address_repo.can_delete_address(session, address_id)
    
    if not can_delete:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message
        )
    
    address_repo.delete_address(session, address)
    return None


@router.post("/default/{address_id}", response_model=AddressRead)
def set_default_address(
    address_id: UUID,
    session: SessionDep,
    current_user: CurrentUser,
):
    """Set an address as default"""
    address = address_repo.get_address_by_id(session, address_id)
    if not address:
        raise HTTPException(status_code=404, detail="Address not found")
    
    if address.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    address_repo.set_default_address(session, current_user.id, address_id)
    
    # ✅ Get updated address and return explicitly
    updated = address_repo.get_address_by_id(session, address_id)
    
    return AddressRead(
        id=updated.id,
        user_id=updated.user_id,
        label=updated.label,
        line1=updated.line1,
        line2=updated.line2,
        city=updated.city,
        state=updated.state,
        postal_code=updated.postal_code,
        country=updated.country,
        is_default=updated.is_default,
        created_at=updated.created_at,
    )