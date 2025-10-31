from __future__ import annotations

import sys
import os
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple, Type, Union

from scrapy import Spider, Request
from scrapy.crawler import CrawlerProcess
from scrapy.http import Response
from scrapy.utils.project import get_project_settings


CallableParse = Callable[[Response], Iterable[Union[Dict[str, Any], Request]]]
PipelineCallable = Callable[[Dict[str, Any], Spider], Dict[str, Any]]


class _FuncPipeline:
    def __init__(self, func: PipelineCallable):
        self._func = func

    def process_item(self, item, spider):
        return self._func(item, spider)


class ScrapySDK:
    """
    A light SDK around Scrapy that lets you:
      - Quickly crawl with an ad-hoc spider (sync).
      - Register pipelines & middlewares without full Scrapy scaffolding.
      - Tune common settings (UA, proxies, robots, retries, concurrency, AutoThrottle).
      - Export to feeds (JSON/CSV/NDJSON) or collect items in-memory.

    Typical usage:
        sdk = ScrapySDK().set_user_agent("MyBot/1.0").enable_autothrottle()
        items = sdk.fetch(
            ["https://example.com"],
            parse=lambda r: [{"url": r.url, "title": r.css("title::text").get()}]
        )
    """

    def __init__(
        self,
        *,
        base_settings: Optional[Dict[str, Any]] = None,
        log_level: str = "INFO",
    ) -> None:
        default = {
            "BOT_NAME": "scrapy_sdk",
            "ROBOTSTXT_OBEY": True,
            "CONCURRENT_REQUESTS": 8,
            "DOWNLOAD_DELAY": 0,
            "RETRY_ENABLED": True,
            "RETRY_TIMES": 2,
            "FEED_EXPORT_ENCODING": "utf-8",
            "LOG_LEVEL": log_level,
            # sane timeouts
            "DOWNLOAD_TIMEOUT": 30,
            "DNS_TIMEOUT": 10,
            # avoid noisy telnet console
            "TELNETCONSOLE_ENABLED": False,
        }
        if base_settings:
            default.update(base_settings)

        self._settings = default
        self._pipelines: List[Tuple[int, Union[Type, PipelineCallable]]] = []
        self._downloader_mw: List[Tuple[int, Type]] = []
        self._spider_mw: List[Tuple[int, Type]] = []
        self._feeds: Dict[str, Dict[str, Any]] = {}
        self._items_collector_enabled = False

    # ------------------------- Popular settings -------------------------

    def set_user_agent(self, ua: str) -> "ScrapySDK":
        self._settings["DEFAULT_REQUEST_HEADERS"] = {"User-Agent": ua}
        return self

    def set_proxies(self, *, http: Optional[str] = None, https: Optional[str] = None) -> "ScrapySDK":
        """
        Simple proxy support via environment variables understood by Requests-like middlewares.
        For advanced proxy rotation, add a downloader middleware instead.
        """
        if http:
            os.environ["http_proxy"] = http
            os.environ["HTTP_PROXY"] = http
        if https:
            os.environ["https_proxy"] = https
            os.environ["HTTPS_PROXY"] = https
        return self

    def obey_robots(self, obey: bool = True) -> "ScrapySDK":
        self._settings["ROBOTSTXT_OBEY"] = obey
        return self

    def set_concurrency(
        self,
        *,
        requests: int = 8,
        per_domain: Optional[int] = None,
        per_ip: Optional[int] = None,
        delay: float = 0.0,
    ) -> "ScrapySDK":
        self._settings["CONCURRENT_REQUESTS"] = requests
        if per_domain is not None:
            self._settings["CONCURRENT_REQUESTS_PER_DOMAIN"] = per_domain
        if per_ip is not None:
            self._settings["CONCURRENT_REQUESTS_PER_IP"] = per_ip
        self._settings["DOWNLOAD_DELAY"] = delay
        return self

    def set_retry(self, *, enabled: bool = True, times: int = 2, http_codes: Optional[Sequence[int]] = None) -> "ScrapySDK":
        self._settings["RETRY_ENABLED"] = enabled
        self._settings["RETRY_TIMES"] = times
        if http_codes is not None:
            self._settings["RETRY_HTTP_CODES"] = list(http_codes)
        return self

    def enable_autothrottle(
        self,
        *,
        start_delay: float = 1.0,
        max_delay: float = 10.0,
        target_concurrency: float = 1.0,
        debug: bool = False,
    ) -> "ScrapySDK":
        self._settings.update(
            {
                "AUTOTHROTTLE_ENABLED": True,
                "AUTOTHROTTLE_START_DELAY": start_delay,
                "AUTOTHROTTLE_MAX_DELAY": max_delay,
                "AUTOTHROTTLE_TARGET_CONCURRENCY": target_concurrency,
                "AUTOTHROTTLE_DEBUG": debug,
            }
        )
        return self

    def set_cookies(self, *, enabled: bool = True) -> "ScrapySDK":
        self._settings["COOKIES_ENABLED"] = enabled
        return self

    def set_download_timeout(self, seconds: int) -> "ScrapySDK":
        self._settings["DOWNLOAD_TIMEOUT"] = seconds
        return self

    # ------------------------- Feeds & outputs -------------------------

    def add_feed(
        self,
        uri: str,
        *,
        fmt: str = "json",
        overwrite: bool = True,
        fields: Optional[Sequence[str]] = None,
        indent: Optional[int] = None,
    ) -> "ScrapySDK":
        """
        Add a feed export target, e.g.:
            sdk.add_feed("out.json", fmt="json")
            sdk.add_feed("s3://bucket/path.ndjson", fmt="jsonlines")
            sdk.add_feed("out.csv", fmt="csv", fields=["url","title"])
        """
        self._feeds[uri] = {
            "format": fmt,
            "overwrite": overwrite,
            **({"fields": list(fields)} if fields else {}),
            **({"indent": indent} if indent is not None else {}),
        }
        return self

    def collect_items_in_memory(self, enabled: bool = True) -> "ScrapySDK":
        """Collect scraped items into a list returned by .crawl() / .fetch()."""
        self._items_collector_enabled = enabled
        return self

    # ------------------------- Pipelines & Middlewares -------------------------

    def add_pipeline(self, pipeline: Union[Type, PipelineCallable], *, order: int = 300) -> "ScrapySDK":
        """
        Add a pipeline either as a class or a simple function(item, spider)->item.
        Order: lower runs earlier.
        """
        self._pipelines.append((order, pipeline))
        return self

    def add_downloader_middleware(self, mw_class: Type, *, order: int = 543) -> "ScrapySDK":
        self._downloader_mw.append((order, mw_class))
        return self

    def add_spider_middleware(self, mw_class: Type, *, order: int = 543) -> "ScrapySDK":
        self._spider_mw.append((order, mw_class))
        return self

    # ------------------------- Spider creation -------------------------

    def make_spider(
        self,
        name: str,
        *,
        start_urls: Sequence[str],
        allowed_domains: Optional[Sequence[str]] = None,
        headers: Optional[Dict[str, str]] = None,
        parse: Optional[CallableParse] = None,
        handle_err: Optional[Callable[[Response], None]] = None,
        custom_settings: Optional[Dict[str, Any]] = None,
    ) -> Type[Spider]:
        """
        Build a minimal Spider class dynamically.
        `parse` should yield dict items or Request objects.
        """

        headers = headers or {}

        def _start_requests(self: Spider):
            for u in start_urls:
                yield Request(u, headers=headers)

        def _parse(self: Spider, response: Response):
            if parse:
                yield from parse(response)
            else:
                # Default: return page URL + <title>
                title = response.css("title::text").get()
                yield {"url": response.url, "title": title}

        attrs = {
            "name": name,
            "start_requests": _start_requests,
            "parse": _parse,
        }
        if allowed_domains:
            attrs["allowed_domains"] = list(allowed_domains)
        if custom_settings:
            attrs["custom_settings"] = custom_settings
        if handle_err:
            attrs["errback"] = handle_err  # used when scheduling Requests with errback

        return type(name, (Spider,), attrs)

    # ------------------------- Running crawls -------------------------

    def _build_settings(self) -> Dict[str, Any]:
        s = dict(self._settings)
        module = sys.modules[self.__class__.__module__]  # where ScrapySDK is defined

        # Pipelines
        if self._pipelines:
            pipelines_sorted = sorted(self._pipelines, key=lambda t: t[0])
            pipeline_dict = {}
            for order, pipe in pipelines_sorted:
                if callable(pipe) and not isinstance(pipe, type):
                    # Wrap function in a unique class AND register it in the module's globals
                    cls_name = f"FuncPipeline_{id(pipe)}"
                    cls = type(cls_name, (_FuncPipeline,), {"__init__": lambda s: _FuncPipeline.__init__(s, pipe)})
                    setattr(module, cls_name, cls)  # <-- make importable by path
                    pipeline_dict[f"{module.__name__}.{cls_name}"] = order
                else:
                    pipeline_dict[f"{pipe.__module__}.{pipe.__name__}"] = order
            s["ITEM_PIPELINES"] = pipeline_dict

        # Middlewares
        if self._downloader_mw:
            d = {}
            for order, mw in sorted(self._downloader_mw, key=lambda t: t[0]):
                d[f"{mw.__module__}.{mw.__name__}"] = order
            s["DOWNLOADER_MIDDLEWARES"] = d

        if self._spider_mw:
            d = {}
            for order, mw in sorted(self._spider_mw, key=lambda t: t[0]):
                d[f"{mw.__module__}.{mw.__name__}"] = order
            s["SPIDER_MIDDLEWARES"] = d

        if self._feeds:
            s["FEEDS"] = self._feeds

        return s

   
    def crawl(
        self,
        spiders: Union[Type[Spider], Sequence[Type[Spider]]],
        *,
        return_items: bool | None = None,
    ) -> List[Dict[str, Any]]:
        """
        Run one or many spiders synchronously.
        Returns collected items if enabled.
        """
        spiders = [spiders] if isinstance(spiders, type) else list(spiders)

        items: List[Dict[str, Any]] = []
        settings = self._build_settings()

        # Attach function pipelines (instances) if any
        # Scrapy instantiates pipeline classes; for function pipelines we need to
        # expose them via from_crawler. The simple approach is to monkey-patch the class.
        func_pipelines: List[Type[_FuncPipeline]] = []
        for order, pipe in self._pipelines:
            if callable(pipe) and not isinstance(pipe, type):
                cls = type(f"FuncPipeline_{id(pipe)}", (_FuncPipeline,), {"__init__": lambda s: _FuncPipeline.__init__(s, pipe)})
                func_pipelines.append(cls)

        # Optional built-in collector pipeline
        collect = self._items_collector_enabled if return_items is None else return_items
        if collect:
            def _collector(item, spider):
                items.append(dict(item))
                return item
            self.add_pipeline(_collector, order=299)  # ensure before user 300

            settings = self._build_settings()  # rebuild with collector

        # Build process each time (safe sync API)
        process = CrawlerProcess(settings=settings or get_project_settings())

        for sp in spiders:
            process.crawl(sp)

        process.start()  # blocks until all crawlers finish
        return items

    def fetch(
        self,
        start_urls: Sequence[str],
        *,
        parse: Optional[CallableParse] = None,
        allowed_domains: Optional[Sequence[str]] = None,
        headers: Optional[Dict[str, str]] = None,
        custom_settings: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
      
        SpiderCls = self.make_spider(
            name="sdk_tmp_spider",
            start_urls=start_urls,
            allowed_domains=allowed_domains,
            headers=headers,
            parse=parse,
            custom_settings=custom_settings,
        )
        self.collect_items_in_memory(True)
        return self.crawl(SpiderCls, return_items=True)
