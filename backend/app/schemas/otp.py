from pydantic import BaseModel,EmailStr

class OTPInitiateRequest(BaseModel):
    email: EmailStr
    username: str | None = None
    password: str | None = None
    full_name: str | None = None
    phone: str | None = None

class OTPVerifyRequest(BaseModel):
    email:EmailStr
    otp_code:str
    username:str
    password:str
    full_name:str |None=None
    phone:str |None=None


