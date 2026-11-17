
import asyncio
import logging
import logfire
import os
from cuk_assistant.core.factory import create_rag_orchestrator

os.environ["LOGFIRE_TOKEN"] = "pylf_v1_us_VyF69dF9BcBnhNgYl9l7vldG9C5hpVQLkPcGZRJqz8wV"
logfire.configure(token=os.environ["LOGFIRE_TOKEN"])
logfire.instrument_httpx()
logfire.instrument_pydantic()

async def test_backend_slot_filling():
    orchestrator = create_rag_orchestrator()
    session_id = "test-session-123"
    query = "What is DBMS?"
    
    # Simulate turn 1: Initial query
    print("--- Turn 1: Initial Query ---")
    async for event in orchestrator.stream_turn(query=query, session_id=session_id):
        print(f"Event: {event}")
        
    # Simulate turn 2: Batch Selection
    print("\n--- Turn 2: Batch Selection ---")
    slots = {"batch_year": "2024"}
    async for event in orchestrator.stream_turn(query=query, session_id=session_id, slots=slots):
        print(f"Event: {event}")

if __name__ == "__main__":
    asyncio.run(test_backend_slot_filling())
