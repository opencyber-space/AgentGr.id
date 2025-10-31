import logging
from typing import Any, Dict, Optional
from .policy_sandbox import LocalPolicyEvaluator
from .db.schema import Subject
from .db.agents_db import SubjectUtils

logger = logging.getLogger(__name__)


class PreProcessingPolicy:
    def __init__(self, subject: Subject, injects: Optional[Dict[str, Any]] = None) -> None:
        self.name = "pre_processor"
        self.policy: Optional[LocalPolicyEvaluator] = None
        injects = injects or {}
        try:
            logger.debug(f"Initializing PreProcessingPolicy for subject '{subject}'.")
            self.policy_data = SubjectUtils.get_policy_by_type(self.name, subject)
            if self.policy_data:
                logger.info(f"PreProcessingPolicy found for subject '{subject}'. Loading settings...")
                self.policy_data.settings.update(injects)
                self.policy = LocalPolicyEvaluator(
                    policy_rule_uri=self.policy_data.policy_rule_uri,
                    settings=self.policy_data.settings,
                    parameters=self.policy_data.parameters,
                )
                logger.info("PreProcessingPolicy initialized successfully.")
            else:
                logger.warning(f"No PreProcessingPolicy found for subject '{subject}'.")
        except Exception as e:
            logger.exception(f"Failed to initialize PreProcessingPolicy: {e}")
            self.policy_data = None

    def execute(self, data: Any) -> Any:
        if not self.policy:
            logger.warning("PreProcessingPolicy not initialized. Returning input unchanged.")
            return data
        try:
            logger.debug(f"Executing PreProcessingPolicy with data: {data}")
            result = self.policy.execute_policy_rule(data)
            logger.debug(f"PreProcessingPolicy execution result: {result}")
            return result
        except Exception as e:
            logger.exception(f"Error executing PreProcessingPolicy: {e}")
            raise

    def execute_management_command(self, command_name: str, command_data: Any) -> Any:
        if not self.policy:
            msg = f"PreProcessingPolicy not initialized for management command '{command_name}'."
            logger.error(msg)
            raise Exception(msg)
        try:
            logger.info(f"Executing management command '{command_name}' on PreProcessingPolicy with data: {command_data}")
            result = self.policy.execute_mgmt_command(command_name, command_data)
            logger.debug(f"Management command result (PreProcessingPolicy): {result}")
            return result
        except Exception as e:
            logger.exception(f"Error executing management command on PreProcessingPolicy: {e}")
            raise


class PostProcessingPolicy:
    def __init__(self, subject: Subject, injects: Optional[Dict[str, Any]] = None) -> None:
        self.name = "post_processor"
        self.policy: Optional[LocalPolicyEvaluator] = None
        injects = injects or {}
        try:
            logger.debug(f"Initializing PostProcessingPolicy for subject '{subject}'.")
            self.policy_data = SubjectUtils.get_policy_by_type(self.name, subject)
            if self.policy_data:
                logger.info(f"PostProcessingPolicy found for subject '{subject}'. Loading settings...")
                self.policy_data.settings.update(injects)
                self.policy = LocalPolicyEvaluator(
                    policy_rule_uri=self.policy_data.policy_rule_uri,
                    settings=self.policy_data.settings,
                    parameters=self.policy_data.parameters,
                )
                logger.info("PostProcessingPolicy initialized successfully.")
            else:
                logger.warning(f"No PostProcessingPolicy found for subject '{subject}'.")
        except Exception as e:
            logger.exception(f"Failed to initialize PostProcessingPolicy: {e}")
            self.policy_data = None

    def execute(self, data: Any) -> Any:
        if not self.policy:
            logger.warning("PostProcessingPolicy not initialized. Returning input unchanged.")
            return data
        try:
            logger.debug(f"Executing PostProcessingPolicy with data: {data}")
            result = self.policy.execute_policy_rule(data)
            logger.debug(f"PostProcessingPolicy execution result: {result}")
            return result
        except Exception as e:
            logger.exception(f"Error executing PostProcessingPolicy: {e}")
            raise

    def execute_management_command(self, command_name: str, command_data: Any) -> Any:
        if not self.policy:
            msg = f"PostProcessingPolicy not initialized for management command '{command_name}'."
            logger.error(msg)
            raise Exception(msg)
        try:
            logger.info(f"Executing management command '{command_name}' on PostProcessingPolicy with data: {command_data}")
            result = self.policy.execute_mgmt_command(command_name, command_data)
            logger.debug(f"Management command result (PostProcessingPolicy): {result}")
            return result
        except Exception as e:
            logger.exception(f"Error executing management command on PostProcessingPolicy: {e}")
            raise


class MessageConvertorPolicy:
    def __init__(self, subject: Subject, injects: Optional[Dict[str, Any]] = None) -> None:
        self.name = "message_transformer"
        self.policy: Optional[LocalPolicyEvaluator] = None
        injects = injects or {}
        try:
            logger.debug(f"Initializing MessageConvertorPolicy for subject '{subject}'.")
            self.policy_data = SubjectUtils.get_policy_by_type(self.name, subject)
            if self.policy_data:
                logger.info(f"MessageConvertorPolicy found for subject '{subject}'. Loading settings...")
                self.policy_data.settings.update(injects)
                self.policy = LocalPolicyEvaluator(
                    policy_rule_uri=self.policy_data.policy_rule_uri,
                    settings=self.policy_data.settings,
                    parameters=self.policy_data.parameters,
                )
                logger.info("MessageConvertorPolicy initialized successfully.")
            else:
                logger.warning(f"No MessageConvertorPolicy found for subject '{subject}'.")
        except Exception as e:
            logger.exception(f"Failed to initialize MessageConvertorPolicy: {e}")
            self.policy_data = None

    def execute(self, data: Any) -> Any:
        if not self.policy:
            logger.warning("MessageConvertorPolicy not initialized. Returning input unchanged.")
            return data
        try:
            logger.debug(f"Executing MessageConvertorPolicy with data: {data}")
            result = self.policy.execute_policy_rule(data)
            logger.debug(f"MessageConvertorPolicy execution result: {result}")
            return result
        except Exception as e:
            logger.exception(f"Error executing MessageConvertorPolicy: {e}")
            raise

    def execute_management_command(self, command_name: str, command_data: Any) -> Any:
        if not self.policy:
            msg = f"MessageConvertorPolicy not initialized for management command '{command_name}'."
            logger.error(msg)
            raise Exception(msg)
        try:
            logger.info(f"Executing management command '{command_name}' on MessageConvertorPolicy with data: {command_data}")
            result = self.policy.execute_mgmt_command(command_name, command_data)
            logger.debug(f"Management command result (MessageConvertorPolicy): {result}")
            return result
        except Exception as e:
            logger.exception(f"Error executing management command on MessageConvertorPolicy: {e}")
            raise
