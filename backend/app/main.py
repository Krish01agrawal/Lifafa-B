import os
from dotenv import load_dotenv

# Try to load environment variables from multiple possible locations
possible_env_paths = [
    os.path.join(os.path.dirname(__file__), '..', '..', '.env'),  # Root directory
    os.path.join(os.path.dirname(__file__), '..', '.env'),       # Backend directory
    os.path.join(os.path.dirname(__file__), '.env'),             # App directory
]

env_loaded = False
for env_path in possible_env_paths:
    if os.path.exists(env_path):
        env_loaded = load_dotenv(env_path)
        print(f"Environment file loaded from {env_path}: {env_loaded}")
        break
    else:
        print(f"Environment file not found at: {env_path}")

if not env_loaded:
    print("No .env file found, using system environment variables")

print(f"FRONTEND_URL from env: {os.getenv('FRONTEND_URL')}")
print(f"GOOGLE_CLIENT_ID from env: {os.getenv('GOOGLE_CLIENT_ID')}")

# Set default environment variables if not present
if not os.getenv("FRONTEND_URL"):
    os.environ["FRONTEND_URL"] = "http://localhost:8000"
    print("Set default FRONTEND_URL: http://localhost:8000")

# Now proceed with other imports
from fastapi import FastAPI, Depends, HTTPException, status, Request, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from app.auth import verify_google_token, create_jwt_token, decode_jwt_token, refresh_google_access_token, is_google_token_expired, is_user_session_expired
from app.oauth import generate_auth_url, exchange_code_for_tokens
from app.db import users_collection, emails_collection
from app.gmail import build_gmail_service, build_gmail_service_simple, fetch_emails
from app.mem0_agent import upload_emails_to_mem0, query_mem0
from app.models import GoogleToken, GmailFetchPayload
from app.websocket import router as websocket_router
import logging
from datetime import datetime, timedelta, timezone
from bson import ObjectId
from pydantic import BaseModel
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi.concurrency import run_in_threadpool

# Configure comprehensive logging
from app.logger_config import setup_logging
from app.utils import log_environment_info
setup_logging()
logger = logging.getLogger(__name__)

# Log environment info on module load
log_environment_info()

app = FastAPI()

# Define the security scheme
security = HTTPBearer()

# Allow CORS from frontend origin (adjust as needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",  # Added for local dev
        "http://localhost:8001",  # Added for local dev (if backend is on this port)
        "http://127.0.0.1:8000", # Added for local dev
        "http://127.0.0.1:8001", # Added for local dev (if backend is on this port)
        "https://localhost:8000", 
        "https://localhost:8001", 
        "https://127.0.0.1:8000", 
        "https://127.0.0.1:8001",
        "https://ec2-13-127-58-101.ap-south-1.compute.amazonaws.com", 
        "https://ec2-13-127-58-101.ap-south-1.compute.amazonaws.com/api"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept", "Origin", "Referrer-Policy"],
    expose_headers=["*"]
)

app.include_router(websocket_router)

# Initialize APScheduler
scheduler = AsyncIOScheduler()

# Define a Pydantic model for the test query request body
class TestMem0QueryPayload(BaseModel):
    user_id: str
    query: str


@app.post("/auth/google-login")
async def google_login(payload: GoogleToken):
    logger.info(f"Received request for /auth/google-login with token: {payload.token[:30]}...")
    try:
        logger.info("Verifying Google token...")
        raw_user_info_from_google = verify_google_token(payload.token)
        logger.info(f"Google token verified. Raw User info from Google: {raw_user_info_from_google}")

        user_id_from_google = raw_user_info_from_google["user_id"]
        logger.info(f"Checking user in database: {user_id_from_google}")
        
        # Fetch user from DB to get the version with _id (if it exists)
        user_in_db = await users_collection.find_one({"user_id": user_id_from_google})
        
        final_user_info_to_return = {}

        if not user_in_db:
            logger.info("User not found, creating new user with Google info...")
            # Use the info directly from Google for the first insert
            # MongoDB will add an _id field automatically
            user_to_insert = raw_user_info_from_google.copy() # Use a copy
            user_to_insert['initial_gmailData_sync'] = False # Initialize initial_gmailData_sync
            user_to_insert['fetched_email'] = False  # Initialize fetched_email
            insert_result = await users_collection.insert_one(user_to_insert)
            logger.info(f"New user created. Inserted ID: {insert_result.inserted_id}")
            # Fetch the newly created user to get all fields including the auto-generated _id
            final_user_info_to_return = await users_collection.find_one({"_id": insert_result.inserted_id})
            if not final_user_info_to_return:
                 logger.error("CRITICAL: User just inserted but not found by _id!")
                 final_user_info_to_return = raw_user_info_from_google # Fallback, but _id will be missing
        else:
            logger.info("User found in database.")
            final_user_info_to_return = user_in_db

        # Ensure _id (and any other ObjectId) is converted to string before returning
        serializable_user_info = convert_objectid_to_str(final_user_info_to_return)
        logger.info(f"Serializable user info for response: {serializable_user_info}")

        logger.info("Creating JWT token...")
        # Create JWT based on consistent user_id and email
        jwt_payload_data = {"user_id": serializable_user_info["user_id"], "email": serializable_user_info["email"]}
        jwt_token = create_jwt_token(jwt_payload_data)
        logger.info("JWT token created successfully.")
        
        {
            "jwt_token": jwt_token,
            "user": {
                "email": serializable_user_info["email"],
                "name": serializable_user_info["name"],
                "picture": serializable_user_info["picture"],
                "user_id": serializable_user_info["user_id"],
            },
        }
        return {"jwt_token": jwt_token, "user": serializable_user_info}
    except HTTPException as e:
        logger.error(f"HTTPException in google_login: {e.detail}", exc_info=True)
        raise 
    except Exception as e:
        logger.error(f"Unexpected error in google_login: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"An unexpected error occurred: {str(e)}"
        )

@app.post("/gmail/fetch")
async def gmail_fetch(payload: GmailFetchPayload):
    # Authenticate user with JWT
    logger.info("Received request for /gmail/fetch")
    try:
        logger.info("Decoding JWT token...")
        user = decode_jwt_token(payload.jwt_token)
        user_id = user.get("user_id")
        logger.info(f"JWT decoded. User ID: {user_id}")

        # Call the core processing function
        result = await _trigger_and_process_user_emails(user_id=user_id, access_token=payload.access_token, max_results=4500)

        if result["status"] == "error":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result["message"]
            )

        return {"message": result["message"], "count": result["count"]}
    except HTTPException as e:
        logger.error(f"HTTPException in gmail_fetch: {e.detail}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Unexpected error in gmail_fetch: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"An unexpected error occurred during gmail fetch: {str(e)}"
        )

@app.post("/test/mem0-query")
async def test_mem0_query_endpoint(payload: TestMem0QueryPayload):
    logger.info(f"Received request for /test/mem0-query for user_id: {payload.user_id} with query: {payload.query}")
    try:
        # Note: This endpoint does not perform JWT authentication for simplicity in direct testing.
        # In a production scenario, you would likely want to protect this.
        results = await query_mem0(user_id=payload.user_id, query=payload.query)
        return results
    except Exception as e:
        logger.error(f"Error in /test/mem0-query endpoint: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(e)}"
        )

# Add new OAuth routes after the existing CORS setup
@app.get("/auth/login")
async def login():
    """Redirect user to Google OAuth consent screen."""
    try:
        auth_url, state = generate_auth_url()
        logger.info(f"Redirecting user to Google OAuth with state: {state}")
        return RedirectResponse(url=auth_url)
    except Exception as e:
        logger.error(f"Error in /auth/login: {e}")
        raise HTTPException(status_code=500, detail=f"Authentication error: {e}")

@app.get("/auth/callback")
async def oauth_callback(code: str = None, state: str = None, error: str = None):
    """Handle OAuth callback from Google."""
    # Try multiple ways to get frontend URL
    frontend_url = (
        os.getenv("FRONTEND_URL") or 
        os.getenv("FRONTEND_BASE_URL") or 
        "http://localhost:8000"  # Default fallback
    )
    
    logger.info(f"OAuth callback - FRONTEND_URL: {frontend_url}")
    logger.info(f"OAuth callback - All env vars: FRONTEND_URL={os.getenv('FRONTEND_URL')}")
    
    if error:
        logger.error(f"OAuth error: {error}")
        return RedirectResponse(url=f"{frontend_url}?error={error}")
    
    if not code or not state:
        logger.error("Missing code or state in OAuth callback")
        return RedirectResponse(url=f"{frontend_url}?error=missing_parameters")
    
    try:
        # Exchange code for tokens and user info
        credentials, user_info = exchange_code_for_tokens(code, state)
        logger.info(f"OAuth successful for user: {user_info['email']}")
        
        # Store or update user in database
        user_id_from_google = user_info["user_id"]
        user_in_db = await users_collection.find_one({"user_id": user_id_from_google})
        
        if not user_in_db:
            logger.info("Creating new user from OAuth...")
            # Store user info with OAuth tokens
            user_data = user_info.copy()
            # Calculate user session expiry (3 months from signup)
            signup_date = datetime.now(timezone.utc)
            user_session_expiry = signup_date + timedelta(days=90)  # 3 months
            
            user_data.update({
                "access_token": credentials.token,
                "refresh_token": credentials.refresh_token,
                "token_expiry": credentials.expiry.isoformat() if credentials.expiry else None,  # Google token (1 hour)
                "user_session_expiry": user_session_expiry.isoformat(),  # User session (3 months)
                "signup_date": signup_date.isoformat(),
                "initial_gmailData_sync": False,  # Initialize initial_gmailData_sync
                "fetched_email": False  # Initialize fetched_email
            })
            insert_result = await users_collection.insert_one(user_data)
            final_user_info = await users_collection.find_one({"_id": insert_result.inserted_id})
        else:
            logger.info("Updating existing user with new OAuth tokens...")
            # Update existing user with new tokens
            update_data = {
                "access_token": credentials.token,
                "refresh_token": credentials.refresh_token,
                "token_expiry": credentials.expiry.isoformat() if credentials.expiry else None,  # Google token (1 hour)
                "name": user_info.get("name"),
                "picture": user_info.get("picture")
            }
            
            # If user doesn't have user_session_expiry, add it (for existing users)
            if not user_in_db.get("user_session_expiry"):
                signup_date = datetime.now(timezone.utc)
                user_session_expiry = signup_date + timedelta(days=90)  # 3 months
                update_data.update({
                    "user_session_expiry": user_session_expiry.isoformat(),
                    "signup_date": signup_date.isoformat()
                })
            await users_collection.update_one(
                {"user_id": user_id_from_google},
                {"$set": update_data}
            )
            final_user_info = await users_collection.find_one({"user_id": user_id_from_google})
        
        # Create JWT token
        jwt_payload = {"user_id": user_info["user_id"], "email": user_info["email"]}
        jwt_token = create_jwt_token(jwt_payload)
        
        logger.info(f"OAuth completed successfully for user: {user_info['email']}")
        
        # Redirect to frontend with JWT token (no auto-email fetching)
        return RedirectResponse(url=f"{frontend_url}?token={jwt_token}&user={user_info['email']}")
        
    except Exception as e:
        logger.error(f"Error in OAuth callback: {e}")
        return RedirectResponse(url=f"{frontend_url}?error=auth_failed")

@app.post("/emails/fetch")
async def fetch_user_emails(authorization: str = Header(None)):
    """
    Fetch emails for authenticated user.
    Expects Authorization header with Bearer token.
    """
    try:
        # Validate authorization header
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
        
        token = authorization.split(" ")[1]
        user = decode_jwt_token(token)
        user_id = user.get("user_id")
        user_email = user.get("email")
        
        logger.info(f"Fetching emails for user: {user_email} via /emails/fetch")
        
        # Call the core processing function (it will handle token management automatically)
        result = await _trigger_and_process_user_emails(user_id=user_id, max_results=4500) # Default max_results

        if result["status"] == "error":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result["message"]
            )
        
        return {
            "success": True,
            "message": result["message"],
            "email_count": result["count"],
            "user_email": user_email
        }
        
    except HTTPException as e:
        logger.error(f"HTTPException in fetch_user_emails: {e.detail}")
        raise
    except Exception as e:
        logger.error(f"Error in fetch_user_emails: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch emails: {str(e)}"
        )

# Alternative endpoint with JWT in body (easier for frontend)
class EmailFetchRequest(BaseModel):
    jwt_token: str
    max_results: int = 4500

@app.post("/emails/fetch-with-token")
async def fetch_user_emails_with_token(payload: EmailFetchRequest):
    """
    Fetch emails for authenticated user.
    Expects JWT token in request body.
    """
    try:
        # Decode JWT token
        user = decode_jwt_token(payload.jwt_token)
        user_id = user.get("user_id")
        user_email = user.get("email")
        
        logger.info(f"Fetching emails for user: {user_email} via /emails/fetch-with-token")
        
        # Call the core processing function (it will handle token management automatically)
        result = await _trigger_and_process_user_emails(user_id=user_id, max_results=payload.max_results)

        if result["status"] == "error":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result["message"]
            )
        
        return {
            "success": True,
            "message": result["message"],
            "email_count": result["count"],
            "user_email": user_email
        }
        
    except HTTPException as e:
        logger.error(f"HTTPException in fetch_user_emails_with_token: {e.detail}")
        raise
    except Exception as e:
        logger.error(f"Error in fetch_user_emails_with_token: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch emails: {str(e)}"
        )

@app.get("/me")
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Fetch details for the currently authenticated user.
    Uses HTTPBearer token for authentication.
    """
    logger.info("Received request for /me")
    try:
        token = credentials.credentials
        logger.info("Decoding JWT token for /me...")
        user_payload = decode_jwt_token(token)
        user_id = user_payload.get("user_id")
        
        if not user_id:
            logger.error("User ID not found in JWT payload for /me")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User ID not found in token"
            )
        
        logger.info(f"Fetching user data for user_id: {user_id}")
        user_in_db = await users_collection.find_one({"user_id": user_id})
        
        if not user_in_db:
            logger.warning(f"User not found in database with user_id: {user_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Ensure initial_gmailData_sync is accurate
        has_email_data = await emails_collection.count_documents({"user_id": user_id}) > 0
        current_sync_status_in_db = user_in_db.get("initial_gmailData_sync")

        if current_sync_status_in_db is None or current_sync_status_in_db != has_email_data:
            logger.info(f"Updating initial_gmailData_sync for user {user_id} from {current_sync_status_in_db} to {has_email_data}")
            await users_collection.update_one(
                {"user_id": user_id},
                {"$set": {"initial_gmailData_sync": has_email_data}}
            )
            user_in_db["initial_gmailData_sync"] = has_email_data # Reflect change in current dict
        
        # fetched_email field will be returned as is from the database.
        # It's updated when a fetch process is initiated.

        # Convert ObjectId to string before returning
        serializable_user_info = convert_objectid_to_str(user_in_db)
        logger.info(f"Successfully fetched user data for /me: {serializable_user_info.get('email')}")
        # Add session status information
        if user_session_expiry := serializable_user_info.get("user_session_expiry"):
            try:
                expiry_time = datetime.fromisoformat(user_session_expiry.replace('Z', '+00:00'))
                current_time = datetime.now(timezone.utc)
                days_remaining = (expiry_time - current_time).days
                serializable_user_info["session_days_remaining"] = max(0, days_remaining)
                serializable_user_info["session_expired"] = is_user_session_expired(user_session_expiry)
            except Exception:
                serializable_user_info["session_days_remaining"] = 0
                serializable_user_info["session_expired"] = True
        
        return serializable_user_info
        
    except HTTPException as e:
        # Log specific HTTP exceptions and re-raise
        logger.error(f"HTTPException in /me endpoint: {e.detail}", exc_info=e.status_code not in [401, 404]) # Don't need full stack for 401/404
        raise
    except Exception as e:
        logger.error(f"Unexpected error in /me endpoint: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(e)}"
        )

def convert_objectid_to_str(data):
    """Recursively converts ObjectId instances in a dictionary or list to strings."""
    if isinstance(data, list):
        return [convert_objectid_to_str(item) for item in data]
    elif isinstance(data, dict):
        return {key: convert_objectid_to_str(value) for key, value in data.items()}
    elif isinstance(data, ObjectId):
        return str(data)
    return data

async def get_valid_access_token(user_id: str):
    """
    Get a valid access token for the user, refreshing it if necessary.
    Returns (access_token, refresh_token, updated_user_data)
    """
    logger.info(f"🔑 Getting valid access token for user_id: {user_id}")
    
    # Get user data from database
    user_in_db = await users_collection.find_one({"user_id": user_id})
    if not user_in_db:
        raise HTTPException(status_code=404, detail="User not found")
    
    access_token = user_in_db.get("access_token")
    refresh_token = user_in_db.get("refresh_token")
    token_expiry = user_in_db.get("token_expiry")
    user_session_expiry = user_in_db.get("user_session_expiry")
    
    if not access_token:
        raise HTTPException(status_code=400, detail="No access token found for user")
    
    # Check if user session has expired (3 months)
    if is_user_session_expired(user_session_expiry):
        logger.warning(f"🚫 User session expired for user {user_id} (3 months passed)")
        raise HTTPException(status_code=401, detail="User session expired. Please login again.")
    
    # Check if Google access token is expired (1 hour)
    if is_google_token_expired(token_expiry):
        logger.info(f"🔄 Access token expired for user {user_id}, refreshing...")
        
        if not refresh_token:
            raise HTTPException(status_code=400, detail="No refresh token available, user needs to re-authenticate")
        
        try:
            # Refresh the token
            new_tokens = refresh_google_access_token(refresh_token)
            
            # Update user in database with new tokens
            update_data = {
                "access_token": new_tokens["access_token"],
                "token_expiry": new_tokens["token_expiry"]
            }
            
            # Update refresh token if a new one was provided
            if new_tokens.get("refresh_token") and new_tokens["refresh_token"] != refresh_token:
                update_data["refresh_token"] = new_tokens["refresh_token"]
            
            await users_collection.update_one(
                {"user_id": user_id},
                {"$set": update_data}
            )
            
            logger.info(f"✅ Access token refreshed and updated for user {user_id}")
            
            # Update our local variables
            access_token = new_tokens["access_token"]
            refresh_token = new_tokens.get("refresh_token", refresh_token)
            
            # Get updated user data
            user_in_db = await users_collection.find_one({"user_id": user_id})
            
        except Exception as e:
            logger.error(f"❌ Failed to refresh access token for user {user_id}: {str(e)}")
            raise HTTPException(status_code=401, detail=f"Failed to refresh access token: {str(e)}")
    else:
        logger.info(f"✅ Access token is still valid for user {user_id}")
    
    return access_token, refresh_token, user_in_db

# Core email processing function - Updated with automatic token refresh
async def _trigger_and_process_user_emails(user_id: str, access_token: str = None, max_results: int = 4500):
    logger.info(f"🚀 Starting comprehensive email processing for user_id: {user_id} (max_results: {max_results})")
    
    processing_start_time = datetime.now()
    
    try:
        # Step 1: Mark that email fetch process has been initiated for this user
        logger.info(f"📝 Step 1/7: Marking fetched_email as true for user_id: {user_id}")
        try:
            await users_collection.update_one(
                {"user_id": user_id},
                {"$set": {"fetched_email": True}}
            )
            logger.info(f"✅ Step 1/7: fetched_email marked as true for user_id: {user_id}")
        except Exception as db_error:
            logger.error(f"❌ Step 1/7: Failed to update fetched_email for user_id {user_id}: {str(db_error)}", exc_info=True)
            raise Exception(f"Database update failed: {str(db_error)}")

        # Step 2: Get valid access token (with automatic refresh if needed)
        logger.info(f"🔑 Step 2/7: Getting valid access token for user_id: {user_id}")
        try:
            if access_token:
                # If access_token provided, use it directly (for backward compatibility)
                logger.info(f"✅ Step 2/7: Using provided access token for user_id: {user_id}")
                valid_access_token = access_token
                refresh_token = None
            else:
                # Get from database and refresh if needed
                valid_access_token, refresh_token, updated_user_data = await get_valid_access_token(user_id)
                logger.info(f"✅ Step 2/7: Valid access token obtained for user_id: {user_id}")
        except Exception as token_error:
            logger.error(f"❌ Step 2/7: Failed to get valid access token for user_id {user_id}: {str(token_error)}", exc_info=True)
            raise Exception(f"Token validation failed: {str(token_error)}")

        # Step 3: Build Gmail service and fetch emails
        logger.info(f"🔧 Step 3/7: Building Gmail service for user_id: {user_id}")
        try:
            service = await run_in_threadpool(build_gmail_service_simple, valid_access_token)
            logger.info(f"✅ Step 3/7: Gmail service built successfully for user_id: {user_id}")
        except Exception as service_error:
            logger.error(f"❌ Step 3/7: Failed to build Gmail service for user_id {user_id}: {str(service_error)}", exc_info=True)
            raise Exception(f"Gmail service initialization failed: {str(service_error)}")
        
        # Step 4: Fetch emails from Gmail
        logger.info(f"📧 Step 4/7: Fetching emails from Gmail for user_id: {user_id} (max: {max_results})...")
        fetch_start_time = datetime.now()
        try:
            emails = await fetch_emails(service, user_id=user_id, max_results=max_results)
            fetch_duration = (datetime.now() - fetch_start_time).total_seconds()
            logger.info(f"✅ Step 4/7: Fetched {len(emails)} emails from Gmail for user_id: {user_id} (took {fetch_duration:.2f}s)")
        except Exception as fetch_error:
            logger.error(f"❌ Step 4/7: Failed to fetch emails for user_id {user_id}: {str(fetch_error)}", exc_info=True)
            raise Exception(f"Email fetch failed: {str(fetch_error)}")
        
        if emails:
            # Step 5: Store emails in MongoDB
            logger.info(f"💾 Step 5/7: Storing {len(emails)} emails in MongoDB for user_id: {user_id}...")
            storage_start_time = datetime.now()
            
            try:
                # Add user_id to each email
                for email_item in emails:
                    email_item['user_id'] = user_id
                
                # Remove existing emails for this user to avoid duplicates before new insertion
                logger.info(f"🗑️ Step 5/7: Removing existing emails for user_id: {user_id}")
                delete_result = await emails_collection.delete_many({"user_id": user_id})
                logger.info(f"🗑️ Step 5/7: Deleted {delete_result.deleted_count} existing emails for user_id: {user_id}")
                
                # Insert new emails
                logger.info(f"📥 Step 5/7: Inserting {len(emails)} new emails for user_id: {user_id}")
                insert_result = await emails_collection.insert_many(emails)
                storage_duration = (datetime.now() - storage_start_time).total_seconds()
                logger.info(f"✅ Step 5/7: {len(insert_result.inserted_ids)} emails stored in MongoDB for user_id: {user_id} (took {storage_duration:.2f}s)")
                
            except Exception as storage_error:
                logger.error(f"❌ Step 5/7: Failed to store emails in MongoDB for user_id {user_id}: {str(storage_error)}", exc_info=True)
                raise Exception(f"Email storage failed: {str(storage_error)}")
            
            # Step 6: Upload to Mem0
            logger.info(f"🧠 Step 6/7: Uploading {len(emails)} emails to Mem0 for user_id: {user_id}...")
            mem0_start_time = datetime.now()
            
            try:
                await upload_emails_to_mem0(user_id, emails)
                mem0_duration = (datetime.now() - mem0_start_time).total_seconds()
                logger.info(f"✅ Step 6/7: Emails uploaded to Mem0 for user_id: {user_id} (took {mem0_duration:.2f}s)")
            except Exception as mem0_error:
                logger.error(f"❌ Step 6/7: Failed to upload emails to Mem0 for user_id {user_id}: {str(mem0_error)}", exc_info=True)
                # Note: We don't raise here to allow the process to continue and mark as synced
                logger.warning(f"⚠️ Step 6/7: Continuing despite Mem0 upload failure for user_id: {user_id}")

            # Step 7: Update initial_gmailData_sync for the user as process completed  
            logger.info(f"🏁 Step 7/7: Updating initial_gmailData_sync to true for user_id: {user_id}")
            try:
                await users_collection.update_one(
                    {"user_id": user_id},
                    {"$set": {"initial_gmailData_sync": True}}
                )
                
                total_duration = (datetime.now() - processing_start_time).total_seconds()
                logger.info(f"✅ Step 7/7: initial_gmailData_sync updated for user_id: {user_id}")
                logger.info(f"🎉 Email processing completed successfully for user_id: {user_id} (total time: {total_duration:.2f}s)")
                
                return {
                    "status": "success", 
                    "message": f"Successfully fetched and processed {len(emails)} emails for user {user_id}", 
                    "count": len(emails),
                    "processing_time_seconds": total_duration
                }
                
            except Exception as final_update_error:
                logger.error(f"❌ Step 7/7: Failed to update initial_gmailData_sync for user_id {user_id}: {str(final_update_error)}", exc_info=True)
                # Even if this fails, we still processed the emails successfully
                total_duration = (datetime.now() - processing_start_time).total_seconds()
                logger.warning(f"⚠️ Email processing completed but final status update failed for user_id: {user_id}")
                
                return {
                    "status": "success", 
                    "message": f"Successfully fetched and processed {len(emails)} emails for user {user_id} (final status update failed)", 
                    "count": len(emails),
                    "processing_time_seconds": total_duration
                }
        else:
            # If no emails were fetched, still mark initial_gmailData_sync as true because the fetch process completed.
            # This prevents re-fetching if the user genuinely has no emails or if max_results was 0.
            logger.info(f"📭 No emails found for user_id: {user_id}. Marking initial_gmailData_sync as true.")
            
            try:
                await users_collection.update_one(
                    {"user_id": user_id},
                    {"$set": {"initial_gmailData_sync": True}} # Mark as synced even if no emails
                )
                
                total_duration = (datetime.now() - processing_start_time).total_seconds()
                logger.info(f"✅ initial_gmailData_sync updated (no emails found) for user_id: {user_id} (total time: {total_duration:.2f}s)")
                
                return {
                    "status": "success", 
                    "message": f"Email fetch process completed. No emails found for user {user_id}", 
                    "count": 0,
                    "processing_time_seconds": total_duration
                }
                
            except Exception as no_emails_update_error:
                logger.error(f"❌ Failed to update initial_gmailData_sync (no emails case) for user_id {user_id}: {str(no_emails_update_error)}", exc_info=True)
                total_duration = (datetime.now() - processing_start_time).total_seconds()
                
                return {
                    "status": "success", 
                    "message": f"Email fetch process completed. No emails found for user {user_id} (status update failed)", 
                    "count": 0,
                    "processing_time_seconds": total_duration
                }

    except Exception as e:
        total_duration = (datetime.now() - processing_start_time).total_seconds()
        logger.error(f"💥 Critical error during email processing for user_id {user_id} (after {total_duration:.2f}s): {str(e)}", exc_info=True)
        
        # Reset fetched_email to false so the user can retry
        try:
            await users_collection.update_one(
                {"user_id": user_id},
                {"$set": {"fetched_email": False}}
            )
            logger.info(f"🔄 Reset fetched_email to false for user_id: {user_id} due to processing failure")
        except Exception as reset_error:
            logger.error(f"❌ Failed to reset fetched_email for user_id {user_id}: {str(reset_error)}", exc_info=True)
        
        return {
            "status": "error", 
            "message": f"Failed to process emails for user {user_id}: {str(e)}",
            "processing_time_seconds": total_duration
        }

async def check_and_fetch_new_user_emails():
    logger.info("Background worker: Checking for users with fetched_email=false")
    try:
        users_to_fetch = users_collection.find({"fetched_email": False})
        async for user in users_to_fetch:
            user_id = user.get("user_id")
            access_token = user.get("access_token") # Assuming access_token is stored and valid
            
            if not user_id or not access_token:
                logger.warning(f"Background worker: Skipping user {user.get('_id')} due to missing user_id or access_token.")
                continue

            # Check token validity if possible (e.g., expiry if stored)
            # For simplicity, we assume the token is valid or will be handled by build_gmail_service
            
            logger.info(f"Background worker: Found user {user_id} with fetched_email=false. Triggering email processing.")
            # Using a default max_results for background tasks, adjust as needed
            await _trigger_and_process_user_emails(user_id=user_id, access_token=access_token, max_results=4500) 
            # Add a small delay or use a more sophisticated queue if you have many users to avoid bursting API limits
            # await asyncio.sleep(1) # Example delay

        logger.info("Background worker: Finished checking for users.")
    except Exception as e:
        logger.error(f"Background worker: Error during check_and_fetch_new_user_emails: {str(e)}", exc_info=True)

@app.on_event("startup")
async def startup_event():
    # Schedule the job to run every 2 minutes
    scheduler.add_job(check_and_fetch_new_user_emails, "interval", minutes=2, id="fetch_new_emails_job")
    scheduler.start()
    logger.info("APScheduler started. Job 'fetch_new_emails_job' scheduled every 2 minutes.")

@app.on_event("shutdown")
async def shutdown_event():
    scheduler.shutdown()
    logger.info("APScheduler shut down.")
