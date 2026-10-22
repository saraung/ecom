import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from sqlmodel import Session, select
from app.models.otp import OTP
from app.services.email_service import email_service

# Maximum wrong-code guesses before the code is burned.
MAX_OTP_ATTEMPTS = 5
OTP_TTL_MINUTES = 10
# Minimum gap between two codes sent to the same email+purpose.
RESEND_COOLDOWN_SECONDS = 60


def generate_otp() -> str:
    # secrets (CSPRNG), not random — these codes guard privileged logins.
    # Range keeps leading zeros: f"{...:06d}".
    return f"{secrets.randbelow(10 ** 6):06d}"


def _hash_code(code: str) -> str:
    """SHA-256 of the code — the DB never holds a usable code."""
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _codes_match(provided: str, stored_hash: str) -> bool:
    return hmac.compare_digest(_hash_code(provided.strip()), stored_hash)


def create_otp(session: Session, email: str, purpose: str) -> tuple[str, bool]:
    """Create + email an OTP. Returns (code, email_sent).

    Callers MUST check ``email_sent`` — the UI must never claim "code sent"
    when the provider rejected it (that strands users on a screen whose
    codes can never arrive).
    """
    statement = select(OTP).where(
        OTP.email == email,
        OTP.purpose == purpose,
        OTP.is_used == False
    )
    old_otps = session.exec(statement).all()
    for otp in old_otps:
        session.delete(otp)
    session.commit()

    otp_code = generate_otp()
    expires_at = datetime.now() + timedelta(minutes=OTP_TTL_MINUTES)

    new_otp = OTP(
        email=email,
        otp_code=_hash_code(otp_code),
        purpose=purpose,
        expires_at=expires_at
    )
    session.add(new_otp)
    session.commit()
    session.refresh(new_otp)

    sent = send_otp_email(email, otp_code, purpose)

    return otp_code, bool(sent)


def verify_otp(session: Session, email: str, otp_code: str, purpose: str) -> bool:
    """
    Verify OTP.
    Returns: True if valid, False otherwise.

    Invalid codes increment the attempt counter; once MAX_OTP_ATTEMPTS is
    reached the code is burned (marked used) and must be re-requested.
    """
    # ✅ Find the OTP
    statement = select(OTP).where(
        OTP.email == email,
        OTP.purpose == purpose,
        OTP.is_used == False
    )
    otp = session.exec(statement).first()

    # ✅ Check if OTP exists
    if not otp:
        return False

    # ✅ Burn codes that exhausted their guesses.
    if (otp.attempts or 0) >= MAX_OTP_ATTEMPTS:
        otp.is_used = True
        session.add(otp)
        session.commit()
        return False

    # ✅ Check if expired
    if otp.expires_at < datetime.now():
        return False

    if not _codes_match(otp_code or "", otp.otp_code or ""):
        return False

    otp.is_used = True
    session.add(otp)
    session.commit()

    return True


def send_otp_email(email: str, otp_code: str, purpose: str) -> bool:
    """Send OTP via email. Returns True if the provider accepted it."""
    purpose_labels = {
        "signup": "account verification",
        "reset_password": "password reset",
        "change_email": "email change",
        "admin_login": "admin sign-in verification",
    }

    label = purpose_labels.get(purpose, purpose)

    subject = f"Your OTP for {label}"

    html_body = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">
        <h2 style="color: #4F46E5;">Email Verification</h2>
        <p>Hello,</p>
        <p>Your OTP for <strong>{label}</strong> is:</p>

        <div style="background: #f3f4f6; padding: 16px; text-align: center; border-radius: 8px; margin: 20px 0;">
            <span style="font-size: 32px; font-weight: bold; letter-spacing: 8px; color: #1f2937;">
                {otp_code}
            </span>
        </div>

        <p style="color: #6b7280; font-size: 14px;">
            This OTP is valid for <strong>{OTP_TTL_MINUTES} minutes</strong>.
        </p>
        <p style="color: #6b7280; font-size: 14px;">
            If you didn't request this, please ignore this email and consider
            changing your password.
        </p>

        <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 20px 0;">
        <p style="color: #9ca3af; font-size: 12px; text-align: center;">
            This is an automated email. Please do not reply.
        </p>
    </div>
    """

    # ✅ Use your existing email service (return value tells the caller
    # whether the code can actually arrive).
    return email_service.send_email(
        to=email,
        subject=subject,
        html_body=html_body
    )


def get_otp_attempts(session: Session, email: str) -> int:
    """Get failed attempts count for an email"""
    statement = select(OTP).where(
        OTP.email == email,
        OTP.is_used == False
    )
    otp = session.exec(statement).first()
    return otp.attempts if otp else 0


def increment_otp_attempts(session: Session, email: str):
    """Increment failed attempts for OTP"""
    statement = select(OTP).where(
        OTP.email == email,
        OTP.is_used == False
    )
    otp = session.exec(statement).first()
    if otp:
        otp.attempts += 1
        session.add(otp)
        session.commit()


def remaining_otp_attempts(session: Session, email: str, purpose: str) -> int:
    """Guesses left for the live code (0 = burned/expired/missing)."""
    statement = select(OTP).where(
        OTP.email == email,
        OTP.purpose == purpose,
        OTP.is_used == False
    )
    otp = session.exec(statement).first()
    if not otp or otp.expires_at < datetime.now():
        return 0
    return max(0, MAX_OTP_ATTEMPTS - (otp.attempts or 0))


def resend_cooldown_remaining(
    session: Session, email: str, purpose: str
) -> int:
    """Seconds until a new code may be requested (0 = allowed)."""
    statement = select(OTP).where(
        OTP.email == email,
        OTP.purpose == purpose,
    )
    otps = session.exec(statement).all()
    if not otps:
        return 0
    latest = max(o.created_at for o in otps if o.created_at is not None)
    if latest is None:
        return 0
    # created_at may be naive (legacy) — compare in the same domain.
    now = datetime.now(latest.tzinfo) if latest.tzinfo else datetime.now()
    elapsed = (now - latest).total_seconds()
    return max(0, int(RESEND_COOLDOWN_SECONDS - elapsed))
