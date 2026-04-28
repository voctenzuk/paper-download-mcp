"""Health-probe tool for paper-download sources and Sci-Hub mirrors."""

import asyncio

from ..server import mcp
from ..services.doctor_service import run_doctor


@mcp.tool()
async def paper_doctor() -> dict:
    """Probe the health of all paper-download sources and Sci-Hub mirrors.

    Returns a structured availability report. Useful for diagnosing why a
    download failed: distinguishes between source outages, mirror outages,
    and configuration problems. Does not download any PDFs.
    """
    return await asyncio.to_thread(run_doctor)
