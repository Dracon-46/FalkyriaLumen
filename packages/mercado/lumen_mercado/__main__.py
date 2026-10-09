"""``python -m lumen_mercado``: o mesmo que ``lumen mercado``."""

import sys

from .cli import main

sys.exit(main())
