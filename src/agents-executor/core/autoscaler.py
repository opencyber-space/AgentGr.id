from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List, Optional

from .policy_base import PoliciesManager
from .lb import LoadBalancer
from .deployer_client import DeployerClient


logger = logging.getLogger(__name__)


class AutoScaler:
    NAME = "autoscaler"

    def __init__(
        self,
        policies: "PoliciesManager",
        lb: "LoadBalancer",
        deployer: "DeployerClient",
        subject_id: str,
        *,
        meshes: Optional[Dict[str, Any]] = None,
        delegate_api_url: str = "",
        interval_sec: int = 30,
        thread_name: str = "AutoScalerThread",
    ) -> None:
        self.policies = policies
        self.lb = lb
        self.deployer = deployer
        self.subject_id = subject_id
        self.meshes = meshes or {}
        self.delegate_api_url = delegate_api_url
        self.interval_sec = interval_sec

        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._thread_name = thread_name

        def _get_instances() -> List[str]:
            with lb._lock:
                return list(lb.current_instances)

        def _get_queue_depth() -> int:
            return lb._in_q.qsize()

        self.policies.add_policy(
            self.NAME,
            injects={
                "get_instances": _get_instances,
                "get_queue_depth": _get_queue_depth,
            },
        )

    # ------------------------------------------------------------------ #
    # Lifecycle                                                            #
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name=self._thread_name, daemon=True
        )
        self._thread.start()
        logger.info("[AutoScaler] started (interval=%ds subject=%s)", self.interval_sec, self.subject_id)

    def stop(self, timeout: Optional[float] = 5.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)
            self._thread = None

    # ------------------------------------------------------------------ #
    # Background loop                                                      #
    # ------------------------------------------------------------------ #

    def _run(self) -> None:
        while not self._stop.wait(self.interval_sec):
            try:
                self._tick()
            except Exception:
                logger.exception("[AutoScaler] unhandled error in tick")

    def _tick(self) -> None:
        with self.lb._lock:
            instances: List[str] = list(self.lb.current_instances)

        state: Dict[str, Any] = {
            "instance_count": len(instances),
            "instance_ids": instances,
            "queue_depth": self.lb._in_q.qsize(),
            "subject_id": self.subject_id,
        }

        logger.debug("[AutoScaler] tick state=%s", state)

        decision = self._evaluate(state)

        if decision == "scale_up":
            self._scale_up()
        elif decision == "scale_down":
            self._scale_down(instances)
        else:
            logger.debug("[AutoScaler] no action (decision=%r)", decision)

    def _evaluate(self, state: Dict[str, Any]) -> Optional[str]:
        try:
            result = self.policies.execute(self.NAME, state, self._default_policy)
            if isinstance(result, dict):
                return result.get("action")
            if isinstance(result, str):
                return result
            return None
        except KeyError:
            return self._default_policy(state)
        except Exception:
            logger.exception("[AutoScaler] policy evaluation error")
            return None

    @staticmethod
    def _default_policy(state: Dict[str, Any]) -> Optional[str]:
        """Fallback: no action when no policy is configured."""
        return None

    # ------------------------------------------------------------------ #
    # Scale actions                                                        #
    # ------------------------------------------------------------------ #

    def _scale_up(self) -> None:
        logger.info("[AutoScaler] scale_up subject=%s", self.subject_id)
        try:
            results = self.deployer.create_instances(
                self.subject_id,
                count=1,
                meshes=self.meshes,
                delegate_api_url=self.delegate_api_url,
            )
            logger.info("[AutoScaler] scale_up result=%s", results)
        except Exception:
            logger.exception("[AutoScaler] scale_up failed")

    def _scale_down(self, instances: List[str]) -> None:
        if not instances:
            logger.info("[AutoScaler] scale_down requested but no instances to remove")
            return
        # Remove the last known instance to minimise in-flight disruption
        target = instances[-1]
        logger.info("[AutoScaler] scale_down subject=%s instance=%s", self.subject_id, target)
        try:
            results = self.deployer.remove_instances(self.subject_id, [target])
            logger.info("[AutoScaler] scale_down result=%s", results)
        except Exception:
            logger.exception("[AutoScaler] scale_down failed")
