import random
import time
import logging
from typing import List, Dict, Optional
import aiohttp
from aiohttp_socks import ProxyConnector
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class Proxy(BaseModel):
    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None
    failures: int = 0
    last_used: float = 0

class ProxyManager:
    def __init__(self, rotation_interval: int = 300, max_failures: int = 3):
        self.proxies: List[Proxy] = []
        self.rotation_interval = rotation_interval
        self.max_failures = max_failures
        self.current_proxy: Optional[Proxy] = None

    def add_proxy(self, proxy: Dict):
        """Add a new proxy to the pool"""
        self.proxies.append(Proxy(**proxy))

    def get_proxy(self) -> Optional[Proxy]:
        """Get next available proxy"""
        now = time.time()
        available_proxies = [
            p for p in self.proxies
            if p.failures < self.max_failures and
               (now - p.last_used) > self.rotation_interval
        ]

        if not available_proxies:
            logger.warning("No available proxies")
            return None

        proxy = random.choice(available_proxies)
        proxy.last_used = now
        self.current_proxy = proxy
        return proxy

    def mark_failed(self, proxy: Proxy):
        """Mark proxy as failed"""
        proxy.failures += 1
        logger.warning(f"Proxy {proxy.host}:{proxy.port} failed. Total failures: {proxy.failures}")

    async def get_connector(self) -> ProxyConnector:
        """Get aiohttp connector with proxy"""
        proxy = self.get_proxy()
        if not proxy:
            return aiohttp.TCPConnector()

        return ProxyConnector.from_url(
            f"socks5://{proxy.username}:{proxy.password}@{proxy.host}:{proxy.port}"
            if proxy.username and proxy.password
            else f"socks5://{proxy.host}:{proxy.port}"
        )