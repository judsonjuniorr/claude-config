import os
import sys

# Make sibling helper (_base) and the parent doctor scripts importable whether the
# suite is run via `unittest discover` (package import) or a file run directly.
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
