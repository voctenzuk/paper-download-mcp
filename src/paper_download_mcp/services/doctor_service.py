"""Health probes for paper-download sources and Sci-Hub mirrors."""

from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import requests

from ..scihub_core.config.mirrors import MirrorConfig
from ..scihub_core.config.settings import Settings

PROBE_TIMEOUT_SECONDS = 10
# Stable, well-known DOI used purely as a synthetic probe target. A 404 here
# means "API alive but record missing", not "API down".
PROBE_DOI = "10.1038/nature12373"
PROBE_ARXIV_ID = "2301.00001"

# HTTP statuses that indicate the endpoint responded — auth/missing record are
# not outages, so we accept 200/401/403/404 as healthy.
_HEALTHY_STATUSES = frozenset({200, 401, 403, 404})

# Sci-Hub mirrors often sit behind Cloudflare, which returns 403 for non-browser
# clients but proves the host is reachable.
_HEALTHY_MIRROR_STATUSES = frozenset({200, 403})


def _user_agent(email: str) -> str:
    return f"paper-download-mcp/doctor (mailto: {email})"


def _resolve_email() -> str:
    settings = Settings()
    if settings.email:
        return settings.email
    return os.environ.get("PAPER_DOWNLOAD_EMAIL", "noreply@example.com")


def _build_source_targets(email: str) -> list[tuple[str, str]]:
    return [
        ("Unpaywall", f"https://api.unpaywall.org/v2/{PROBE_DOI}?email={email}"),
        ("OpenAlex", f"https://api.openalex.org/works/https://doi.org/{PROBE_DOI}"),
        (
            "Europe PMC",
            f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:{PROBE_DOI}&format=json",
        ),
        ("Crossref", f"https://api.crossref.org/works/{PROBE_DOI}"),
        ("arXiv", f"https://export.arxiv.org/api/query?id_list={PROBE_ARXIV_ID}"),
        ("CORE", "https://api.core.ac.uk/v3/search/works?q=test&limit=1"),
    ]


def _probe(
    name: str,
    url: str,
    headers: dict[str, str],
    healthy_statuses: frozenset[int],
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        # GET — most JSON APIs reject HEAD with 405; we only inspect the
        # status line, so the small extra payload is acceptable.
        response = requests.get(url, headers=headers, timeout=PROBE_TIMEOUT_SECONDS)
        latency_ms = int((time.monotonic() - started) * 1000)
        status = response.status_code
        return {
            "name": name,
            "ok": status in healthy_statuses,
            "status": status,
            "latency_ms": latency_ms,
            "error": None,
        }
    except Exception as exc:
        latency_ms = int((time.monotonic() - started) * 1000)
        return {
            "name": name,
            "ok": False,
            "status": None,
            "latency_ms": latency_ms,
            "error": str(exc)[:200],
        }


def _probe_many(
    targets: list[tuple[str, str]],
    headers: dict[str, str],
    healthy_statuses: frozenset[int],
) -> list[dict[str, Any]]:
    if not targets:
        return []
    results: list[dict[str, Any] | None] = [None] * len(targets)
    with ThreadPoolExecutor(max_workers=max(1, len(targets))) as executor:
        future_to_index = {
            executor.submit(_probe, name, url, headers, healthy_statuses): index
            for index, (name, url) in enumerate(targets)
        }
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            results[index] = future.result()
    return [r for r in results if r is not None]


def run_doctor() -> dict[str, Any]:
    """Probe all paper-download sources and Sci-Hub mirrors; return a structured report."""
    settings = Settings()
    email = _resolve_email()
    headers = {"User-Agent": _user_agent(email)}

    mirrors = MirrorConfig.get_all_mirrors()

    config = {
        "scihub_mirrors": list(mirrors),
        "scihub_year_threshold": getattr(settings, "year_threshold", 2021),
        "scihub_disable": bool(getattr(settings, "scihub_disable", False)),
        "tls_mode": getattr(settings, "tls_mode", "strict") or "strict",
        "email": email,
        "https_proxy": os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or None,
    }

    source_targets = _build_source_targets(email)
    sources = _probe_many(source_targets, headers, _HEALTHY_STATUSES)

    mirror_targets = [(url, url) for url in mirrors]
    mirror_results = _probe_many(mirror_targets, headers, _HEALTHY_MIRROR_STATUSES)
    # Reshape mirror entries: drop "name", surface "url" instead.
    scihub_mirrors = [
        {
            "url": entry["name"],
            "ok": entry["ok"],
            "status": entry["status"],
            "latency_ms": entry["latency_ms"],
            "error": entry["error"],
        }
        for entry in mirror_results
    ]

    sources_ok = sum(1 for s in sources if s["ok"])
    mirrors_ok = sum(1 for m in scihub_mirrors if m["ok"])

    summary = {
        "sources_ok": sources_ok,
        "sources_total": len(sources),
        "mirrors_ok": mirrors_ok,
        "mirrors_total": len(scihub_mirrors),
        "ready_to_download": sources_ok >= 2,
        "scihub_reachable": mirrors_ok > 0,
    }

    return {
        "config": config,
        "sources": sources,
        "scihub_mirrors": scihub_mirrors,
        "summary": summary,
    }
