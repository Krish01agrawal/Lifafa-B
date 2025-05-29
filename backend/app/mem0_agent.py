# from mem0 import MemoryClient
from agno.agent import Agent, RunResponse
from agno.models.openai import OpenAIChat
import os
try:
    # AsyncMemoryClient for async uploads, MemoryClient for synchronous agent interaction with Mem0 Platform
    from mem0 import AsyncMemoryClient, MemoryClient 
except ImportError:
    raise ImportError("mem0 is not installed. Install it using `pip install mem0ai`.")

# These environment variables are crucial for the agent and Mem0 client
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MEM0_API_KEY = os.getenv("MEM0_API_KEY") 

# Optional: Print statements for verifying env vars (can be removed in production)
print(f"MEM0_AGENT - OPENAI_API_KEY: {OPENAI_API_KEY is not None}")
print(f"MEM0_AGENT - MEM0_API_KEY: {MEM0_API_KEY is not None}")

# Client for asynchronous email uploads to Mem0 Platform
aclient = AsyncMemoryClient() 

# Client for the agno Agent to interact with Mem0 Platform (e.g., for context retrieval)
# Assumes Agent might prefer or work better with a synchronous client for its 'memory' parameter.
# Both AsyncMemoryClient and MemoryClient (for platform) will use MEM0_API_KEY from env.
agent_memory_platform_client = MemoryClient()

# Initialize the agno Agent
agent = Agent(
    model=OpenAIChat(), # This will use OPENAI_API_KEY from environment
    memory=agent_memory_platform_client, # Provide the Mem0 Platform client to the agent
    # add_context=True, # Depending on agno, this might be used in conjunction with the memory client
                         # or the memory client itself handles context fetching based on user_id in run()
)

async def upload_emails_to_mem0(user_id: str, emails: list):
    print(f"Starting email upload process to Mem0 for user_id: {user_id}. Total emails to process: {len(emails)}")
    # Ensure each email is uploaded to Mem0, using its Gmail ID as memory_id for de-duplication/update.
    for email_data in emails:
        gmail_message_id = email_data.get('id') # Assumes email_data from MongoDB has 'id' field from Gmail message ID

        if not gmail_message_id:
            print(f"Skipping email upload: Mem0 for user {user_id} due to missing Gmail message ID. Subject: {email_data.get('subject', 'N/A')}")
            continue # Skip this email if it doesn't have a unique ID

        # Construct the content to be stored in Mem0
        content = f"Subject: {email_data.get('subject', 'N/A')}\nSnippet: {email_data.get('snippet', '')}\nBody: {email_data.get('body', '')}"
        
        # Mem0 expects a list of messages for the .add() method
        messages_to_add = [
            {
                "role": "user", # Or another role that semantically represents the email data source
                "content": content
            }
        ]
        
        try:
            # Use Gmail's message ID as Mem0's memory_id.
            # This tells Mem0 to update the memory if this ID already exists for the user, otherwise create it.
            print(f"Uploading/updating email with ID {gmail_message_id} to Mem0 for user {user_id}...")
            response = await aclient.add(
                messages=messages_to_add, 
                user_id=user_id,
                memory_id=gmail_message_id 
            )
            # For debugging, you can inspect the response from Mem0:
            # print(f"Mem0 response for memory_id {gmail_message_id} (user {user_id}): {response}")
        except Exception as e:
            print(f"ERROR uploading/updating email (ID: {gmail_message_id}) in Mem0 for user {user_id}: {e}")
    print(f"Finished email upload process to Mem0 for user_id: {user_id}.")

async def query_mem0(user_id: str, query: str):
    print(f"Attempting direct Mem0 search for user_id: {user_id}, query: {query}")
    try:
        # Using aclient.search() for direct Mem0 query. This is an async call.
        # The response will be a list of search results from Mem0, not a RunResponse object.
        search_results = await aclient.search(query=query, user_id=user_id)
        
        print(f"Mem0 search results for user {user_id}: {search_results}") 
        
        # For an API test, returning the raw search results might be useful.
        # Or, you could process them, e.g., concatenate text from hits.
        # Example: return [result.get('text') for result in search_results if result.get('text')]
        return search_results # Returning the raw list of search hits

    except Exception as e:
        print(f"Error during Mem0 search for user {user_id}: {e}")
        # Fallback or error message for direct search failure
        return {"error": f"Failed to search Mem0: {str(e)}"}
