import asyncio
import json
import logging
import random
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress

import aiohttp
from bs4 import BeautifulSoup
from duckduckgo_search import AsyncDDGS
from googlesearch import search

import trafilatura
from openai import AsyncClient
from trafilatura import extract

import discord
from typing import Optional, List

from .character_messages import CharacterMessages
from .moderation import violates_text_tos


SEARCH_LIMIT = 10
WEBSITE_LIMIT = 5000
BROWSING_LIMIT = 5000 * SEARCH_LIMIT
MAX_CONCURRENT_TASKS = 50
MAX_RETRIES = 3
BACKOFF_FACTOR = 1


executor = ThreadPoolExecutor(max_workers=20)


class AIBrowser:
    def __init__(self, bot, openai_client: AsyncClient, timeout: float = 1):
        self.bot = bot
        self.timeout = timeout
        
        self.semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)

        self.client: AsyncClient = openai_client

    async def get_browsing_response(
        self,
        question: str,
        image_count: int,
        messages: List[dict],
        match_history: CharacterMessages,
        stream: Optional[bool] = True,
        moderate: Optional[bool] = True,
    ):
        if moderate:
            reject = await violates_text_tos(client=self.client, prompt=question, allow_nsfw=False)
            if reject:
                return None, None

        website_data = []
        available_websites = await self.fetch_available_websites(question)
        if available_websites:
            tasks = [self.limited_web_scraper(url) for url in available_websites]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, str):
                    website_data.append(result[:WEBSITE_LIMIT])
                elif isinstance(result, Exception):
                    pass

        clean_website_data = json.dumps(", ".join(website_data))[:BROWSING_LIMIT] if website_data else "No data found"

        image_urls = []
        if image_count > 0:
            with suppress(Exception):
                available_images = await AsyncDDGS().aimages(question, max_results=SEARCH_LIMIT)
                selected_images = random.sample(available_images, min(image_count, len(available_images)))
                image_urls = [img.get("image") for img in selected_images]

        if moderate:
            reject = await violates_text_tos(client=self.client, prompt=clean_website_data, allow_nsfw=False, threshold=0.6)
            if reject:
                return None, None

        current_image_count = len(image_urls)
        image_description = (
            f"Mention in your response that you have sent {current_image_count} images matching the question or the requested images."
            if current_image_count > 0
            else ""
        )

        current_datetime = discord.utils.utcnow()
        weekday = current_datetime.strftime("%A")
        formatted_datetime = current_datetime.strftime(f"%Y-%m-%d %H:%M ({weekday})")

        browsing_prompt = f"""
                You are an AI assistant tasked with analyzing and summarizing information from multiple websites to answer the user's question: {question}. The current date and time is: **{formatted_datetime}**. 

                ### Context
                You will receive:
                1. **Match History**: A detailed record of the user's ongoing conversation and the question or topic to be addressed.
                2. **Website Data**: Information extracted from multiple websites, provided in the format `url: content`, separated by commas.

                ### Website Data
                Here is the content from the websites:
                {clean_website_data}

                ### Instructions
                1. **Primary Objective**:
                    - Use the content from the provided websites to construct a detailed, accurate, and relevant response to the user's question or topic from the match history.
                    - Cross-check information across sources to resolve discrepancies and determine the most credible and up-to-date answer.

                2. **Handling Conflicting Information**:
                    - If the sources provide conflicting information:
                        - Prioritize the **most credible and recent sources**, considering the timestamps or publication dates of the content.
                        - Explain discrepancies clearly if they cannot be resolved, but aim to provide a single, cohesive answer whenever possible.
                    - Mention if the information cannot be definitively determined, but minimize such cases.

                3. **Time-Sensitive Information**:
                    - Pay attention to dates and times mentioned in the website content. Evaluate their relevance based on the **current date and time** ({formatted_datetime}).
                    - Ensure that **time sequences** are logically consistent. For example, avoid presenting an event occurring in the past as if it happens in the future or vice versa.
                    - Always cross-verify and ensure that events or releases are presented in the **correct chronological order**, reflecting their actual sequence based on the provided dates.

                4. **Formatting Guidelines**:
                    - Use **clear sections and paragraphs**, separating key points with `\n`.
                    - Avoid leaving the response blank or vague. If no useful information is available, explicitly inform the user.

                5. **Credibility, Sources, and Clarity**:
                    - **It is mandatory** to provide a **list of raw URLs of the sources used** to substantiate your response. These must be included in the "sources" section of your output as an array. Maximum of 5 sources.
                    - Disregard content that appears speculative, outdated, or irrelevant to the user's query.
                    - Strive for precise and clear answers without omitting essential details.

                ### Additional Requirements
                - Your response must be in the same language as the question or topic presented in the match history. Ensure the language matches exactly, even for technical terms or phrases.
                - Double-check that all dates and timelines provided in the answer make logical sense relative to one another and to the current date ({formatted_datetime}). If inconsistencies arise in the sources, clarify and reconcile them where possible.
        """

        messages.append(
            {
                "role": "user",
                "content": f"{image_description} IMPORTANT: {browsing_prompt}",
            }
        )

        history_content = f"The researched website data are: {clean_website_data}"
        match_history.add_tool_message("Web-Browsing", history_content)

        if moderate:
            return (
                await self.client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=messages,
                    temperature=0.3,
                    stream=stream,
                    response_format=generate_schema(),
                ),
                image_urls,
            )
        else:
            f"{image_description} Data: {clean_website_data}", image_urls

    async def fetch_available_websites(self, question: str):
        search_methods = [
            (self.duckduckgo_search, "duckduckgo_search"),
            (self.google_search, "google_search"),
            (self.bing_search, "bing_search"),
            (self.yahoo_search, "yahoo_search"),
        ]
        random.shuffle(search_methods)

        for method, method_name in search_methods:
            try:
                available_websites = await method(question, max_results=SEARCH_LIMIT)
                if available_websites:
                    return available_websites
            except Exception as e:
                pass

        return []

    @staticmethod
    async def duckduckgo_search(query: str, max_results: int = 10) -> list:
        try:
            async with AsyncDDGS() as client:
                return [result.get("href") for result in await client.atext(query, max_results=max_results)]
        except Exception as e:
            return []

    async def google_search(self, query: str, max_results: int = 10) -> list:
        try:
            return await self.bot.loop.run_in_executor(None, lambda: list(search(query, num_results=max_results)))
        except Exception as e:
            return []

    @staticmethod
    async def bing_search(query: str, max_results: int = 10):
        query = query.replace(" ", "+")
        url = f"https://www.bing.com/search?q={query}&count={max_results}"
        headers = {"User-Agent": "Mozilla/5.0"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    html = await response.text()
                    soup = BeautifulSoup(html, "html.parser")
                    return [a["href"] for h2 in soup.find_all("h2") if (a := h2.find("a"))]
        except Exception as e:
            return []

    @staticmethod
    async def yahoo_search(query: str, max_results: int = 10):
        query = query.replace(" ", "+")
        url = f"https://search.yahoo.com/search?p={query}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        html_content = await response.text()
                        soup = BeautifulSoup(html_content, "html.parser")
                        return [a["href"] for a in soup.select(".dd.algo .title a")]
        except Exception as e:
            return []

    async def limited_web_scraper(self, url: str) -> Optional[str]:
        async with self.semaphore:
            return await self.web_scraper(url)

    async def web_scraper(self, url: str) -> Optional[str]:

        def start_scraping(current_url: str):
            try:
                downloaded = trafilatura.fetch_url(current_url)
                return extract(downloaded, include_comments=False, include_tables=True, no_fallback=True)
            except:
                return None

        try:
            scraped_data = await asyncio.wait_for(
                self.bot.loop.run_in_executor(executor, start_scraping, url), timeout=self.timeout
            )
            if scraped_data:
                return f"**Source URL:** {url}: {scraped_data}"
        except:
            pass

        return None


def generate_schema() -> dict:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "web_browsing",
            "strict": True,
            "schema": {
                "type": "object",
                "required": ["summary", "sources"],
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": (
                            "Provide a detailed summary that directly addresses the question or topic from the match history "
                            "by synthesizing and analyzing the provided website content. "
                            "IMPORTANT:\n"
                            "- Resolve discrepancies by prioritizing the most credible and recent sources. "
                            "- Clearly mention if conflicting information exists but aim to present a cohesive answer.\n"
                            "- Pay attention to dates/times in the content and evaluate their relevance based on the current date "
                            "and time. For historical questions, combine information logically.\n"
                            "- Use `\\n` for clear formatting with separate sections for key points.\n"
                            "- Never leave the summary blank; if no information is available, inform the user explicitly."
                        ),
                    },
                    "sources": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "description": "Raw URL of the source",
                        },
                        "description": (
                            "A list of raw URLs from sources extracted or referenced during the web browsing process. Maximum of 5 sources"
                        ),
                    },
                },
                "additionalProperties": False,
            },
        },
    }
