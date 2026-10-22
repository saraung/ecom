from typing import Literal

from pydantic import BaseModel, EmailStr


class GoogleAuthRequest(BaseModel):
    id_token: str  # Google ID token from frontend
    # Same channel split as the password login — see app.schemas.user.UserLogin.
    audience: Literal["admin", "storefront"] = "admin"


class GoogleUserInfo(BaseModel):
    id: str
    email: EmailStr
    name: str
    given_name: str | None = None
    family_name: str | None = None
    picture: str | None = None
    verified_email: bool = False