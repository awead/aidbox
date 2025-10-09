#!/usr/bin/env python3
"""Script to run the FHIR chat web server."""

import sys
import uvicorn

from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


if __name__ == "__main__":
    uvicorn.run(
        "src.web.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
