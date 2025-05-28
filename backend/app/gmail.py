from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
import base64
import re
from typing import List
import html
import os

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def build_gmail_service(access_token: str):
    creds = Credentials(token=access_token)
    service = build('gmail', 'v1', credentials=creds)
    return service

async def fetch_emails(service, user_id='me', max_results=100):
    results = service.users().messages().list(userId=user_id, maxResults=max_results).execute()
    messages = results.get('messages', [])
    emails = []
    for msg in messages:
        message = service.users().messages().get(userId=user_id, id=msg['id'], format='full').execute()
        payload = message['payload']
        headers = payload.get('headers', [])
        subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '')
        snippet = message.get('snippet', '')
        body = ""
        if 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                    break
                elif part['mimeType'] == 'text/html':
                    raw_html = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                    body = clean_html(raw_html)
                    break
        else:
            if payload.get('body') and payload['body'].get('data'):
                body = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')

        emails.append({
            "id": msg['id'],
            "subject": subject,
            "snippet": snippet,
            "body": body,
        })
    return emails

def clean_html(raw_html):
    # Basic clean-up to remove HTML tags, decode entities
    text = re.sub('<[^<]+?>', '', raw_html)
    text = html.unescape(text)
    return text.strip()
