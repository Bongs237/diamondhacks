# Run this to set up the agent on agentverse for local development
# MAKE SURE IT USES THE ENV FILE or this bout to fail
# e.g. cd backend && uv run --env-file ../.env setup_agent.py

import os
from uagents_core.utils.registration import (
    register_chat_agent,
    RegistrationRequestCredentials,
)

register_chat_agent(
    "Eventpulse-ben",
    "https://sniffier-robbin-egotistic.ngrok-free.dev",
    active=True,
    credentials=RegistrationRequestCredentials(
        agentverse_api_key=os.environ["AGENTVERSE_KEY"],
        agent_seed_phrase=os.environ["AGENT_SEED_PHRASE"],        
    ),
)
