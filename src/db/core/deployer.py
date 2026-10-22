# agent_deployer_integration.py
from __future__ import annotations

import logging
from typing import Optional, Dict
from urllib.parse import urlparse

from kubernetes.client import ApiException

from .crud import AgentDeployersDB, AgentDeployersDBError
from .schema import AgentDeployer 
from .k8s_executor import AgentsDeployerInstaller  


def _extract_public_host_from_kubeconfig(kubeconfig: Dict) -> str:
    
    try:
        clusters = kubeconfig.get("clusters") or []
        if not clusters:
            raise ValueError("kubeconfig.clusters is empty")
        server = clusters[0]["cluster"]["server"]
        host = urlparse(server).hostname
        if not host:
            raise ValueError(f"Unable to parse host from server URL: {server}")
        return host
    except Exception as e:
        raise ValueError(f"Failed to extract public host from kubeconfig: {e}")


def create_agent_deployer(
    *,
    kubeconfig: Dict,
    deployer_id: str,
    deployer_name: str,
    deployer_cluster_id: str,
    deployer_public_ip: str,
    db: AgentDeployersDB,
    logger: Optional[logging.Logger] = None,
) -> AgentDeployer:
   
    log = logger or logging.getLogger("agent-deployer.create")
    if not log.handlers:
        logging.basicConfig(level="INFO")

    # 1) Deploy to Kubernetes
    installer = AgentsDeployerInstaller(kubeconfig, logger=log)
    installer.deploy()

    # 2) Build public URL (use installer’s fixed NodePort)
    node_port = installer.NODE_PORT
    public_url = f"http://{deployer_public_ip}:{node_port}"

    # 3) Write to DB (with rollback on failure)
    ad = AgentDeployer(
        deployer_id=deployer_id,
        deployer_name=deployer_name,
        deployer_public_url=public_url,
        deployer_cluster_id=deployer_cluster_id,
        deployer_ip=deployer_public_ip
    )

    try:
        created = db.create_deployer(ad)
        log.info("AgentDeployer created in DB: id=%s url=%s", created.deployer_id, created.deployer_public_url)
        return created
    except AgentDeployersDBError as e:
        log.error("DB error creating AgentDeployer, rolling back K8s resources: %s", e)
        try:
            installer.remove()
        except ApiException as re:
            log.error("Rollback failed while removing K8s resources: %s", re)
        raise


def remove_agent_deployer(
    *,
    kubeconfig: Dict,
    deployer_id: str,
    db: AgentDeployersDB,
    logger: Optional[logging.Logger] = None,
) -> bool:
   
    log = logger or logging.getLogger("agent-deployer.remove")
    if not log.handlers:
        logging.basicConfig(level="INFO")

    # 1) Remove from Kubernetes
    installer = AgentsDeployerInstaller(kubeconfig, logger=log)
    installer.remove()

    # 2) Remove from DB
    try:
        ok = db.delete_deployer(deployer_id)
        if ok:
            log.info("AgentDeployer deleted from DB: id=%s", deployer_id)
        else:
            log.info("AgentDeployer not found in DB: id=%s", deployer_id)
        return ok
    except AgentDeployersDBError as e:
        log.error("DB error deleting AgentDeployer id=%s: %s", deployer_id, e)
        raise
