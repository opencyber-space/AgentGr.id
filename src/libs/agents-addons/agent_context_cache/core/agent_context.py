from .cache import InMemoryContextCache
from .config import ContextConfigurations
from .context_mgmt import ContextUpdateProcessor, ContextBufferQueue
from .topics_pusher import TopicsListConfig, ContextUpdateEventPusher

from threading import Thread

class AgentContextCache:
    def __init__(self):
        self.buffer_queue = ContextBufferQueue()

        self.cache = InMemoryContextCache(buffer_queue=self.buffer_queue)

        self.context_configurations = ContextConfigurations(context_cache=self.cache)

        self.topics_list_config = TopicsListConfig(self.context_configurations)

        self.event_pusher = ContextUpdateEventPusher(self.topics_list_config)

        self.update_processor = ContextUpdateProcessor(
            buffer_queue=self.buffer_queue,
            event_pusher=self.event_pusher
        )

        self.update_processor_thread = Thread(target=self.update_processor.process_updates, daemon=True)
        self.update_processor_thread.start()

    # Methods to interact with the cache
    def set(self, key, value, namespace="default"):
        self.cache.set(key, value, namespace)

    def get(self, key, namespace="default"):
        return self.cache.get(key, namespace)

    def delete(self, key, namespace="default"):
        self.cache.delete(key, namespace)

    def list_keys(self, namespace="default"):
        return self.cache.list_keys(namespace)

    def clear_namespace(self, namespace="default"):
        self.cache.clear_namespace(namespace)

    def list_namespaces(self):
        return self.cache.list_namespaces()

    # Methods to interact with configurations
    def set_topics_list(self, topics):
        self.context_configurations.set_topics_list(topics)

    def get_topics_list(self):
        return self.context_configurations.get_topics_list()

    def enable_backup(self):
        self.context_configurations.enable_backup()

    def disable_backup(self):
        self.context_configurations.disable_backup()

    def is_backup_enabled(self):
        return self.context_configurations.is_backup_enabled()

    def set_backup_settings(self, settings):
        self.context_configurations.set_backup_settings(settings)

    def get_backup_settings(self):
        return self.context_configurations.get_backup_settings()

    def shutdown(self):
        self.update_processor.stop_processing()
        self.update_processor_thread.join()
