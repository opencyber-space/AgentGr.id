import os
import re
import time
import logging
from typing import Optional, Dict, Any
import json

from kubernetes import client, config
from kubernetes.client import ApiException


class AgentsExecutorManager:
    NAMESPACE = "agents"

    def __init__(self, *, logger: Optional[logging.Logger] = None) -> None:
        # Logging
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        if not self.logger.handlers:
            logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())

        # In-cluster config
        config.load_incluster_config()

        # K8s clients
        self.core = client.CoreV1Api()
        self.apps = client.AppsV1Api()

        # Required envs
        self.executor_image = os.getenv("EXECUTOR_IMAGE_NAME")
        self.subject_db_url = os.getenv("SUBJECT_DB_URL")
        self.policy_db_url = os.getenv("POLICY_DB_URL")

        # New envs / images
        self.scouter_image = os.getenv("JOB_SCOUTER_IMAGE_NAME")
        self.exchange_api_url = os.getenv("JOB_EXCHANGE_API_URL")
        # SUBJECTS_DB_URL should be same as SUBJECT_DB_URL, but allow explicit override
        self.subjects_db_url = os.getenv(
            "SUBJECT_DB_URL", self.subject_db_url)

        # Optional: allow overriding redis image; default to a stable tag
        self.redis_image = os.getenv("REDIS_IMAGE_NAME", "redis:7-alpine")

        missing = [name for name, val in {
            "EXECUTOR_IMAGE_NAME": self.executor_image,
            "SUBJECT_DB_URL": self.subject_db_url,
            "POLICY_DB_URL": self.policy_db_url,
            "JOB_SCOUTER_IMAGE_NAME": self.scouter_image,
            "JOB_EXCHANGE_API_URL": self.exchange_api_url,
        }.items() if not val]
        if missing:
            raise RuntimeError(
                f"Missing required environment variables: {', '.join(missing)}")

        # Ensure namespace
        self._ensure_namespace()

    def create_executor(self, subject_id: str, meshes=[]) -> Dict[str, Any]:
        name = self._name_for_subject(subject_id)
        labels = {
            "app": "executor",
            "component": "subject-executor",
            "subject-id": subject_id,
        }

        logging.info(f"[Meshes] {meshes}")

        # --- Container: executor (existing) ---
        executor_container = client.V1Container(
            name="executor",
            image=self.executor_image,
            image_pull_policy="Always",
            env=[
                client.V1EnvVar(name="SUBJECT_ID", value=subject_id),
                client.V1EnvVar(name="SUBJECT_DB_URL",
                                value=self.subject_db_url),
                client.V1EnvVar(name="POLICY_DB_URL",
                                value=self.policy_db_url),
                client.V1EnvVar(name="MESH_LIST", value=json.dumps({"meshes": meshes}))
            ],
            ports=[client.V1ContainerPort(
                container_port=9000, name="executor-http")],
        )

        # --- Container: redis ---
        redis_container = client.V1Container(
            name="redis",
            image=self.redis_image,
            image_pull_policy="Always",
            ports=[client.V1ContainerPort(container_port=6379, name="redis")],
        )

        # --- Container: scouter ---
        scouter_env = [
            client.V1EnvVar(name="SUBJECT_ID", value=subject_id),
            client.V1EnvVar(name="POLICY_DB_URL", value=self.policy_db_url),
            client.V1EnvVar(name="SUBJECT_DB_URL",
                            value=self.subjects_db_url),
            client.V1EnvVar(name="JOB_EXCHANGE_API_URL",
                            value=self.exchange_api_url),
        ]
        scouter_container = client.V1Container(
            name="scouter",
            image=self.scouter_image,
            image_pull_policy="Always",
            env=scouter_env,
            ports=[client.V1ContainerPort(
                container_port=10000, name="scouter-http")],
        )

        pod_spec = client.V1PodSpec(
            containers=[executor_container,
                        redis_container, scouter_container],
            restart_policy="Always",
        )

        pod_template = client.V1PodTemplateSpec(
            metadata=client.V1ObjectMeta(labels=labels),
            spec=pod_spec,
        )

        dep_spec = client.V1DeploymentSpec(
            replicas=1,
            selector=client.V1LabelSelector(match_labels=labels),
            template=pod_template,
        )

        deployment = client.V1Deployment(
            api_version="apps/v1",
            kind="Deployment",
            metadata=client.V1ObjectMeta(name=name, labels=labels),
            spec=dep_spec,
        )

        # Create or replace deployment
        try:
            self.apps.read_namespaced_deployment(
                name=name, namespace=self.NAMESPACE)
            self.logger.info(f"Deployment '{name}' exists; replacing...")
            self.apps.replace_namespaced_deployment(
                name=name, namespace=self.NAMESPACE, body=deployment
            )
        except ApiException as e:
            if e.status == 404:
                self.logger.info(f"Creating Deployment '{name}'...")
                self.apps.create_namespaced_deployment(
                    namespace=self.NAMESPACE, body=deployment
                )
            else:
                raise

        # --- Build Services (NodePort; nodePort left None so K8s assigns) ---
        exec_svc_name = f"{name}-executor-svc"
        scout_svc_name = f"{name}-scouter-svc"

        # If services exist, preserve current nodePort to avoid immutable-field issues
        existing_exec_nodeport = self._get_existing_nodeport(exec_svc_name)
        existing_scout_nodeport = self._get_existing_nodeport(scout_svc_name)

        executor_service = client.V1Service(
            api_version="v1",
            kind="Service",
            metadata=client.V1ObjectMeta(
                name=exec_svc_name,
                labels={"app": "executor", "subject-id": subject_id},
            ),
            spec=client.V1ServiceSpec(
                selector={
                    "app": "executor", "component": "subject-executor", "subject-id": subject_id},
                type="NodePort",
                ports=[
                    client.V1ServicePort(
                        name="executor-port",
                        port=9000,
                        target_port=9000,
                        node_port=existing_exec_nodeport,  # keep old if present, else let K8s assign
                    )
                ],
            ),
        )

        scouter_service = client.V1Service(
            api_version="v1",
            kind="Service",
            metadata=client.V1ObjectMeta(
                name=scout_svc_name,
                labels={"app": "executor", "subject-id": subject_id},
            ),
            spec=client.V1ServiceSpec(
                selector={
                    "app": "executor", "component": "subject-executor", "subject-id": subject_id},
                type="NodePort",
                ports=[
                    client.V1ServicePort(
                        name="scouter-port",
                        port=10000,
                        target_port=10000,
                        node_port=existing_scout_nodeport,  # keep old if present, else let K8s assign
                    )
                ],
            ),
        )

        # Create or replace services
        for svc in [executor_service, scouter_service]:
            try:
                self.core.read_namespaced_service(
                    name=svc.metadata.name, namespace=self.NAMESPACE
                )
                self.logger.info(
                    f"Service '{svc.metadata.name}' exists; replacing...")
                self.core.replace_namespaced_service(
                    name=svc.metadata.name, namespace=self.NAMESPACE, body=svc
                )
            except ApiException as e:
                if e.status == 404:
                    self.logger.info(
                        f"Creating Service '{svc.metadata.name}'...")
                    self.core.create_namespaced_service(
                        namespace=self.NAMESPACE, body=svc
                    )
                else:
                    raise

        # Wait briefly for nodePorts to be allocated (especially on first create)
        exec_svc, scout_svc = self._wait_for_nodeports(
            exec_svc_name, scout_svc_name)

        self.logger.info(
            f"Executor + Scouter ready with services in namespace '{self.NAMESPACE}'"
        )

        # === RETURN the NodePorts (and some helpful extras) ===
        return {
            "name": name,
            "executor": {
                "service_name": exec_svc.metadata.name,
                "cluster_ip": exec_svc.spec.cluster_ip,
                "port": 9000,
                "node_port": exec_svc.spec.ports[0].node_port,
            },
            "scouter": {
                "service_name": scout_svc.metadata.name,
                "cluster_ip": scout_svc.spec.cluster_ip,
                "port": 10000,
                "node_port": scout_svc.spec.ports[0].node_port,
            },
        }

    def remove_executor(self, subject_id: str) -> bool:
        name = self._name_for_subject(subject_id)
        try:
            self.apps.delete_namespaced_deployment(
                name=name,
                namespace=self.NAMESPACE,
                body=client.V1DeleteOptions(
                    propagation_policy="Foreground",
                    grace_period_seconds=0
                ),
            )
            self.logger.info(f"Delete requested for Deployment '{name}'.")
            return True
        except ApiException as e:
            if e.status == 404:
                self.logger.info(
                    f"Deployment '{name}' not found; nothing to delete.")
                return True
            self.logger.error(f"Failed to delete Deployment '{name}': {e}")
            return False

    def _get_existing_nodeport(self, svc_name: str) -> Optional[int]:
        """Return existing NodePort if service exists, else None."""
        try:
            svc = self.core.read_namespaced_service(
                name=svc_name, namespace=self.NAMESPACE)
            if svc and svc.spec and svc.spec.ports:
                return svc.spec.ports[0].node_port
        except ApiException as e:
            if e.status != 404:
                raise
        return None

    def _wait_for_nodeports(self, exec_svc_name: str, scout_svc_name: str, timeout_s: int = 30, interval_s: float = 0.5):
        """Poll until both services have nodePort assigned (or timeout)."""
        deadline = time.time() + timeout_s
        exec_svc = scout_svc = None
        while time.time() < deadline:
            exec_svc = self.core.read_namespaced_service(
                exec_svc_name, self.NAMESPACE)
            scout_svc = self.core.read_namespaced_service(
                scout_svc_name, self.NAMESPACE)

            exec_has = bool(
                exec_svc.spec and exec_svc.spec.ports and exec_svc.spec.ports[0].node_port)
            scout_has = bool(
                scout_svc.spec and scout_svc.spec.ports and scout_svc.spec.ports[0].node_port)
            if exec_has and scout_has:
                return exec_svc, scout_svc
            time.sleep(interval_s)

        # Return whatever we have; caller will see None if allocation didn’t happen in time
        return exec_svc, scout_svc

    def _ensure_namespace(self) -> None:
        try:
            self.core.read_namespace(self.NAMESPACE)
            self.logger.debug(f"Namespace '{self.NAMESPACE}' already exists.")
        except ApiException as e:
            if e.status == 404:
                self.logger.info(f"Creating namespace '{self.NAMESPACE}'...")
                ns = client.V1Namespace(
                    metadata=client.V1ObjectMeta(
                        name=self.NAMESPACE,
                        labels={"managed-by": "agents-executor-manager"}
                    )
                )
                self.core.create_namespace(ns)
            else:
                raise

    @staticmethod
    def _name_for_subject(subject_id: str) -> str:
        # Lowercase, replace invalid, trim 63 chars, no leading/trailing '-'
        name = re.sub(r'[^a-z0-9\-]+', '-', subject_id.lower())
        name = re.sub(r'-+', '-', name).strip('-')
        if not name:
            name = "subject"
        base = f"executor-{name}"
        return (base[:63]).rstrip('-')
    

    def delete_resources_by_subject_label(self, subject_id: str) -> dict:
    
        label_selector = f"subjectId={subject_id}"
        deleted = {"deployments": [], "services": []}

        try:
            deps = self.apps.list_namespaced_deployment(
                namespace=self.NAMESPACE, label_selector=label_selector
            )
            for dep in deps.items:
                name = dep.metadata.name
                self.logger.info(f"Deleting Deployment '{name}' (subject-id={subject_id})")
                try:
                    self.apps.delete_namespaced_deployment(
                        name=name,
                        namespace=self.NAMESPACE,
                        body=client.V1DeleteOptions(
                            propagation_policy="Foreground",
                            grace_period_seconds=0,
                        ),
                    )
                    deleted["deployments"].append(name)
                except ApiException as e:
                    if e.status == 404:
                        self.logger.info(f"Deployment '{name}' already gone.")
                    else:
                        self.logger.error(f"Failed deleting Deployment '{name}': {e}")

        except ApiException as e:
            self.logger.error(f"Failed to list Deployments for subject-id={subject_id}: {e}")

        # --- Delete Services ---
        try:
            svcs = self.core.list_namespaced_service(
                namespace=self.NAMESPACE, label_selector=label_selector
            )
            for svc in svcs.items:
                name = svc.metadata.name
                self.logger.info(f"Deleting Service '{name}' (subject-id={subject_id})")
                try:
                    self.core.delete_namespaced_service(
                        name=name,
                        namespace=self.NAMESPACE,
                    )
                    deleted["services"].append(name)
                except ApiException as e:
                    if e.status == 404:
                        self.logger.info(f"Service '{name}' already gone.")
                    else:
                        self.logger.error(f"Failed deleting Service '{name}': {e}")

        except ApiException as e:
            self.logger.error(f"Failed to list Services for subject-id={subject_id}: {e}")

        self.logger.info(
            f"Deleted (requested) resources for subject-id={subject_id} in ns={self.NAMESPACE} -> "
            f"deployments={deleted['deployments']}, services={deleted['services']}"
        )
        return deleted
