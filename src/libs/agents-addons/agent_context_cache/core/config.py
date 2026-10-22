import logging
from .cache import InMemoryContextCache

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class ContextConfigurations:
    def __init__(self, context_cache: InMemoryContextCache, namespace="config"):
        self.context_cache = context_cache
        self.namespace = namespace

    def set_config(self, key, value):
        try:
            self.context_cache.set(key, value, namespace=self.namespace)
            logger.info(f"Config set: {key} = {value}")
        except Exception as e:
            logger.error(f"Error setting config {key} = {value}: {e}")
            raise

    def get_config(self, key):
        try:
            value = self.context_cache.get(key, namespace=self.namespace)
            logger.info(f"Config retrieved: {key} = {value}")
            return value
        except Exception as e:
            logger.error(f"Error retrieving config for {key}: {e}")
            raise

    def delete_config(self, key):
        try:
            self.context_cache.delete(key, namespace=self.namespace)
            logger.info(f"Config deleted: {key}")
        except Exception as e:
            logger.error(f"Error deleting config {key}: {e}")
            raise

    def list_configs(self):
        try:
            configs = self.context_cache.list_keys(namespace=self.namespace)
            logger.info(f"Configs listed: {configs}")
            return configs
        except Exception as e:
            logger.error(f"Error listing configs: {e}")
            raise

    def clear_configs(self):
        try:
            self.context_cache.clear_namespace(namespace=self.namespace)
            logger.info("All configs cleared")
        except Exception as e:
            logger.error(f"Error clearing configs: {e}")
            raise

    # Specific methods for topics list
    def set_topics_list(self, topics):
        try:
            if not isinstance(topics, list):
                raise ValueError("Topics must be a list.")
            self.set_config("topics_list", topics)
            logger.info(f"Topics list set: {topics}")
        except Exception as e:
            logger.error(f"Error setting topics list: {e}")
            raise

    def get_topics_list(self):
        try:
            topics = self.get_config("topics_list") or []
            logger.info(f"Topics list retrieved: {topics}")
            return topics
        except Exception as e:
            logger.error(f"Error retrieving topics list: {e}")
            raise

    def add_topic(self, topic):
        try:
            topics = self.get_topics_list()
            if topic not in topics:
                topics.append(topic)
                self.set_topics_list(topics)
                logger.info(f"Topic added: {topic}")
            else:
                logger.info(f"Topic already exists: {topic}")
        except Exception as e:
            logger.error(f"Error adding topic {topic}: {e}")
            raise

    def remove_topic(self, topic):
        try:
            topics = self.get_topics_list()
            if topic in topics:
                topics.remove(topic)
                self.set_topics_list(topics)
                logger.info(f"Topic removed: {topic}")
            else:
                logger.warning(f"Topic not found: {topic}")
        except Exception as e:
            logger.error(f"Error removing topic {topic}: {e}")
            raise

    # Specific methods for backup management
    def enable_backup(self):
        try:
            self.set_config("backup_enabled", True)
            logger.info("Backup enabled")
        except Exception as e:
            logger.error(f"Error enabling backup: {e}")
            raise

    def disable_backup(self):
        try:
            self.set_config("backup_enabled", False)
            logger.info("Backup disabled")
        except Exception as e:
            logger.error(f"Error disabling backup: {e}")
            raise

    def is_backup_enabled(self):
        try:
            backup_enabled = self.get_config("backup_enabled") or False
            logger.info(f"Backup enabled: {backup_enabled}")
            return backup_enabled
        except Exception as e:
            logger.error(f"Error checking if backup is enabled: {e}")
            raise

    def set_backup_settings(self, settings):
        try:
            if not isinstance(settings, dict):
                raise ValueError("Backup settings must be a dictionary.")
            self.set_config("backup_settings", settings)
            logger.info(f"Backup settings set: {settings}")
        except Exception as e:
            logger.error(f"Error setting backup settings: {e}")
            raise

    def get_backup_settings(self):
        try:
            settings = self.get_config("backup_settings") or {}
            logger.info(f"Backup settings retrieved: {settings}")
            return settings
        except Exception as e:
            logger.error(f"Error retrieving backup settings: {e}")
            raise
