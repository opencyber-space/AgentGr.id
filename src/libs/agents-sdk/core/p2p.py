# peers_manager.py
import os
import json
import asyncio
import uuid
import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

from nats.aio.client import Client as NATS
from nats.aio.msg import Msg

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

TaskHandler = Callable[[str, Dict[str, Any]], Dict[str, Any]] 
MeshMessageHandler = Callable[[str, Any], None]
EventHandler = Callable[[str, str, Dict[str, Any]], None]

@dataclass
class Mesh:
    mesh_id: str
    http_url: str
    nats_url: str
    nc: NATS = field(default_factory=NATS)
    sub_sid: Optional[int] = None
    sub_sid_executor: Optional[int] = None
    sub_sid_events: Optional[int] = None


class PeersManager:
    

    def __init__(
        self,
        *,
        mesh_subject: str = "mesh",
        loop: Optional[asyncio.AbstractEventLoop] = None,
        agent_data: Any = None,  
    ):

        if loop is None:
            self.loop = asyncio.new_event_loop()
            self._own_loop = True
        else:
            self.loop = loop
            self._own_loop = False

        self._loop_thread: Optional[threading.Thread] = None
        self._loop_started_evt = threading.Event()

        self.mesh_subject = mesh_subject
        self._meshes: Dict[str, Mesh] = {}
        self._handler: Optional[MeshMessageHandler] = None
        self._lock = asyncio.Lock()

        if agent_data is None:
            raise ValueError("agent_data is required and must have .to_dict()")
        self.subject: Dict[str, Any] = agent_data.to_dict()
        self.self_subject_id: str = os.getenv("SUBJECT_ID", "") or self.subject.get("subject_id", "")
        if not self.self_subject_id:
            logger.warning("SUBJECT_ID not set and not present in agent_data; presence messages may be ambiguous.")

        self.agents: Dict[str, Dict[str, Any]] = {}                 
        self._pending_tasks: Dict[str, asyncio.Future] = {}        


    def start_background_loop(self) -> None:
        if self.loop.is_running():
            return
        if self._loop_thread and self._loop_thread.is_alive():
            return

        def _runner():
            asyncio.set_event_loop(self.loop)
            self._loop_started_evt.set()
            self.loop.run_forever()

        self._loop_thread = threading.Thread(target=_runner, name="PeersManagerLoop", daemon=True)
        self._loop_thread.start()
        self._loop_started_evt.wait(timeout=5)

    def stop_background_loop(self) -> None:
        if self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
        if self._loop_thread:
            self._loop_thread.join(timeout=5)
            self._loop_thread = None

    def _ensure_loop_running(self) -> None:
        if not self.loop.is_running():
            self.start_background_loop()


    def set_message_handler(self, handler: MeshMessageHandler) -> None:
        self._handler = handler

    
    def register_event_handler(self, handler: Callable[[str, str, Dict[str, Any]], None]) -> None:
        self._event_handler = handler


    async def add_mesh(
        self,
        mesh_id: str,
        http_url: Optional[str] = None,
        nats_url: Optional[str] = None,
        **nats_connect_kwargs,
    ) -> None:

        subject_id = os.getenv("SUBJECT_ID")

        if not http_url or not nats_url:
            raise ValueError("For now, a mesh must be installed with (mesh_id, http_url, nats_url).")

        async with self._lock:
            if mesh_id in self._meshes:
                raise ValueError(f"Mesh '{mesh_id}' already exists")

            mesh = Mesh(mesh_id=mesh_id, http_url=http_url, nats_url=nats_url)
            logger.info(f"[{mesh_id}] Connecting to NATS: {nats_url}")

            await mesh.nc.connect(
                servers=[nats_url],
                name=f"{self.self_subject_id or 'agent'}::{mesh_id}",
                **nats_connect_kwargs,
            )

            sub_sid = await mesh.nc.subscribe(self.mesh_subject, cb=self._mk_on_msg(mesh_id))

            events_topic = f"{subject_id}__events"

            mesh.sub_sid_events = await mesh.nc.subscribe(events_topic, cb=self._mk_on_msg(mesh_id))

            mesh.sub_sid = sub_sid
            self._meshes[mesh_id] = mesh

            logger.info(f"[{mesh_id}] Listening on '{self.mesh_subject}' {events_topic}, HTTP URL saved: {http_url}")

        await self._announce_join(mesh_id)

    async def remove_mesh(self, mesh_id: str) -> None:
        async with self._lock:
            mesh = self._meshes.pop(mesh_id, None)
            if not mesh:
                return
            try:
                if mesh.sub_sid is not None:
                    await mesh.nc.unsubscribe(mesh.sub_sid)
            finally:
                await self._safe_close(mesh.nc)
                logger.info(f"[{mesh_id}] Disconnected")

    async def unregister(self, mesh_id: Optional[str] = None) -> None:
        targets: List[str] = [mesh_id] if mesh_id else list(self._meshes.keys())
        for mid in targets:
            await self._announce_remove(mid)

    async def close(self) -> None:
        async with self._lock:
            meshes = list(self._meshes.values())
            self._meshes.clear()
        await asyncio.gather(*(self._teardown_mesh(m) for m in meshes), return_exceptions=True)

    # ---- Blocking mesh management wrappers ----

    def add_mesh_sync(self, mesh_id: str, http_url: str, nats_url: str, **nats_connect_kwargs) -> None:
        self._ensure_loop_running()
        fut = asyncio.run_coroutine_threadsafe(
            self.add_mesh(mesh_id, http_url=http_url, nats_url=nats_url, **nats_connect_kwargs),
            self.loop,
        )
        fut.result()

    def remove_mesh_sync(self, mesh_id: str) -> None:
        self._ensure_loop_running()
        fut = asyncio.run_coroutine_threadsafe(self.remove_mesh(mesh_id), self.loop)
        fut.result()

    def unregister_sync(self, mesh_id: Optional[str] = None) -> None:
        self._ensure_loop_running()
        fut = asyncio.run_coroutine_threadsafe(self.unregister(mesh_id), self.loop)
        fut.result()

    def close_sync(self) -> None:
        self._ensure_loop_running()
        fut = asyncio.run_coroutine_threadsafe(self.close(), self.loop)
        fut.result()

    async def send(self, subject_id: str, task_data: Dict[str, Any]) -> None:
        topic = f"{subject_id}__executor"
        targets = self._target_mesh_ids_for_subject(subject_id)
        await asyncio.gather(*(self._publish_raw(mid, topic, task_data) for mid in targets))

    async def send_and_wait(
        self,
        task_id: str,
        subject_id: str,
        task_data: Dict[str, Any],
        timeout: Optional[float] = None,
        internal_task_id = None
    ) -> Dict[str, Any]:

        if not internal_task_id:
            internal_task_id = str(uuid.uuid4())

        # prepare packet:
        task_data = {
            "task_id": task_id,
            "task": task_data,
            "origin": {
                "internal_task_id": internal_task_id,
                "sender_subject_id": os.getenv("SUBJECT_ID"),
                "exchange_id": "x"
            }
        }

        if internal_task_id in self._pending_tasks:
            raise ValueError(f"internal_task_id '{internal_task_id}' is already pending")

        fut: asyncio.Future = self.loop.create_future()
        self._pending_tasks[internal_task_id] = fut
        try:
            await self.send(subject_id, task_data)
            return await asyncio.wait_for(fut, timeout=timeout) if timeout else await fut
        finally:
            self._pending_tasks.pop(internal_task_id, None)

    async def reply(
        self,
        task_id: str,
        to_subject_id: str,
        result_data: Dict[str, Any],
        *,
        status: str = "ok",
        mesh_ids: Optional[List[str]] = None,
    ) -> None:
        payload = {
            "event": "reply",
            "task_id": task_id,
            "subject_id": self.self_subject_id,
            "to_subject_id": to_subject_id,
            "status": status,
            "data": result_data,
        }

        logger.info(f"[P2P reply] sending payload {payload}")

        targets = list(mesh_ids) if mesh_ids else self._target_mesh_ids_for_subject(to_subject_id)
        await asyncio.gather(*(self._publish_raw(mid, to_subject_id, payload) for mid in targets))

    async def reply_error(
        self,
        task_id: str,
        to_subject_id: str,
        error_message: str,
        *,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        mesh_ids: Optional[List[str]] = None,
    ) -> None:
        err = {"message": error_message}
        if error_code:
            err["code"] = error_code
        if details:
            err["details"] = details
        await self.reply(task_id, to_subject_id, err, status="error", mesh_ids=mesh_ids)

    # ---- Blocking wrappers ----

    def send_sync(self, task_id: str, subject_id: str, task_data: Dict[str, Any], internal_task_id=None) -> None:

        if not internal_task_id:
            internal_task_id = str(uuid.uuid4())

        task_data = {
            "task_id": task_id,
            "task": task_data,
            "origin": {
                "internal_task_id": internal_task_id,
                "sender_subject_id": os.getenv("SUBJECT_ID")
            }
        }

        self._ensure_loop_running()
        fut = asyncio.run_coroutine_threadsafe(self.send(subject_id, task_data), self.loop)
        fut.result()

    def send_and_wait_sync(
        self,
        task_id: str,
        subject_id: str,
        task_data: Dict[str, Any],
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        self._ensure_loop_running()
        coro = self.send_and_wait(task_id, subject_id, task_data, timeout=timeout)
        fut = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return fut.result()

    def reply_sync(
        self,
        task_id: str,
        to_subject_id: str,
        result_data: Dict[str, Any],
        *,
        status: str = "ok",
        mesh_ids: Optional[List[str]] = None,
    ) -> None:
        self._ensure_loop_running()
        fut = asyncio.run_coroutine_threadsafe(
            self.reply(task_id, to_subject_id, result_data, status=status, mesh_ids=mesh_ids),
            self.loop,
        )
        fut.result()

    def reply_error_sync(
        self,
        task_id: str,
        to_subject_id: str,
        error_message: str,
        *,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        mesh_ids: Optional[List[str]] = None,
    ) -> None:
        self._ensure_loop_running()
        fut = asyncio.run_coroutine_threadsafe(
            self.reply_error(task_id, to_subject_id, error_message, error_code=error_code, details=details, mesh_ids=mesh_ids),
            self.loop,
        )
        fut.result()


    def _mk_on_msg(self, mesh_id: str):
        async def _on_msg(msg: Msg):
            payload = None
            try:
                payload = json.loads(msg.data.decode("utf-8"))
            except Exception:
                payload = None  # leave as None if not JSON

            # ---- Presence + Events ----
            if isinstance(payload, dict) and "event" in payload:
                evt = payload.get("event")

                # 1) Presence: join/remove
                if evt in ("join", "remove"):
                    sid = payload.get("subject_id")
                    if sid and sid != self.self_subject_id:
                        if evt == "join":
                            data = payload.get("peer") or {}
                            self._register_seen_agent(sid, data, mesh_id)
                        else:  # "remove"
                            self._unregister_seen_agent(sid, mesh_id)

                elif evt == "custom_event":
                    event_name = payload.get("event_name")
                    event_data = payload.get("event_data") or {}
                    if hasattr(self, "_event_handler") and self._event_handler:
                        try:
                            self._event_handler(mesh_id, event_name, event_data)
                        except Exception as e:
                            logger.exception(f"[{mesh_id}] event handler error: {e}")

            # ---- Task replies (resolve pending futures) ----
            if isinstance(payload, dict) and "event" in payload and payload["event"] == "reply":

                tid = payload.get("task_id")
                fut = self._pending_tasks.get(tid)
                if fut and not fut.done():
                    try:
                        fut.set_result(payload)
                    except Exception as e:
                        logger.exception(f"[{mesh_id}] failed to set task result for {tid}: {e}")

            # ---- User-provided async message handler (optional) ----
            if self._handler:
                try:
                    await self._handler(mesh_id, msg)
                except Exception as e:
                    logger.exception(f"[{mesh_id}] handler error: {e}")
            else:
                # Default logging if no handler
                if payload is not None:
                    logger.info(f"[{mesh_id}] {msg.subject}: {payload}")
                else:
                    logger.info(f"[{mesh_id}] {msg.subject}: {msg.data!r}")

        return _on_msg

    
    async def broadcast_event(
        self,
        event_name: str,
        event_data: Dict[str, Any],
        mesh_ids: Optional[List[str]] = None,
    ) -> None:
       
        payload = {
            "event": "custom_event",
            "event_name": event_name,
            "event_data": event_data,
            "subject_id": self.self_subject_id,
        }
        targets = mesh_ids or list(self._meshes.keys())
        await asyncio.gather(*(self._publish_raw(mid, self.mesh_subject, payload) for mid in targets))


    async def send_event(
        self,
        event_name: str,
        event_data: Dict[str, Any],
        subject_id: str,
        mesh_ids: Optional[List[str]] = None,
    ) -> None:
      
        topic = f"{subject_id}__events"
        payload = {
            "event": "custom_event",
            "event_name": event_name,
            "event_data": event_data,
            "from_subject_id": self.self_subject_id,
        }
        targets = mesh_ids or self._target_mesh_ids_for_subject(subject_id)
        await asyncio.gather(*(self._publish_raw(mid, topic, payload) for mid in targets))

    def broadcast_event_sync(
        self,
        event_name: str,
        event_data: Dict[str, Any],
        mesh_ids: Optional[List[str]] = None,
    ) -> None:
        
        self._ensure_loop_running()
        coro = self.broadcast_event(event_name, event_data, mesh_ids)
        fut = asyncio.run_coroutine_threadsafe(coro, self.loop)
        fut.result()


    def send_event_sync(
        self,
        event_name: str,
        event_data: Dict[str, Any],
        subject_id: str,
        mesh_ids: Optional[List[str]] = None,
    ) -> None:
        
        self._ensure_loop_running()
        coro = self.send_event(event_name, event_data, subject_id, mesh_ids)
        fut = asyncio.run_coroutine_threadsafe(coro, self.loop)
        fut.result()



    def _register_seen_agent(self, subject_id: str, data: Dict[str, Any], mesh_id: str) -> None:
        entry = self.agents.get(subject_id)
        if entry is None:
            self.agents[subject_id] = {"data": data, "mesh_ids": [mesh_id]}
            return
        entry["data"] = data or entry.get("data", {})
        if mesh_id not in entry["mesh_ids"]:
            entry["mesh_ids"].append(mesh_id)

    def _unregister_seen_agent(self, subject_id: str, mesh_id: str) -> None:
        entry = self.agents.get(subject_id)
        if not entry:
            return
        mesh_ids = entry.get("mesh_ids", [])
        if mesh_id in mesh_ids:
            mesh_ids.remove(mesh_id)
        if not mesh_ids:
            self.agents.pop(subject_id, None)


    def _target_mesh_ids_for_subject(self, subject_id: str) -> List[str]:
        entry = self.agents.get(subject_id)
        if entry and entry.get("mesh_ids"):
            return list(entry["mesh_ids"])
        return list(self._meshes.keys())

    async def _publish_raw(self, mesh_id: str, subject: str, obj: Dict[str, Any]) -> None:
        mesh = self._meshes.get(mesh_id)
        if not mesh:
            raise ValueError(f"Mesh '{mesh_id}' is not registered")
        data = json.dumps(obj).encode("utf-8")
        await mesh.nc.publish(subject, data)

    async def _announce_join(self, mesh_id: str) -> None:
        payload = {
            "event": "join",
            "peer": self.subject,
            "subject_id": self.self_subject_id,
        }
        await self._publish_raw(mesh_id, self.mesh_subject, payload)

    async def _announce_remove(self, mesh_id: str) -> None:
        payload = {
            "event": "remove",
            "subject_id": self.self_subject_id,
        }
        await self._publish_raw(mesh_id, self.mesh_subject, payload)


    async def _teardown_mesh(self, mesh: Mesh) -> None:
        try:
            if mesh.sub_sid is not None:
                await mesh.nc.unsubscribe(mesh.sub_sid)
        except Exception:
            pass
        await self._safe_close(mesh.nc)

    async def _safe_close(self, nc: NATS) -> None:
        try:
            if nc.is_connected:
                await nc.drain()
        except Exception:
            try:
                await nc.close()
            except Exception:
                pass

    # ---------------------------- Introspection ------------------------------

    def list_meshes(self) -> Dict[str, Dict[str, str]]:
        return {mid: {"http_url": m.http_url, "nats_url": m.nats_url} for mid, m in self._meshes.items()}

    def list_agents(self) -> Dict[str, Dict[str, Any]]:
        return self.agents

    # -------------- Mesh init functions -----------------------------------------
    async def initialize_meshes(self, meshes: Optional[List[Dict[str, str]]] = None) -> None:
        try:
            if meshes is None:
                env_val = os.getenv("MESH_LIST")
                if not env_val:
                    logging.warning("MESH_LIST not set; no meshes to initialize.")
                    return
                data = json.loads(env_val)
                meshes = data.get("meshes", [])
            if not isinstance(meshes, list):
                raise ValueError("initialize_meshes: 'meshes' must be a list of mesh definitions.")

            for mesh in meshes:
                mesh_id = mesh.get("mesh_id")
                url = mesh.get("url")
                if not mesh_id or not url:
                    logging.warning(f"Skipping invalid mesh entry: {mesh}")
                    continue
                # Use same URL for HTTP and NATS if only 'url' is provided
                http_url = url if url.startswith("http") else None
                nats_url = url if url.startswith("nats") else url
                await self.add_mesh(mesh_id, http_url=http_url or f"http://{mesh_id}", nats_url=nats_url)
            logging.info(f"Initialized {len(meshes)} mesh(es) from MESH_LIST.")
        except Exception as e:
            logging.exception(f"Failed to initialize meshes: {e}")
    
    def initialize_meshes_sync(self, meshes: Optional[List[Dict[str, str]]] = None) -> None:
        self._ensure_loop_running()
        fut = asyncio.run_coroutine_threadsafe(self.initialize_meshes(meshes), self.loop)
        fut.result()



def init_p2p_manager(
    *,
    agent_data: Any,
    mesh_subject: str = "mesh",
    meshes: Optional[List[Dict[str, str]]] = None,
    message_handler: Optional[MeshMessageHandler] = None,
    event_handler: Optional[EventHandler] = None,
    use_env_mesh_list: bool = True,
) -> "PeersManager":
   
    pm = PeersManager(mesh_subject=mesh_subject, agent_data=agent_data)

    if message_handler is not None:
        pm.set_message_handler(message_handler)
    if event_handler is not None:
        pm.register_event_handler(event_handler)

    # Start the background asyncio loop (listeners live here)
    pm.start_background_loop()

    if meshes is not None:
        fut = asyncio.run_coroutine_threadsafe(pm.initialize_meshes(meshes), pm.loop)
        fut.result()
    elif use_env_mesh_list:
        fut = asyncio.run_coroutine_threadsafe(pm.initialize_meshes(), pm.loop)
        fut.result()

    logging.info("[P2P] PeersManager initialized; NATS listeners active.")
    return pm


def shutdown_p2p_manager(pm: "PeersManager") -> None:
   
    try:
        pm.close_sync()           
    finally:
        pm.stop_background_loop()  
    logging.info("[P2P] PeersManager shut down cleanly.")
