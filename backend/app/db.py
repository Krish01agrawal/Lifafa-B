from motor.motor_asyncio import AsyncIOMotorClient
from typing import Optional
import os
import certifi # Import certifi

# MONGO_URI = os.getenv(
#     "MONGO_URI",
#     "mongodb+srv://itskashyap26:%40gitartham1@cluster0.swuj2.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
# )
MONGO_URI = "mongodb+srv://itskashyap26:%40gitartham1@cluster0.swuj2.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
print("............................................................")
print("............................................................")
print("............................................................")
print("............................................................")
print("............................................................")
print("............................................................")
print("............................................................")
print("............................................................")
print("............................................................")
print("............................................................")
print("............................................................")
print("............................................................")
print("............................................................")
print("............................................................")
print("............................................................")
print("............................................................")
print("MONGO_URI:", repr(os.getenv("MONGO_URI")))
print("MONGO_URI:", MONGO_URI)
print("............................................................")
print("............................................................")
print("............................................................")
print("............................................................")
print("............................................................")
print("............................................................")
print("............................................................")
print("............................................................")
print("............................................................")
print("............................................................")
print("............................................................")
print("............................................................")
print("............................................................")
print("............................................................")
print("............................................................")
print("............................................................")

# Get CA file path from certifi
ca = certifi.where()

# Append tlsCAFile to the MONGO_URI or pass it as an argument
# Option 1: Append to URI (might require pymongo[srv] or motor[srv])
# if "?" in MONGO_URI:
#     MONGO_URI_WITH_CA = f"{MONGO_URI}&tlsCAFile={ca}"
# else:
#     MONGO_URI_WITH_CA = f"{MONGO_URI}/?tlsCAFile={ca}"
# client = AsyncIOMotorClient(MONGO_URI_WITH_CA)

# Option 2: Pass as a keyword argument (Preferred for motor)
client = AsyncIOMotorClient(MONGO_URI, tlsCAFile=ca) 
# For older PyMongo/Motor versions, it might be `ssl_cert_reqs=ssl.CERT_REQUIRED, ssl_ca_certs=ca`
# but tlsCAFile is generally preferred with modern drivers for Atlas.

db = client.genai_gmail_chat

# Create collections if they don't exist
# if "users" not in db.list_collection_names():
#     db.create_collection("users")
# if "emails" not in db.list_collection_names():
#     db.create_collection("emails")
# if "chats" not in db.list_collection_names():
#     db.create_collection("chats")

users_collection = db["users"]
emails_collection = db["emails"]
chats_collection = db["chats"]
