"""``python -m lumen_economia``: o mesmo que ``lumen economia``."""

import sys

from .cli import main

sys.exit(main())
