# peers_manager.py
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Dict, Optional

from nats.aio.client import Client as NATS
from nats.aio.msg import Msg

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

MeshMessageHandler = Callable[[str, Msg], Awaitable[None]]
# signature: async handler(mesh_id: str, msg: Msg) -> None


@dataclass
class Mesh:
    mesh_id: str
    http_url: str
    nats_url: str
    nc: NATS = field(default_factory=NATS)
    sub_sid: Optional[int] = None


class PeersManager:
  

    def __init__(self, *, mesh_subject: str = "mesh", loop: Optional[asyncio.AbstractEventLoop] = None, agent_data):
        self.mesh_subject = mesh_subject
        self.loop = loop or asyncio.get_event_loop()
        self._meshes: Dict[str, Mesh] = {}
        self._handler: Optional[MeshMessageHandler] = None
        self._lock = asyncio.Lock()

    # ---- Public API ---------------------------------------------------------

    def set_message_handler(self, handler: MeshMessageHandler) -> None:
        """Register an async callback for every message from any mesh."""
        self._handler = handler

    async def add_mesh(
        self,
        mesh_id: str,
        http_url: Optional[str] = None,
        nats_url: Optional[str] = None,
        **nats_connect_kwargs,
    ) -> None:
        """
        Add a mesh by (mesh_id, http_url, nats_url).
        For now, if only mesh_id is given, raise (per spec).
        Creates a dedicated NATS connection and subscribes to self.mesh_subject.
        """
        if not http_url or not nats_url:
            raise ValueError("For now, a mesh must be installed with (mesh_id, http_url, nats_url).")

        async with self._lock:
            if mesh_id in self._meshes:
                raise ValueError(f"Mesh '{mesh_id}' already exists")

            mesh = Mesh(mesh_id=mesh_id, http_url=http_url, nats_url=nats_url)
            logger.info(f"[{mesh_id}] Connecting to NATS: {nats_url}")

            await mesh.nc.connect(
                servers=[nats_url],
                # You can pass auth/reconnect options via **nats_connect_kwargs
                **nats_connect_kwargs,
            )

            async def _on_msg(msg: Msg):
                # Route to user handler if present
                if self._handler:
                    try:
                        await self._handler(mesh_id, msg)
                    except Exception as e:
                        logger.exception(f"[{mesh_id}] handler error: {e}")
                else:
                    logger.info(f"[{mesh_id}] {msg.subject}: {msg.data!r}")

            sub_sid = await mesh.nc.subscribe(self.mesh_subject, cb=_on_msg)
            mesh.sub_sid = sub_sid
            self._meshes[mesh_id] = mesh

            logger.info(f"[{mesh_id}] Listening on '{self.mesh_subject}', HTTP URL saved: {http_url}")

    async def remove_mesh(self, mesh_id: str) -> None:
        """Unsubscribe and close the mesh's NATS connection."""
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

    async def close(self) -> None:
        """Close all mesh connections."""
        async with self._lock:
            meshes = list(self._meshes.values())
            self._meshes.clear()
        await asyncio.gather(*(self._teardown_mesh(m) for m in meshes), return_exceptions=True)

    # ---- Helpers ------------------------------------------------------------

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


    def list_meshes(self) -> Dict[str, Dict[str, str]]:
        return {mid: {"http_url": m.http_url, "nats_url": m.nats_url} for mid, m in self._meshes.items()}
