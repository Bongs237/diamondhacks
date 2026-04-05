"""FastAPI application entrypoint.

Mounts the Twilio webhook router and serves the API.
Run with: uvicorn main:app --reload --port 8000
"""

import logging
import os
import sys

from dotenv import load_dotenv
from fastapi import FastAPI

# Load .env before anything reads os.getenv
load_dotenv()

# Configure logging to stdout so we see mock-mode warnings immediately
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    stream=sys.stdout,
)

from api.webhooks.twilio_webhook import router as twilio_router  # noqa: E402

app = FastAPI(
    title="EventPulse",
    description="Group event planning via SMS — powered by ASI:One agents",
)

app.include_router(twilio_router)


@app.get("/health")
async def health():
    """Quick health check for testing that the server is up."""
    keys_status = {
        "asi1": bool(os.getenv("ASI1_API_KEY")),
        "twilio": bool(os.getenv("TWILIO_ACCOUNT_SID")),
        "anthropic": bool(os.getenv("ANTHROPIC_API_KEY")),
        "stripe": bool(os.getenv("STRIPE_SECRET_KEY")),
    }
    return {"status": "ok", "keys_configured": keys_status}

@app.get("/api/submit/{id}")
async def submit(id: str):
    return {"message": "Join request submitted"}

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
