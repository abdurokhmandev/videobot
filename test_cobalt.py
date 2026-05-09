import aiohttp
import asyncio
import json

async def main():
    async with aiohttp.ClientSession() as s:
        async with s.post(
            'https://api.cobalt.tools/',
            headers={
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            },
            json={'url': 'https://www.instagram.com/reel/DXtMS9ACAmg/'}
        ) as r:
            print(r.status)
            print(await r.text())

asyncio.run(main())
