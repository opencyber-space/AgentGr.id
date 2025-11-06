import os
import re
import logging
from typing import Optional, Dict

from kubernetes import client, config
from kubernetes.client import ApiException, ApiClient


class AgentsDeployerInstaller:
  

    NAMESPACE = "agent-deployer"
    NAME = "agents-deployer"
    NODE_PORT = 30777
    CONTAINER_PORT = 9000

    def __init__(self, kubeconfig: Dict, *, logger: Optional[logging.Logger] = None) -> None:
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        if not self.logger.handlers:
            logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())

        try:
            self.api_client: ApiClient = config.new_client_from_config_dict(kubeconfig)
        except Exception:
            config.load_kube_config_from_dict(kubeconfig)
            self.api_client = ApiClient()

        self.core = client.CoreV1Api(self.api_client)
        self.apps = client.AppsV1Api(self.api_client)

        # Resolve required envs
        self.image = os.getenv("AGENT_DEPLOYER_IMAGE_NAME")
        self.env_EXECUTOR_IMAGE_NAME = os.getenv("EXECUTOR_IMAGE_NAME")
        self.env_SUBJECT_DB_URL = os.getenv("SUBJECT_DB_URL")
        self.env_POLICY_DB_URL = os.getenv("POLICY_DB_URL")
        self.env_SCOUTER_IMAGE_NAME = os.getenv("JOB_SCOUTER_IMAGE_NAME")
        self.env_JOB_EXCHANGE_API_URL = os.getenv("JOB_EXCHANGE_API_URL")
        self.env_AGENT_DEPLOYER_IMAGE = os.getenv("AGENT_CORE_IMAGE")

        missing = [k for k, v in {
            "AGENT_DEPLOYER_IMAGE_NAME": self.image,
            "EXECUTOR_IMAGE_NAME": self.env_EXECUTOR_IMAGE_NAME,
            "SUBJECT_DB_URL": self.env_SUBJECT_DB_URL,
            "POLICY_DB_URL": self.env_POLICY_DB_URL,
        }.items() if not v]
        if missing:
            raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

        self._ensure_namespace()


    def deploy(self) -> None:
        self._upsert_deployment()
        self._upsert_service()
        self.logger.info("Agents Deployer is applied (deployment + service).")

    def remove(self) -> None:
        # Delete Service
        try:
            self.core.delete_namespaced_service(
                name=self.NAME, namespace=self.NAMESPACE, body=client.V1DeleteOptions()
            )
            self.logger.info(f"Delete requested for Service '{self.NAME}'.")
        except ApiException as e:
            if e.status != 404:
                self.logger.error(f"Failed to delete Service '{self.NAME}': {e}")

        # Delete Deployment
        try:
            self.apps.delete_namespaced_deployment(
                name=self.NAME, namespace=self.NAMESPACE,
                body=client.V1DeleteOptions(propagation_policy="Foreground", grace_period_seconds=0)
            )
            self.logger.info(f"Delete requested for Deployment '{self.NAME}'.")
        except ApiException as e:
            if e.status != 404:
                self.logger.error(f"Failed to delete Deployment '{self.NAME}': {e}")

    # ---------------- Internals ----------------

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
                        labels={"managed-by": "agents-deployer-installer"}
                    )
                )
                self.core.create_namespace(ns)
            else:
                raise

    def _labels(self) -> Dict[str, str]:
        return {
            "app": "agents-deployer",
            "component": "agents-deployer",
        }

    def _upsert_deployment(self) -> None:
        labels = self._labels()

        container = client.V1Container(
            name="agents-deployer",
            image=self.image,
            image_pull_policy="Always",
            ports=[client.V1ContainerPort(container_port=self.CONTAINER_PORT)],
            env=[
                client.V1EnvVar(name="EXECUTOR_IMAGE_NAME", value=self.env_EXECUTOR_IMAGE_NAME),
                client.V1EnvVar(name="SUBJECT_DB_URL", value=self.env_SUBJECT_DB_URL),
                client.V1EnvVar(name="POLICY_DB_URL", value=self.env_POLICY_DB_URL),
                client.V1EnvVar(name="JOB_SCOUTER_IMAGE_NAME", value=self.env_SCOUTER_IMAGE_NAME),
                client.V1EnvVar(name="JOB_EXCHANGE_API_URL", value=self.env_JOB_EXCHANGE_API_URL),
                client.V1EnvVar(name="AGENT_CORE_IMAGE", value=self.env_AGENT_DEPLOYER_IMAGE),
                client.V1EnvVar(name="AGENT_DELEGATE_URL", value=os.getenv("AGENT_DELEGATE_URL"))
            ],
        )

        pod_spec = client.V1PodSpec(
            containers=[container],
            restart_policy="Always",
        )

        template = client.V1PodTemplateSpec(
            metadata=client.V1ObjectMeta(labels=labels),
            spec=pod_spec
        )

        spec = client.V1DeploymentSpec(
            replicas=1,
            selector=client.V1LabelSelector(match_labels=labels),
            template=template,
            strategy=client.V1DeploymentStrategy(
                type="RollingUpdate",
                rolling_update=client.V1RollingUpdateDeployment(max_unavailable=1, max_surge=1)
            )
        )

        deployment = client.V1Deployment(
            api_version="apps/v1",
            kind="Deployment",
            metadata=client.V1ObjectMeta(name=self.NAME, labels=labels),
            spec=spec,
        )

        try:
            self.apps.read_namespaced_deployment(self.NAME, self.NAMESPACE)
            self.logger.info(f"Deployment '{self.NAME}' exists; replacing...")
            self.apps.replace_namespaced_deployment(self.NAME, self.NAMESPACE, deployment)
        except ApiException as e:
            if e.status == 404:
                self.logger.info(f"Creating Deployment '{self.NAME}'...")
                self.apps.create_namespaced_deployment(self.NAMESPACE, deployment)
            else:
                raise

    def _upsert_service(self) -> None:
        labels = self._labels()

        svc_spec = client.V1ServiceSpec(
            type="NodePort",
            selector=labels,
            ports=[
                client.V1ServicePort(
                    name="http",
                    port=self.CONTAINER_PORT,        # service port 8080
                    target_port=self.CONTAINER_PORT, # container port 8080
                    node_port=self.NODE_PORT,        # fixed NodePort 30777
                    protocol="TCP",
                )
            ],
        )

        service = client.V1Service(
            api_version="v1",
            kind="Service",
            metadata=client.V1ObjectMeta(name=self.NAME, labels=labels),
            spec=svc_spec,
        )

        try:
            existing = self.core.read_namespaced_service(self.NAME, self.NAMESPACE)
            if existing.spec and existing.spec.cluster_ip:
                service.spec.cluster_ip = existing.spec.cluster_ip
            if existing.metadata and existing.metadata.resource_version:
                service.metadata.resource_version = existing.metadata.resource_version

            self.logger.info(f"Service '{self.NAME}' exists; replacing...")
            self.core.replace_namespaced_service(self.NAME, self.NAMESPACE, service)
        except ApiException as e:
            if e.status == 404:
                self.logger.info(f"Creating Service '{self.NAME}'...")
                self.core.create_namespaced_service(self.NAMESPACE, service)
            else:
                raise
