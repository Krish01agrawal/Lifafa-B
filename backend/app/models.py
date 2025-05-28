from pydantic import BaseModel

class GoogleToken(BaseModel):
    token: str

class ChatQuery(BaseModel):
    message: str
    jwt_token: str

class ChatResponse(BaseModel):
    reply: str

class GmailFetchPayload(BaseModel):
    jwt_token: str
    access_token: str
