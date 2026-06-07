from __future__ import annotations

import importlib.util
import ipaddress
from pathlib import Path
import re
import secrets
import shutil
import socket
import tempfile
import time
from typing import Any
from urllib.parse import urlencode, urlparse
import urllib.request

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from .config import settings
from .douyin import DouyinParser, is_douyin_url


router = APIRouter(prefix="/api", tags=["video"])
_download_tickets: dict[str, dict[str, Any]] = {}
_douyin_parser = DouyinParser()
MAX_PROXY_IMAGE_BYTES = 8 * 1024 * 1024
YTDLP_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}
URL_IN_TEXT_PATTERN = re.compile(r"https?://[^\s<>'\"，。；！？、）】》]+", re.IGNORECASE)


class ParseRequest(BaseModel):
    url: str


class DirectUrlRequest(BaseModel):
    url: str
    format_id: str
    kind: str = "video"


def _import_ytdlp():
    try:
        import yt_dlp

        return yt_dlp
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="后端未安装 yt-dlp") from exc


def _ytdlp_impersonate_target() -> Any | None:
    if importlib.util.find_spec("curl_cffi") is None:
        return None
    try:
        from yt_dlp.networking.impersonate import ImpersonateTarget

        return ImpersonateTarget.from_str("chrome")
    except Exception:
        return None


def _base_ytdlp_opts(use_impersonation: bool = False) -> dict[str, Any]:
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "http_headers": YTDLP_HTTP_HEADERS,
    }
    impersonate = _ytdlp_impersonate_target() if use_impersonation else None
    if use_impersonation and impersonate is not None:
        opts["impersonate"] = impersonate
    return opts


def _ytdlp_opts_variants(extra: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    variants = [_base_ytdlp_opts(use_impersonation=False)]
    if _ytdlp_impersonate_target() is not None:
        variants.append(_base_ytdlp_opts(use_impersonation=True))
    if extra:
        for opts in variants:
            opts.update(extra)
    return variants


def _clean_ytdlp_error(exc: Exception) -> str:
    message = re.sub(r"\x1b\[[0-9;]*m", "", str(exc)).strip()
    if "Fresh cookies" in message:
        return (
            "目标平台要求提供新鲜 Cookie 才能解析这个视频。当前版本不会保存或传递平台 Cookie，"
            "因此无法解析这类受限制链接。可以换公开视频链接或无登录限制的分享链接后重试。"
        )
    return message


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\r\n]+', "_", name).strip(" .")
    return cleaned[:120] or "download"


def _extract_video_url(text: str) -> str:
    raw = text.strip()
    match = URL_IN_TEXT_PATTERN.search(raw)
    if not match:
        raise HTTPException(status_code=400, detail="未找到 http 或 https 视频链接")
    url = match.group(0).strip().rstrip(").,;!?:")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="请输入有效的视频链接")
    if (parsed.hostname or "").lower() == "v.douyin.com":
        short_code = re.match(r"^/([^/?#:]+)", parsed.path)
        if short_code:
            return f"{parsed.scheme}://{parsed.netloc}/{short_code.group(1)}/"
    return url


def _assert_public_image_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(status_code=400, detail="图片地址不正确")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise HTTPException(status_code=400, detail="图片域名无法解析") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
            raise HTTPException(status_code=400, detail="不允许代理内网图片地址")


def _referer_for_image(url: str) -> str:
    host = urlparse(url).hostname or ""
    if host.endswith("hdslb.com"):
        return "https://www.bilibili.com/"
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}/"


def _format_bytes(value: int | None) -> str:
    if not value:
        return "未知"
    size = float(value)
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return "未知"


def _filesize(fmt: dict[str, Any] | None) -> int | None:
    if not fmt:
        return None
    return fmt.get("filesize") or fmt.get("filesize_approx")


def _height_label(fmt: dict[str, Any]) -> str:
    if fmt.get("height"):
        return f"{fmt['height']}p"
    if fmt.get("resolution") and fmt["resolution"] != "audio only":
        return str(fmt["resolution"])
    return fmt.get("format_note") or fmt.get("format_id") or "视频"


def _sort_key(item: dict[str, Any]) -> tuple[int, int]:
    return (int(item.get("height") or 0), int(item.get("tbr") or 0))


def _normalize_formats(info: dict[str, Any]) -> list[dict[str, Any]]:
    formats = info.get("formats") or []
    combined: list[dict[str, Any]] = []
    video_only: dict[int, dict[str, Any]] = {}
    best_audio: dict[str, Any] | None = None

    for fmt in formats:
        if not fmt.get("format_id"):
            continue
        vcodec = fmt.get("vcodec")
        acodec = fmt.get("acodec")
        has_video = vcodec and vcodec != "none"
        has_audio = acodec and acodec != "none"
        if has_audio and not has_video:
            if best_audio is None or _sort_key(fmt) > _sort_key(best_audio):
                best_audio = fmt
        elif has_video and has_audio:
            combined.append(fmt)
        elif has_video:
            height = int(fmt.get("height") or 0)
            if height and (height not in video_only or _sort_key(fmt) > _sort_key(video_only[height])):
                video_only[height] = fmt

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for fmt in sorted(combined, key=_sort_key, reverse=True):
        height = int(fmt.get("height") or 0)
        key = f"combined:{height}:{fmt.get('ext')}"
        if key in seen:
            continue
        seen.add(key)
        size = _filesize(fmt)
        items.append(
            {
                "id": fmt["format_id"],
                "label": f"{_height_label(fmt)} {fmt.get('ext', 'video')}",
                "kind": "video",
                "ext": fmt.get("ext") or "mp4",
                "height": height or None,
                "filesize": size,
                "filesize_text": _format_bytes(size),
                "note": "音视频一体",
            }
        )

    best_audio_size = _filesize(best_audio)
    for height, fmt in sorted(video_only.items(), reverse=True):
        size = (_filesize(fmt) or 0) + (best_audio_size or 0)
        items.append(
            {
                "id": f"{fmt['format_id']}+bestaudio/best",
                "label": f"{height}p MP4",
                "kind": "video",
                "ext": "mp4",
                "height": height,
                "filesize": size or None,
                "filesize_text": _format_bytes(size or None),
                "note": "视频轨 + 最佳音频轨",
            }
        )

    duration = int(info.get("duration") or 0)
    audio_size = int(duration * 128_000 / 8) if duration else best_audio_size
    items.append(
        {
            "id": "bestaudio/best",
            "label": "MP3 音频",
            "kind": "audio",
            "ext": "mp3",
            "height": None,
            "filesize": audio_size,
            "filesize_text": _format_bytes(audio_size),
            "note": "提取并转码为 MP3",
        }
    )
    return items


def extract_raw_info(url: str) -> dict[str, Any]:
    yt_dlp = _import_ytdlp()
    last_exc: Exception | None = None
    for opts in _ytdlp_opts_variants({"skip_download": True}):
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)
        except Exception as exc:
            last_exc = exc
    assert last_exc is not None
    raise HTTPException(status_code=400, detail=f"链接解析失败：{_clean_ytdlp_error(last_exc)}") from last_exc


def parse_video(text: str) -> dict[str, Any]:
    url = _extract_video_url(text)
    if is_douyin_url(url):
        try:
            return _douyin_parser.parse(url)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"抖音链接解析失败：{exc}") from exc

    info = extract_raw_info(url)
    formats = _normalize_formats(info)
    return {
        "id": info.get("id"),
        "title": info.get("title") or "未命名视频",
        "webpage_url": info.get("webpage_url") or url,
        "thumbnail": info.get("thumbnail"),
        "author": info.get("uploader") or info.get("channel"),
        "duration": info.get("duration"),
        "view_count": info.get("view_count"),
        "platform": info.get("extractor_key") or info.get("extractor"),
        "formats": formats,
    }


@router.post("/parse")
def parse_endpoint(payload: ParseRequest) -> dict[str, Any]:
    return {"video": parse_video(payload.url)}


@router.get("/image-proxy")
def image_proxy(url: str = Query(...)) -> Response:
    _assert_public_image_url(url)
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "Referer": _referer_for_image(url),
            "User-Agent": "Mozilla/5.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as upstream:
            content_type = upstream.headers.get("content-type", "application/octet-stream").split(";", 1)[0]
            if not content_type.startswith("image/"):
                raise HTTPException(status_code=400, detail="远程地址不是图片")
            content = upstream.read(MAX_PROXY_IMAGE_BYTES + 1)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"封面图片读取失败：{exc}") from exc
    if len(content) > MAX_PROXY_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="图片过大")
    return Response(
        content,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )


def _download_with_ytdlp(url: str, format_id: str, kind: str, task_dir: Path) -> Path:
    yt_dlp = _import_ytdlp()
    extra: dict[str, Any] = {"outtmpl": str(task_dir / "%(title).180B.%(ext)s")}
    if kind == "audio":
        extra.update(
            {
                "format": format_id,
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }
                ],
            }
        )
    else:
        extra.update({"format": format_id, "merge_output_format": "mp4"})

    last_exc: Exception | None = None
    for opts in _ytdlp_opts_variants(extra):
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            break
        except Exception as exc:
            last_exc = exc
    else:
        assert last_exc is not None
        raise last_exc

    files = [path for path in task_dir.iterdir() if path.is_file() and not path.name.endswith(".part")]
    if not files:
        raise HTTPException(status_code=500, detail="下载完成但未找到输出文件")
    return max(files, key=lambda item: item.stat().st_size)


@router.get("/download")
def download_endpoint(
    background_tasks: BackgroundTasks,
    url: str | None = Query(default=None),
    format_id: str | None = Query(default=None),
    kind: str = Query("video", pattern="^(video|audio)$"),
    ticket: str | None = Query(default=None),
) -> FileResponse:
    if ticket:
        ticket_data = _download_tickets.get(ticket)
        if not ticket_data or ticket_data["expires_at"] < time.time():
            raise HTTPException(status_code=400, detail="下载链接已失效，请重新生成")
        url = ticket_data["url"]
        format_id = ticket_data["format_id"]
        kind = ticket_data["kind"]
    if not url or not format_id:
        raise HTTPException(status_code=400, detail="缺少下载参数")
    url = _extract_video_url(url)

    task_dir = Path(tempfile.mkdtemp(prefix="download-", dir=settings.download_dir))
    try:
        if is_douyin_url(url) and format_id.startswith("douyin_"):
            output = _douyin_parser.download_to(url, task_dir, kind)
        else:
            output = _download_with_ytdlp(url, format_id, kind, task_dir)
    except HTTPException:
        shutil.rmtree(task_dir, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(task_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=f"下载失败：{_clean_ytdlp_error(exc)}") from exc

    background_tasks.add_task(shutil.rmtree, task_dir, True)
    return FileResponse(output, filename=_safe_filename(output.name), media_type="application/octet-stream")


@router.post("/download")
def create_download_link(payload: DirectUrlRequest) -> dict[str, str]:
    if payload.kind not in {"video", "audio"}:
        raise HTTPException(status_code=400, detail="下载类型不正确")
    url = _extract_video_url(payload.url)
    token = secrets.token_urlsafe(24)
    _download_tickets[token] = {
        "url": url,
        "format_id": payload.format_id,
        "kind": payload.kind,
        "expires_at": time.time() + 300,
    }
    return {"download_url": "/api/download?" + urlencode({"ticket": token})}
