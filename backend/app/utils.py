import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional
from functools import wraps
import traceback
from datetime import datetime

logger = logging.getLogger(__name__)

class RetryConfig:
    """Configuration for retry mechanisms"""
    def __init__(self, max_attempts: int = 3, delay: float = 1.0, backoff_factor: float = 2.0):
        self.max_attempts = max_attempts
        self.delay = delay
        self.backoff_factor = backoff_factor

async def retry_async(
    func: Callable,
    config: RetryConfig = None,
    exceptions: tuple = (Exception,),
    context: str = "operation"
) -> Any:
    """
    Retry an async function with exponential backoff.
    """
    if config is None:
        config = RetryConfig()
    
    last_exception = None
    
    for attempt in range(config.max_attempts):
        try:
            logger.debug(f"🔄 Attempt {attempt + 1}/{config.max_attempts} for {context}")
            result = await func()
            if attempt > 0:
                logger.info(f"✅ {context} succeeded on attempt {attempt + 1}")
            return result
            
        except exceptions as e:
            last_exception = e
            logger.warning(f"⚠️ {context} failed on attempt {attempt + 1}: {str(e)}")
            
            if attempt < config.max_attempts - 1:
                delay = config.delay * (config.backoff_factor ** attempt)
                logger.info(f"⏰ Retrying {context} in {delay:.2f} seconds...")
                await asyncio.sleep(delay)
            else:
                logger.error(f"❌ {context} failed after {config.max_attempts} attempts")
    
    raise last_exception

def safe_execute(func: Callable, error_msg: str = "Operation failed", **kwargs) -> tuple:
    """
    Safely execute a function and return (success, result, error)
    """
    try:
        result = func(**kwargs)
        return True, result, None
    except Exception as e:
        logger.error(f"{error_msg}: {str(e)}", exc_info=True)
        return False, None, str(e)

async def safe_execute_async(func: Callable, error_msg: str = "Async operation failed", **kwargs) -> tuple:
    """
    Safely execute an async function and return (success, result, error)
    """
    try:
        result = await func(**kwargs)
        return True, result, None
    except Exception as e:
        logger.error(f"{error_msg}: {str(e)}", exc_info=True)
        return False, None, str(e)

class EmailProcessingTracker:
    """Track email processing statistics and errors"""
    
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.start_time = datetime.now()
        self.total_emails = 0
        self.successful = 0
        self.failed = 0
        self.errors: List[Dict] = []
        self.current_step = "Initializing"
        
    def set_total(self, total: int):
        self.total_emails = total
        logger.info(f"📊 Processing tracker initialized for user {self.user_id}: {total} emails to process")
    
    def set_step(self, step: str):
        self.current_step = step
        logger.info(f"⏳ {self.user_id}: {step}")
    
    def mark_success(self, email_id: str = None):
        self.successful += 1
        if email_id:
            logger.debug(f"✅ {self.user_id}: Email {email_id} processed successfully ({self.successful}/{self.total_emails})")
    
    def mark_failure(self, email_id: str, error: str, step: str = None):
        self.failed += 1
        error_entry = {
            "email_id": email_id,
            "error": error,
            "step": step or self.current_step,
            "timestamp": datetime.now().isoformat()
        }
        self.errors.append(error_entry)
        logger.error(f"❌ {self.user_id}: Email {email_id} failed in {step or self.current_step}: {error}")
    
    def get_progress(self) -> Dict:
        processed = self.successful + self.failed
        progress_pct = (processed / self.total_emails * 100) if self.total_emails > 0 else 0
        duration = (datetime.now() - self.start_time).total_seconds()
        
        return {
            "user_id": self.user_id,
            "total_emails": self.total_emails,
            "processed": processed,
            "successful": self.successful,
            "failed": self.failed,
            "progress_percentage": progress_pct,
            "duration_seconds": duration,
            "current_step": self.current_step,
            "errors": self.errors[-5:] if self.errors else []  # Last 5 errors
        }
    
    def log_summary(self):
        duration = (datetime.now() - self.start_time).total_seconds()
        success_rate = (self.successful / self.total_emails * 100) if self.total_emails > 0 else 0
        
        logger.info(f"📊 Processing Summary for {self.user_id}:")
        logger.info(f"   📧 Total emails: {self.total_emails}")
        logger.info(f"   ✅ Successful: {self.successful}")
        logger.info(f"   ❌ Failed: {self.failed}")
        logger.info(f"   📈 Success rate: {success_rate:.1f}%")
        logger.info(f"   ⏱️ Duration: {duration:.2f}s")
        
        if self.errors:
            logger.warning(f"   🚨 Error breakdown:")
            error_counts = {}
            for error in self.errors:
                step = error.get('step', 'unknown')
                error_counts[step] = error_counts.get(step, 0) + 1
            
            for step, count in error_counts.items():
                logger.warning(f"     - {step}: {count} errors")

def sanitize_email_content(content: str, max_length: int = 10000) -> str:
    """
    Sanitize email content to prevent issues with storage/processing.
    """
    if not content:
        return ""
    
    try:
        # Remove null bytes and other problematic characters
        content = content.replace('\x00', '')
        
        # Limit length to prevent memory issues
        if len(content) > max_length:
            logger.warning(f"⚠️ Content truncated from {len(content)} to {max_length} characters")
            content = content[:max_length] + "... [TRUNCATED]"
        
        # Ensure it's valid UTF-8
        content = content.encode('utf-8', errors='ignore').decode('utf-8')
        
        return content
        
    except Exception as e:
        logger.error(f"❌ Error sanitizing content: {str(e)}")
        return f"[CONTENT_SANITIZATION_ERROR: {str(e)}]"

def validate_email_data(email_data: Dict) -> tuple:
    """
    Validate email data structure and content.
    Returns (is_valid, validation_errors)
    """
    errors = []
    
    # Check required fields
    required_fields = ['id', 'subject', 'snippet', 'body']
    for field in required_fields:
        if field not in email_data:
            errors.append(f"Missing required field: {field}")
        elif email_data[field] is None:
            errors.append(f"Field {field} is None")
    
    # Validate email ID
    if 'id' in email_data:
        if not isinstance(email_data['id'], str) or len(email_data['id']) == 0:
            errors.append("Email ID must be a non-empty string")
    
    # Check for extremely large content that might cause issues
    for field in ['subject', 'snippet', 'body']:
        if field in email_data and isinstance(email_data[field], str):
            if len(email_data[field]) > 50000:  # 50KB limit
                errors.append(f"Field {field} is too large ({len(email_data[field])} chars)")
    
    return len(errors) == 0, errors

def log_environment_info():
    """Log important environment information for debugging"""
    import os
    import sys
    
    logger.info("🌍 Environment Information:")
    logger.info(f"   🐍 Python version: {sys.version}")
    logger.info(f"   📁 Working directory: {os.getcwd()}")
    logger.info(f"   🔑 OPENAI_API_KEY configured: {'OPENAI_API_KEY' in os.environ}")
    logger.info(f"   🧠 MEM0_API_KEY configured: {'MEM0_API_KEY' in os.environ}")
    logger.info(f"   📊 GOOGLE_CLIENT_ID configured: {'GOOGLE_CLIENT_ID' in os.environ}")

def format_error_for_user(error: Exception, context: str = "operation") -> str:
    """
    Format an error message in a user-friendly way while preserving technical details in logs.
    """
    error_msg = str(error)
    
    # Map common errors to user-friendly messages
    if "401" in error_msg or "unauthorized" in error_msg.lower():
        user_msg = "Authentication failed. Please check your Google account permissions."
    elif "403" in error_msg or "forbidden" in error_msg.lower():
        user_msg = "Access denied. Please ensure you have granted necessary permissions."
    elif "404" in error_msg or "not found" in error_msg.lower():
        user_msg = "Some emails could not be found (they may have been deleted)."
    elif "429" in error_msg or "rate limit" in error_msg.lower():
        user_msg = "Too many requests. Please try again later."
    elif "quota" in error_msg.lower():
        user_msg = "API quota exceeded. Please try again later."
    elif "network" in error_msg.lower() or "connection" in error_msg.lower():
        user_msg = "Network connection issue. Please check your internet connection."
    else:
        user_msg = f"An error occurred during {context}. Please try again."
    
    # Log the technical details
    logger.error(f"❌ Technical error in {context}: {error_msg}", exc_info=True)
    
    return user_msg 