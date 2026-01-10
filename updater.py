"""应用更新检查模块"""

import json
import platform
import urllib.request
import urllib.error
import webbrowser
from dataclasses import dataclass
from typing import Optional

from loguru import logger
from version import get_version, compare_versions, GITHUB_REPO


@dataclass
class UpdateInfo:
    """更新信息"""
    has_update: bool
    current_version: str
    latest_version: str
    release_notes: str
    download_url: str
    release_url: str


def check_for_updates() -> Optional[UpdateInfo]:
    """
    检查是否有新版本
    返回: UpdateInfo 对象，失败时返回 None
    """
    current = get_version()
    logger.info(f"开始检查更新，当前版本: {current}")

    if current == "dev":
        logger.debug("开发模式，跳过更新检查")
        return None

    try:
        api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        logger.debug(f"请求 API: {api_url}")

        request = urllib.request.Request(
            api_url,
            headers={
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "veo3free-updater"
            }
        )

        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))

        latest_version = data.get("tag_name", "").lstrip('v')
        release_notes = data.get("body", "")
        release_url = data.get("html_url", "")
        logger.info(f"获取到最新版本: {latest_version}")

        system = platform.system().lower()
        download_url = ""

        for asset in data.get("assets", []):
            name = asset.get("name", "").lower()
            if system == "darwin" and "macos" in name and name.endswith(".dmg"):
                download_url = asset.get("browser_download_url", "")
                logger.debug(f"找到 macOS 下载链接: {name}")
                break
            elif system == "windows" and "windows" in name and name.endswith(".zip"):
                download_url = asset.get("browser_download_url", "")
                logger.debug(f"找到 Windows 下载链接: {name}")
                break

        if not download_url:
            download_url = release_url
            logger.debug("使用 Release 页面作为下载链接")

        has_update = compare_versions(current, latest_version) < 0
        logger.info(f"版本比较: {current} vs {latest_version}, 有更新: {has_update}")

        return UpdateInfo(
            has_update=has_update,
            current_version=current,
            latest_version=latest_version,
            release_notes=release_notes,
            download_url=download_url,
            release_url=release_url
        )

    except urllib.error.URLError as e:
        logger.error(f"检查更新失败（网络错误）: {type(e).__name__}: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"解析更新信息失败: {e}")
        return None
    except Exception as e:
        logger.error(f"检查更新时发生错误: {type(e).__name__}: {e}")
        return None


def open_download_page(url: str) -> bool:
    """在浏览器中打开下载页面"""
    try:
        webbrowser.open(url)
        return True
    except Exception as e:
        logger.error(f"打开浏览器失败: {e}")
        return False
