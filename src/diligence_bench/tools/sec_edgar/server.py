from __future__ import annotations

import html
import json
import logging
import os
import re
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from mcp.server.fastmcp import FastMCP

from diligence_bench.tools.sec_edgar.edgar_client import (
    DEFAULT_CACHE_SIZE,
    EdgarClient,
    normalize_accession,
)

logger = logging.getLogger(__name__)

DEFAULT_TOOL_OUTPUT_CHAR_BUDGET = 16000
TRUNCATION_SENTINEL = "... [truncated; use bash with grep -A/-B /path to inspect]"
STATEMENT_CONCEPTS = {
    "balance_sheet": {
        "Assets": ["Assets"],
        "Liabilities": ["Liabilities"],
        "StockholdersEquity": ["StockholdersEquity"],
    },
    "income_statement": {
        "Revenues": [
            "Revenues",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "SalesRevenueNet",
        ],
        "NetIncomeLoss": ["NetIncomeLoss"],
    },
    "cash_flow_statement": {
        "CashAndCashEquivalents": [
            "CashAndCashEquivalentsAtCarryingValue",
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        ],
        "CashFlowFromOperations": ["NetCashProvidedByUsedInOperatingActivities"],
    },
}


@dataclass
class _ServerContext:
    client: EdgarClient
    tool_output_char_budget: int

    async def close(self) -> None:
        await self.client.close()


_context: _ServerContext | None = None


@asynccontextmanager
async def _lifespan(server: FastMCP):
    del server
    try:
        context = _get_context()
        await context.client.preload_ticker_map()
        yield context
    finally:
        if _context is not None:
            await _context.close()


mcp = FastMCP("sec-edgar", lifespan=_lifespan)


@mcp.tool()
async def sec_filings(query: str, form_type: str = "10-Q", num_results: int = 5) -> str:
    """Search SEC EDGAR for company filings by ticker, CIK, or company name."""

    try:
        context = _get_context()
        cik = await context.client.resolve_cik(query)
        submissions = await context.client.fetch_submissions(cik)
        recent = submissions.get("filings", {}).get("recent", {})
        results = _filing_rows(
            company=str(submissions.get("name", "")),
            recent=recent,
            form_type=form_type,
            num_results=num_results,
        )
        return _truncate(json.dumps(results), context.tool_output_char_budget)
    except Exception as exc:
        logger.warning("sec_filings failed for %s: %s", query, exc)
        return json.dumps({"error": str(exc)})


@mcp.tool()
async def sec_filing_content(
    identifier: str,
    accession_number: str,
    item: str = "",
) -> str:
    """Fetch SEC filing content. Use `item` for sections: "Item 7", "Note 12", "Footnote 5"."""

    try:
        context = _get_context()
        cik = await context.client.resolve_cik(identifier)
        document = await context.client.fetch_filing_document(cik, accession_number)
        text = _html_to_text(document.text)
        if item:
            section = _extract_item_section(text, item)
            if section is None:
                return json.dumps(
                    {
                        "error": f"Section {item!r} not found",
                        "available_sections": _available_sections(text),
                    }
                )
            text = section

        return _truncate(text, context.tool_output_char_budget)
    except Exception as exc:
        logger.warning(
            "sec_filing_content failed for %s/%s: %s",
            identifier,
            accession_number,
            exc,
        )
        return json.dumps({"error": str(exc)})


@mcp.tool()
async def sec_financials(identifier: str, statement: str = "balance_sheet") -> str:
    """Get parsed financial statements from SEC company facts."""

    try:
        if statement not in STATEMENT_CONCEPTS:
            return json.dumps(
                {
                    "error": f"Statement {statement!r} not found",
                    "available": list(STATEMENT_CONCEPTS),
                }
            )

        context = _get_context()
        cik = await context.client.resolve_cik(identifier)
        facts = await context.client.fetch_company_facts(cik)
        payload = {
            "cik": cik,
            "entity_name": facts.get("entityName", ""),
            "statement": statement,
            "facts": _statement_facts(facts, statement),
        }
        return _truncate(json.dumps(payload), context.tool_output_char_budget)
    except Exception as exc:
        logger.warning("sec_financials failed for %s: %s", identifier, exc)
        return json.dumps({"error": str(exc)})


@mcp.tool()
async def sec_resolve_company(query: str) -> str:
    """Resolve a company name, ticker, or CIK to its SEC identifiers. Returns ticker, CIK, and official company name."""

    try:
        context = _get_context()
        cik = await context.client.resolve_cik(query)
        submissions = await context.client.fetch_submissions(cik)
        return json.dumps(
            {
                "cik": cik,
                "name": submissions.get("name", ""),
                "tickers": submissions.get("tickers", []),
                "exchanges": submissions.get("exchanges", []),
                "sic": submissions.get("sic", ""),
                "sic_description": submissions.get("sicDescription", ""),
            }
        )
    except Exception as exc:
        logger.warning("sec_resolve_company failed for %s: %s", query, exc)
        return json.dumps({"error": str(exc)})


@mcp.tool()
async def sec_filing_search(
    identifier: str,
    accession_number: str,
    query: str,
    context_chars: int = 500,
) -> str:
    """Search within a specific SEC filing for a keyword or phrase. Returns matching passages with surrounding context."""

    try:
        context = _get_context()
        cik = await context.client.resolve_cik(identifier)
        document = await context.client.fetch_filing_document(cik, accession_number)
        text = _html_to_text(document.text)
        results = _search_text(text, query, context_chars)
        if not results:
            return json.dumps({"matches": [], "note": f"No matches for {query!r} in this filing"})
        return _truncate(json.dumps({"matches": results}), context.tool_output_char_budget)
    except Exception as exc:
        logger.warning(
            "sec_filing_search failed for %s/%s: %s",
            identifier,
            accession_number,
            exc,
        )
        return json.dumps({"error": str(exc)})


def main() -> None:
    if any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
        sys.stdout.write("Run this module as a FastMCP stdio server.\n")
        return

    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    for noisy in ("httpx", "httpcore", "mcp", "mcp.server", "mcp.server.lowlevel.server"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    mcp.run(transport="stdio")


def _get_context() -> _ServerContext:
    global _context
    if _context is None:
        _context = _build_context_from_env()
    return _context


def _build_context_from_env() -> _ServerContext:
    return _ServerContext(
        client=EdgarClient(
            user_agent=os.getenv("SEC_USER_AGENT", ""),
            cache_size=_parse_int_env("SEC_EDGAR_CACHE_SIZE", DEFAULT_CACHE_SIZE),
        ),
        tool_output_char_budget=_parse_int_env(
            "TOOL_OUTPUT_CHAR_BUDGET",
            DEFAULT_TOOL_OUTPUT_CHAR_BUDGET,
        ),
    )


def _filing_rows(
    *,
    company: str,
    recent: dict[str, Any],
    form_type: str,
    num_results: int,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    forms = list(recent.get("form", []))
    filing_dates = list(recent.get("filingDate", []))
    accession_numbers = list(recent.get("accessionNumber", []))
    primary_documents = list(recent.get("primaryDocument", []))
    target_form = form_type.strip().upper()
    limit = max(num_results, 0)
    if limit == 0:
        return rows

    for index, form in enumerate(forms):
        if target_form and str(form).upper() != target_form:
            continue
        rows.append(
            {
                "company": company,
                "form": str(form),
                "filing_date": _list_value(filing_dates, index),
                "accession_number": normalize_accession(_list_value(accession_numbers, index)),
                "primary_document": _list_value(primary_documents, index),
            }
        )
        if len(rows) >= limit:
            break
    return rows


def _statement_facts(facts: dict[str, Any], statement: str) -> dict[str, list[dict[str, Any]]]:
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    output: dict[str, list[dict[str, Any]]] = {}
    for output_name, candidate_concepts in STATEMENT_CONCEPTS[statement].items():
        output[output_name] = []
        for concept in candidate_concepts:
            concept_data = us_gaap.get(concept)
            if not isinstance(concept_data, dict):
                continue
            values = _recent_fact_values(concept_data)
            if values:
                output[output_name] = values
                break
    return output


def _recent_fact_values(concept_data: dict[str, Any]) -> list[dict[str, Any]]:
    units = concept_data.get("units", {})
    values = units.get("USD") or units.get("shares") or []
    if not isinstance(values, list):
        return []
    recent_values = [
        {
            "end": value.get("end"),
            "filed": value.get("filed"),
            "form": value.get("form"),
            "fy": value.get("fy"),
            "fp": value.get("fp"),
            "val": value.get("val"),
            "accn": value.get("accn"),
        }
        for value in values
        if isinstance(value, dict) and value.get("val") is not None
    ]
    recent_values.sort(key=lambda value: (str(value.get("end")), str(value.get("filed"))))
    recent_values.reverse()
    return recent_values[:8]


def _html_to_text(raw: str) -> str:
    with_breaks = re.sub(r"(?i)<(br|p|div|tr|table|h[1-6])\b[^>]*>", "\n", raw)
    without_tags = re.sub(r"<[^>]+>", " ", with_breaks)
    decoded = html.unescape(without_tags).replace("\xa0", " ")
    decoded = re.sub(r"[ \t]+", " ", decoded)
    decoded = re.sub(r"\n\s+", "\n", decoded)
    decoded = re.sub(r"\n{3,}", "\n\n", decoded)
    return decoded.strip()


def _extract_item_section(text: str, item: str) -> str | None:
    note_match = re.search(r"(?i)(?:notes?|footnotes?)\s*(\d+)", item)
    if note_match:
        num = note_match.group(1)
        return _extract_heading_section(
            text,
            re.compile(rf"(?im)^\s*(?:notes?|footnotes?)\s+{re.escape(num)}\b[^\n]*"),
            re.compile(r"(?im)^\s*(?:notes?|footnotes?)\s+\d+\b[^\n]*"),
        )

    target = _normalize_item(item)
    if target is None:
        return None
    return _extract_heading_section(
        text,
        re.compile(rf"(?im)^\s*item\s+{re.escape(target)}\.?\b[^\n]*"),
        re.compile(r"(?im)^\s*item\s+\d{1,2}[A-Z]?\.?\b[^\n]*"),
    )


def _extract_heading_section(
    text: str,
    heading_pattern: re.Pattern[str],
    next_heading_pattern: re.Pattern[str],
) -> str | None:
    best_section = ""
    for match in heading_pattern.finditer(text):
        next_match = next_heading_pattern.search(text, match.end())
        end = next_match.start() if next_match else len(text)
        section = text[match.start() : end].strip()
        if len(section) > len(best_section):
            best_section = section
    return best_section or None


def _available_sections(text: str) -> list[str]:
    patterns = [
        re.compile(r"(?im)^\s*(item\s+\d{1,2}[A-Z]?\.?[^\n]{0,120})"),
        re.compile(r"(?im)^\s*((?:notes?|footnotes?)\s+\d+[^\n]{0,120})"),
    ]
    seen: set[str] = set()
    sections: list[str] = []
    for pattern in patterns:
        for match in pattern.finditer(text):
            section = re.sub(r"\s+", " ", match.group(1)).strip()
            key = section.lower()
            if key not in seen:
                seen.add(key)
                sections.append(section)
    return sections[:30]


def _normalize_item(item: str) -> str | None:
    match = re.search(r"(?i)(?:item\s*)?(\d{1,2}[A-Z]?)", item)
    if match is None:
        return None
    return match.group(1).upper()


def _search_text(text: str, query: str, context_chars: int) -> list[dict[str, Any]]:
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    results: list[dict[str, Any]] = []
    seen_ranges: list[tuple[int, int]] = []
    for match in pattern.finditer(text):
        start = max(0, match.start() - context_chars)
        end = min(len(text), match.end() + context_chars)
        overlaps = any(
            min(end, prev_end) - max(start, prev_start) > context_chars
            for prev_start, prev_end in seen_ranges
        )
        if overlaps:
            continue
        seen_ranges.append((start, end))
        results.append({"position": match.start(), "passage": text[start:end]})
        if len(results) >= 10:
            break
    return results


def _truncate(text: str, budget: int) -> str:
    if len(text) <= budget:
        return text
    return text[:budget] + TRUNCATION_SENTINEL


def _list_value(values: list[Any], index: int) -> str:
    if index >= len(values):
        return ""
    return str(values[index])


def _parse_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("invalid integer env var %s=%s; using %d", name, raw, default)
        return default


if __name__ == "__main__":
    main()
