#!/usr/bin/env python3
"""
Test script to demonstrate user session expiry functionality
"""

from datetime import datetime, timezone, timedelta

def test_session_expiry():
    """Test the session expiry calculation"""
    
    # Simulate signup on June 7th, 2024
    signup_date = datetime(2024, 6, 7, 10, 58, 21, tzinfo=timezone.utc)
    print(f"📅 Signup Date: {signup_date.strftime('%B %d, %Y at %H:%M:%S UTC')}")
    
    # Calculate 3 months from signup
    user_session_expiry = signup_date + timedelta(days=90)
    print(f"⏰ User Session Expiry (3 months): {user_session_expiry.strftime('%B %d, %Y at %H:%M:%S UTC')}")
    print(f"📝 ISO Format: {user_session_expiry.isoformat()}")
    
    # Compare with Google token expiry (1 hour)
    google_token_expiry = signup_date + timedelta(hours=1)
    print(f"\n🔍 Google Token Expiry (1 hour): {google_token_expiry.strftime('%B %d, %Y at %H:%M:%S UTC')}")
    print(f"📝 ISO Format: {google_token_expiry.isoformat()}")
    
    # Show the difference
    print(f"\n✅ **Key Differences:**")
    print(f"   • Google Token: Expires in 1 hour (managed by Google)")
    print(f"   • User Session: Expires in 3 months (managed by our app)")
    print(f"   • Your request: User session from June 7 → September 5 ✓")
    
    # Show current status if we were to check today
    current_time = datetime.now(timezone.utc)
    days_until_session_expiry = (user_session_expiry - current_time).days
    
    print(f"\n📊 **Current Status:**")
    print(f"   • Current Time: {current_time.strftime('%B %d, %Y')}")
    print(f"   • Days until session expiry: {days_until_session_expiry}")
    print(f"   • Session Active: {'Yes ✅' if days_until_session_expiry > 0 else 'No ❌'}")

if __name__ == "__main__":
    test_session_expiry() 