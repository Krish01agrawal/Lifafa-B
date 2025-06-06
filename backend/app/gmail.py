from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
import base64
import re
from typing import List
import html
import os
from datetime import datetime, timedelta
from fastapi.concurrency import run_in_threadpool

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def build_gmail_service(access_token: str):
    creds = Credentials(token=access_token)
    service = build('gmail', 'v1', credentials=creds)
    return service

async def fetch_emails(service, user_id='me', max_results=4500):
    # Calculate the date 15 days ago for the query
    # Note: Gmail API's 'newer_than:15d' is simpler and often preferred.
    # query_string = 'newer_than:15d'

    # Using newer_than:15d for simplicity with Gmail API
    query_filter = 'newer_than:120d'
    
    all_messages = []
    page_token = None
    
    while True:
        # Wrap the blocking .execute() call in run_in_threadpool
        results = await run_in_threadpool(
            service.users().messages().list(
                userId=user_id, 
                maxResults=500,  # Request 500 per page (API maximum)
                q=query_filter,
                pageToken=page_token
            ).execute
        )
        
        messages_on_page = results.get('messages', [])
        all_messages.extend(messages_on_page)
        
        page_token = results.get('nextPageToken')
        
        # Stop if no more pages or if we have enough messages
        if not page_token or len(all_messages) >= max_results:
            break
            
    # If we fetched more than max_results due to page size, trim the list
    if len(all_messages) > max_results:
        all_messages = all_messages[:max_results]

    if not all_messages:
        print(f"No emails found matching criteria: {query_filter}")
        return []
    
    emails = []
    # Process only the messages up to max_results
    for msg_summary in all_messages: # Iterate through the potentially trimmed list
        # Wrap the blocking .execute() call in run_in_threadpool
        message = await run_in_threadpool(
            service.users().messages().get(userId=user_id, id=msg_summary['id'], format='full').execute
        )
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
                body_data = payload['body'].get('data')
                if body_data:
                    body = base64.urlsafe_b64decode(body_data).decode('utf-8')
                else:
                    body = ""
            else:
                body = ""

        emails.append({
            "id": msg_summary['id'],
            "subject": subject,
            "snippet": snippet,
            "body": body,
        })
        # Stop fetching details if we've reached max_results
        if len(emails) >= max_results:
            break
    return emails

def clean_html(raw_html):
    # Basic clean-up to remove HTML tags, decode entities
    text = re.sub('<[^<]+?>', '', raw_html)
    text = html.unescape(text)
    return text.strip()
