"""DeskDock 启动入口。"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deskdock.app import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
