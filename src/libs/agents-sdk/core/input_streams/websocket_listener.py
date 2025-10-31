import json
import logging
import os
import signal
import sys
from typing import Callable, Dict, Optional

from websockets.sync.server import serve
from websockets.exceptions import ConnectionClosedOK, ConnectionClosedError

JsonDict = Dict[str, object]
SyncCallback = Callable[[JsonDict], JsonDict]


class WebSocketJSONSyncServer:
  

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 8765,
        auth_token: Optional[str] = None, 
        max_size: int = 2 * 1024 * 1024, 
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.host = host
        self.port = port
        self.auth_token = auth_token
        self.max_size = max_size

        self.logger = logger or logging.getLogger(self.__class__.__name__)
        if not self.logger.handlers:
            logging.basicConfig(
                level=os.getenv("LOG_LEVEL", "INFO").upper(),
                format="%(asctime)s %(levelname)s %(name)s: %(message)s",
            )

        self._callback: Optional[SyncCallback] = None
        self._server = None
        self._stop_requested = False

    # ----------------- Public API -----------------

    def run_forever(self, callback: SyncCallback) -> None:
        
        self._callback = callback

        def _signal_handler(signum, frame):
            self.logger.info("Signal %s received; stopping...", signum)
            self._stop_requested = True
            os._exit(0)

        try:
            signal.signal(signal.SIGINT, _signal_handler)
            signal.signal(signal.SIGTERM, _signal_handler)
        except Exception:
            pass

        self.logger.info("Starting WebSocket server on ws://%s:%d", self.host, self.port)
        with serve(
            self._handler,
            self.host,
            self.port,
            max_size=self.max_size,
        ) as server:
            self._server = server
            # Block until a stop is requested
            try:
                while not self._stop_requested:
                    server.serve_forever()
            finally:
                self.logger.info("Shutting down WebSocket server...")

    # ----------------- Internals -----------------

    def _handler(self, websocket):
      
        if self.auth_token:
            auth = websocket.request_headers.get("Authorization", "")
            if not (auth.startswith("Bearer ") and auth.split(" ", 1)[1] == self.auth_token):
                try:
                    websocket.send(json.dumps({"ok": False, "error": {"code": "unauthorized", "message": "Unauthorized"}}))
                except Exception:
                    pass
                websocket.close(code=1008, reason="Unauthorized")
                return

        peer = self._peer(websocket)
        self.logger.info("Client connected: %s", peer)

        try:
            for raw in websocket:
                # --- Parse JSON ---
                try:
                    if isinstance(raw, (bytes, bytearray)):
                        raw = raw.decode("utf-8", errors="strict")
                    msg = json.loads(raw)
                    if not isinstance(msg, dict):
                        raise ValueError("Message must be a JSON object")
                except Exception as e:
                    self._send_error(websocket, None, "bad_json", str(e))
                    continue

                req_id = msg.get("id")

                try:
                    assert self._callback is not None, "Callback not set"
                    result = self._callback(msg)  # <- single, synchronous call
                    if not isinstance(result, dict):
                        raise TypeError("Callback must return a dict")
                except Exception as e:
                    # Return error envelope
                    self._send_error(websocket, req_id, "callback_error", str(e))
                    continue

                response: JsonDict = {"id": req_id, "ok": True, "data": result}
                try:
                    websocket.send(json.dumps(response, ensure_ascii=False))
                except Exception as e:
                    self.logger.warning("Send failed to %s: %s", peer, e)
                    break

        except ConnectionClosedOK:
            self.logger.info("Client closed: %s", peer)
        except ConnectionClosedError as e:
            self.logger.warning("Connection error %s: %s", peer, e)
        except Exception as e:
            self.logger.exception("Unhandled error for %s: %s", peer, e)
        finally:
            try:
                websocket.close()
            except Exception:
                pass

    def _send_error(self, websocket, req_id, code: str, message: str):
        err = {"id": req_id, "ok": False, "error": {"code": code, "message": message}}
        try:
            websocket.send(json.dumps(err, ensure_ascii=False))
        except Exception:
            pass

    @staticmethod
    def _peer(websocket) -> str:
        try:
            host, port, *_ = websocket.remote_address or ("?", "?")
            return f"{host}:{port}"
        except Exception:
            return "unknown"


