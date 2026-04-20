import asyncio
import json
from app.config import settings
from app.schemas.signal import SignalIncomingMessage
from app.services.ai_engine import ai_engine
from app.db.session import SessionLocal

# Force AI on for testing
settings.feature_ai_enabled = True

async def main():
    print("🤖 --- SMB Local Simulator ---")
    
    if not settings.ai_api_key or settings.ai_api_key == "sk-your-api-key-here":
        print("⚠️  Warning: AI_API_KEY is not set or is using the default value.")
        print("Please set a real API key in .env to test the AI properly.")
        return

    print("✅ AI Engine available. Connecting to DB...")
    
    # 1. Simulate an incoming message
    raw_payload = {
        "envelope": {
            "source": "+1234567890",
            "sourceNumber": "+1234567890",
            "sourceName": "TestUser",
            "timestamp": 1670000000000,
            "dataMessage": {
                "timestamp": 1670000000000,
                "message": "Ahoj, jaké produkty máte na skladě?",
                "expiresInSeconds": 0
            }
        }
    }
    
    msg = SignalIncomingMessage.model_validate(raw_payload)
    print(f"\n📩 [Incoming] {msg.envelope.sender_name}: {msg.envelope.text}")
    
    # 2. Process via AI Engine directly
    print("⏳ Processing via AI Engine...")
    async with SessionLocal() as db:
        response = await ai_engine.generate_reply(db, msg)
        
    print(f"\n📨 [Bot Reply]:\n{response}\n")

if __name__ == "__main__":
    asyncio.run(main())
