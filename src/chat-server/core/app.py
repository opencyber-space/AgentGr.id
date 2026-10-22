import logging
import uuid
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from . import db, delegate
from .config import LOG_LEVEL

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("chat.app")


def create_app() -> FastAPI:
    app = FastAPI(title="Chat Server", version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    async def startup():
        await db.init_db()

    @app.on_event("shutdown")
    async def shutdown():
        await db.close_db()

    # ------------------------------------------------------------------
    # WebSocket
    # ------------------------------------------------------------------

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await websocket.accept()
        session_id: Optional[str] = None
        subject_id: Optional[str] = None

        try:
            # Step 1 — initialisation
            init = await websocket.receive_json()
            if init.get("type") != "init" or not init.get("subject_id"):
                await websocket.send_json({
                    "type": "error",
                    "message": "First message must be {\"type\": \"init\", \"subject_id\": \"...\"}",
                })
                await websocket.close(code=1008)
                return

            subject_id = init["subject_id"]
            session_id = f"sess-{uuid.uuid4().hex[:8]}"

            await db.create_session(session_id, subject_id, {"init": init})
            await websocket.send_json({
                "type": "session",
                "session_id": session_id,
                "subject_id": subject_id,
            })
            logger.info("New session session_id=%s subject_id=%s", session_id, subject_id)

            # Step 2 — message loop
            while True:
                data = await websocket.receive_json()
                msg_type = data.get("type", "message")

                if msg_type == "ping":
                    await websocket.send_json({"type": "pong"})
                    continue

                task_id = data.get("task_id") or f"task-{uuid.uuid4().hex[:6]}"
                task_data = data.get("task_data", {})

                # Save request to DB
                request_payload = {
                    "subject_id": subject_id,
                    "session_id": session_id,
                    "task_id": task_id,
                    "task_data": task_data,
                }
                await db.save_message(
                    session_id, "request", task_id, subject_id,
                    request_json=request_payload,
                )

                # Forward to delegate server
                try:
                    _, response_body = await delegate.submit_and_wait(
                        subject_id, session_id, task_id, task_data
                    )
                    await db.save_message(
                        session_id, "response", task_id, subject_id,
                        response_json=response_body,
                    )
                    await websocket.send_json({
                        "type": "response",
                        "task_id": task_id,
                        "data": response_body,
                    })
                    logger.info("task_id=%s completed for session_id=%s", task_id, session_id)

                except Exception as exc:
                    logger.warning("Delegate error task_id=%s: %s", task_id, exc)
                    err_body = {"error": str(exc)}
                    await db.save_message(
                        session_id, "error", task_id, subject_id,
                        response_json=err_body,
                    )
                    await websocket.send_json({
                        "type": "error",
                        "task_id": task_id,
                        "message": str(exc),
                    })

        except WebSocketDisconnect:
            logger.info("WebSocket closed session_id=%s", session_id)
        except Exception as exc:
            logger.exception("Unexpected WebSocket error session_id=%s: %s", session_id, exc)
            try:
                await websocket.send_json({"type": "error", "message": str(exc)})
            except Exception:
                pass

    # ------------------------------------------------------------------
    # REST API
    # ------------------------------------------------------------------

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/sessions")
    async def list_sessions(subject_id: Optional[str] = Query(None)):
        """List all sessions, optionally filtered by subject_id."""
        sessions = await db.list_sessions(subject_id)
        return {"sessions": sessions, "count": len(sessions)}

    @app.get("/api/sessions/{session_id}")
    async def get_session(session_id: str):
        """Get a single session by ID."""
        session = await db.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return session

    @app.get("/api/sessions/{session_id}/messages")
    async def get_messages(session_id: str):
        """Get all messages (requests + responses) for a session."""
        session = await db.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        messages = await db.list_messages(session_id)
        return {
            "session_id": session_id,
            "subject_id": session["subject_id"],
            "messages": messages,
            "count": len(messages),
        }

    @app.get("/api/subjects/{subject_id}/sessions")
    async def get_subject_sessions(subject_id: str):
        """List all sessions for a given subject."""
        sessions = await db.list_sessions(subject_id)
        return {"subject_id": subject_id, "sessions": sessions, "count": len(sessions)}

    return app
