import aiohttp
from typing import Optional, Any


async def get(url: str, headers: Optional[dict[str, str]] = None, params: Optional[dict[str, Any]] = None):
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, params=params) as response:
            if response.status != 200:
                return None
            return await response.json()


async def post(url: str, headers: Optional[dict] = None, params: Optional[dict[str, Any]] = None, body: Optional[dict] = None):
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=body, headers=headers, params=params) as response:
            if response.status != 200:
                return None
            return await response.json()


async def put(url: str, headers: Optional[dict] = None, params: Optional[dict[str, Any]] = None, body: Optional[dict] = None):
    async with aiohttp.ClientSession() as session:
        async with session.put(url, json=body, headers=headers, params=params) as response:
            if response.status != 200:
                return None
            return await response.json()

async def delete(url: str, headers: Optional[dict] = None, params: Optional[dict[str, Any]] = None):
    async with aiohttp.ClientSession() as session:
        async with session.delete(url, headers=headers, params=params) as response:
            if response.status != 200:
                return None
            return await response.json()
            
