import os
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, status, Depends, BackgroundTasks, Request
from sqlmodel import Session,select
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select as sa_select, update

from app.api.deps import SessionDep, CurrentUser, CurrentUser
from app.core.rate_limit import limiter
from app.schemas.google_auth import GoogleAuthRequest
from app.schemas.user import UserCreate, UserRead, UserLogin, SetPasswordRequest, UserUpdateProfile
from app.schemas.token import TokenPair, RefreshRequest
from app.schemas.otp import OTPInitiateRequest,OTPVerifyRequest
from app.repositories import user as user_repo
from app.repositories import token as token_repo
from app.repositories import rbac as rbac_repo
from app.core.security import verify_password, create_access_token, hash_password, generate_reset_token
from app.core.security import (
    AUDIENCE_ADMIN,
    AUDIENCE_STOREFRONT,
    create_login_challenge,
    verify_login_challenge,
)
from app.services import otp_service
from app.services.email_service import email_service
from app.services.email_outbox import enqueue_email, deliver_pending_emails
from app.services.google_auth_service import google_auth_service
from app.services.otp_service import create_otp,verify_otp,increment_otp_attempts,get_otp_attempts
from app.core.config import settings
from app.models.user import User
from app.models.otp import OTP
from app.models.password_reset import PasswordResetToken
from app.models.email_outbox import EmailOutbox

router = APIRouter(prefix="/auth", tags=["auth"])


def _issue_access_token(
    session: SessionDep, user: User, audience: str = AUDIENCE_ADMIN, session_id: str | None = None,
) -> str:
    """Access token carrying legacy role + dynamic permission set."""
    role_value = getattr(user.role, "value", user.role) or "customer"
    try:
        permissions = rbac_repo.get_user_permissions(session, user.id)
    except Exception:
        # RBAC tables may not exist yet on old databases — degrade to
        # a role-only token instead of failing login.
        permissions = []
    return create_access_token(
        subject=user.email, role=role_value, permissions=permissions,
        audience=audience,
        session_id=session_id, token_version=user.token_version,
    )


def _issue_tokens(session: Session, user: User, audience: str = AUDIENCE_ADMIN) -> TokenPair:
    try:
        raw = token_repo.issue_refresh_token(session, user.id, scope=audience, commit=False)
        record = token_repo.get_valid_token(session, raw)
        access = _issue_access_token(session, user, audience, str(record.session_id))
        session.commit()
        return TokenPair(access_token=access, refresh_token=raw)
    except Exception:
        session.rollback()
        raise


def _require_otp_sent(sent: bool) -> None:
    """Fail honestly when the email provider rejects the OTP.

    A silently-unsent code strands the user on a screen whose codes can
    never arrive — worse than an explicit error they can act on.
    """
    if not sent:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Could not send the verification email — the email service "
                "is unavailable. Please try again in a few minutes."
            ),
        )


def _mask_email(email: str) -> str:
    """a***@example.com — enough to reassure, useless to an attacker."""
    try:
        local, domain = email.split("@", 1)
    except ValueError:
        return "***"
    if len(local) <= 1:
        masked = "*"
    else:
        masked = local[0] + "***"
    return f"{masked}@{domain}"


def _privileged_or_tokens(
    session: SessionDep, user: User, audience: str = AUDIENCE_ADMIN
) -> TokenPair | dict:
    """Step-up gate for privileged accounts (any non-customer permission).

    - Shoppers (no permissions): session tokens immediately.
    - Staff/managers/admins: password is verified by the caller, then an OTP
      challenge is issued — tokens are only minted at /login/verify-otp.

    The gate applies to the ADMIN audience only. Staff shopping in the
    storefront are issued a storefront-scoped token instead: they keep full
    customer rights, and ``require_perm`` refuses that token on admin routes.
    That matches the product rule that staff orders are allowed but flagged
    (Order.placed_by_staff) rather than banned.
    """
    if audience != AUDIENCE_ADMIN:
        return _issue_tokens(session, user, audience)

    try:
        permissions = rbac_repo.get_user_permissions(session, user.id)
    except Exception:
        permissions = []
    if not permissions:
        return _issue_tokens(session, user, audience)

    _, sent = otp_service.create_otp(session, user.email, "admin_login")
    _require_otp_sent(sent)
    return {
        "otp_required": True,
        "challenge_token": create_login_challenge(user.email),
        "expires_in_minutes": 5,
        "email_masked": _mask_email(user.email),
    }


def _assign_default_role(session: SessionDep, user: User) -> None:
    """Link a freshly registered user to the customer system role.

    Best-effort: registration must never fail because of RBAC — the legacy
    ``User.role`` default already covers authorization fallback.
    """
    try:
        if rbac_repo.get_user_roles(session, user.id):
            return
        customer = rbac_repo.get_role_by_slug(session, "customer")
        if customer is not None:
            rbac_repo.set_user_roles(session, user, [customer])
    except Exception as e:
        print(f"⚠️ Could not assign default role to {user.email}: {e}")


def _user_read_with_security(
    session: SessionDep, user: User
) -> dict:
    """UserRead payload enriched with dynamic roles/permissions."""
    data = UserRead.model_validate(user).model_dump()
    try:
        data.update(rbac_repo.user_security_profile(session, user))
    except Exception:
        legacy = getattr(user.role, "value", user.role) or "customer"
        data.update({"roles": [str(legacy)], "permissions": []})
    return data


# ========== Request Schemas ==========

class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class VerifyLoginOtpRequest(BaseModel):
    challenge_token: str
    otp_code: str


class ResendLoginOtpRequest(BaseModel):
    challenge_token: str


# ========== Authentication Endpoints ==========

# @router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
# def register(data: UserCreate, session: SessionDep):
#     if user_repo.get_user_by_email(session, data.email):
#         raise HTTPException(status_code=400, detail="Email already registered")
#     if user_repo.get_user_by_username(session, data.username):
#         raise HTTPException(status_code=400, detail="Username already taken")
    
#     user = user_repo.create_user(session, data)
    
#     # Send welcome email
#     if settings.SENDGRID_API_KEY:
#         try:
#             email_service.send_welcome_email(user)
#             print(f"✅ Welcome email sent to {user.email}")
#         except Exception as e:
#             print(f"❌ Failed to send welcome email: {str(e)}")
    
#     return user

@router.post("/register/initiate")
def initiate_registration(
    request: OTPInitiateRequest,
    session: SessionDep,
):
    """
    Step 1: Send OTP to user's email for verification.
    """
    # ✅ Check if email already registered
    existing_user = user_repo.get_user_by_email(session, request.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # ✅ Check if username is taken before sending OTP
    if request.username:
        existing_username = user_repo.get_user_by_username(session, request.username)
        if existing_username:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already taken"
            )
    
    # ✅ Check rate limiting (max 3 attempts per hour)
    from datetime import datetime, timedelta
    statement = select(OTP).where(
        OTP.email == request.email,
        OTP.created_at > datetime.now() - timedelta(hours=1)
    )
    recent_otps = session.exec(statement).all()
    if len(recent_otps) >= 3:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many OTP requests. Please wait 1 hour."
        )
    
    # ✅ Generate and send OTP
    _, sent = create_otp(session, request.email, "signup")
    _require_otp_sent(sent)

    return {
        "message": "OTP sent to your email",
        "email": request.email,
        "expires_in": "10 minutes"
    }


@router.post("/register/verify")
def verify_registration(
    request: OTPVerifyRequest,
    session: SessionDep,
):
    """
    Step 2: Verify OTP and create user account.
    """
    # ✅ Check if email already registered (double-check)
    existing_user = user_repo.get_user_by_email(session, request.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # ✅ Check if username is taken
    existing_username = user_repo.get_user_by_username(session, request.username)
    if existing_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken"
        )
    
    # ✅ Verify OTP
    is_valid = verify_otp(session, request.email, request.otp_code, "signup")
    if not is_valid:
        # ✅ Increment failed attempts
        increment_otp_attempts(session, request.email)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OTP"
        )
    
    # ✅ OTP verified - Create user
    user_data = UserCreate(
        email=request.email,
        username=request.username,
        password=request.password,
        full_name=request.full_name,
        phone=request.phone,
    )
    
    user = user_repo.create_user(session, user_data, commit=False)
    enqueue_email(session, f"user:{user.id}:welcome", "send_welcome_email", user)
    session.commit()
    _assign_default_role(session, user)
    
    return {
        "message": "Account created successfully",
        "user": {
            "id": str(user.id),
            "email": user.email,
            "username": user.username,
            "full_name": user.full_name,
        }
    }


@router.post("/register/resend-otp")
def resend_otp(
    request: OTPInitiateRequest,
    session: SessionDep,
):
    """
    Resend OTP for registration.
    """
    # ✅ Check if email already registered
    existing_user = user_repo.get_user_by_email(session, request.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # ✅ Generate and send new OTP
    _, sent = create_otp(session, request.email, "signup")
    _require_otp_sent(sent)

    return {
        "message": "OTP resent to your email",
        "email": request.email,
        "expires_in": "10 minutes"
    }


    
@router.post("/login")
@limiter.limit("10/minute")
def login(request: Request, data: UserLogin, session: SessionDep):
    user = user_repo.get_user_by_email(session, data.email)
    
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    
    # Check if user is Google-only (no password set)
    if user.auth_provider == "google" and not user.password_hash:
        raise HTTPException(
            status_code=400, 
            detail="This account was created with Google. Please sign in with Google."
        )
    
    # Verify password
    if not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    # Privileged accounts stop here until the OTP challenge is completed;
    # shoppers receive tokens immediately. The step-up applies to the admin
    # audience only — a storefront login is never challenged (see
    # _privileged_or_tokens).
    return _privileged_or_tokens(session, user, data.audience)


@router.post("/login/verify-otp", response_model=TokenPair)
@limiter.limit("10/minute")
def verify_login_otp(
    request: Request, data: VerifyLoginOtpRequest, session: SessionDep
):
    """Exchange a login challenge + email OTP for session tokens.

    The challenge token proves the password step; the OTP proves inbox
    control. Wrong codes count against the attempt budget — burned codes
    must be re-requested via /login/resend-otp.
    """
    email = verify_login_challenge(data.challenge_token)
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Challenge expired. Please sign in again.",
        )
    user = user_repo.get_user_by_email(session, email)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Challenge expired. Please sign in again.",
        )

    if not otp_service.verify_otp(session, email, data.otp_code, "admin_login"):
        otp_service.increment_otp_attempts(session, email)
        remaining = otp_service.remaining_otp_attempts(
            session, email, "admin_login"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Invalid or expired code. "
                f"{remaining} attempt(s) remaining."
                if remaining
                else "Code locked after too many attempts. Request a new code."
            ),
        )

    return _issue_tokens(session, user, AUDIENCE_ADMIN)


@router.post("/login/resend-otp")
@limiter.limit("3/minute")
def resend_login_otp(request: Request, data: ResendLoginOtpRequest, session: SessionDep):
    """Re-send the admin-login OTP for a live challenge (60s cooldown)."""
    email = verify_login_challenge(data.challenge_token)
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Challenge expired. Please sign in again.",
        )
    user = user_repo.get_user_by_email(session, email)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Challenge expired. Please sign in again.",
        )

    wait = otp_service.resend_cooldown_remaining(session, email, "admin_login")
    if wait:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Please wait {wait} second(s) before requesting a new code.",
        )

    _, sent = otp_service.create_otp(session, email, "admin_login")
    _require_otp_sent(sent)
    return {
        "message": "A new code was sent",
        "email_masked": _mask_email(email),
        "expires_in": "10 minutes",
    }


@router.post("/refresh", response_model=TokenPair)
def refresh(data: RefreshRequest, session: SessionDep):
    record = token_repo.get_valid_token(session, data.refresh_token)
    if not record:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    user = session.execute(sa_select(User).where(User.id == record.user_id).with_for_update()
                           .execution_options(populate_existing=True)).scalars().first()
    if user is None or not user.is_active:
        raise HTTPException(401, "Invalid or expired refresh token")
    # Re-issue with the scope the session was ORIGINALLY created under. Reading
    # it from the stored record is what stops a storefront session from
    # upgrading itself to an admin-capable token on refresh.
    scope = record.scope or AUDIENCE_ADMIN
    try:
        new_refresh = token_repo.rotate_token(session, record, commit=False)
        access = _issue_access_token(session, user, scope, str(record.session_id))
        session.commit()
        return TokenPair(access_token=access, refresh_token=new_refresh)
    except Exception:
        session.rollback()
        raise


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(data: RefreshRequest, session: SessionDep):
    record = token_repo.get_token(session, data.refresh_token)
    if not record:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    token_repo.revoke_session(session, record)
    session.commit()


@router.get("/me", response_model=UserRead)
def me(session: SessionDep, current_user: CurrentUser):
    return _user_read_with_security(session, current_user)


@router.put("/profile", response_model=UserRead)
def update_profile(
    profile_data: UserUpdateProfile,
    session: SessionDep,
    current_user: CurrentUser,
):
    """
    Update user profile (full_name, phone, username).
    """
    # Username uniqueness check
    if profile_data.username:
        if profile_data.username != current_user.username:
            existing = user_repo.get_user_by_username(session, profile_data.username)
            if existing and existing.id != current_user.id:
                raise HTTPException(
                    status_code=400,
                    detail="Username already taken"
                )
            current_user.username = profile_data.username
    
    # Update other fields
    if profile_data.full_name is not None:
        current_user.full_name = profile_data.full_name
    
    if profile_data.phone is not None:
        current_user.phone = profile_data.phone
    
    if profile_data.push_notifications_enabled is not None:
        current_user.push_notifications_enabled = profile_data.push_notifications_enabled
    
    if profile_data.email_notifications_enabled is not None:
        current_user.email_notifications_enabled = profile_data.email_notifications_enabled
    
    session.add(current_user)
    session.commit()
    session.refresh(current_user)
    
    return _user_read_with_security(session, current_user)


@router.post("/google")
@limiter.limit("10/minute")
def google_auth(
    request: Request,
    request_data: GoogleAuthRequest,
    session: SessionDep,
):
    """
    Authenticate with Google ID token.

    Privileged accounts (any admin permission) must still complete the
    email OTP challenge — a compromised Google account alone is not enough.
    """
    # Verify Google token
    google_user = google_auth_service.verify_id_token(request_data.id_token)
    if not google_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google token or Google Auth not configured"
        )
    
    # Check if user exists by email
    user = user_repo.get_user_by_email(session, google_user.email)
    
    if not user:
        # Create new user (Google only)
        username = google_user.email.split('@')[0]
        # Remove special characters for username
        username = ''.join(c for c in username if c.isalnum())
        
        existing = user_repo.get_user_by_username(session, username)
        if existing:
            username = f"{username}_{uuid.uuid4().hex[:6]}"
        
        user = User(
            email=google_user.email,
            username=username,
            full_name=google_user.name,
            email_verified=google_user.verified_email,
            auth_provider="google",
            google_id=google_user.id,
            is_active=True,
            password_hash=None,
        )
        session.add(user)
        enqueue_email(session, f"user:{user.id}:welcome", "send_welcome_email", user)
        session.commit()
        session.refresh(user)
        _assign_default_role(session, user)
        
    
    else:
        # User exists - link Google account if not already
        if not user.google_id:
            user.google_id = google_user.id
            user.auth_provider = "both" if user.password_hash else "google"
            session.add(user)
            session.commit()
            session.refresh(user)
            print(f"✅ Linked Google account to existing user: {user.email}")
        
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account disabled"
            )
    
    # Privileged accounts stop here until the OTP challenge is completed;
    # shoppers receive tokens immediately. Channel split as in /login.
    return _privileged_or_tokens(session, user, request_data.audience)


@router.post("/set-password", response_model=dict)
def set_password(
    data: SetPasswordRequest,
    session: SessionDep,
    current_user: CurrentUser,
):
    """
    Set password for Google users (so they can also login with email/password).
    """
    # Only Google-only users can set password
    if current_user.auth_provider == "email":
        raise HTTPException(
            status_code=400,
            detail="You already have a password. Use 'change-password' instead."
        )
    
    if current_user.password_hash:
        raise HTTPException(
            status_code=400,
            detail="You already have a password set."
        )
    
    current_user.password_hash = hash_password(data.password)
    current_user.auth_provider = "both"
    session.add(current_user)
    session.commit()
    
    return {"message": "Password set successfully. You can now login with email/password."}


# ========== Password Reset Endpoints ==========

@router.post("/forgot-password", status_code=status.HTTP_200_OK)
def forgot_password(
    request: ForgotPasswordRequest,
    session: SessionDep,
    background_tasks: BackgroundTasks, 
):
    """
    Request password reset link.
    If email exists, send reset link. Always return 200 OK for security.
    """
    # Find user by email
    user = user_repo.get_user_by_email(session, request.email)
    
    # Always return 200 OK (security: don't reveal if email exists)
    if not user:
        print(f"⚠️ Password reset requested for non-existent email: {request.email}")
        return {"message": "If an account with this email exists, a reset link has been sent."}
    
    # Check if user has a password (Google-only users can't reset password)
    if not user.password_hash:
        print(f"⚠️ Password reset requested for Google-only user: {user.email}")
        return {"message": "If an account with this email exists, a reset link has been sent."}
    
    # Delete any existing reset tokens for this user
    session.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id
    ).delete()

    # Supersede any reset mail that is still queued. Its token was just
    # invalidated above, so sending it later would only deliver a dead link.
    session.query(EmailOutbox).filter(
        EmailOutbox.to_email == user.email,
        EmailOutbox.event_key.like("password-reset:%"),
        EmailOutbox.sent_at.is_(None),
    ).delete(synchronize_session=False)
    
    # Generate reset token (valid for 1 hour)
    token = generate_reset_token()
    expires_at = datetime.utcnow() + timedelta(hours=settings.RESET_TOKEN_EXPIRE_HOURS)
    
    # Store token in database
    reset_token = PasswordResetToken(
        token=token_repo._hash(token),
        user_id=user.id,
        expires_at=expires_at,
        used=False,
    )
    session.add(reset_token)
    outbox = enqueue_email(session, f"password-reset:{reset_token.id}", "send_password_reset_email",
                  user_email=user.email, user_name=user.full_name or user.username,
                  reset_token=token, expires_at=expires_at)
    session.commit()

    # On serverless hosts the in-process scheduler is not guaranteed to run, so
    # try the send in-request as well. The row stays in the outbox if the
    # provider fails. Local development keeps the normal 30s scheduler path
    # (and tests never touch the network).
    if os.getenv("VERCEL") or settings.ENVIRONMENT.lower() == "production":
        deliver_pending_emails(session, limit=1, event_key=outbox.event_key)
    
    print(f"✅ Password reset token generated for {user.email}")
    return {"message": "If an account with this email exists, a reset link has been sent."}


@router.post("/reset-password", status_code=status.HTTP_200_OK)
def reset_password(
    request: ResetPasswordRequest,
    session: SessionDep,
):
    """
    Reset password using token.
    """
    # Get token from database
    reset_token = session.query(PasswordResetToken).filter(
        PasswordResetToken.token == token_repo._hash(request.token),
        PasswordResetToken.used == False,
        PasswordResetToken.expires_at > datetime.utcnow(),
    ).first()
    
    if not reset_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )
    claimed = session.execute(update(PasswordResetToken).where(
        PasswordResetToken.id == reset_token.id, PasswordResetToken.used.is_(False),
    ).values(used=True).execution_options(synchronize_session=False))
    if claimed.rowcount != 1:
        session.rollback()
        raise HTTPException(400, "Invalid or expired reset token")
    
    # Get user
    user = session.get(User, reset_token.user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    # Update password
    user.password_hash = hash_password(request.new_password)
    user.auth_provider = "both" if user.google_id else "email"
    
    # Mark token as used
    reset_token.used = True
    
    session.add(user)
    session.add(reset_token)
    token_repo.invalidate_user_sessions(session, user)
    session.commit()
    
    print(f"✅ Password reset successful for {user.email}")
    return {"message": "Password reset successfully. You can now login with your new password."}


@router.post("/change-password", status_code=status.HTTP_200_OK)
def change_password(
    request: ChangePasswordRequest,
    session: SessionDep,
    current_user: CurrentUser,
):
    """
    Change password for logged-in user.
    Requires current password for verification.
    """
    # Check if user has a password (Google-only users can't change password via this endpoint)
    if not current_user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You don't have a password set. Use 'set-password' endpoint.",
        )
    
    # Verify current password
    if not verify_password(request.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )
    
    # Update password
    current_user.password_hash = hash_password(request.new_password)
    session.add(current_user)
    token_repo.invalidate_user_sessions(session, current_user)
    session.commit()
    
    print(f"✅ Password changed successfully for {current_user.email}")
    return {"message": "Password changed successfully."}
