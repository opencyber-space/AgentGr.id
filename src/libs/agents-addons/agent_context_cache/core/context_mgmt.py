import threading
import logging
from queue import Queue

from .topics_pusher import ContextUpdateEventPusher


class ContextBufferQueue:
    def __init__(self):
        self.queue = Queue()

    def add_operation(self, operation):
        self.queue.put(operation)

    def get_operation(self):
        return self.queue.get()

    def is_empty(self):
        return self.queue.empty()


class ContextUpdateProcessor:
    def __init__(self, buffer_queue: ContextBufferQueue, event_pusher: ContextUpdateEventPusher, backup_manager=None):
        self.buffer_queue = buffer_queue
        self.event_pusher = event_pusher
        self.backup_manager = backup_manager
        self._stop_event = threading.Event()
        self._thread = None

    def process_updates(self):
        while not self._stop_event.is_set():
            try:
                if not self.buffer_queue.is_empty():
                    operation = self.buffer_queue.get_operation()
                    self.event_pusher.push_update(operation)

                    # Optional: Handle backup management
                    if self.backup_manager:
                        self.backup_manager.handle_backup(operation)

            except Exception as e:
                logging.error(f"Error processing update: {e}")

    def start(self):
        if self._thread is None or not self._thread.is_alive():
            self._stop_event.clear()
            self._thread = threading.Thread(target=self.process_updates, daemon=True)
            self._thread.start()
            logging.info("ContextUpdateProcessor started.")

    def stop(self):
        if self._thread and self._thread.is_alive():
            self._stop_event.set()
            self._thread.join()
            logging.info("ContextUpdateProcessor stopped.")