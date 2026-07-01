#!/usr/bin/env python3
"""
Apify scraper — targets amoblamientos/muebles businesses in Rosario, Santa Fe.

Priority:
  1. Apify CLI (apify run)
  2. Apify run-sync REST API
  3. OSM fallback (basic, limited data)

Output: overwrites dataset.json (root) after every run.
"""

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import requests
from colorama import Fore, Style, init

from config import config

init(autoreset=True)

ACTOR_ID = config.APIFY_ACTOR_ID
DATASET_OUT = config.DATASET_FILE
APIFY_API_BASE = "https://api.apify.com/v2"

# Token pool — rotamos por query para distribuir el uso entre cuentas
_TOKENS = [t for t in [config.APIFY_TOKEN, config.APIFY_TOKEN_2] if t]
TOKEN = _TOKENS[0] if _TOKENS else ""


def _pick_token(index: int) -> str:
    """Devuelve el token correspondiente al índice de query (round-robin)."""
    if not _TOKENS:
        return ""
    tok = _TOKENS[index % len(_TOKENS)]
    cuenta = (index % len(_TOKENS)) + 1
    print(f"{Fore.CYAN}     cuenta {cuenta}/{len(_TOKENS)}")
    return tok

# How many results to request per search query
RESULTS_PER_QUERY = 50


def _build_actor_input(query: str) -> dict:
    """Build Google Maps Scraper actor input for one query."""
    return {
        "searchStringsArray": [query],
        "language": "es",
        "maxCrawledPlacesPerSearch": RESULTS_PER_QUERY,
        "countryCode": "ar",
        "includeHistogram": False,
        "includeOpeningHours": False,
        "includePeopleAlsoSearch": False,
        "exportPlaceUrls": False,
        "additionalInfo": False,
        "scrapeDirectories": False,
        "scrapeTableReservationProvider": False,
        "deeperCityScrape": False,
    }


def _normalize_apify_record(item: dict) -> dict:
    """Normalize Apify Google Maps record to internal format."""
    return {
        "title": item.get("title", ""),
        "totalScore": item.get("totalScore"),
        "reviewsCount": item.get("reviewsCount", 0),
        "street": item.get("street", ""),
        "city": item.get("city", ""),
        "state": item.get("state", ""),
        "countryCode": item.get("countryCode", ""),
        "phone": item.get("phone", ""),
        "website": item.get("website", ""),
        "categories": item.get("categories", []),
        "categoryName": item.get("categoryName", ""),
        "url": item.get("url", ""),
        "permanentlyClosed": item.get("permanentlyClosed", False),
    }


# ── Method 1: Apify CLI ───────────────────────────────────────────────────────

def _cli_available() -> bool:
    return shutil.which("apify") is not None


def _scrape_via_cli(queries: list[str]) -> list[dict] | None:
    """Run Apify actor via CLI and return combined results, or None on failure."""
    if not _cli_available():
        return None

    print(f"{Fore.CYAN}🔧 Usando Apify CLI...")

    all_results = []
    seen_phones = set()

    for query in queries:
        print(f"{Fore.CYAN}  🔍 Buscando: {query}")

        actor_input = _build_actor_input(query)
        input_json = json.dumps(actor_input)

        try:
            result = subprocess.run(
                [
                    "apify", "call", ACTOR_ID,
                    "--silent",
                    "--output-dataset",
                ],
                input=input_json,
                capture_output=True,
                text=True,
                timeout=300,
            )

            if result.returncode != 0:
                print(f"{Fore.YELLOW}  ⚠️  CLI error: {result.stderr[:200]}")
                continue

            # The CLI outputs JSON array to stdout when --output-dataset is set
            try:
                items = json.loads(result.stdout)
                if not isinstance(items, list):
                    items = [items]
            except json.JSONDecodeError:
                print(f"{Fore.YELLOW}  ⚠️  CLI output parse error")
                continue

            added = 0
            for item in items:
                rec = _normalize_apify_record(item)
                phone = rec.get("phone", "")
                if phone and phone in seen_phones:
                    continue
                if phone:
                    seen_phones.add(phone)
                all_results.append(rec)
                added += 1

            print(f"{Fore.GREEN}  ✅ {added} resultados")

        except subprocess.TimeoutExpired:
            print(f"{Fore.YELLOW}  ⚠️  Timeout en query: {query}")
        except Exception as e:
            print(f"{Fore.YELLOW}  ⚠️  Error: {e}")

        time.sleep(2)

    return all_results if all_results else None


# ── Method 2: Apify run-sync API ─────────────────────────────────────────────

def _scrape_via_api(queries: list[str]) -> list[dict] | None:
    """Run actor via Apify REST API (run-sync) and return results."""
    if not _TOKENS:
        print(f"{Fore.RED}❌ APIFY_TOKEN no configurado en .env")
        return None

    print(f"{Fore.CYAN}🌐 Usando Apify API...")

    all_results = []
    seen_phones = set()

    for idx, query in enumerate(queries):
        token = _pick_token(idx)
        print(f"{Fore.CYAN}  🔍 Buscando: {query}")

        actor_input = _build_actor_input(query)
        url = f"{APIFY_API_BASE}/acts/{ACTOR_ID.replace('/', '~')}/run-sync-get-dataset-items"

        try:
            resp = requests.post(
                url,
                json=actor_input,
                params={"token": token},
                timeout=300,
                headers={"Content-Type": "application/json"},
            )

            if resp.status_code != 201:
                print(f"{Fore.YELLOW}  ⚠️  API HTTP {resp.status_code}: {resp.text[:200]}")
                continue

            items = resp.json()
            if not isinstance(items, list):
                items = items.get("items", [])

            added = 0
            for item in items:
                rec = _normalize_apify_record(item)
                phone = rec.get("phone", "")
                if phone and phone in seen_phones:
                    continue
                if phone:
                    seen_phones.add(phone)
                all_results.append(rec)
                added += 1

            print(f"{Fore.GREEN}  ✅ {added} resultados")

        except requests.Timeout:
            print(f"{Fore.YELLOW}  ⚠️  Timeout — query: {query}")
        except Exception as e:
            print(f"{Fore.YELLOW}  ⚠️  Error: {e}")

        time.sleep(3)

    return all_results if all_results else None


# ── Method 3: Async API (start run → poll → fetch dataset) ───────────────────

def _scrape_via_async_api(queries: list[str]) -> list[dict] | None:
    """Start actor run, poll until done, fetch dataset."""
    if not _TOKENS:
        return None

    print(f"{Fore.CYAN}⏳ Usando Apify API async...")

    all_results = []
    seen_phones = set()

    for idx, query in enumerate(queries):
        token = _pick_token(idx)
        print(f"{Fore.CYAN}  🔍 Buscando: {query}")
        actor_input = _build_actor_input(query)

        # Start run
        run_url = f"{APIFY_API_BASE}/acts/{ACTOR_ID.replace('/', '~')}/runs"
        try:
            run_resp = requests.post(
                run_url,
                json=actor_input,
                params={"token": token},
                timeout=30,
            )
            if run_resp.status_code not in (200, 201):
                print(f"{Fore.YELLOW}  ⚠️  Start run HTTP {run_resp.status_code}")
                continue

            run_id = run_resp.json()["data"]["id"]
        except Exception as e:
            print(f"{Fore.YELLOW}  ⚠️  Error starting run: {e}")
            continue

        # Poll until SUCCEEDED
        status_url = f"{APIFY_API_BASE}/actor-runs/{run_id}"
        timeout_at = time.time() + 300
        while time.time() < timeout_at:
            time.sleep(8)
            try:
                st = requests.get(status_url, params={"token": token}, timeout=15).json()
                status = st["data"]["status"]
                if status == "SUCCEEDED":
                    break
                elif status in ("FAILED", "ABORTED", "TIMED-OUT"):
                    print(f"{Fore.YELLOW}  ⚠️  Run {status}")
                    run_id = None
                    break
            except Exception:
                pass
        else:
            print(f"{Fore.YELLOW}  ⚠️  Polling timeout")
            continue

        if not run_id:
            continue

        # Fetch dataset
        dataset_id = run_resp.json()["data"]["defaultDatasetId"]
        items_url = f"{APIFY_API_BASE}/datasets/{dataset_id}/items"
        try:
            items = requests.get(
                items_url,
                params={"token": token, "format": "json"},
                timeout=60,
            ).json()
        except Exception as e:
            print(f"{Fore.YELLOW}  ⚠️  Error fetching dataset: {e}")
            continue

        added = 0
        for item in items:
            rec = _normalize_apify_record(item)
            phone = rec.get("phone", "")
            if phone and phone in seen_phones:
                continue
            if phone:
                seen_phones.add(phone)
            all_results.append(rec)
            added += 1

        print(f"{Fore.GREEN}  ✅ {added} resultados")
        time.sleep(2)

    return all_results if all_results else None


# ── Public entry point ────────────────────────────────────────────────────────

def _load_existing_dataset() -> tuple[list[dict], set[str]]:
    """Load existing dataset.json and return (records, seen_phones)."""
    if not DATASET_OUT.exists():
        return [], set()
    try:
        with open(DATASET_OUT, "r", encoding="utf-8") as f:
            records = json.load(f)
        if not isinstance(records, list):
            return [], set()
        seen = {r.get("phone", "") for r in records if r.get("phone")}
        return records, seen
    except Exception:
        return [], set()


def run_scraper(queries: list[str] | None = None) -> list[dict]:
    """
    Run Apify scraper for all configured queries across all niches.
    Tries CLI → sync API → async API.
    Merges new results into dataset.json (never overwrites existing records).
    Returns the full accumulated dataset.
    """
    if queries is None:
        queries = config.APIFY_SEARCH_QUERIES

    existing, existing_phones = _load_existing_dataset()

    print(f"\n{'='*60}")
    print(f"APIFY SCRAPER — {len(config.NICHES)} nichos, Rosario")
    print(f"{'='*60}")
    print(f"   Queries:              {len(queries)}")
    print(f"   Resultados por query: {RESULTS_PER_QUERY}")
    print(f"   Ya en dataset:        {len(existing)}")
    print(f"{'='*60}\n")

    new_results = None

    # 1. CLI
    if _cli_available():
        new_results = _scrape_via_cli(queries)

    # 2. run-sync API
    if new_results is None and TOKEN:
        new_results = _scrape_via_api(queries)

    # 3. async API
    if new_results is None and TOKEN:
        new_results = _scrape_via_async_api(queries)

    if new_results is None:
        print(f"\n{Fore.RED}Scraping fallido. Verificá APIFY_TOKEN en .env")
        print(f"{Fore.YELLOW}Alternativa: copia manualmente el JSON de Apify a dataset.json")
        return existing

    # Merge — only append records whose phone isn't already in dataset
    added = 0
    for rec in new_results:
        phone = rec.get("phone", "")
        if phone and phone in existing_phones:
            continue
        if phone:
            existing_phones.add(phone)
        existing.append(rec)
        added += 1

    DATASET_OUT.parent.mkdir(exist_ok=True)
    with open(DATASET_OUT, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    print(f"\n{Fore.GREEN}Scraping completado: +{added} nuevos ({len(existing)} total)")
    print(f"   Guardado en: {DATASET_OUT}")

    return existing


if __name__ == "__main__":
    run_scraper()
