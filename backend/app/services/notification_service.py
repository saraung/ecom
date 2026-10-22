from typing import Dict, List, Optional
import asyncio
import json
import uuid
from datetime import datetime, timezone
from fastapi import WebSocket
from sqlalchemy.orm import Session

class EcommerceNotificationService:
    def __init__(self):
        self.connections: Dict[str, List[WebSocket]] = {}
        self.notification_history: Dict[str, List[dict]] = {}
    
    async def connect(self, user_id: str, websocket: WebSocket):
        """Connect a user's WebSocket"""
        # ❌ REMOVE THIS LINE - websocket is already accepted in the endpoint
        # await websocket.accept()
        
        print(f"📝 Connecting user: {user_id}")
        
        if user_id not in self.connections:
            self.connections[user_id] = []
        
        # Check if this websocket is already connected for this user
        if websocket not in self.connections[user_id]:
            self.connections[user_id].append(websocket)
            print(f"✅ User {user_id} connected. Total connections: {len(self.connections[user_id])}")
        else:
            print(f"⚠️ WebSocket already connected for user {user_id}")
        
        # Send any missed notifications
        if user_id in self.notification_history:
            print(f"📬 Sending {len(self.notification_history[user_id])} missed notifications")
            for notification in self.notification_history[user_id]:
                try:
                    await websocket.send_json(notification)
                except Exception as e:
                    print(f"❌ Failed to send missed notification: {e}")
            del self.notification_history[user_id]
    
    def disconnect(self, user_id: str, websocket: WebSocket):
        """Disconnect a user's WebSocket"""
        print(f"🔌 Disconnecting user: {user_id}")
        
        if user_id in self.connections:
            if websocket in self.connections[user_id]:
                self.connections[user_id].remove(websocket)
                print(f"✅ WebSocket removed for user {user_id}")
            if not self.connections[user_id]:
                del self.connections[user_id]
                print(f"✅ User {user_id} fully disconnected")
    
    async def send_personal_notification(
        self,
        user_id: str,
        title: str,
        body: str,
        data: dict,
        notification_type: str = "general"
    ):
        """Send notification to specific user"""
        print(f"📤 Sending notification to user: {user_id}")
        
        notification = {
            "id": str(uuid.uuid4()),
            "title": title,
            "body": body,
            "data": data,
            "type": notification_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "read": False
        }
        
        # If user is connected, send immediately
        if user_id in self.connections:
            print(f"✅ User {user_id} is connected with {len(self.connections[user_id])} websocket(s)")
            for websocket in self.connections[user_id]:
                try:
                    await websocket.send_json(notification)
                    print(f"✅ Notification sent to websocket")
                except Exception as e:
                    print(f"❌ Failed to send to websocket: {e}")
                    self.disconnect(user_id, websocket)
        else:
            # Store for later delivery
            print(f"📝 User {user_id} not connected, storing notification")
            if user_id not in self.notification_history:
                self.notification_history[user_id] = []
            self.notification_history[user_id].append(notification)
        
        return notification
    
    async def broadcast_promotion(
        self,
        title: str,
        body: str,
        data: dict = None,
        target_user_ids: List[str] = None,
        notification_type: str = "promotion",
        audience: str | None = None,
    ):
        """Send promotional notification to all or specific users.

        ``audience`` gates the unfiltered broadcast path: ``shopper``
        broadcasts reach storefront clients, while anything else (admin
        operational traffic such as order_placed / order_cancelled) stays
        out of shopper sockets. Targeted sends (explicit user ids) bypass
        the gate — the caller already resolved recipients.
        """
        if data is None:
            data = {}

        print(f"📢 Broadcasting promotion: {title}")
        print(f"👥 Connected users: {list(self.connections.keys())}")

        sent_count = 0
        failed_count = 0

        # If target_user_ids provided, send only to those users
        if target_user_ids:
            print(f"🎯 Target users: {target_user_ids}")
            for user_id in target_user_ids:
                try:
                    await self.send_personal_notification(
                        user_id=user_id,
                        title=title,
                        body=body,
                        data=data,
                        notification_type=notification_type,
                    )
                    sent_count += 1
                except Exception as e:
                    print(f"❌ Failed to send to user {user_id}: {e}")
                    failed_count += 1
        else:
            # Unfiltered broadcasts are shopper traffic only — never fan out
            # staff operational alerts to every connected socket.
            if audience is not None and audience != "shopper":
                print(f"⏭️ Skipping non-shopper broadcast (audience={audience})")
                return {
                    "sent_count": 0,
                    "failed_count": 0,
                    "total_connected_users": len(self.connections),
                }
            # Send to all connected users
            for user_id in list(self.connections.keys()):
                try:
                    await self.send_personal_notification(
                        user_id=user_id,
                        title=title,
                        body=body,
                        data=data,
                        notification_type=notification_type,
                    )
                    sent_count += 1
                except Exception as e:
                    print(f"❌ Failed to send to user {user_id}: {e}")
                    failed_count += 1
        
        print(f"📊 Results - Sent: {sent_count}, Failed: {failed_count}")
        
        return {
            "sent_count": sent_count,
            "failed_count": failed_count,
            "total_connected_users": len(self.connections)
        }
    
    def get_connected_users(self) -> List[str]:
        """Get list of connected user IDs"""
        return list(self.connections.keys())
    
    def get_connection_count(self) -> int:
        """Get total number of connected users"""
        return len(self.connections)


# Initialize singleton
notification_service = EcommerceNotificationService()