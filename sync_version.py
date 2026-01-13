"""从 pyproject.toml 同步版本号到 version.py，打包前运行"""

import re
import tomllib
from pathlib import Path

root = Path(__file__).parent

with open(root / "pyproject.toml", "rb") as f:
    version = tomllib.load(f)["project"]["version"]

version_file = root / "version.py"
content = version_file.read_text()
content = re.sub(r'__version__ = "[^"]+"', f'__version__ = "{version}"', content)
version_file.write_text(content)

print(f"版本号已同步: {version}")
