"""``python -m lumen_painel``: o mesmo que ``lumen painel``."""

import sys

from .cli import main

sys.exit(main())
