import logging
import requests
import time

from .policy_sandbox import LocalPolicyEvaluator

logger = logging.getLogger(__name__)


class LocalType1Evaluator:

    def __init__(self, policy_rule_uri: str, parameters: dict) -> None:
        self.policy_rule_uri = policy_rule_uri
        self.parameters = parameters

        logger.info(
            f"Initializing LocalType1Evaluator with policy_rule_uri={policy_rule_uri}")
        self.evaluator = LocalPolicyEvaluator(self.policy_rule_uri, parameters)

    def set_parameters(self, new_parameters):
        logger.debug(f"Updating parameters for evaluator: {new_parameters}")
        self.parameters = new_parameters
        self.evaluator.executor.parameters = new_parameters

    def execute(self, input_data: dict):
        logger.info(f"Executing policy rule for URI: {self.policy_rule_uri}")
        logger.debug(f"Input data: {input_data}")
        try:
            result = self.evaluator.execute_policy_rule(input_data)
            logger.debug(f"Execution result: {result}")
            return result
        except Exception as e:
            logger.error(
                f"Error while executing policy rule '{self.policy_rule_uri}': {e}", exc_info=True)
            raise


class CentralType2Executor:
    def __init__(self, executor_id: str, endpoint: str, policy_rule_uri: str, parameters: dict) -> None:
        self.executor_id = executor_id
        self.endpoint = endpoint.rstrip("/")  # remove trailing slash if any
        self.policy_rule_uri = policy_rule_uri
        self.parameters = parameters

        logger.info(
            f"Initialized CentralType2Executor with executor_id={executor_id}, endpoint={self.endpoint}, policy_rule_uri={policy_rule_uri}")

    def execute(self, input_data: dict):
        url = f"{self.endpoint}/executor/{self.executor_id}/execute_policy"
        payload = {
            "policy_rule_uri": self.policy_rule_uri,
            "input_data": input_data,
            "parameters": self.parameters
        }

        logger.info(f"Sending policy execution request to {url}")
        logger.debug(f"Payload: {payload}")

        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            response_json = response.json()
            logger.debug(f"Response JSON: {response_json}")

            if not response_json.get("success", False):
                raise Exception(f"Execution failed: {response_json}")

            return response_json.get("data")

        except Exception as e:
            logger.error(
                f"Execution failed for executor_id={self.executor_id}: {e}", exc_info=True)
            raise


class FunctionType3Executor:
    def __init__(self, function_id: str, endpoint: str) -> None:
        self.function_id = function_id
        self.endpoint = endpoint.rstrip("/")  # ensure no trailing slash
        logger.info(
            f"Initialized FunctionType3Executor with function_id={function_id}, endpoint={self.endpoint}")

    def execute(self, input_data: dict):
        url = f"{self.endpoint}/function/call_function/{self.function_id}"
        logger.info(f"Calling function at {url}")
        logger.debug(f"Input data: {input_data}")

        try:
            response = requests.post(url, json=input_data, timeout=10)
            response.raise_for_status()
            response_json = response.json()
            logger.debug(f"Response JSON: {response_json}")

            if not response_json.get("success", False):
                raise Exception(f"Function call failed: {response_json}")

            return response_json.get("data")

        except Exception as e:
            logger.error(
                f"Function execution failed for function_id={self.function_id}: {e}", exc_info=True)
            raise


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
            f"Initialized JobType4Executor with executor_id={executor_id}, endpoint={endpoint}")

    def execute(self, job_name: str, input_data: dict):
        submit_url = f"{self.endpoint}/jobs/submit/{self.executor_id}"
        submit_payload = {
            "name": job_name,
            "policy_rule_uri": self.policy_rule_uri,
            "policy_rule_parameters": self.parameters,
            "node_selector": self.node_selector,
            "inputs": input_data
        }

        logger.info(f"Submitting job to {submit_url}")
        logger.debug(f"Job payload: {submit_payload}")

        try:
            submit_resp = requests.post(
                submit_url, json=submit_payload, timeout=10)
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
            f"Job {job_id} not completed after {self.max_retries * self.poll_interval} seconds")
