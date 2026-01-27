import asyncio
import http.cookies
import json
import re
import subprocess
from time import time
from urllib.parse import quote, urljoin

import m3u8
from aiohttp import ClientSession, TCPConnector
from multidict import CIMultiDictProxy

# 注意：以下导入需确保你的项目目录结构正确，若运行报错需检查utils模块路径
import utils.constants as constants
from utils.config import config
from utils.i18n import t
from utils.requests.tools import headers as request_headers
from utils.tools import get_resolution_value
from utils.types import TestResult, ChannelTestResult, TestResultCacheData

# 全局配置（原有逻辑不变）
http.cookies._is_legal_key = lambda _: True
cache: TestResultCacheData = {}
speed_test_timeout = config.speed_test_timeout
speed_test_filter_host = config.speed_test_filter_host
open_filter_resolution = config.open_filter_resolution
min_resolution_value = config.min_resolution_value
max_resolution_value = config.max_resolution_value
open_supply = config.open_supply
open_filter_speed = config.open_filter_speed
min_speed_value = config.min_speed
m3u8_headers = ['application/x-mpegurl', 'application/vnd.apple.mpegurl', 'audio/mpegurl', 'audio/x-mpegurl']
default_ipv6_delay = 0.1
default_ipv6_resolution = "1920x1080"
default_ipv6_result = {
    'speed': float("inf"),
    'delay': default_ipv6_delay,
    'resolution': default_ipv6_resolution
}


async def get_speed_with_download(url: str, headers: dict = None, session: ClientSession = None,
                                  timeout: int = speed_test_timeout) -> dict[
    str, float | None]:
    """
    Get the speed of the url with a total timeout（原有逻辑未修改）
    """
    start_time = time()
    delay = -1
    total_size = 0
    if session is None:
        session = ClientSession(connector=TCPConnector(ssl=False), trust_env=True)
        created_session = True
    else:
        created_session = False
    try:
        async with session.get(url, headers=headers, timeout=timeout) as response:
            if response.status != 200:
                raise Exception("Invalid response")
            delay = int(round((time() - start_time) * 1000))
            async for chunk in response.content.iter_any():
                if chunk:
                    total_size += len(chunk)
    except:
        pass
    finally:
        total_time = time() - start_time
        if created_session:
            await session.close()
        return {
            'speed': total_size / total_time / 1024 / 1024,
            'delay': delay,
            'size': total_size,
            'time': total_time,
        }


async def get_headers(url: str, headers: dict = None, session: ClientSession = None, timeout: int = 5) -> \
        CIMultiDictProxy[str] | dict[
            any, any]:
    """
    Get the headers of the url（原有逻辑未修改）
    """
    if session is None:
        session = ClientSession(connector=TCPConnector(ssl=False), trust_env=True)
        created_session = True
    else:
        created_session = False
    res_headers = {}
    try:
        async with session.head(url, headers=headers, timeout=timeout) as response:
            res_headers = response.headers
    except:
        pass
    finally:
        if created_session:
            await session.close()
        return res_headers


async def get_url_content(url: str, headers: dict = None, session: ClientSession = None,
                          timeout: int = speed_test_timeout) -> str:
    """
    Get the content of the url（原有逻辑未修改）
    """
    if session is None:
        session = ClientSession(connector=TCPConnector(ssl=False), trust_env=True)
        created_session = True
    else:
        created_session = False
    content = ""
    try:
        async with session.get(url, headers=headers, timeout=timeout) as response:
            if response.status == 200:
                content = await response.text()
            else:
                raise Exception("Invalid response")
    except:
        pass
    finally:
        if created_session:
            await session.close()
        return content


def check_m3u8_valid(headers: CIMultiDictProxy[str] | dict[any, any]) -> bool:
    """
    Check if the m3u8 url is valid（原有逻辑未修改）
    """
    content_type = headers.get('Content-Type', '').lower()
    if not content_type:
        return False
    return any(item in content_type for item in m3u8_headers)


def _parse_time_to_seconds(t: str) -> float:
    """
    Parse time string to seconds（原有逻辑未修改）
    """
    if not t:
        return 0.0
    parts = [p.strip() for p in t.split(':') if p.strip() != ""]
    if not parts:
        return 0.0
    try:
        total = 0.0
        for i, part in enumerate(reversed(parts)):
            total += float(part) * (60 ** i)
        return total
    except Exception:
        return 0.0


def _try_extract_speed_from_ffmpeg_output(output: str) -> float | None:
    """
    Try to extract speed from ffmpeg output（仅优化解析优先级，优先用流媒体真实码率）
    """

    def parse_size_value(value_str: str, unit: str | None) -> float:
        try:
            val = float(value_str)
        except Exception:
            return 0.0
        if not unit:
            return val
        unit_lower = unit.lower()
        if unit_lower in ("b", "bytes"):
            return val
        if unit_lower in ("kib", "k"):
            return val * 1024.0
        if unit_lower in ("kb",):
            return val * 1000.0
        if unit_lower in ("mib", "mb"):
            return val * 1024.0 * 1024.0
        return val

    # ========== 测速准确度优化：优先解析ffmpeg的bitrate（真实流媒体码率，最贴近实际播放速度） ==========
    try:
        m_bitrate = re.search(r"bitrate=\s*([0-9\.]+)\s*k?bits/s", output)
        if m_bitrate:
            kbps = float(m_bitrate.group(1))
            return kbps / 8.0 / 1024.0  # kbps → MB/s（1MB=8192kb）
    except Exception:
        pass

    # 原有解析逻辑（兜底，保留不变）
    try:
        total_bytes = 0.0
        m_video = re.search(r"video:\s*([0-9]+(?:\.[0-9]+)?)\s*(KiB|MiB|kB|B|kb|KB)?", output, re.IGNORECASE)
        m_audio = re.search(r"audio:\s*([0-9]+(?:\.[0-9]+)?)\s*(KiB|MiB|kB|B|kb|KB)?", output, re.IGNORECASE)
        if m_video:
            total_bytes += parse_size_value(m_video.group(1), m_video.group(2))
        if m_audio:
            total_bytes += parse_size_value(m_audio.group(1), m_audio.group(2))

        m_time = re.search(r"time=\s*([0-9:\.]+)", output)
        if total_bytes > 0 and m_time:
            secs = _parse_time_to_seconds(m_time.group(1))
            if secs > 0:
                return total_bytes / secs / 1024.0 / 1024.0
    except Exception:
        pass

    try:
        m_lsize = re.search(r"Lsize=\s*([0-9]+(?:\.[0-9]+)?)\s*(KiB|kB|MiB|B|kb|KB)?", output, re.IGNORECASE)
        m_size = re.search(r"size=\s*([0-9]+(?:\.[0-9]+)?)\s*(KiB|kB|MiB|B|kb|KB)?", output, re.IGNORECASE)
        m_time = re.search(r"time=\s*([0-9:\.]+)", output)
        size_bytes = 0.0
        if m_lsize and m_lsize.group(1).upper() != "N/A":
            size_bytes = parse_size_value(m_lsize.group(1), m_lsize.group(2))
        elif m_size:
            size_bytes = parse_size_value(m_size.group(1), m_size.group(2))
        if size_bytes > 0 and m_time:
            secs = _parse_time_to_seconds(m_time.group(1))
            if secs > 0:
                return size_bytes / secs / 1024.0 / 1024.0
    except Exception:
        pass

    return None


async def get_result(url: str, headers: dict = None, resolution: str = None,
                     filter_resolution: bool = config.open_filter_resolution,
                     timeout: int = speed_test_timeout) -> dict[str, float | None]:
    """
    Get the test result of the url（仅优化测速准确度，其余逻辑不变）
    """
    info = {'speed': 0, 'delay': -1, 'resolution': resolution}
    location = None
    try:
        url = quote(url, safe=':/?$&=@[]%').partition('$')[0]
        async with ClientSession(connector=TCPConnector(ssl=False), trust_env=True) as session:
            res_headers = await get_headers(url, headers, session)
            location = res_headers.get('Location')
            if location:
                info.update(await get_result(location, headers, resolution, filter_resolution, timeout))
            else:
                url_content = await get_url_content(url, headers, session, timeout)
                if url_content:
                    m3u8_obj = m3u8.loads(url_content)
                    playlists = m3u8_obj.playlists
                    segments = m3u8_obj.segments
                    if playlists:
                        best_playlist = max(m3u8_obj.playlists, key=lambda p: p.stream_info.bandwidth)
                        playlist_url = urljoin(url, best_playlist.uri)
                        playlist_content = await get_url_content(playlist_url, headers, session, timeout)
                        if playlist_content:
                            media_playlist = m3u8.loads(playlist_content)
                            segment_urls = [urljoin(playlist_url, segment.uri) for segment in media_playlist.segments]
                    else:
                        segment_urls = [urljoin(url, segment.uri) for segment in segments]
                    if not segment_urls:
                        raise Exception("Segment urls not found")
                    # ========== 测速准确度优化1：跳过前1个初始化片段，取后续5个有效片段 ==========
                    sample_segments = segment_urls[1:6] if len(segment_urls) > 1 else segment_urls
                    start_time = time()
                    tasks = [get_speed_with_download(ts_url, headers, session, timeout) for ts_url in sample_segments]
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    # ========== 测速准确度优化2：过滤有效结果，按片段大小加权计算速度 ==========
                    valid_results = [r for r in results if isinstance(r, dict) and r['time'] > 0 and r['size'] > 0]
                    if valid_results:
                        total_size = sum(r['size'] for r in valid_results)
                        # 加权时间 = 每个片段的(大小/总大小) * 片段耗时，大片段占比更高
                        weighted_time = sum((r['size'] / total_size) * r['time'] for r in valid_results)
                        info['speed'] = total_size / weighted_time / 1024 / 1024 if weighted_time > 0 else 0
                        # 延迟取有效片段的平均延迟，排除无效值
                        valid_delays = [r['delay'] for r in valid_results if r['delay'] > 0]
                        info['delay'] = int(round(sum(valid_delays) / len(valid_delays))) if valid_delays else int(round((time() - start_time) * 1000))
                    else:
                        info['speed'] = 0
                        info['delay'] = int(round((time() - start_time) * 1000))
                else:
                    res_info = await get_speed_with_download(url, headers, session, timeout)
                    info.update({'speed': res_info['speed'], 'delay': res_info['delay']})
                try:
                    if round(info['speed'], 2) == 0 and info['delay'] != -1:
                        ff_out = await ffmpeg_url(url, headers, timeout)
                        if ff_out:
                            parsed_speed = _try_extract_speed_from_ffmpeg_output(ff_out)
                            if parsed_speed is not None and parsed_speed > 0:
                                info['speed'] = parsed_speed
                            try:
                                _, parsed_resolution = get_video_info(ff_out)
                                if parsed_resolution:
                                    info['resolution'] = parsed_resolution
                            except Exception:
                                pass
                except Exception:
                    pass
    except:
        pass
    finally:
        if not info['resolution'] and filter_resolution and not location and info['delay'] != -1:
            info['resolution'] = await get_resolution_ffprobe(url, headers, timeout)
        return info


async def get_delay_requests(url, timeout=speed_test_timeout, proxy=None):
    """
    Get the delay of the url by requests（原有逻辑未修改）
    """
    async with ClientSession(
            connector=TCPConnector(ssl=False), trust_env=True
    ) as session:
        start = time()
        end = None
        try:
            async with session.get(url, timeout=timeout, proxy=proxy) as response:
                if response.status == 404:
                    return -1
                content = await response.read()
                if content:
                    end = time()
                else:
                    return -1
        except Exception as e:
            return -1
        return int(round((end - start) * 1000)) if end else -1


def check_ffmpeg_installed_status():
    """
    Check ffmpeg is installed（原有逻辑未修改）
    """
    status = False
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        status = result.returncode == 0
    except FileNotFoundError:
        status = False
    except Exception as e:
        print(e)
    finally:
        if status:
            print(t("msg.ffmpeg_installed"))
        else:
            print(t("msg.ffmpeg_not_installed"))
        return status


async def ffmpeg_url(url, headers=None, timeout=10):
    """
    Get the ffmpeg output of the url（仅优化采样参数，提升解析准确度）
    """
    headers_str = "".join(f"{k}: {v}\r\n" for k, v in headers.items())

    args = ["ffmpeg", "-t", "2"]  # ========== 测速准确度优化：仅采样2秒，足够计算码率，减少耗时 ==========
    if headers_str:
        args += ["-headers", headers_str]
    args += ["-http_persistent", "0", "-stats", "-i", url, "-f", "null", "-",
             "-hide_banner", "-loglevel", "stats"]  # 隐藏无关输出，仅保留统计信息

    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        if err:
            return err.decode(errors="ignore")
        if out:
            return out.decode(errors="ignore")
        return None
    except asyncio.TimeoutError:
        if proc:
            proc.kill()
        return None
    except Exception:
        if proc:
            proc.kill()
        return None
    finally:
        if proc:
            await proc.wait()


async def get_resolution_ffprobe(url: str, headers: dict = None, timeout: int = speed_test_timeout) -> str | None:
    """
    Get the resolution of the url by ffprobe（仅优化兜底逻辑，避免空分辨率导致测速结果过滤误判）
    """
    resolution = None
    proc = None
    try:
        probe_args = [
            'ffprobe',
            '-v', 'error',
            '-headers', ''.join(f'{k}: {v}\r\n' for k, v in headers.items()) if headers else '',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height,codec_type',  # 增加codec_type判断是否为视频流
            "-of", 'json',
            url
        ]
        proc = await asyncio.create_subprocess_exec(*probe_args, stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.PIPE)
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
        video_stream = json.loads(out.decode('utf-8'))["streams"][0]
        # ========== 测速准确度优化：兜底纯音频流/分辨率为0的情况，避免空值 ==========
        if video_stream.get("codec_type") != "video" or video_stream.get("width") == 0 or video_stream.get("height") == 0:
            return "音频流"  # 纯音频流标记，避免空分辨率被过滤
        resolution = f"{video_stream['width']}x{video_stream['height']}"
    except:
        if proc:
            proc.kill()
    finally:
        if proc:
            await proc.wait()
        return resolution


def get_video_info(video_info):
    """
    Get the video info（原有逻辑未修改）
    """
    frame_size = -1
    resolution = None
    if video_info is not None:
        info_data = video_info.replace(" ", "")
        matches = re.findall(r"frame=(\d+)", info_data)
        if matches:
            frame_size = int(matches[-1])
        match = re.search(r"(\d{3,4}x\d{3,4})", video_info)
        if match:
            resolution = match.group(0)
    return frame_size, resolution


async def check_stream_delay(url_info):
    """
    Check the stream delay（原有逻辑未修改）
    """
    try:
        url = url_info["url"]
        video_info = await ffmpeg_url(url)
        if video_info is None:
            return -1
        frame, resolution = get_video_info(video_info)
        if frame is None or frame == -1:
            return -1
        url_info["resolution"] = resolution
        return url_info, frame
    except Exception as e:
        print(e)
        return -1


def get_avg_result(result) -> TestResult:
    """
    Get average test result（原有逻辑未修改）
    """
    return {
        'speed': sum(item['speed'] or 0 for item in result) / len(result),
        'delay': max(
            int(sum(item['delay'] or -1 for item in result) / len(result)), -1),
        'resolution': max((item['resolution'] for item in result), key=get_resolution_value)
    }


def get_speed_result(key: str) -> TestResult:
    """
    Get the speed result of the url from cache（原有逻辑未修改）
    """
    if key in cache:
        return get_avg_result(cache[key])
    else:
        return {'speed': 0, 'delay': -1, 'resolution': 0}


async def get_speed(data, headers=None, ipv6_proxy=None, filter_resolution=open_filter_resolution,
                    timeout=speed_test_timeout, logger=None, callback=None) -> TestResult:
    """
    Get the speed (response time and resolution) of the url（原有逻辑未修改）
    """
    url = data['url']
    resolution = data['resolution']
    result: TestResult = {'speed': 0, 'delay': -1, 'resolution': resolution}
    headers = {**request_headers, **(headers or {})}
    try:
        cache_key = data['host'] if speed_test_filter_host else url
        if cache_key and cache_key in cache:
            result = get_avg_result(cache[cache_key])
        else:
            if data['ipv_type'] == "ipv6" and ipv6_proxy:
                result.update(default_ipv6_result)
            elif constants.rt_url_pattern.match(url) is not None:
                start_time = time()
                if not result['resolution'] and filter_resolution:
                    result['resolution'] = await get_resolution_ffprobe(url, headers, timeout)
                result['delay'] = int(round((time() - start_time) * 1000))
                if result['resolution'] is not None:
                    result['speed'] = float("inf")
            else:
                result.update(await get_result(url, headers, resolution, filter_resolution, timeout))
            if cache_key:
                cache.setdefault(cache_key, []).append(result)
    finally:
        if callback:
            callback()
        if logger:
            logger.info(
                f"Name: {data.get('name')}, URL: {data.get('url')}, From: {data.get('origin')}, IPv_Type: {data.get('ipv_type')}, Location: {data.get('location')}, ISP: {data.get('isp')}, Date: {data['date']}, Delay: {result.get('delay') or -1} ms, Speed: {result.get('speed') or 0:.2f} M/s, Resolution: {result.get('resolution')}"
            )
        return result


def get_sort_result(
        results,
        supply=open_supply,
        filter_speed=open_filter_speed,
        min_speed=min_speed_value,
        filter_resolution=open_filter_resolution,
        min_resolution=min_resolution_value,
        max_resolution=max_resolution_value,
        ipv6_support=True
) -> list[ChannelTestResult]:
    """
    Get the sorted test results（原有逻辑未修改）
    """
    total_result = []
    for result in results:
        if not ipv6_support and result["ipv_type"] == "ipv6":
            result.update(default_ipv6_result)
        result_speed, result_delay, resolution = (
            result.get("speed") or 0,
            result.get("delay"),
            result.get("resolution")
        )
        if result_delay == -1:
            continue
        if not supply:
            if filter_speed and result_speed < min_speed:
                continue
            if filter_resolution and resolution:
                resolution_value = get_resolution_value(resolution)
                if resolution_value < min_resolution or resolution_value > max_resolution:
                    continue
        total_result.append(result)
    total_result.sort(key=lambda item: item.get("speed") or 0, reverse=True)
    return total_result


def clear_cache():
    """
    Clear the speed test cache（原有逻辑未修改）
    """
    global cache
    cache = {}
