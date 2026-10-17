"""Allow `python -m src` to work."""
import sys
from .cli import main
sys.exit(main())
