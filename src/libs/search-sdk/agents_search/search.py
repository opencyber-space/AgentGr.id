from __future__ import annotations

import logging
from typing import Dict, Optional, Any, List, Sequence

from .aios import AIOSSearchSelectorAPI
from .custom import BaseSearchSelector  # your abstract base for selectors


class AgentSearchSelector:
   

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self._logger = logger or logging.getLogger(self.__class__.__name__)
        self._registry: Dict[str, BaseSearchSelector] = {}

    # ---------- Registration ----------

    def register_new_selector(
        self,
        *,
        name: str,
        model: str,
        inference_server_id: str,
        aios_url_map: Dict[str, str],
        system_message: str = "",
        session_id: Optional[str] = None,
        overwrite: bool = False,
        logger: Optional[logging.Logger] = None,
    ) -> BaseSearchSelector:
        """
        Create and register an AIOS-backed selector under `name`.
        """
        if not overwrite and name in self._registry:
            raise ValueError(f"Selector '{name}' already exists")

        sel = AIOSSearchSelectorAPI(
            model=model,
            inference_server_id=inference_server_id,
            aios_url_map=aios_url_map,
            system_message=system_message,
            session_id=session_id,
            logger=logger or self._logger.getChild(f"sel:{name}"),
        )
        self._registry[name] = sel
        self._logger.debug("Registered AIOSSearchSelectorAPI as '%s'", name)
        return sel

    def register_custom_selector(
        self,
        *,
        name: str,
        selector: BaseSearchSelector,
        overwrite: bool = False,
    ) -> None:
        """
        Register a preconstructed selector that implements BaseSearchSelector.
        """
        if not isinstance(selector, BaseSearchSelector):
            raise TypeError("selector must be an instance of BaseSearchSelector")

        if not overwrite and name in self._registry:
            raise ValueError(f"Selector '{name}' already exists")

        self._registry[name] = selector
        self._logger.debug(
            "Registered custom selector as '%s' (%s)", name, selector.__class__.__name__
        )

    # ---------- Accessors ----------

    def get_selector(self, name: str) -> BaseSearchSelector:
        try:
            return self._registry[name]
        except KeyError:
            raise KeyError(f"Selector '{name}' not found")

    def has_selector(self, name: str) -> bool:
        return name in self._registry

    def list_selectors(self) -> List[str]:
        return list(self._registry.keys())

    # ---------- Removal ----------

    def unregister_selector(self, name: str) -> None:
        try:
            del self._registry[name]
            self._logger.debug("Unregistered selector '%s'", name)
        except KeyError:
            raise KeyError(f"Selector '{name}' not found")

    def clear_selectors(self) -> None:
        self._registry.clear()
        self._logger.debug("Cleared all registered selectors")


    def select_item(
        self,
        *,
        name: str,
        items: Sequence[Dict[str, Any]],
        id_key: str = "id",
        query: Optional[str] = None,
        fields_to_show: Optional[List[str]] = None,
        # model params (kept consistent with your other APIs)
        temperature: float = 0.0,
        top_p: float = 0.95,
        max_tokens: int = 512,
        system_message: Optional[str] = None,
        # passthrough to provider (e.g., seq_no, extra_headers):
        **provider_kwargs: Any,
    ) -> str:
       
        sel = self.get_selector(name)
        self._logger.debug(
            "Selecting item using '%s' with items=%d, id_key=%s, query_present=%s",
            name, len(items), id_key, bool(query),
        )
        return sel.select_item(
            items=items,
            id_key=id_key,
            query=query,
            fields_to_show=fields_to_show,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            system_message=system_message,
            **provider_kwargs,
        )
    
    def search_from_objects(
        self,
        *,
        name: str,
        objects: Sequence[Any],
        id_attr: str = "id",
        query: Optional[str] = None,
        fields_to_show: Optional[List[str]] = None,
        temperature: float = 0.0,
        top_p: float = 0.95,
        max_tokens: int = 512,
        system_message: Optional[str] = None,
        **provider_kwargs: Any,
    ) -> str:
       
        items: List[Dict[str, Any]] = []
        for i, obj in enumerate(objects):
            if not hasattr(obj, id_attr):
                raise ValueError(f"Object {i} missing required attr '{id_attr}'")
            if not hasattr(obj, "get_searchable_representation"):
                raise ValueError(f"Object {i} missing get_searchable_representation()")

            items.append({
                "id": str(getattr(obj, id_attr)),
                "representation": obj.get_searchable_representation(),
            })

        return self.select_item(
            name=name,
            items=items,
            id_key="id",
            query=query,
            fields_to_show=(fields_to_show or ["representation"]),
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            system_message=system_message,
            **provider_kwargs,
        )

