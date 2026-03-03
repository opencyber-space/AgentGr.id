import os
import re
import time
import logging
from typing import Optional, Dict, Any

from kubernetes import client, config
from kubernetes.client import ApiException


class WorkflowExecutorManager:
    NAMESPACE = "workflows"

    def __init__(
        self,
        *,
        delegate_api_url: str,
        policy_db_url: str,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        if not self.logger.handlers:
            logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())

        config.load_incluster_config()

        self.core = client.CoreV1Api()
        self.apps = client.AppsV1Api()

        self.executor_image: Optional[str] = os.getenv("WORKFLOW_EXECUTOR_IMAGE_NAME")
        self.subject_db_url: Optional[str] = os.getenv("SUBJECT_DB_URL")

        self.delegate_api_url: str = delegate_api_url
        self.policy_db_url: str = policy_db_url

        missing = [
            name
            for name, val in {
                "WORKFLOW_EXECUTOR_IMAGE_NAME": self.executor_image,
                "SUBJECT_DB_URL": self.subject_db_url,
                "DELEGATE_API_URL": self.delegate_api_url,
                "POLICY_DB_URL": self.policy_db_url,
            }.items()
            if not val
        ]

        if missing:
            raise RuntimeError(
                f"Missing required configuration values: {', '.join(missing)}"
            )

        self._ensure_namespace()

    # ==========================================================
    # CREATE EXECUTOR
    # ==========================================================
    def create_executor(
        self,
        *,
        workflow_id: str,
        deployment_name: str,
        replicas: int = 1,
    ) -> Dict[str, Any]:

        name: str = self._sanitize_name(deployment_name)
        service_name: str = f"{name}-svc"

        labels = {
            "app": "workflow-executor",
            "workflow-id": workflow_id,
            "deployment-name": name,
        }

        container = client.V1Container(
            name="workflow-executor",
            image=self.executor_image,
            image_pull_policy="Always",
            env=[
                client.V1EnvVar(name="WORKFLOW_ID", value=workflow_id),
                client.V1EnvVar(name="DELEGATE_API_URL", value=self.delegate_api_url),
                client.V1EnvVar(name="POLICY_DB_URL", value=self.policy_db_url),
                client.V1EnvVar(name="SUBJECT_DB_URL", value=self.subject_db_url),
            ],
            ports=[
                client.V1ContainerPort(
                    container_port=9100,
                    name="workflow-http",
                )
            ],
        )

        pod_spec = client.V1PodSpec(
            containers=[container],
            restart_policy="Always",
        )

        pod_template = client.V1PodTemplateSpec(
            metadata=client.V1ObjectMeta(labels=labels),
            spec=pod_spec,
        )

        deployment_spec = client.V1DeploymentSpec(
            replicas=replicas,
            selector=client.V1LabelSelector(match_labels=labels),
            template=pod_template,
        )

        deployment = client.V1Deployment(
            api_version="apps/v1",
            kind="Deployment",
            metadata=client.V1ObjectMeta(name=name, labels=labels),
            spec=deployment_spec,
        )

        # Create or replace deployment
        try:
            self.apps.read_namespaced_deployment(name=name, namespace=self.NAMESPACE)
            self.logger.info(f"Deployment '{name}' exists; replacing...")
            self.apps.replace_namespaced_deployment(
                name=name,
                namespace=self.NAMESPACE,
                body=deployment,
            )
        except ApiException as e:
            if e.status == 404:
                self.logger.info(f"Creating Deployment '{name}'...")
                self.apps.create_namespaced_deployment(
                    namespace=self.NAMESPACE,
                    body=deployment,
                )
            else:
                raise

        # ============================
        # SERVICE
        # ============================
        existing_nodeport = self._get_existing_nodeport(service_name)

        service = client.V1Service(
            api_version="v1",
            kind="Service",
            metadata=client.V1ObjectMeta(
                name=service_name,
                labels=labels,
            ),
            spec=client.V1ServiceSpec(
                selector=labels,
                type="NodePort",
                ports=[
                    client.V1ServicePort(
                        name="workflow-port",
                        port=9100,
                        target_port=9100,
                        node_port=existing_nodeport,
                    )
                ],
            ),
        )

        try:
            self.core.read_namespaced_service(
                name=service_name,
                namespace=self.NAMESPACE,
            )
            self.logger.info(f"Service '{service_name}' exists; replacing...")
            self.core.replace_namespaced_service(
                name=service_name,
                namespace=self.NAMESPACE,
                body=service,
            )
        except ApiException as e:
            if e.status == 404:
                self.logger.info(f"Creating Service '{service_name}'...")
                self.core.create_namespaced_service(
                    namespace=self.NAMESPACE,
                    body=service,
                )
            else:
                raise

        service_obj = self._wait_for_nodeport(service_name)

        return {
            "deployment_name": name,
            "service_name": service_name,
            "cluster_ip": service_obj.spec.cluster_ip,
            "port": 9100,
            "node_port": service_obj.spec.ports[0].node_port,
            "replicas": replicas,
        }

    # ==========================================================
    # REMOVE EXECUTOR
    # ==========================================================
    def remove_executor(
        self,
        *,
        deployment_name: str,
    ) -> bool:

        name: str = self._sanitize_name(deployment_name)
        service_name: str = f"{name}-svc"

        try:
            self.apps.delete_namespaced_deployment(
                name=name,
                namespace=self.NAMESPACE,
                body=client.V1DeleteOptions(
                    propagation_policy="Foreground",
                    grace_period_seconds=0,
                ),
            )
        except ApiException as e:
            if e.status != 404:
                raise

        try:
            self.core.delete_namespaced_service(
                name=service_name,
                namespace=self.NAMESPACE,
            )
        except ApiException as e:
            if e.status != 404:
                raise

        self.logger.info(f"Deployment '{name}' and Service '{service_name}' removed.")
        return True

    # ==========================================================
    # HELPERS
    # ==========================================================
    def _get_existing_nodeport(self, service_name: str) -> Optional[int]:
        try:
            svc = self.core.read_namespaced_service(
                name=service_name,
                namespace=self.NAMESPACE,
            )
            if svc.spec and svc.spec.ports:
                return svc.spec.ports[0].node_port
        except ApiException as e:
            if e.status != 404:
                raise
        return None

    def _wait_for_nodeport(
        self,
        service_name: str,
        timeout_s: int = 30,
        interval_s: float = 0.5,
    ) -> client.V1Service:

        deadline = time.time() + timeout_s
        while time.time() < deadline:
            svc = self.core.read_namespaced_service(
                service_name,
                self.NAMESPACE,
            )
            if svc.spec and svc.spec.ports and svc.spec.ports[0].node_port:
                return svc
            time.sleep(interval_s)

        return self.core.read_namespaced_service(
            service_name,
            self.NAMESPACE,
        )

    def _ensure_namespace(self) -> None:
        try:
            self.core.read_namespace(self.NAMESPACE)
        except ApiException as e:
            if e.status == 404:
                ns = client.V1Namespace(
                    metadata=client.V1ObjectMeta(
                        name=self.NAMESPACE,
                        labels={"managed-by": "workflow-executor-manager"},
                    )
                )
                self.core.create_namespace(ns)
            else:
                raise

    @staticmethod
    def _sanitize_name(name: str) -> str:
        sanitized = re.sub(r"[^a-z0-9\-]+", "-", name.lower())
        sanitized = re.sub(r"-+", "-", sanitized).strip("-")
        if not sanitized:
            sanitized = "workflow"
        return sanitized[:63].rstrip("-")