from __future__ import annotations

from core.message_bus import BusMessage, MessageType, message_bus


async def agent_to_agent(session_id: str, sender: str, recipient: str, message_type: MessageType, content: dict):
    # silent bus: peer agent direct message, no orchestrator intervention.
    await message_bus.publish(
        BusMessage(
            session_id=session_id,
            sender=sender,
            recipient=recipient,
            message_type=message_type,
            content=content,
        )
    )


async def peer_agent_exchange(session_id: str, sender: str, recipient: str, content: dict):
    await agent_to_agent(session_id, sender, recipient, MessageType.CHALLENGE, content)
