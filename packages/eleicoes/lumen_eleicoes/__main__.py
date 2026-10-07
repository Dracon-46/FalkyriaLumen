"""Permite rodar a aba Eleições com ``python -m lumen_eleicoes``; repassa para ``cli.main``."""

import sys

from .cli import main

sys.exit(main())
