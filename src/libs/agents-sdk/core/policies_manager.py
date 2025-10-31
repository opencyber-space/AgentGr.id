import logging
from .policy_sandbox import LocalPolicyEvaluator
from .db.schema import Subject
from typing import Dict, Any, Optional
from .db.agents_db import SubjectUtils

logger = logging.getLogger(__name__)


class PolicyEvaluator:

    def __init__(self, name, subject: Subject, injects=None) -> None:
        self.name = name
        self.policy: LocalPolicyEvaluator = None
        injects = injects or {}
        try:
            logger.debug(
                f"Initializing PolicyEvaluator for policy '{name}' and subject '{subject}'.")
            self.policy_data = SubjectUtils.get_policy_by_type(name, subject)
            if self.policy_data:
                logger.info(
                    f"Policy '{name}' found for subject '{subject}'. Loading settings...")
                self.policy_data.settings.update(injects)
                self.policy = LocalPolicyEvaluator(
                    policy_rule_uri=self.policy_data.policy_rule_uri,
                    settings=self.policy_data.settings,
                    parameters=self.policy_data.parameters
                )
                logger.info(f"Policy '{name}' initialized successfully.")
            else:
                logger.warning(
                    f"No policy '{name}' found for subject '{subject}'.")
        except Exception as e:
            logger.exception(
                f"Failed to initialize PolicyEvaluator for policy '{name}': {e}")
            self.policy_data = None

    def execute(self, data):
        if not self.policy:
            logger.warning(
                f"Execute called but policy '{self.name}' is not initialized. Returning input data unchanged.")
            return data
        try:
            logger.debug(f"Executing policy '{self.name}' with data: {data}")
            result = self.policy.execute_policy_rule(data)
            logger.debug(
                f"Execution result for policy '{self.name}': {result}")
            return result
        except Exception as e:
            logger.exception(f"Error executing policy '{self.name}': {e}")
            raise

    def execute_management_command(self, command_name, command_data):
        if not self.policy:
            msg = f"Policy '{self.name}' not initialized for management command '{command_name}'."
            logger.error(msg)
            raise Exception(msg)
        try:
            logger.info(
                f"Executing management command '{command_name}' on policy '{self.name}' with data: {command_data}")
            result = self.policy.execute_mgmt_command(
                command_name, command_data)
            logger.debug(
                f"Management command '{command_name}' result for policy '{self.name}': {result}")
            return result
        except Exception as e:
            logger.exception(
                f"Error executing management command '{command_name}' for policy '{self.name}': {e}")
            raise


class PoliciesManager:
    def __init__(self, subject: Subject) -> None:
        self.subject = subject
        self._policies: Dict[str, PolicyEvaluator] = {}
        logger.info(f"PoliciesManager initialized for subject '{subject}'.")

    def add_policy(self, name: str, injects: Optional[Dict[str, Any]] = None) -> None:
        if name in self._policies:
            logger.warning(f"Policy '{name}' already exists. Overwriting...")
        try:
            evaluator = PolicyEvaluator(name, self.subject, injects or {})
            self._policies[name] = evaluator
            logger.info(f"Policy '{name}' added to PoliciesManager.")
        except Exception as e:
            logger.exception(f"Failed to add policy '{name}': {e}")
            raise

    def remove_policy(self, name: str) -> None:
        if name in self._policies:
            del self._policies[name]
            logger.info(f"Policy '{name}' removed from PoliciesManager.")
        else:
            logger.warning(f"Tried to remove non-existent policy '{name}'.")

    def execute(self, name: str, data: Any) -> Any:
        evaluator = self._policies.get(name)
        if not evaluator:
            logger.error(f"Execute called for unknown policy '{name}'.")
            raise KeyError(f"Policy '{name}' not found.")
        return evaluator.execute(data)

    def execute_management_command(self, name: str, command_name: str, command_data: Any) -> Any:
        evaluator = self._policies.get(name)
        if not evaluator:
            logger.error(
                f"Management command '{command_name}' called for unknown policy '{name}'.")
            raise KeyError(f"Policy '{name}' not found.")
        return evaluator.execute_management_command(command_name, command_data)

    def list_policies(self) -> Dict[str, PolicyEvaluator]:
        return dict(self._policies)
