from __future__ import annotations

import asyncio
import random
import re
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

import httpx

DATA_SEC_BASE_URL = "https://data.sec.gov"
WWW_SEC_BASE_URL = "https://www.sec.gov"
DEFAULT_CACHE_SIZE = 1000


_RETRY_STATUS_CODES = frozenset({429, 503})
_RETRY_MAX_ATTEMPTS = 6
_RETRY_BASE_DELAY_S = 1.0
_RETRY_MAX_DELAY_S = 30.0


class _LRUCache:
    def __init__(self, max_size: int) -> None:
        self._max_size = max(max_size, 1)
        self._items: OrderedDict[str, Any] = OrderedDict()

    def get(self, key: str) -> Any | None:
        if key not in self._items:
            return None
        value = self._items.pop(key)
        self._items[key] = value
        return value

    def set(self, key: str, value: Any) -> None:
        if key in self._items:
            self._items.pop(key)
        self._items[key] = value
        if len(self._items) > self._max_size:
            self._items.popitem(last=False)


@dataclass(frozen=True)
class FilingDocument:
    primary_document: str
    text: str


class EdgarClient:
    def __init__(self, *, user_agent: str, cache_size: int = DEFAULT_CACHE_SIZE) -> None:
        if not user_agent.strip():
            raise RuntimeError("SEC_USER_AGENT is required for SEC EDGAR tools")
        self._client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "User-Agent": user_agent,
                "Accept-Encoding": "gzip, deflate",
            },
            follow_redirects=True,
        )
        self._json_cache = _LRUCache(cache_size)
        self._text_cache = _LRUCache(cache_size)
        self._ticker_entries: list[dict[str, Any]] | None = None

    async def close(self) -> None:
        await self._client.aclose()

    async def preload_ticker_map(self) -> None:
        await self._load_ticker_entries()

    async def resolve_cik(self, query: str) -> str:
        cleaned = query.strip()
        if not cleaned:
            raise RuntimeError("Company query is required")

        cik_match = re.fullmatch(r"(?:CIK)?\s*0*(\d{1,10})", cleaned, re.IGNORECASE)
        if cik_match:
            return cik_match.group(1).zfill(10)

        query_lower = cleaned.lower()
        entries = await self._load_ticker_entries()
        for entry in entries:
            if str(entry.get("ticker", "")).lower() == query_lower:
                return _format_cik(entry["cik_str"])

        for entry in entries:
            company_name = str(entry.get("title", "")).lower()
            if query_lower in company_name or company_name in query_lower:
                return _format_cik(entry["cik_str"])

        raise RuntimeError(f"No company found for {query!r}. Try a ticker symbol or CIK number.")

    async def fetch_submissions(self, cik: str) -> dict[str, Any]:
        return await self._get_json(f"{DATA_SEC_BASE_URL}/submissions/CIK{_format_cik(cik)}.json")

    async def fetch_company_facts(self, cik: str) -> dict[str, Any]:
        return await self._get_json(
            f"{DATA_SEC_BASE_URL}/api/xbrl/companyfacts/CIK{_format_cik(cik)}.json"
        )

    async def fetch_filing_document(self, cik: str, accession_number: str) -> FilingDocument:
        formatted_cik = _format_cik(cik)
        primary_document = await self._find_primary_document(formatted_cik, accession_number)
        accession_compact = normalize_accession(accession_number).replace("-", "")
        url = (
            f"{WWW_SEC_BASE_URL}/Archives/edgar/data/{int(formatted_cik)}/"
            f"{accession_compact}/{primary_document}"
        )
        return FilingDocument(
            primary_document=primary_document,
            text=await self._get_text(url),
        )

    async def _find_primary_document(self, cik: str, accession_number: str) -> str:
        normalized_accession = normalize_accession(accession_number)
        accession_compact = normalized_accession.replace("-", "")
        index = await self._get_json(
            f"{WWW_SEC_BASE_URL}/Archives/edgar/data/{int(cik)}/{accession_compact}/index.json"
        )

        submissions = await self.fetch_submissions(cik)
        recent = submissions.get("filings", {}).get("recent", {})
        accession_numbers = list(recent.get("accessionNumber", []))
        primary_documents = list(recent.get("primaryDocument", []))
        for index_position, accession in enumerate(accession_numbers):
            if accession == normalized_accession and index_position < len(primary_documents):
                primary = str(primary_documents[index_position])
                if primary:
                    return primary

        candidates = _index_document_names(index)
        for name in candidates:
            lower = name.lower()
            if lower.endswith((".htm", ".html")) and not lower.startswith("ex"):
                return name
        for name in candidates:
            if name.lower().endswith((".txt", ".htm", ".html", ".xml")):
                return name

        raise RuntimeError(f"No primary document found for accession {accession_number!r}")

    async def _load_ticker_entries(self) -> list[dict[str, Any]]:
        if self._ticker_entries is None:
            ticker_map = await self._get_json(f"{WWW_SEC_BASE_URL}/files/company_tickers.json")
            if isinstance(ticker_map, dict):
                self._ticker_entries = [
                    item for item in ticker_map.values() if isinstance(item, dict)
                ]
            elif isinstance(ticker_map, list):
                self._ticker_entries = [item for item in ticker_map if isinstance(item, dict)]
            else:
                raise RuntimeError("SEC ticker map returned an unexpected payload")
        return self._ticker_entries

    async def _get_json(self, url: str) -> Any:
        cached = self._json_cache.get(url)
        if cached is not None:
            return cached
        response = await self._request_with_retry(url)
        payload = response.json()
        self._json_cache.set(url, payload)
        return payload

    async def _get_text(self, url: str) -> str:
        cached = self._text_cache.get(url)
        if cached is not None:
            return str(cached)
        response = await self._request_with_retry(url)
        text = response.text
        self._text_cache.set(url, text)
        return text

    async def _request_with_retry(self, url: str) -> httpx.Response:
        """GET with exponential backoff on 429/503 (SEC rate-limit / overload)."""
        for attempt in range(_RETRY_MAX_ATTEMPTS):
            response = await self._client.get(url)
            if response.status_code in _RETRY_STATUS_CODES:
                if attempt == _RETRY_MAX_ATTEMPTS - 1:
                    response.raise_for_status()
                delay = min(_RETRY_BASE_DELAY_S * (2**attempt), _RETRY_MAX_DELAY_S)
                delay += random.uniform(0, delay)
                await asyncio.sleep(delay)
                continue
            response.raise_for_status()
            return response
        raise RuntimeError(f"SEC EDGAR retries exhausted for {url}")


def normalize_accession(accession_number: str) -> str:
    compact = accession_number.replace("-", "").strip()
    if not re.fullmatch(r"\d{18}", compact):
        raise RuntimeError(f"Invalid SEC accession number: {accession_number!r}")
    return f"{compact[:10]}-{compact[10:12]}-{compact[12:]}"


def _format_cik(value: Any) -> str:
    return str(int(str(value).strip())).zfill(10)


def _index_document_names(index_payload: dict[str, Any]) -> list[str]:
    items = index_payload.get("directory", {}).get("item", [])
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list):
        return []
    names: list[str] = []
    for item in items:
        if isinstance(item, dict) and item.get("name"):
            names.append(str(item["name"]))
    return names
