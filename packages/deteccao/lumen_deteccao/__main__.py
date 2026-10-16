"""``python -m lumen_deteccao``: o mesmo que ``lumen deteccao``."""

import sys

from .cli import main

sys.exit(main())
