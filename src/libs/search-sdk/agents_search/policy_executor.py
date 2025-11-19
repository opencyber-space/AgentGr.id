import logging
from typing import Any, Dict, List, Optional, Sequence

import requests
import time

logger = logging.getLogger(__name__)


class JobType4Executor:
    def __init__(
        self,
        executor_id: str,
        endpoint: str,
        policy_rule_uri: str,
        parameters: dict = None,
        node_selector: dict = None,
        poll_interval: int = 2,
        max_retries: int = 30
    ) -> None:
        self.executor_id = executor_id
        self.endpoint = endpoint.rstrip("/")
        self.policy_rule_uri = policy_rule_uri
        self.parameters = parameters or {}
        self.node_selector = node_selector or {}
        self.poll_interval = poll_interval
        self.max_retries = max_retries

        logger.info(
            f"Initialized JobType4Executor with executor_id={executor_id}, endpoint={endpoint}"
        )

    def execute(self, job_name: str, input_data: dict):
        submit_url = f"{self.endpoint}/jobs/submit/{self.executor_id}"
        submit_payload = {
            "name": job_name,
            "policy_rule_uri": self.policy_rule_uri,
            "policy_rule_parameters": self.parameters,
            "node_selector": self.node_selector,
            "inputs": input_data,
        }

        logger.info(f"Submitting job to {submit_url}")
        logger.debug(f"Job payload: {submit_payload}")

        try:
            submit_resp = requests.post(submit_url, json=submit_payload, timeout=10)
            submit_resp.raise_for_status()
            submit_json = submit_resp.json()

            if not submit_json.get("success", False):
                raise Exception(f"Job submission failed: {submit_json}")

            job_id = submit_json.get("job_id")
            logger.info(f"Job submitted successfully with job_id={job_id}")
        except Exception as e:
            logger.error(f"Failed to submit job: {e}", exc_info=True)
            raise

        # Poll for job status
        status_url = f"{self.endpoint}/jobs/{job_id}"
        logger.info(f"Polling job status at {status_url}")

        for attempt in range(self.max_retries):
            try:
                status_resp = requests.get(status_url, timeout=10)
                status_resp.raise_for_status()
                status_json = status_resp.json()

                if not status_json.get("success", False):
                    raise Exception(f"Job status check failed: {status_json}")

                job_data = status_json["data"]
                job_status = job_data.get("job_status")

                logger.debug(f"Attempt {attempt + 1}: job_status={job_status}")

                if job_status == "completed":
                    logger.info(f"Job {job_id} completed successfully")
                    return job_data.get("job_output_data")

            except Exception as e:
                logger.warning(f"Polling attempt {attempt + 1} failed: {e}")

            time.sleep(self.poll_interval)

        logger.error(f"Job {job_id} did not complete within timeout window")
        raise TimeoutError(
            f"Job {job_id} not completed after {self.max_retries * self.poll_interval} seconds"
        )


class AgentSearchPolicyExecutor:
  
    def __init__(
        self,
        *,
        executor_id: str,
        endpoint: str,
        policy_rule_uri: str,
        parameters: Optional[Dict[str, Any]] = None,
        node_selector: Optional[Dict[str, Any]] = None,
        poll_interval: int = 2,
        max_retries: int = 30,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self.job_executor = JobType4Executor(
            executor_id=executor_id,
            endpoint=endpoint,
            policy_rule_uri=policy_rule_uri,
            parameters=parameters or {},
            node_selector=node_selector or {},
            poll_interval=poll_interval,
            max_retries=max_retries,
        )
        self.logger.info(
            "Initialized AgentSearchPolicyExecutor with executor_id=%s, endpoint=%s, policy_rule_uri=%s",
            executor_id,
            endpoint,
            policy_rule_uri,
        )

    # --------- Low-level API: direct policy execution ---------

    def execute_policy_job(
        self,
        *,
        job_name: str,
        inputs: Dict[str, Any],
    ) -> Any:
        """
        Execute an arbitrary policy job and return job_output_data as-is.
        """
        self.logger.debug("Executing policy job '%s' with inputs keys=%s", job_name, list(inputs.keys()))
        return self.job_executor.execute(job_name, inputs)

    # --------- High-level API: search from objects via policy ---------

    def search_from_objects(
        self,
        *,
        job_name: str,
        objects: Sequence[Any],
        id_attr: str = "id",
        query: Optional[str] = None,
        extra_inputs: Optional[Dict[str, Any]] = None,
    ) -> Any:
       
        items: List[Dict[str, Any]] = []

        for i, obj in enumerate(objects):
            if not hasattr(obj, id_attr):
                raise ValueError(f"Object {i} missing required attr '{id_attr}'")
            if not hasattr(obj, "get_searchable_representation"):
                raise ValueError(f"Object {i} missing get_searchable_representation()")

            items.append(
                {
                    "id": str(getattr(obj, id_attr)),
                    "representation": obj.get_searchable_representation(),
                }
            )

        inputs: Dict[str, Any] = {
            "items": items,
        }
        if query is not None:
            inputs["query"] = query

        if extra_inputs:
            # Let caller extend/override fields if needed
            inputs.update(extra_inputs)

        self.logger.debug(
            "Submitting search policy job '%s' with %d items and query_present=%s",
            job_name,
            len(items),
            bool(query),
        )

        result = self.execute_policy_job(job_name=job_name, inputs=inputs)

       
        return result
