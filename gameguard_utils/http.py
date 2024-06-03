import aiohttp
from typing import Optional


async def get(url: str, headers: dict):
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            if response.status != 200:
                return None
            return await response.json()


async def post(url: str, headers: dict, body: Optional[dict] = None):
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers) as response:
            if response.status != 200:
                return None
            return await response.json()


async def put(url: str, headers: dict, body: Optional[dict] = None):
    async with aiohttp.ClientSession() as session:
        async with session.put(url, json=body, headers=headers) as response:
            if response.status != 200:
                return None
            return await response.json()
