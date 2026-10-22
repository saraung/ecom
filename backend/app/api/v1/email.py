from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr

from app.api.deps import SessionDep, get_current_user, require_perm
from app.models.user import User
from app.services.email_service import email_service


router = APIRouter(prefix="/email", tags=["Email"])


class TestEmailRequest(BaseModel):
    email: EmailStr


@router.post("/test", response_model=dict)
def send_test_email(
    request: TestEmailRequest,
    current_user: User = Depends(
        require_perm("promotions.send")
    ),
):
    """Send a test email (admin only)"""
    success = email_service.send_test_email(request.email)
    
    if not success:
        raise HTTPException(400, "Failed to send email")
    
    return {"message": "Test email sent successfully"}