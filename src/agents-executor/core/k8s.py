from __future__ import annotations

import json, yaml
import logging
import threading
import time
from typing import Callable, Dict, List, Optional

from kubernetes import client, config


def _safe_load_kube_config():
    try:
        config.load_incluster_config()
    except Exception:
        config.load_kube_config_from_dict(yaml.safe_load(open('/home/cognitifai/configs/cluster-5-patch.yaml')))
        current_config = client.Configuration.get_default_copy()
        current_config.verify_ssl = False
        # Set the modified configuration as default
        client.Configuration.set_default(current_config)


def _pods_to_ids(pods: List[client.V1Pod]) -> List[str]:
    return [pod.metadata.labels.get("instanceId") for pod in pods if pod and pod.metadata and pod.metadata.labels]


class AgentsUpdateNotifier:
  

    def __init__(
        self,
        on_instances_update: Callable[[List[str]], None],
        *,
        namespace: str = "agents",
        poll_interval_sec: int = 20,
        refresh_every_n_cycles: int = 1,
        thread_name: str = "AgentsUpdateNotifier",
        logger: Optional[logging.Logger] = None,
    ) -> None:
        
        _safe_load_kube_config()
        self.v1 = client.CoreV1Api()

        self.on_instances_update = on_instances_update
        self.namespace = namespace
        self.poll_interval_sec = poll_interval_sec
        self.refresh_every_n_cycles = max(1, int(refresh_every_n_cycles))

        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._thread_name = thread_name
        self._logger = logger or logging.getLogger(__name__)

        self._current_pods: List[client.V1Pod] = []
        self._cycle_counter = 0

    # ---------- public API ----------

    def start(self, block_id: str) -> None:
        """
        Start the background watcher for the given block_id (label subjectId=<block_id>).
        """
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, args=(block_id,), name=self._thread_name, daemon=True
        )
        self._thread.start()

    def stop(self, timeout: Optional[float] = 5.0) -> None:
        """
        Stop the background watcher.
        """
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)
            self._thread = None

    # ---------- internals ----------

    def _list_pods(self, block_id: str) -> List[client.V1Pod]:
        try:
            label_selector = f"subjectId={block_id}"
            pods = self.v1.list_namespaced_pod(self.namespace, label_selector=label_selector)
            return pods.items or []
        except client.exceptions.ApiException as e:
            self._logger.error(f"CoreV1Api->list_namespaced_pod error: {e}")
            return []
        except Exception as e:
            self._logger.exception(f"Unexpected error listing pods: {e}")
            return []

    def _pods_changed(self, old: List[client.V1Pod], new: List[client.V1Pod]) -> bool:
        # Compare by instanceID multiset to detect adds/removes
        old_ids = sorted(_pods_to_ids(old))
        new_ids = sorted(_pods_to_ids(new))
        return old_ids != new_ids

    def _emit_update(self, pods: List[client.V1Pod]) -> None:
        ids = _pods_to_ids(pods)
        # Call the provided callback with *only* the instances list (what the LB expects)
        try:
            self.on_instances_update(ids)
        except Exception:
            # Never crash the watcher on callback failures
            self._logger.exception("on_instances_update callback raised an exception")

    def _run(self, block_id: str) -> None:
        self._logger.info(
            f"[AgentsUpdateNotifier] Watching namespace='{self.namespace}', subjectId='{block_id}'"
        )
        while not self._stop.is_set():
            self._cycle_counter += 1
            new_pods = self._list_pods(block_id)

            changed = self._pods_changed(self._current_pods, new_pods)
            periodic_refresh = (self._cycle_counter % self.refresh_every_n_cycles == 0)

            if changed:
                self._logger.info(
                    "Agents instances changed: old=%d new=%d",
                    len(self._current_pods), len(new_pods)
                )
                self._emit_update(new_pods)
                self._current_pods = new_pods
                self._cycle_counter = 0  # reset after a change
            elif periodic_refresh:
                self._logger.info(
                    "Agents instances periodic refresh: count=%d",
                    len(new_pods)
                )
                self._emit_update(new_pods)
                self._current_pods = new_pods
                self._cycle_counter = 0

            self._stop.wait(self.poll_interval_sec)
