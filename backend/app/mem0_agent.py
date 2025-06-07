# from mem0 import MemoryClient
from agno.agent import Agent, RunResponse
from agno.models.openai import OpenAIChat
import os
import asyncio
import logging
import openai # Import the openai library
from fastapi.concurrency import run_in_threadpool # Added import

# Configure logging for this module
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    # AsyncMemoryClient for async uploads, MemoryClient for synchronous agent interaction with Mem0 Platform
    from mem0 import AsyncMemoryClient, MemoryClient 
except ImportError:
    logger.error("mem0 is not installed. Install it using `pip install mem0ai`.")
    raise ImportError("mem0 is not installed. Install it using `pip install mem0ai`.")

# These environment variables are crucial for the agent and Mem0 client
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MEM0_API_KEY = os.getenv("MEM0_API_KEY") 

# Initialize OpenAI client
if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY
    logger.info("OpenAI API key configured successfully")
else:
    logger.error("OPENAI_API_KEY environment variable not set")
    # Or raise an exception

# Verify Mem0 API key
if MEM0_API_KEY:
    logger.info("Mem0 API key configured successfully")
else:
    logger.error("MEM0_API_KEY environment variable not set")

# Optional: Print statements for verifying env vars (can be removed in production)
logger.info(f"MEM0_AGENT - OPENAI_API_KEY: {OPENAI_API_KEY is not None}")
logger.info(f"MEM0_AGENT - MEM0_API_KEY: {MEM0_API_KEY is not None}")

# Client for asynchronous email uploads to Mem0 Platform
try:
    aclient = AsyncMemoryClient()
    logger.info("AsyncMemoryClient initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize AsyncMemoryClient: {str(e)}", exc_info=True)
    aclient = None

# Client for the agno Agent to interact with Mem0 Platform (e.g., for context retrieval)
# Assumes Agent might prefer or work better with a synchronous client for its 'memory' parameter.
# Both AsyncMemoryClient and MemoryClient (for platform) will use MEM0_API_KEY from env.
try:
    agent_memory_platform_client = MemoryClient()
    logger.info("MemoryClient initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize MemoryClient: {str(e)}", exc_info=True)
    agent_memory_platform_client = None

# Initialize the agno Agent
# agent = Agent(
#     model=OpenAIChat(), # This will use OPENAI_API_KEY from environment
#     memory=agent_memory_platform_client, # Temporarily remove memory to isolate issue
#     add_context=True, 
# )

async def upload_emails_to_mem0(user_id: str, emails: list):
    """
    Upload emails to Mem0 with comprehensive logging and error handling for each email.
    """
    logger.info(f"Starting email upload process to Mem0 for user_id: {user_id}. Total emails to process: {len(emails)}")
    
    if not aclient:
        logger.error(f"AsyncMemoryClient not available for user {user_id}")
        raise Exception("Mem0 client not properly initialized")
    
    if not emails:
        logger.warning(f"No emails provided for upload to Mem0 for user_id: {user_id}")
        return
    
    successful_uploads = 0
    failed_uploads = 0
    upload_errors = []
    
    # Ensure each email is uploaded to Mem0, using its Gmail ID as memory_id for de-duplication/update.
    for index, email_data in enumerate(emails):
        gmail_message_id = email_data.get('id') # Assumes email_data from MongoDB has 'id' field from Gmail message ID
        email_subject = email_data.get('subject', 'N/A')
        
        logger.info(f"Processing email {index + 1}/{len(emails)} for Mem0 upload - ID: {gmail_message_id}, Subject: '{email_subject}'")

        if not gmail_message_id:
            failed_uploads += 1
            error_msg = f"Skipping email upload to Mem0 for user {user_id} due to missing Gmail message ID. Subject: {email_subject}"
            logger.warning(error_msg)
            upload_errors.append({
                "email_index": index + 1,
                "subject": email_subject,
                "error": "Missing Gmail message ID"
            })
            continue # Skip this email if it doesn't have a unique ID

        try:
            # Validate email data
            email_snippet = email_data.get('snippet', '')
            email_body = email_data.get('body', '')
            
            logger.debug(f"Email ID {gmail_message_id}: Subject length = {len(email_subject)}, Snippet length = {len(email_snippet)}, Body length = {len(email_body)}")
            
            # Construct the content to be stored in Mem0
            content = f"Subject: {email_subject}\\nSnippet: {email_snippet}\\nBody: {email_body}"
            
            if len(content.strip()) == 0:
                logger.warning(f"Email ID {gmail_message_id}: Content is empty, using subject as fallback")
                content = f"Subject: {email_subject}"
            
            logger.debug(f"Email ID {gmail_message_id}: Final content length = {len(content)}")
            
            # Mem0 expects a list of messages for the .add() method
            messages_to_add = [
                {
                    "role": "user", # Or another role that semantically represents the email data source
                    "content": content
                }
            ]
            
            logger.debug(f"Email ID {gmail_message_id}: Prepared message for Mem0 upload")
            
            # Use Gmail's message ID as Mem0's memory_id.
            # This tells Mem0 to update the memory if this ID already exists for the user, otherwise create it.
            logger.info(f"Uploading/updating email with ID {gmail_message_id} to Mem0 for user {user_id}...")
            
            try:
                response = await aclient.add(
                    messages=messages_to_add, 
                    user_id=user_id,
                    memory_id=gmail_message_id 
                )
                
                # Log the response for debugging
                logger.debug(f"Mem0 response for memory_id {gmail_message_id} (user {user_id}): {response}")
                
                # Check if the response indicates success
                if response:
                    successful_uploads += 1
                    logger.info(f"✅ Email {index + 1}/{len(emails)} uploaded successfully to Mem0 - ID: {gmail_message_id}")
                else:
                    failed_uploads += 1
                    error_msg = f"Mem0 returned empty response for email ID {gmail_message_id}"
                    logger.warning(error_msg)
                    upload_errors.append({
                        "email_index": index + 1,
                        "email_id": gmail_message_id,
                        "subject": email_subject,
                        "error": "Empty response from Mem0"
                    })
                    
            except Exception as mem0_api_error:
                failed_uploads += 1
                error_msg = f"Mem0 API error for email ID {gmail_message_id}: {str(mem0_api_error)}"
                logger.error(error_msg, exc_info=True)
                upload_errors.append({
                    "email_index": index + 1,
                    "email_id": gmail_message_id,
                    "subject": email_subject,
                    "error": str(mem0_api_error)
                })
                
                # Check if it's a rate limiting or quota issue
                if "rate limit" in str(mem0_api_error).lower() or "quota" in str(mem0_api_error).lower():
                    logger.warning(f"Rate limit or quota issue detected for user {user_id}. Consider implementing retry with backoff.")
                
                # Check if it's an authentication issue
                if "auth" in str(mem0_api_error).lower() or "unauthorized" in str(mem0_api_error).lower():
                    logger.error(f"Authentication issue with Mem0 for user {user_id}. Check API key configuration.")
                
                continue
                
        except Exception as email_processing_error:
            failed_uploads += 1
            error_msg = f"Error processing email data for Mem0 upload (ID: {gmail_message_id}): {str(email_processing_error)}"
            logger.error(error_msg, exc_info=True)
            upload_errors.append({
                "email_index": index + 1,
                "email_id": gmail_message_id,
                "subject": email_subject,
                "error": str(email_processing_error)
            })
            continue
    
    # Final summary
    logger.info(f"📊 Mem0 upload summary for user_id {user_id}:")
    logger.info(f"   ✅ Successful uploads: {successful_uploads}")
    logger.info(f"   ❌ Failed uploads: {failed_uploads}")
    logger.info(f"   📧 Total emails processed: {len(emails)}")
    
    if upload_errors:
        logger.warning(f"Upload errors for user {user_id}:")
        for error in upload_errors[:5]:  # Log first 5 errors to avoid spam
            logger.warning(f"   - Email {error['email_index']}: {error.get('error', 'Unknown error')}")
        
        if len(upload_errors) > 5:
            logger.warning(f"   ... and {len(upload_errors) - 5} more errors")
    
    logger.info(f"Finished email upload process to Mem0 for user_id: {user_id}.")
    
    # Raise an exception if all uploads failed
    if failed_uploads == len(emails) and len(emails) > 0:
        raise Exception(f"All {len(emails)} email uploads failed for user {user_id}")

async def query_mem0(user_id: str, query: str):
    """
    Query Mem0 with comprehensive logging and error handling.
    """
    logger.info(f"Starting Mem0 query for user_id: {user_id}, query: '{query}'")
    
    system_prompt = (
        "You are a highly insightful assistant specializing in analyzing email data. "
        "Based on the provided email snippets and the user's query, provide a comprehensive and structured answer. "
        "Your response should be easy to understand and professional.\n\n"
        "Follow these guidelines for your response:\n"
        "1. Start with a brief, direct answer or summary of your findings related to the user's query."
        "2. If specific email snippets support your answer, present them clearly, perhaps using bullet points or numbered lists. Refer to them as 'insights from emails' or similar."
        "3. For each relevant insight, explain its significance in relation to the query."
        "4. If multiple emails touch on the same topic, synthesize the information rather than just listing each email separately, unless the user asks for individual email details."
        "5. If the provided email snippets are insufficient to fully answer the query, clearly state what information is missing or what aspects cannot be addressed based on the context."
        "6. Conclude with a summary or an offer for further assistance if applicable."
        "7. Use markdown for formatting, especially for lists, bolding key terms, and ensuring readability. Remember that the output will be rendered in HTML that respects newlines (pre-wrap)."
        "8. Do NOT just list the snippets. Provide analysis and connect them to the user's query."
        "9. If no relevant emails are found in the context, state that clearly, for example: 'Based on the provided email data, I could not find specific information related to your query about [topic].'"
    )
    
    messages = [
        {"role": "system", "content": system_prompt}
    ]
    
    context_str = ""
    retrieved_memories = []
    
    try:
        if agent_memory_platform_client:
            logger.info(f"Searching Mem0 for user {user_id} with query: '{query}'")
            # Wrap the blocking .search() call in run_in_threadpool
            retrieved_memories = await run_in_threadpool(
                agent_memory_platform_client.search, 
                query=query, 
                user_id=user_id, 
                limit=25
            )
            logger.info(f"Mem0 search returned {len(retrieved_memories) if retrieved_memories else 0} results for user {user_id}")
            logger.debug(f"DEBUG [query_mem0]: Mem0 search results for user {user_id}, query '{query}': {retrieved_memories}")
            
            if retrieved_memories:
                context_str = "\\n\\nRelevant email snippets:\\n"
                for i, mem in enumerate(retrieved_memories):
                    memory_content = mem.get('memory', '')
                    context_str += f"{i+1}. {memory_content}\\n"
                    logger.debug(f"Memory {i+1}: {memory_content[:100]}..." if len(memory_content) > 100 else f"Memory {i+1}: {memory_content}")
                
                messages.append({"role": "user", "content": f"Context:\\n{context_str}\\n\\nUser Query: {query}"})
                logger.info(f"Added context from {len(retrieved_memories)} memories to OpenAI query")
            else:
                messages.append({"role": "user", "content": query}) # No context found, just send query
                logger.warning(f"No relevant memories found for user {user_id} and query '{query}'")
        else:
            logger.error(f"agent_memory_platform_client is None for user {user_id}")
            messages.append({"role": "user", "content": query}) # No memory client, just send query

    except Exception as mem_e:
        logger.error(f"Error querying Mem0 for user {user_id}: {str(mem_e)}", exc_info=True)
        messages.append({"role": "user", "content": query}) # Error with memory, just send query
        
    try:
        if not openai.api_key:
            logger.error("OpenAI API key not configured")
            return {"reply": ["Error: OpenAI API key not configured."], "error": True}

        logger.debug(f"Sending {len(messages)} messages to OpenAI for user {user_id}")
        logger.debug(f"DEBUG [query_mem0]: Messages being sent to OpenAI: {messages}")

        # Use asyncio.to_thread for the blocking OpenAI call
        logger.info(f"Calling OpenAI API for user {user_id}")
        response = await asyncio.to_thread(
            openai.chat.completions.create, # Updated to new API: openai.chat.completions.create
            model="gpt-3.5-turbo", # Or your preferred model
            messages=messages,
            temperature=0.7,
            max_tokens=1024 # Adjust as needed
        )
        
        logger.debug(f"DEBUG [query_mem0]: Full OpenAI response: {response}")
        
        if response.choices and response.choices[0].message and response.choices[0].message.content:
            reply_content = response.choices[0].message.content.strip()
            logger.info(f"OpenAI response received for user {user_id} (length: {len(reply_content)})")
            logger.debug(f"DEBUG [query_mem0]: OpenAI reply: {reply_content}")
            return {"reply": [reply_content]}
        else:
            logger.error(f"OpenAI response malformed or empty for user {user_id}. Full response: {response}")
            return {"reply": ["Error: Assistant did not provide a valid response."], "error": True}

    except openai.APIError as e: # More specific OpenAI error handling
        logger.error(f"OpenAI API Error for user {user_id}: {str(e)}", exc_info=True)
        return {"reply": [f"OpenAI API Error: {e}"], "error": True}
    except Exception as e:
        logger.error(f"Exception during OpenAI call for user {user_id} with query '{query}': {str(e)}", exc_info=True)
        return {"reply": [f"Error processing your query: {str(e)}"], "error": True}

# Remove agno agent if no longer needed elsewhere
# del agent 
