import os
import re
import time
import json
import logging
from typing import Optional, Dict, Any, List

from kubernetes import client, config
from kubernetes.client import ApiException


class AgentsInstanceDeployer:
   
    NAMESPACE = "agents"

    def __init__(self, *, logger: Optional[logging.Logger] = None) -> None:
        # Logging
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        if not self.logger.handlers:
            logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())

        # In-cluster config
        config.load_incluster_config()

        # Clients
        self.core = client.CoreV1Api()
        self.apps = client.AppsV1Api()

        # Images and envs
        self.core_image = os.getenv("AGENT_CORE_IMAGE")
        self.redis_image = os.getenv("REDIS_IMAGE_NAME", "redis:7-alpine")

        # Values to pass into agent-core container
        self.job_exchange_api_url = os.getenv("JOB_EXCHANGE_API_URL")
        self.subject_db_url = os.getenv("SUBJECT_DB_URL")

        # Validate required envs for the containers we create
        missing = [k for k, v in {
            "JOB_EXCHANGE_API_URL": self.job_exchange_api_url,
            "SUBJECT_DB_URL": self.subject_db_url,
        }.items() if not v]
        if missing:
            raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

        # Ensure namespace
        self._ensure_namespace()

    # -------- Public API --------

    def deploy_instances(self, instances: List[Dict[str, Any]], image_name, meshes={}, delegate="") -> List[Dict[str, Any]]:
        
        results = []
        for spec in instances or []:
            instance_id = str(spec.get("instance_id") or "").strip()
            subject_id = str(spec.get("subject_id") or "").strip()
            node_selector: Optional[Dict[str, str]] = spec.get("node_selector") or None

            if not instance_id or not subject_id:
                self.logger.error("Skipping instance with missing 'instance_id' or 'subject_id': %s", spec)
                results.append({"ok": False, "error": "Missing instance_id/subject_id", "input": spec})
                continue

            name = self._name(instance_id, subject_id)
            try:
                self._create_or_replace_deployment(
                    name=name,
                    instance_id=instance_id,
                    subject_id=subject_id,
                    node_selector=node_selector,
                    image_name=image_name,
                    meshes=meshes,
                    delegate=delegate
                )
                self._create_or_replace_service(name=name)

                # Optionally wait for service ClusterIP assignment (usually immediate)
                svc = self.core.read_namespaced_service(name=name, namespace=self.NAMESPACE)
                results.append({
                    "ok": True,
                    "name": name,
                    "deployment": name,
                    "service": {
                        "name": svc.metadata.name,
                        "cluster_ip": svc.spec.cluster_ip,
                        "ports": [{
                            "name": p.name,
                            "port": p.port,
                            "target_port": p.target_port,
                            "protocol": p.protocol
                        } for p in (svc.spec.ports or [])]
                    }
                })
            except Exception as e:
                self.logger.exception("Failed deploying instance %s/%s", instance_id, subject_id)
                results.append({"ok": False, "name": name, "error": str(e)})

        return results

    def remove_instance(self, instance_id: str, subject_id: str) -> bool:
        name = self._name(instance_id, subject_id)
        ok = True
        try:
            self.apps.delete_namespaced_deployment(
                name=name, namespace=self.NAMESPACE,
                body=client.V1DeleteOptions(
                    propagation_policy="Foreground",
                    grace_period_seconds=0
                ),
            )
            self.logger.info("Delete requested for Deployment '%s'.", name)
        except ApiException as e:
            if e.status == 404:
                self.logger.info("Deployment '%s' not found; nothing to delete.", name)
            else:
                self.logger.error("Failed deleting Deployment '%s': %s", name, e)
                ok = False

        try:
            self.core.delete_namespaced_service(name=name, namespace=self.NAMESPACE)
            self.logger.info("Delete requested for Service '%s'.", name)
        except ApiException as e:
            if e.status == 404:
                self.logger.info("Service '%s' not found; nothing to delete.", name)
            else:
                self.logger.error("Failed deleting Service '%s': %s", name, e)
                ok = False

        return ok

    # -------- Internals --------

    def _create_or_replace_deployment(
        self,
        *,
        name: str,
        instance_id: str,
        subject_id: str,
        node_selector: Optional[Dict[str, str]] = None,
        image_name: str,
        meshes: dict = {},
        delegate: str = ""
    ) -> None:
        labels = {
            "app": "agent-instance",
            "component": "agent-core",
            "subjectId": subject_id,
            "instanceId": instance_id,
        }

        # --- redis container ---
        redis_container = client.V1Container(
            name="redis",
            image=self.redis_image,
            image_pull_policy="IfNotPresent",
            ports=[client.V1ContainerPort(container_port=6379, name="redis")],
        )

        # --- agent-core container ---
        core_env = [
            client.V1EnvVar(name="JOB_EXCHANGE_API_URL", value=self.job_exchange_api_url),
            client.V1EnvVar(name="SUBJECT_ID", value=subject_id),
            client.V1EnvVar(name="INSTANCE_ID", value=instance_id),
            client.V1EnvVar(name="SUBJECT_DB_URL", value=self.subject_db_url),
            client.V1EnvVar(name="MESH_LIST", value=json.dumps({"meshes": meshes})),
            client.V1EnvVar(name="AGENT_DELEGATE_URL", value=delegate)
        ]
        core_container = client.V1Container(
            name="agent-core",
            image=image_name,
            image_pull_policy="Always",
            env=core_env,
            ports=[client.V1ContainerPort(container_port=8765, name="ws")],
        )

        pod_spec = client.V1PodSpec(
            containers=[redis_container, core_container],
            restart_policy="Always",
            node_selector=node_selector if node_selector else None,
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

        try:
            self.apps.read_namespaced_deployment(name=name, namespace=self.NAMESPACE)
            self.logger.info("Deployment '%s' exists; replacing...", name)
            self.apps.replace_namespaced_deployment(
                name=name, namespace=self.NAMESPACE, body=deployment
            )
        except ApiException as e:
            if e.status == 404:
                self.logger.info("Creating Deployment '%s'...", name)
                self.apps.create_namespaced_deployment(namespace=self.NAMESPACE, body=deployment)
            else:
                raise

    def _create_or_replace_service(self, *, name: str) -> None:
       
        svc = client.V1Service(
            api_version="v1",
            kind="Service",
            metadata=client.V1ObjectMeta(
                name=name,
                labels={"app": "agent-instance"},
            ),
            spec=client.V1ServiceSpec(
                selector={"app": "agent-instance"},
                type="ClusterIP",
                ports=[
                    client.V1ServicePort(
                        name="redis",
                        port=6379,
                        target_port=6379,
                        protocol="TCP",
                    ),
                    client.V1ServicePort(
                        name="ws",
                        port=8765,
                        target_port=8765,
                        protocol="TCP",
                    ),
                ],
            ),
        )

        try:
            self.core.read_namespaced_service(name=name, namespace=self.NAMESPACE)
            self.logger.info("Service '%s' exists; replacing...", name)
            self.core.replace_namespaced_service(
                name=name, namespace=self.NAMESPACE, body=svc
            )
        except ApiException as e:
            if e.status == 404:
                self.logger.info("Creating Service '%s'...", name)
                self.core.create_namespaced_service(namespace=self.NAMESPACE, body=svc)
            else:
                raise

    def _ensure_namespace(self) -> None:
        try:
            self.core.read_namespace(self.NAMESPACE)
            self.logger.debug("Namespace '%s' already exists.", self.NAMESPACE)
        except ApiException as e:
            if e.status == 404:
                self.logger.info("Creating namespace '%s'...", self.NAMESPACE)
                ns = client.V1Namespace(
                    metadata=client.V1ObjectMeta(
                        name=self.NAMESPACE,
                        labels={"managed-by": "agents-instance-deployer"}
                    )
                )
                self.core.create_namespace(ns)
            else:
                raise

    @staticmethod
    def _name(instance_id: str, subject_id: str) -> str:
        base = f"{instance_id}-{subject_id}"
        return (base[:63]).rstrip('-')
