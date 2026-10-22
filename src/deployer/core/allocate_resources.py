from .db.schema import Subject
from .db.agents_db import SubjectUtils

from .policy_sandbox import LocalPolicyEvaluator

from .k8s import ClusterNodeInventory


class ResourceAllocator:

    def __init__(self, subject: Subject, policy_data: dict) -> None:
        self.subject = subject
        self.policy_rule_uri = policy_data.get('policy_rule_uri')
        self.policy_parameters = policy_data.get('parameters')

    def evaluate(self, eval_data: dict):
        subject_dict = self.subject.to_dict()
        node_inventory = ClusterNodeInventory(use_incluster_config=True)
        node_resources = node_inventory.sync_node()

        inputs = {
            "inputs": eval_data,
            "resources": node_resources,
            "subject": subject_dict
        }

        policy = LocalPolicyEvaluator(self.policy_rule_uri, parameters=self.policy_parameters)
        return policy.execute_policy_rule(inputs)
