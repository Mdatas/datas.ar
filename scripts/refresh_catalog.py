#!/usr/bin/env python3
"""Re-read every catalog file size from the Hugging Face API. Thin wrapper around
`datas catalog refresh`; kept as a script so it can run in CI without the CLI entry point.

    python scripts/refresh_catalog.py          # report drift
    python scripts/refresh_catalog.py --write  # update datas/catalog/models.json
"""

import sys

from datas.cli import catalog_refresh

catalog_refresh(write="--write" in sys.argv)
