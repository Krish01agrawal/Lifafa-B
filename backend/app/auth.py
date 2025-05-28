from fastapi import HTTPException
from google.oauth2 import id_token
from google.auth.transport import requests
from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone
import os

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
JWT_SECRET = os.getenv("JWT_SECRET", "supersecretjwtkey")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

def verify_google_token(token: str):
    try:
        idinfo = id_token.verify_oauth2_token(token, requests.Request(), GOOGLE_CLIENT_ID)
        if idinfo['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
            raise HTTPException(status_code=400, detail="Wrong issuer.")
        return {
            "user_id": idinfo['sub'],
            "email": idinfo['email'],
            "name": idinfo.get('name'),
            "picture": idinfo.get('picture')
        }
    except ValueError as e:
        raise HTTPException(status_code=401, detail=f"Invalid Google token: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error verifying Google token: {e}")

def create_jwt_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return encoded_jwt

def decode_jwt_token(token: str):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid JWT token")
