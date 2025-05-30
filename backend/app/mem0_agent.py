# from mem0 import MemoryClient
from agno.agent import Agent, RunResponse
from agno.models.openai import OpenAIChat
import os
import asyncio
import openai # Import the openai library

try:
    # AsyncMemoryClient for async uploads, MemoryClient for synchronous agent interaction with Mem0 Platform
    from mem0 import AsyncMemoryClient, MemoryClient 
except ImportError:
    raise ImportError("mem0 is not installed. Install it using `pip install mem0ai`.")

# These environment variables are crucial for the agent and Mem0 client
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MEM0_API_KEY = os.getenv("MEM0_API_KEY") 

# Initialize OpenAI client
if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY
else:
    print("ERROR: OPENAI_API_KEY environment variable not set.")
    # Or raise an exception

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
# agent = Agent(
#     model=OpenAIChat(), # This will use OPENAI_API_KEY from environment
#     memory=agent_memory_platform_client, # Temporarily remove memory to isolate issue
#     add_context=True, 
# )

async def upload_emails_to_mem0(user_id: str, emails: list):
    print(f"Starting email upload process to Mem0 for user_id: {user_id}. Total emails to process: {len(emails)}")
    # Ensure each email is uploaded to Mem0, using its Gmail ID as memory_id for de-duplication/update.
    for email_data in emails:
        gmail_message_id = email_data.get('id') # Assumes email_data from MongoDB has 'id' field from Gmail message ID

        if not gmail_message_id:
            print(f"Skipping email upload: Mem0 for user {user_id} due to missing Gmail message ID. Subject: {email_data.get('subject', 'N/A')}")
            continue # Skip this email if it doesn't have a unique ID

        # Construct the content to be stored in Mem0
        content = f"Subject: {email_data.get('subject', 'N/A')}\\nSnippet: {email_data.get('snippet', '')}\\nBody: {email_data.get('body', '')}"
        
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
    print(f"Querying OpenAI directly for user_id: {user_id}, query: '{query}'")
    
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
    try:
        if agent_memory_platform_client:
            retrieved_memories = agent_memory_platform_client.search(query=query, user_id=user_id, limit=5) # Limit context size
            print(f"DEBUG [query_mem0]: Mem0 search results for user {user_id}, query '{query}': {retrieved_memories}")
            if retrieved_memories:
                context_str = "\\n\\nRelevant email snippets:\\n"
                for i, mem in enumerate(retrieved_memories):
                    context_str += f"{i+1}. {mem.get('memory', '')}\\n" # 'memory' field holds the text
                messages.append({"role": "user", "content": f"Context:\\n{context_str}\\n\\nUser Query: {query}"})
            else:
                messages.append({"role": "user", "content": query}) # No context found, just send query
        else:
            print(f"DEBUG [query_mem0]: agent_memory_platform_client is None.")
            messages.append({"role": "user", "content": query}) # No memory client, just send query

    except Exception as mem_e:
        print(f"DEBUG [query_mem0]: Error querying Mem0: {mem_e}")
        messages.append({"role": "user", "content": query}) # Error with memory, just send query
        
    try:
        if not openai.api_key:
            return {"reply": ["Error: OpenAI API key not configured."], "error": True}

        print(f"DEBUG [query_mem0]: Messages being sent to OpenAI: {messages}")

        # Use asyncio.to_thread for the blocking OpenAI call
        response = await asyncio.to_thread(
            openai.chat.completions.create, # Updated to new API: openai.chat.completions.create
            model="gpt-3.5-turbo", # Or your preferred model
            messages=messages,
            temperature=0.7,
            max_tokens=1024 # Adjust as needed
        )
        
        # print(f"DEBUG [query_mem0]: Full OpenAI response: {response}")
        
        if response.choices and response.choices[0].message and response.choices[0].message.content:
            reply_content = response.choices[0].message.content.strip()
            print(f"DEBUG [query_mem0]: OpenAI reply: {reply_content}")
            return {"reply": [reply_content]}
        else:
            print(f"ERROR [query_mem0]: OpenAI response malformed or empty. Full response: {response}")
            return {"reply": ["Error: Assistant did not provide a valid response."], "error": True}

    except openai.APIError as e: # More specific OpenAI error handling
        print(f"ERROR [query_mem0]: OpenAI API Error: {e}")
        return {"reply": [f"OpenAI API Error: {e}"], "error": True}
    except Exception as e:
        print(f"ERROR [query_mem0]: Exception during OpenAI call for user {user_id} with query '{query}': {e}")
        return {"reply": [f"Error processing your query: {str(e)}"], "error": True}

# Remove agno agent if no longer needed elsewhere
# del agent 
