from uuid import UUID,uuid4
from datetime import datetime
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, DateTime,func

class PasswordResetToken(SQLModel,table=True):
    __tablename__="password_reset_tokens"

    id:UUID=Field(default_factory=uuid4,primary_key=True)
    token:str=Field(unique=True,index=True)
    user_id:UUID=Field(foreign_key="users.id",index=True)
    expires_at:datetime=Field(sa_column=Column(DateTime(timezone=True)))
    used:bool=Field(default=False)
    created_at:datetime=Field(sa_column=Column(DateTime(timezone=True),server_default=func.now()))


    