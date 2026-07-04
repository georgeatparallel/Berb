"""Allow running as `python -m berb`."""

import asyncio
import sys

from berb.cli import main

sys.exit(main())
