from .config import ContextConfigurations
import json
import logging
import asyncio
import nats
import os

from .config import TopicsListConfig

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class TopicsListConfig:
    def __init__(self, context_configurations: ContextConfigurations):
        self.context_configurations = context_configurations

    def set_topics_list(self, topics):
        self.context_configurations.set_topics_list(topics)

    def get_topics_list(self):
        return self.context_configurations.get_topics_list()

    def add_topic(self, topic):
        self.context_configurations.add_topic(topic)

    def remove_topic(self, topic):
        self.context_configurations.remove_topic(topic)


class ContextUpdateEventPusher:
    def __init__(self, topics_list_config: TopicsListConfig, nats_url="nats://localhost:4222"):
        self.topics_list_config = topics_list_config
        self.nats_url = nats_url
        self.nc = None

    async def _connect_nats(self):
        try:
            self.nc = await nats.connect(self.nats_url)
            logger.info(f"Connected to NATS at {self.nats_url}")
        except Exception as e:
            logger.error(f"Error connecting to NATS: {e}")
            raise

    async def _disconnect_nats(self):
        if self.nc:
            await self.nc.close()
            logger.info("Disconnected from NATS.")

    def push_update(self, operation):
        try:
            asyncio.run(self._push_update_async(operation))
        except Exception as e:
            logger.error(f"Error pushing update: {e}")
            raise

    async def _push_update_async(self, operation):
        if not self.nc:
            await self._connect_nats()

        operation = {
            "event_type": "context_update",
            "sender_subject_id": os.getenv("SUBJECT_ID"),
            "event_data": operation
        }

        try:
            topics = self.topics_list_config.get_topics_list()
            if not topics:
                logger.warning("No topics to push updates to.")

            for topic in topics:
                try:
                    await self.nc.publish(topic, json.dumps(operation).encode())
                    logger.info(f"Update pushed to topic {topic}.")
                except Exception as e:
                    logger.error(f"Error pushing update to topic {topic}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error pushing update: {e}")
            raise
        finally:
            await self._disconnect_nats()
