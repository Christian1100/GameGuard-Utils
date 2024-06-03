import aiohttp


async def post(url: str, headers: dict):
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            if response.status != 200:
                return None
            return await response.json()
