"""Small async JSON transport. Credentials and response bodies never enter errors."""
import asyncio
import aiohttp

class RemoteError(RuntimeError):
    def __init__(self, service, status):
        self.status = status
        super().__init__(f'{service}: HTTP {status}; check access/settings or service status')

class JSONClient:
    def __init__(self, base_url, headers, service):
        self.base_url = base_url.rstrip('/')
        self.headers = headers
        self.service = service
        self.session = None

    async def close(self):
        if self.session:
            await self.session.close()
            self.session = None

    async def request(self, method, path, *, params=None, payload=None, headers=None, retry=False):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=100))
        for attempt in range(3 if retry else 1):
            try:
                async with self.session.request(method, self.base_url + path,
                    headers={**self.headers, **(headers or {})}, params=params, json=payload) as response:
                    if response.status >= 400:
                        if retry and response.status in (429, 500, 502, 503, 504, 529) and attempt < 2:
                            await asyncio.sleep(2 ** attempt)
                            continue
                        raise RemoteError(self.service, response.status)
                    if response.status == 204:
                        return None
                    raw = await response.text()
                    if not raw:
                        return None
                    import json
                    return json.loads(raw)
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                if retry and attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise RuntimeError(f'{self.service}: connection failed or timed out') from None
        raise RuntimeError(f'{self.service}: retries exhausted')
