from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import Session

from app.core.security import (
    AUDIENCE_ADMIN,
    decode_access_token,
)
from app.db.database import get_session
from app.models.user import User, UserRole
from app.repositories.user import get_user_by_email


oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/login"
)


SessionDep = Annotated[
    Session,
    Depends(get_session),
]


def get_current_user(
    session: SessionDep,
    token: Annotated[str, Depends(oauth2_scheme)],
) -> User:

    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={
            "WWW-Authenticate": "Bearer"
        },
    )

    payload = decode_access_token(token)

    if payload is None:
        raise credentials_error

    email = payload.get("sub")

    if not email:
        raise credentials_error

    user = get_user_by_email(
        session,
        email,
    )

    from app.repositories.token import session_is_valid
    if user is None or not user.is_active or not session_is_valid(session, user, payload):
        raise credentials_error

    return user


CurrentUser = Annotated[
    User,
    Depends(get_current_user),
]


# Returned by require_perm/require_role so they can read the caller's token
# audience. Decoding is cheap and happens once per request.
TokenPayload = Annotated[
    dict,
    Depends(lambda token=Depends(oauth2_scheme): decode_access_token(token) or {}),
]


def _assert_admin_audience(payload: dict) -> None:
    """Reject storefront-scoped sessions on privileged endpoints.

    Tokens issued before the ``aud`` claim existed have no audience at all;
    treat those as admin so existing sessions (all created via the OTP-gated
    login) keep working.
    """
    audience = payload.get("aud")
    if audience is not None and audience != AUDIENCE_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This session is not authorized for the admin panel",
        )


def get_user_role_slugs(session: Session, user: User) -> set[str]:
    """Role slugs from the dynamic ``user_roles`` table, falling back to the
    legacy ``User.role`` enum for users not yet backfilled."""
    # Local import to avoid a hard api->repositories->models cycle at import
    # time (repositories.user only imports models/schemas).
    from app.repositories import rbac as rbac_repo

    slugs = set(rbac_repo.get_user_role_slugs(session, user.id))
    if not slugs and user.role is not None:
        legacy = getattr(user.role, "value", user.role)
        slugs.add(str(legacy))
    return slugs


def require_role(*allowed: UserRole):

    def checker(
        session: SessionDep,
        user: CurrentUser,
        payload: TokenPayload,
    ) -> User:

        _assert_admin_audience(payload)

        allowed_slugs = {
            getattr(r, "value", r) if not isinstance(r, str) else r
            for r in allowed
        }
        if not (get_user_role_slugs(session, user) & allowed_slugs):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )

        return user

    return checker


def require_perm(*permissions: str, require_all: bool = True):
    """Dynamic permission guard (replaces ``require_role`` for new code).

    Checks the union of the caller's role grants in the DB — custom roles
    created from the dashboard work automatically.

    Also enforces the token audience: a storefront-scoped session is refused
    before permissions are even consulted, so shopping in the shop never grants
    admin reach.
    """

    def checker(
        session: SessionDep,
        user: CurrentUser,
        payload: TokenPayload,
    ) -> User:

        _assert_admin_audience(payload)

        # Local import (see get_user_role_slugs).
        from app.repositories import rbac as rbac_repo

        granted = set(rbac_repo.get_user_permissions(session, user.id))
        wanted = set(permissions)
        ok = wanted <= granted if require_all else bool(wanted & granted)
        if not ok:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )

        return user

    return checker
