from pydantic import BaseModel


class LoginRequest(BaseModel):
    # plain str (not EmailStr): login just looks the value up, and we must not
    # reject internal/already-stored accounts at the auth boundary.
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str
