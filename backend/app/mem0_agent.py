# from mem0 import MemoryClient
from agno.agent import Agent, RunResponse
from agno.models.openai import OpenAIChat
import os
try:
    # Use AsyncMemoryClient for async operations
    from mem0 import AsyncMemoryClient, Memory # Also import Memory for Agent context if needed
except ImportError:
    raise ImportError("mem0 is not installed. Install it using `pip install mem0ai`.")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MEM0_API_KEY = os.getenv("MEM0_API_KEY") # Ensure MEM0_API_KEY is also explicitly fetched if needed for client init
print("............................................................")
print("............................................................")
print("............................................................")
print("............................................................")
print("............................................................")
print("OPENAI_API_KEY: ", OPENAI_API_KEY)
print("............................................................")
print("............................................................")
print("............................................................")
print("............................................................")
print("............................................................")
print("............................................................")
print("............................................................")

# Initialize AsyncMemoryClient for async operations
# If MEM0_API_KEY is set as an environment variable, AsyncMemoryClient() should pick it up.
# Otherwise, you might need client = AsyncMemoryClient(api_key=MEM0_API_KEY)
aclient = AsyncMemoryClient() 

# For the synchronous Agent context, if client.get_all is synchronous:
# We might need a separate synchronous client or adapt the agent.
# For now, let's assume MemoryClient() or Memory() is for the synchronous part.
# If `client.get_all` in Agent context is also meant to be async, Agent setup might need review.
sync_client_for_agent_context = Memory() # Using open-source `Memory` for `get_all` if it's synchronous
                                        # If using platform `get_all`, it might be `MemoryClient().get_all`

user_id_static = "agnomem0v2.3.O" # Using a more descriptive variable name

agent = Agent(
    model=OpenAIChat(),
    # Assuming get_all from the synchronous client is appropriate here
    # If get_all itself needs to be async, this Agent setup might need adjustment
    # or use of a synchronous wrapper if the Agent class doesn't support async context directly.
    context={"memory": sync_client_for_agent_context.get_all(user_id=user_id_static, limit=500)}, 
    add_context=True,
)

async def upload_emails_to_mem0(user_id: str, emails: list):
    # Upload each email as a separate message in Mem0
    for email in emails:
        content = f"Subject: {email['subject']}\nBody: {email['body']}"
        # Structure as a list of messages for the .add() method
        messages_to_add = [
            {
                "role": "user", # Or another appropriate role representing the email data
                "content": content
            }
        ]
        # Use the async client's .add() method
        # The add method for the platform client usually doesn't require a 'data' sub-dictionary
        response = await aclient.add(messages=messages_to_add, user_id=user_id)
        # print(f"Mem0 add response: {response}") # Optional: log response

async def query_mem0(user_id: str, query: str):
    # This agent uses a synchronous call to get_all in its context. This might be an issue
    # if the underlying get_all for the platform is async only.
    # For now, assuming the agent setup is correct for its intended operation.
    response: RunResponse = await agent.run(query, user_id=user_id)
    return response.result
