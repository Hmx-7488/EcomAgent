from pydantic import BaseModel, Field
class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
class UserRead(BaseModel):
    id: int; username: str; role: str
    model_config = {"from_attributes": True}
class LoginResponse(BaseModel):
    access_token: str; token_type: str = "bearer"; user: UserRead
