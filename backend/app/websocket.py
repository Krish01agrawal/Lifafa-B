from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from jose import jwt
from app.auth import decode_jwt_token
from app.mem0_agent import query_mem0
import asyncio

router = APIRouter()

active_connections = {}

async def get_user_from_token(token: str):
    return decode_jwt_token(token)

@router.websocket("/ws/chat")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        # Receive initial message with JWT token for auth
        data = await websocket.receive_json()
        token = data.get("jwt_token")
        if not token:
            await websocket.close(code=1008)
            return
        user = await get_user_from_token(token)
        user_id = user.get("user_id")

        active_connections[user_id] = websocket

        while True:
            data = await websocket.receive_json()
            query = data.get("message")
            if not query:
                continue
            # Query Mem0 + LLM
            reply = await query_mem0(user_id=user_id, query=query)

            # Stream reply (send as one message for simplicity)
            await websocket.send_json({"reply": reply})

            # TODO: Save chat to MongoDB (can be added here)
    except WebSocketDisconnect:
        if user_id in active_connections:
            del active_connections[user_id]
