#!/usr/bin/env python3
"""
WebSocket client for the chat server.

Usage:
    python3 client.py                        # uses defaults below
    WS_URL=ws://localhost:8080/ws python3 client.py
"""

import asyncio
import json
import os
import sys
import uuid

import websockets

WS_URL = os.getenv("WS_URL", "ws://34.93.251.223:30728/ws")

SUBJECT_ID = "agent-behavioral-code-creator"

TASK_DATA = {
    "user_request": (
        "Function to add three numbers in python"
    )
}


def pretty(label: str, data: dict):
    print(f"\n{'─'*60}")
    print(f"  {label}")
    print(f"{'─'*60}")
    print(json.dumps(data, indent=2))


async def run():
    print(f"Connecting to {WS_URL} ...")

    async with websockets.connect(WS_URL) as ws:

        # ── 1. Initialise session ──────────────────────────────────
        init_msg = {"type": "init", "subject_id": SUBJECT_ID}
        await ws.send(json.dumps(init_msg))
        pretty("SENT  →  init", init_msg)

        session_msg = json.loads(await ws.recv())
        pretty("RECV  ←  session", session_msg)

        if session_msg.get("type") != "session":
            print("ERROR: expected session ack, got:", session_msg)
            sys.exit(1)

        session_id = session_msg["session_id"]
        print(f"\n  session_id : {session_id}")
        print(f"  subject_id : {session_msg['subject_id']}")

        # ── 2. Send task ───────────────────────────────────────────
        task_id = f"task-{uuid.uuid4().hex[:6]}"
        task_msg = {
            "type": "message",
            "task_id": task_id,
            "task_data": {**TASK_DATA, "session_id": session_id},
        }
        await ws.send(json.dumps(task_msg))
        pretty("SENT  →  task", task_msg)

        # ── 3. Wait for response ───────────────────────────────────
        print("\nWaiting for delegate response (this may take a moment)...")
        response = json.loads(await ws.recv())
        pretty("RECV  ←  response", response)

        if response.get("type") == "error":
            print(f"\n  [ERROR] {response.get('message')}")
            sys.exit(1)

        # Pretty-print the generated code if present
        data = response.get("data", {})
        for key in ("output", "result", "text", "content", "code"):
            if key in data:
                print(f"\n{'═'*60}")
                print(f"  Generated output ({key}):")
                print(f"{'═'*60}")
                print(data[key])
                break

    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(run())
