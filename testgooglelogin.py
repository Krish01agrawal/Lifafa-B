from typing import Dict, Any
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
import os
import json
from dotenv import load_dotenv


class GmailHelper:
    def __init__(self, credentials_path: str):
        """Initialize Gmail helper with credentials."""
        self.credentials_path = credentials_path
        self.scopes = [
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.send",
            "https://www.googleapis.com/auth/gmail.modify",
            "https://www.googleapis.com/auth/gmail.compose",
        ]

    def get_auth_url(self, redirect_uri: str, state: str = None) -> str:
        """
        Generate OAuth2 authorization URL for Gmail.

        Args:
            redirect_uri: The URI to redirect to after authorization
            state: Optional state parameter for security

        Returns:
            str: Authorization URL
        """
        try:
            # Load client configuration
            with open(self.credentials_path, "r") as f:
                client_config = json.load(f)

            # Create flow instance
            flow = Flow.from_client_config(
                client_config, scopes=self.scopes, redirect_uri=redirect_uri
            )

            # Generate authorization URL with state parameter
            auth_url, _ = flow.authorization_url(
                access_type="offline",
                include_granted_scopes="true",
                prompt="consent",
                state=state,
            )

            return auth_url

        except Exception as e:
            raise Exception(f"Error generating auth URL: {str(e)}")

    def get_credentials_from_code(self, code: str, redirect_uri: str) -> Credentials:
        """
        Exchange authorization code for credentials.

        Args:
            code: Authorization code from OAuth2 callback
            redirect_uri: The redirect URI used in the authorization request

        Returns:
            Credentials: OAuth2 credentials
        """
        try:
            with open(self.credentials_path, "r") as f:
                client_config = json.load(f)

            flow = Flow.from_client_config(
                client_config, scopes=self.scopes, redirect_uri=redirect_uri
            )

            flow.fetch_token(code=code)
            return flow.credentials

        except Exception as e:
            raise Exception(f"Error exchanging code for credentials: {str(e)}")


if __name__ == "__main__":
    # Load environment variables from .env
    load_dotenv()
    credentials_path = os.getenv("GOOGLE_CLIENT_SECRET_PATH")
    if not credentials_path:
        raise Exception("GOOGLE_CLIENT_SECRET_PATH not set in .env file.")

    # Set your redirect URI (must match Google Cloud Console)
    redirect_uri = "http://localhost:8000/oauth2callback"

    gmail_helper = GmailHelper(credentials_path)
    auth_url = gmail_helper.get_auth_url(redirect_uri)
    print("Go to this URL to log in with Google:", auth_url)

    # After visiting the URL and authorizing, Google will redirect to your redirect_uri with a code parameter
    code = input("Paste the 'code' parameter from the URL after Google redirects you: ")
    creds = gmail_helper.get_credentials_from_code(code, redirect_uri)
    print("Access Token:", creds.token)




