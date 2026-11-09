"""Absolute script path makes this installation's worker identifiable."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.planner_worker import main

if __name__ == '__main__':
    main()
