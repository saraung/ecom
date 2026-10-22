from datetime import datetime
from sqlmodel import SQLModel, Field
from uuid import UUID, uuid4

class OTP(SQLModel, table=True):
    __tablename__ = "otps"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    email: str = Field(index=True, max_length=255)
    # SHA-256 hex digest of the 6-digit code (never the code itself).
    otp_code: str = Field(max_length=128)
    purpose: str = Field(max_length=50)  # "signup", "reset_password", "change_email"
    expires_at: datetime
    is_used: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.now)
    attempts: int = Field(default=0)  # Track failed attempts