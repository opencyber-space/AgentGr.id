from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence

from .aios import AIOSEmbeddingsAPI     
from .custom import BaseEmbeddingsGenerator


class AgentEmbeddingsManager:
   

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self._logger = logger or logging.getLogger(self.__class__.__name__)
        self._registry: Dict[str, BaseEmbeddingsGenerator] = {}

    # ---------- Registration ----------

    def register_new_generator(
        self,
        *,
        name: str,
        model: str,
        inference_server_id: str,
        aios_url_map: Dict[str, str],
        session_id: Optional[str] = None,
        overwrite: bool = False,
        logger: Optional[logging.Logger] = None,
        default_mode: str = "embedding",
    ) -> BaseEmbeddingsGenerator:
        """
        Create and register an AIOS-backed embeddings generator under `name`.
        """
        if not overwrite and name in self._registry:
            raise ValueError(f"Generator '{name}' already exists")

        gen = AIOSEmbeddingsAPI(
            model=model,
            inference_server_id=inference_server_id,
            aios_url_map=aios_url_map,
            session_id=session_id,
            logger=logger or self._logger.getChild(f"emb:{name}"),
            default_mode=default_mode,
        )
        self._registry[name] = gen
        self._logger.debug("Registered AIOSEmbeddingsAPI as '%s'", name)
        return gen

    def register_custom_generator(
        self,
        *,
        name: str,
        generator: BaseEmbeddingsGenerator,
        overwrite: bool = False,
    ) -> None:
       
        if not isinstance(generator, BaseEmbeddingsGenerator):
            raise TypeError("generator must be an instance of BaseEmbeddingsGenerator")

        if not overwrite and name in self._registry:
            raise ValueError(f"Generator '{name}' already exists")

        self._registry[name] = generator
        self._logger.debug(
            "Registered custom embeddings generator as '%s' (%s)", name, generator.__class__.__name__
        )

    # ---------- Accessors ----------

    def get_generator(self, name: str) -> BaseEmbeddingsGenerator:
        try:
            return self._registry[name]
        except KeyError:
            raise KeyError(f"Generator '{name}' not found")

    def has_generator(self, name: str) -> bool:
        return name in self._registry

    def list_generators(self) -> List[str]:
        return list(self._registry.keys())

    # ---------- Removal ----------

    def unregister_generator(self, name: str) -> None:
        try:
            del self._registry[name]
            self._logger.debug("Unregistered embeddings generator '%s'", name)
        except KeyError:
            raise KeyError(f"Generator '{name}' not found")

    def clear_generators(self) -> None:
        self._registry.clear()
        self._logger.debug("Cleared all registered embeddings generators")

    # ---------- Embeddings ----------

    def embed_texts(
        self,
        *,
        name: str,
        texts: Sequence[str],
        batch_size: int = 0,
        # passthrough (e.g., seq_no, extra_headers, mode, and any gen_params)
        **provider_kwargs: Any,
    ) -> List[List[float]]:
        gen = self.get_generator(name)
        self._logger.debug(
            "Embedding texts using '%s' (count=%d, batch_size=%s)",
            name, len(texts), batch_size or "all"
        )
        return gen.embed_texts(texts, batch_size=batch_size, **provider_kwargs)

    def embed_objects(
        self,
        *,
        name: str,
        objects: Sequence[Any],
        id_attr: str = "id",
        rep_method: str = "get_searchable_representation",
        batch_size: int = 0,
        # passthrough (e.g., seq_no, extra_headers, mode, and any gen_params)
        **provider_kwargs: Any,
    ) -> Dict[str, List[float]]:
        gen = self.get_generator(name)
        self._logger.debug(
            "Embedding objects using '%s' (count=%d, id_attr=%s, rep_method=%s, batch_size=%s)",
            name, len(objects), id_attr, rep_method, batch_size or "all"
        )
        return gen.embed_objects(
            objects,
            id_attr=id_attr,
            rep_method=rep_method,
            batch_size=batch_size,
            **provider_kwargs,
        )
