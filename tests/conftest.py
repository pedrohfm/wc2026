"""Make both the new package (src/wc2026) and the frozen legacy reference
(tests/legacy_engine.py) importable during tests."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))   # -> import wc2026
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # -> import legacy_engine
