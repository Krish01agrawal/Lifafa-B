from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
import base64
import re
from typing import List
import html
import os
import logging
from datetime import datetime, timedelta
from fastapi.concurrency import run_in_threadpool
from googleapiclient.errors import HttpError

# Configure logging for this module
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def build_gmail_service(access_token: str, refresh_token: str = None, user_id: str = None):
    """
    Build Gmail service with proper error handling and logging.
    Automatically refreshes access token if expired.
    """
    logger.info(f"Building Gmail service with access token: {access_token[:20]}...")
    try:
        # Create credentials object
        creds = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token" if refresh_token else None,
            client_id=os.getenv("GOOGLE_CLIENT_ID") if refresh_token else None,
            client_secret=os.getenv("GOOGLE_CLIENT_SECRET") if refresh_token else None
        )
        
        # Build the service
        service = build('gmail', 'v1', credentials=creds)
        logger.info("Gmail service built successfully")
        return service, creds
        
    except Exception as e:
        logger.error(f"Failed to build Gmail service: {str(e)}", exc_info=True)
        raise Exception(f"Gmail service build failed: {str(e)}")

def build_gmail_service_simple(access_token: str):
    """
    Simple Gmail service builder for backward compatibility.
    """
    service, _ = build_gmail_service(access_token)
    return service

async def fetch_emails(service, user_id='me', max_results=4500):
    """
    Fetch emails with comprehensive logging and error handling for each step.
    """
    logger.info(f"Starting email fetch for user_id: {user_id}, max_results: {max_results}")
    
    # Calculate the date 15 days ago for the query
    # Note: Gmail API's 'newer_than:15d' is simpler and often preferred.
    # query_string = 'newer_than:15d'

    # Using newer_than:15d for simplicity with Gmail API
    query_filter = 'newer_than:120d'
    logger.info(f"Using query filter: {query_filter}")
    
    all_messages = []
    page_token = None
    page_count = 0
    
    try:
        while True:
            page_count += 1
            logger.info(f"Fetching page {page_count} of messages...")
            
            try:
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
                logger.info(f"Page {page_count}: Retrieved {len(messages_on_page)} messages")
                all_messages.extend(messages_on_page)
                
                page_token = results.get('nextPageToken')
                logger.info(f"Page {page_count}: Next page token: {'Available' if page_token else 'None'}")
                
                # Stop if no more pages or if we have enough messages
                if not page_token or len(all_messages) >= max_results:
                    logger.info(f"Stopping pagination. Total messages collected: {len(all_messages)}")
                    break
                    
            except HttpError as e:
                logger.error(f"Gmail API HttpError on page {page_count}: {str(e)}", exc_info=True)
                if e.resp.status == 401:
                    raise Exception(f"Authentication failed: {str(e)}")
                elif e.resp.status == 403:
                    raise Exception(f"Permission denied: {str(e)}")
                elif e.resp.status == 429:
                    logger.warning(f"Rate limit hit on page {page_count}, continuing with available messages")
                    break
                else:
                    raise Exception(f"Gmail API error: {str(e)}")
            except Exception as e:
                logger.error(f"Unexpected error on page {page_count}: {str(e)}", exc_info=True)
                raise Exception(f"Failed to fetch message list: {str(e)}")
                
        # If we fetched more than max_results due to page size, trim the list
        if len(all_messages) > max_results:
            logger.info(f"Trimming messages from {len(all_messages)} to {max_results}")
            all_messages = all_messages[:max_results]

        if not all_messages:
            logger.warning(f"No emails found matching criteria: {query_filter}")
            return []
        
        logger.info(f"Total messages to process: {len(all_messages)}")
        emails = []
        successful_emails = 0
        failed_emails = 0
        
        # Process only the messages up to max_results
        for index, msg_summary in enumerate(all_messages):
            email_id = msg_summary.get('id', 'unknown')
            logger.info(f"Processing email {index + 1}/{len(all_messages)} - ID: {email_id}")
            
            try:
                # Wrap the blocking .execute() call in run_in_threadpool
                message = await run_in_threadpool(
                    service.users().messages().get(userId=user_id, id=email_id, format='full').execute
                )
                logger.debug(f"Successfully retrieved message details for email ID: {email_id}")
                
                # Extract email data with error handling
                try:
                    payload = message.get('payload', {})
                    headers = payload.get('headers', [])
                    
                    # Extract subject
                    subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '')
                    logger.debug(f"Email ID {email_id}: Subject = '{subject}'")
                    
                    # Extract snippet
                    snippet = message.get('snippet', '')
                    logger.debug(f"Email ID {email_id}: Snippet length = {len(snippet)}")
                    
                    # Extract body with detailed logging
                    body = ""
                    body_extracted = False
                    
                    if 'parts' in payload:
                        logger.debug(f"Email ID {email_id}: Processing multipart message with {len(payload['parts'])} parts")
                        for part_index, part in enumerate(payload['parts']):
                            part_mime_type = part.get('mimeType', 'unknown')
                            logger.debug(f"Email ID {email_id}: Part {part_index + 1} - MIME type: {part_mime_type}")
                            
                            if part_mime_type == 'text/plain':
                                try:
                                    if part.get('body', {}).get('data'):
                                        body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                                        logger.debug(f"Email ID {email_id}: Extracted plain text body (length: {len(body)})")
                                        body_extracted = True
                                        break
                                except Exception as decode_error:
                                    logger.warning(f"Email ID {email_id}: Failed to decode plain text part: {str(decode_error)}")
                                    
                            elif part_mime_type == 'text/html':
                                try:
                                    if part.get('body', {}).get('data'):
                                        raw_html = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                                        body = clean_html(raw_html)
                                        logger.debug(f"Email ID {email_id}: Extracted HTML body (length: {len(body)})")
                                        body_extracted = True
                                        break
                                except Exception as decode_error:
                                    logger.warning(f"Email ID {email_id}: Failed to decode HTML part: {str(decode_error)}")
                    else:
                        logger.debug(f"Email ID {email_id}: Processing single-part message")
                        if payload.get('body') and payload['body'].get('data'):
                            try:
                                body_data = payload['body'].get('data')
                                if body_data:
                                    body = base64.urlsafe_b64decode(body_data).decode('utf-8')
                                    logger.debug(f"Email ID {email_id}: Extracted single-part body (length: {len(body)})")
                                    body_extracted = True
                                else:
                                    logger.warning(f"Email ID {email_id}: Body data is empty")
                                    body = ""
                            except Exception as decode_error:
                                logger.warning(f"Email ID {email_id}: Failed to decode single-part body: {str(decode_error)}")
                                body = ""
                        else:
                            logger.warning(f"Email ID {email_id}: No body data found")
                            body = ""
                    
                    if not body_extracted and not body:
                        logger.warning(f"Email ID {email_id}: No body content extracted, using snippet as fallback")
                        body = snippet
                    
                    # Create email object
                    email_data = {
                        "id": email_id,
                        "subject": subject,
                        "snippet": snippet,
                        "body": body,
                    }
                    
                    emails.append(email_data)
                    successful_emails += 1
                    logger.info(f"Email {index + 1}/{len(all_messages)} processed successfully - ID: {email_id}")
                    
                except Exception as email_processing_error:
                    failed_emails += 1
                    logger.error(f"Email ID {email_id}: Failed to process email data: {str(email_processing_error)}", exc_info=True)
                    continue
                    
            except HttpError as e:
                failed_emails += 1
                logger.error(f"Gmail API HttpError for email ID {email_id}: {str(e)}", exc_info=True)
                if e.resp.status == 401:
                    raise Exception(f"Authentication failed while fetching email {email_id}: {str(e)}")
                elif e.resp.status == 403:
                    logger.error(f"Permission denied for email ID {email_id}: {str(e)}")
                elif e.resp.status == 404:
                    logger.warning(f"Email ID {email_id} not found (possibly deleted)")
                elif e.resp.status == 429:
                    logger.warning(f"Rate limit hit while fetching email ID {email_id}")
                else:
                    logger.error(f"Gmail API error for email ID {email_id}: {str(e)}")
                continue
                
            except Exception as e:
                failed_emails += 1
                logger.error(f"Unexpected error processing email ID {email_id}: {str(e)}", exc_info=True)
                continue
            
            # Stop fetching details if we've reached max_results
            if len(emails) >= max_results:
                logger.info(f"Reached max_results limit ({max_results}), stopping email processing")
                break
                
        logger.info(f"Email fetch completed. Successful: {successful_emails}, Failed: {failed_emails}, Total: {len(emails)}")
        return emails
        
    except Exception as e:
        logger.error(f"Fatal error during email fetch: {str(e)}", exc_info=True)
        raise Exception(f"Email fetch failed: {str(e)}")

def clean_html(raw_html):
    """
    Clean HTML content with error handling and logging.
    """
    try:
        # Basic clean-up to remove HTML tags, decode entities
        text = re.sub('<[^<]+?>', '', raw_html)
        text = html.unescape(text)
        cleaned_text = text.strip()
        logger.debug(f"HTML cleaning: Input length {len(raw_html)} -> Output length {len(cleaned_text)}")
        return cleaned_text
    except Exception as e:
        logger.error(f"Error cleaning HTML: {str(e)}", exc_info=True)
        return raw_html  # Return original if cleaning fails
