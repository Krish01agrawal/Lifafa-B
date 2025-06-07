#!/usr/bin/env python3
"""
Test script to verify the enhanced logging and error handling system.
Run this script to see how the logging works before testing with real Gmail data.
"""

import sys
import os
import asyncio
import logging
from datetime import datetime

# Add the backend/app directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend', 'app'))

from logger_config import setup_logging
from utils import (
    EmailProcessingTracker, 
    validate_email_data, 
    sanitize_email_content,
    format_error_for_user,
    log_environment_info
)

async def test_logging_system():
    """Test the comprehensive logging system"""
    
    # Setup logging
    setup_logging()
    logger = logging.getLogger(__name__)
    
    logger.info("🚀 Starting logging system test")
    
    # Test environment logging
    log_environment_info()
    
    # Test different log levels
    logger.debug("🔍 This is a debug message")
    logger.info("ℹ️ This is an info message")
    logger.warning("⚠️ This is a warning message")
    logger.error("❌ This is an error message")
    
    # Test email processing tracker
    tracker = EmailProcessingTracker("test_user_123")
    tracker.set_total(5)
    
    # Simulate processing some emails
    test_emails = [
        {"id": "email1", "subject": "Test Subject 1", "snippet": "Test snippet", "body": "Test body"},
        {"id": "email2", "subject": "Test Subject 2", "snippet": "Test snippet", "body": "Test body"},
        {"id": "email3", "subject": "", "snippet": "Test snippet", "body": "Test body"},  # Missing subject
        {"id": "", "subject": "Test Subject 4", "snippet": "Test snippet", "body": "Test body"},  # Missing ID
        {"id": "email5", "subject": "Test Subject 5", "snippet": "Test snippet", "body": "Test body"},
    ]
    
    tracker.set_step("Processing emails")
    
    for i, email in enumerate(test_emails, 1):
        logger.info(f"📧 Processing email {i}/5 - ID: {email.get('id', 'MISSING')}")
        
        # Validate email data
        is_valid, validation_errors = validate_email_data(email)
        
        if is_valid:
            tracker.mark_success(email.get('id'))
            logger.info(f"✅ Email {i} processed successfully")
        else:
            error_msg = f"Validation failed: {', '.join(validation_errors)}"
            tracker.mark_failure(email.get('id', f'email_{i}'), error_msg, "validation")
            logger.error(f"❌ Email {i} failed validation: {error_msg}")
        
        # Small delay to simulate processing time
        await asyncio.sleep(0.1)
    
    # Test content sanitization
    logger.info("🧹 Testing content sanitization")
    
    problematic_content = "Normal text\x00null byte\nLong content " + "x" * 15000
    sanitized = sanitize_email_content(problematic_content, max_length=1000)
    logger.info(f"📝 Sanitized content length: {len(sanitized)}")
    
    # Test error formatting
    logger.info("🔧 Testing error formatting")
    
    test_errors = [
        Exception("401 Unauthorized"),
        Exception("403 Forbidden"),
        Exception("429 Too Many Requests"),
        Exception("Network connection failed"),
        Exception("Some unknown error occurred")
    ]
    
    for error in test_errors:
        user_friendly_msg = format_error_for_user(error, "email processing")
        logger.info(f"🔄 Original: {str(error)} -> User-friendly: {user_friendly_msg}")
    
    # Log final summary
    tracker.log_summary()
    
    logger.info("✅ Logging system test completed successfully")
    logger.info("📝 Check 'gmail_upload.log' for detailed logs")
    logger.info("🚨 Check 'gmail_upload_errors.log' for error logs")

if __name__ == "__main__":
    print("🧪 Testing Gmail Upload Logging System")
    print("=" * 50)
    
    try:
        asyncio.run(test_logging_system())
        print("\n✅ Test completed successfully!")
        print("📁 Log files created:")
        print("   - gmail_upload.log (detailed logs)")
        print("   - gmail_upload_errors.log (error logs)")
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc() 