from fastapi import HTTPException
from google.oauth2 import id_token
from google.auth.transport import requests
from google.oauth2.credentials import Credentials
from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone
import os
import logging

logger = logging.getLogger(__name__)

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
JWT_SECRET = os.getenv("JWT_SECRET", "supersecretjwtkey")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = 60 * 24 * 90  # 90 days (3 months)

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

def refresh_google_access_token(refresh_token: str, client_id: str = None, client_secret: str = None):
    """
    Refresh Google OAuth access token using refresh token.
    Returns new credentials object with fresh access token.
    """
    try:
        client_id = client_id or os.getenv("GOOGLE_CLIENT_ID")
        client_secret = client_secret or os.getenv("GOOGLE_CLIENT_SECRET")
        
        if not client_id or not client_secret:
            raise ValueError("Google client ID and secret are required for token refresh")
        
        logger.info(f"Refreshing Google access token...")
        
        # Create credentials object with refresh token
        credentials = Credentials(
            token=None,  # Will be refreshed
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret
        )
        
        # Refresh the credentials
        credentials.refresh(requests.Request())
        
        logger.info(f"✅ Google access token refreshed successfully")
        
        return {
            "access_token": credentials.token,
            "refresh_token": credentials.refresh_token,  # May be the same or new
            "token_expiry": credentials.expiry.isoformat() if credentials.expiry else None
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to refresh Google access token: {str(e)}")
        raise HTTPException(status_code=401, detail=f"Failed to refresh access token: {str(e)}")

def is_google_token_expired(token_expiry_str: str) -> bool:
    """
    Check if Google OAuth token is expired or will expire in the next 5 minutes.
    """
    if not token_expiry_str:
        return True
    
    try:
        expiry_time = datetime.fromisoformat(token_expiry_str.replace('Z', '+00:00'))
        # Consider token expired if it expires in the next 5 minutes
        buffer_time = datetime.now(timezone.utc) + timedelta(minutes=5)
        return expiry_time <= buffer_time
    except Exception as e:
        logger.warning(f"⚠️ Error parsing token expiry '{token_expiry_str}': {str(e)}")
        return True  # Assume expired if we can't parse

def is_user_session_expired(user_session_expiry_str: str) -> bool:
    """
    Check if user session is expired (3 months from signup).
    """
    if not user_session_expiry_str:
        return True
    
    try:
        expiry_time = datetime.fromisoformat(user_session_expiry_str.replace('Z', '+00:00'))
        current_time = datetime.now(timezone.utc)
        return current_time >= expiry_time
    except Exception as e:
        logger.warning(f"⚠️ Error parsing user session expiry '{user_session_expiry_str}': {str(e)}")
        return True  # Assume expired if we can't parse
