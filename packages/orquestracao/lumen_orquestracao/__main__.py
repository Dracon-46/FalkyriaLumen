"""Permite rodar o pipeline com ``python -m lumen_orquestracao``; repassa para ``cli.main``."""

import sys

from .cli import main

sys.exit(main())
