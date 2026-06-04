from .context_mgmt import ContextBufferQueue


class InMemoryContextCache:
    def __init__(self, buffer_queue: ContextBufferQueue = None):

        self.store = {}
        self.buffer_queue = buffer_queue

    def _get_namespace(self, namespace):
        if namespace not in self.store:
            self.store[namespace] = {}
        return self.store[namespace]

    def _record_operation(self, operation_type, key, value=None, namespace="default"):

        if self.buffer_queue:
            operation = {
                "operation": operation_type,
                "namespace": namespace,
                "key": key,
                "value": value
            }
            self.buffer_queue.add_operation(operation)

    def set(self, key, value, namespace="default"):
        namespace_store = self._get_namespace(namespace)
        namespace_store[key] = value
        self._record_operation("set", key, value, namespace)

    def get(self, key, namespace="default"):
        namespace_store = self._get_namespace(namespace)
        return namespace_store.get(key, None)

    def delete(self, key, namespace="default"):
        namespace_store = self._get_namespace(namespace)
        if key in namespace_store:
            del namespace_store[key]
            self._record_operation("delete", key, namespace=namespace)

    def list_keys(self, namespace="default"):
        namespace_store = self._get_namespace(namespace)
        return list(namespace_store.keys())

    def clear_namespace(self, namespace="default"):
        if namespace in self.store:
            self.store[namespace] = {}
            self._record_operation(
                "clear_namespace", None, namespace=namespace)

    def list_namespaces(self):
        return list(self.store.keys())


class ContextStoreWrapper:
    def __init__(self, cache: InMemoryContextCache):
        self.cache = cache

    def GET(self, key, namespace="default"):
        return self.cache.get(key, namespace)

    def SET(self, key, value, namespace="default"):
        self.cache.set(key, value, namespace)

    def DELETE(self, key, namespace="default"):
        self.cache.delete(key, namespace)

    def CREATE_NS(self, namespace="default"):
        self.cache._get_namespace(namespace)

    def inner(self):
        return self.cache
