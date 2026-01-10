"""版本管理模块"""

import os
from pathlib import Path

APP_NAME = "veo3free"
GITHUB_REPO = "jasper9w/veo3free"


def get_version() -> str:
    """获取当前应用版本号"""
    try:
        # 首先尝试从 importlib 读取
        from importlib.metadata import version, PackageNotFoundError
        try:
            return version(APP_NAME)
        except PackageNotFoundError:
            pass
    except ImportError:
        pass

    # 如果失败，从 pyproject.toml 读取
    try:
        project_root = Path(__file__).parent
        pyproject_path = project_root / "pyproject.toml"

        if pyproject_path.exists():
            # Python 3.11+ 有 tomllib，否则使用简单正则
            try:
                import tomllib
                with open(pyproject_path, 'rb') as f:
                    data = tomllib.load(f)
                    return data.get('project', {}).get('version', 'dev')
            except (ImportError, Exception):
                # 备用方案：简单正则提取
                with open(pyproject_path, 'r') as f:
                    for line in f:
                        if line.startswith('version'):
                            # 提取 version = "1.0.0" 中的版本号
                            parts = line.split('=', 1)
                            if len(parts) == 2:
                                version_str = parts[1].strip().strip('"').strip("'")
                                if version_str:
                                    return version_str
    except Exception:
        pass

    return "dev"


def compare_versions(current: str, latest: str) -> int:
    """
    比较两个版本号
    返回: -1 (当前版本较旧), 0 (相同), 1 (当前版本较新)
    """
    def parse_version(v: str) -> tuple:
        v = v.lstrip('v')
        parts = v.split('.')
        # 补齐至少3位，不足的补0
        while len(parts) < 3:
            parts.append('0')
        return tuple(int(p) for p in parts[:3])

    try:
        current_tuple = parse_version(current)
        latest_tuple = parse_version(latest)

        if current_tuple < latest_tuple:
            return -1
        elif current_tuple > latest_tuple:
            return 1
        return 0
    except (ValueError, IndexError):
        return 0
