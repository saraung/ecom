from uuid import UUID
from typing import Optional

from sqlalchemy import func, select
from sqlmodel import Session

from app.models.user import User, UserRole
from app.schemas.user import UserCreate
from app.core.security import hash_password


def get_user_by_email(session: Session, email: str) -> User | None:
    statement = select(User).where(User.email == email)
    result = session.execute(statement)
    return result.scalar_one_or_none()


def get_user_by_username(session: Session, username: str) -> User | None:
    statement = select(User).where(User.username == username)
    result = session.execute(statement)
    return result.scalar_one_or_none()


def create_user(session: Session, data: UserCreate, *, commit: bool = True) -> User:
    user = User(
        email=data.email,
        username=data.username,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
        phone=data.phone,
    )
    session.add(user)
    if commit:
        session.commit()
        session.refresh(user)
    else:
        session.flush()
    return user


def get_user_by_id(session: Session, user_id: UUID) -> User | None:
    """Get user by ID"""
    return session.get(User, user_id)


def get_all_users(
    session: Session,
    skip: int = 0,
    limit: int = 20,
    search: str | None = None,
    role: UserRole | str | None = None,
    is_active: bool | None = None,
) -> tuple[list[User], int]:
    """
    Get all users with filters and pagination.

    Args:
        session: Database session
        skip: Number of records to skip
        limit: Maximum records to return
        search: Search by email, username, or full_name
        role: Legacy role enum member/value OR a dynamic role slug
            (e.g. "packer") — slugs are matched via the user_roles table.
        is_active: Filter by active status

    Returns:
        tuple: (list of users, total count)
    """
    from app.models.rbac import Role, UserRoleLink

    statement = select(User)

    # Apply filters
    if search:
        statement = statement.where(
            (User.email.ilike(f"%{search}%")) |
            (User.username.ilike(f"%{search}%")) |
            (User.full_name.ilike(f"%{search}%"))
        )

    if role:
        role_value = getattr(role, "value", role)
        legacy_values = {r.value for r in UserRole}
        if role_value in legacy_values:
            statement = statement.where(User.role == UserRole(role_value))
        else:
            # Dynamic (custom) role slug → match via role assignments.
            statement = (
                statement.join(
                    UserRoleLink, UserRoleLink.user_id == User.id
                ).join(Role, Role.id == UserRoleLink.role_id)
                .where(Role.slug == role_value)
            )
    
    if is_active is not None:
        statement = statement.where(User.is_active == is_active)
    
    # Get total count
    count_statement = select(func.count()).select_from(statement.subquery())
    result = session.execute(count_statement)
    total = result.scalar() or 0
    
    # Get paginated results
    statement = statement.order_by(User.created_at.desc()).offset(skip).limit(limit)
    result = session.execute(statement)
    users = result.scalars().all()
    
    return users, total


def get_user_stats(session: Session) -> dict:
    """
    Get user statistics.
    
    Returns:
        dict: User statistics (total, active, inactive, by role, by auth provider)
    """
    total_users = session.execute(select(func.count()).select_from(User)).scalar() or 0
    
    active_users = session.execute(
        select(func.count()).select_from(User).where(User.is_active == True)
    ).scalar() or 0
    
    inactive_users = total_users - active_users
    
    admin_users = session.execute(
        select(func.count()).select_from(User).where(User.role == UserRole.admin)
    ).scalar() or 0
    
    staff_users = session.execute(
        select(func.count()).select_from(User).where(User.role == UserRole.staff)
    ).scalar() or 0
    
    manager_users = session.execute(
        select(func.count()).select_from(User).where(User.role == UserRole.manager)
    ).scalar() or 0
    
    customer_users = session.execute(
        select(func.count()).select_from(User).where(User.role == UserRole.customer)
    ).scalar() or 0
    
    google_users = session.execute(
        select(func.count()).select_from(User).where(User.auth_provider == "google")
    ).scalar() or 0
    
    email_users = session.execute(
        select(func.count()).select_from(User).where(User.auth_provider == "email")
    ).scalar() or 0
    
    # Users with both auth methods
    both_users = session.execute(
        select(func.count()).select_from(User).where(User.auth_provider == "both")
    ).scalar() or 0
    
    return {
        "total_users": total_users,
        "active_users": active_users,
        "inactive_users": inactive_users,
        "admin_users": admin_users,
        "staff_users": staff_users,
        "manager_users": manager_users,
        "customer_users": customer_users,
        "google_users": google_users,
        "email_users": email_users,
        "both_users": both_users,
    }


def update_user_by_admin(
    session: Session,
    user: User,
    update_data: dict,
    *, commit: bool = True,
) -> User:
    """
    Update user by admin.
    
    Args:
        session: Database session
        user: User object to update
        update_data: Dictionary of fields to update
    
    Returns:
        User: Updated user
    """
    for key, value in update_data.items():
        if value is not None:
            setattr(user, key, value)
    
    session.add(user)
    if commit:
        session.commit()
        session.refresh(user)
    else:
        session.flush()
    return user


def delete_user(session: Session, user: User, *, commit: bool = True) -> None:
    """
    Hard delete user (use with caution).
    
    Args:
        session: Database session
        user: User object to delete
    """
    session.delete(user)
    session.commit() if commit else session.flush()


def update_user_profile(session: Session, user: User, update_data: dict) -> User:
    """
    Update user profile (for non-admin users).
    
    Args:
        session: Database session
        user: User object to update
        update_data: Dictionary of fields to update
    
    Returns:
        User: Updated user
    """
    allowed_fields = ["full_name", "phone", "username"]
    
    for key, value in update_data.items():
        if key in allowed_fields and value is not None:
            setattr(user, key, value)
    
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def set_user_password(session: Session, user: User, password_hash: str) -> User:
    """
    Set user password (for Google users setting password).
    
    Args:
        session: Database session
        user: User object
        password_hash: Hashed password
    
    Returns:
        User: Updated user
    """
    user.password_hash = password_hash
    session.add(user)
    session.commit()
    session.refresh(user)
    return user
