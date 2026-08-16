"""`python -m cb5 …` → CLI."""

import sys

from cb5.cli import main

sys.exit(main(sys.argv[1:]))
