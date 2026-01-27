import random
import requests
from lxml import etree
import os
import threading
import time
import sys
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
# 如需使用代理请取消注释，确保proxyTest.py存在
# from proxyTest import get_valid_proxies

# ========== 新增：代码B的核心测速函数（加_a后缀避免命名冲突） ==========
import asyncio
import re
import subprocess
from time import time
from urllib.parse import urljoin
import m3u8
from aiohttp import ClientSession, TCPConnector

def _parse_time_to_seconds_a(t: str) -> float:
    """解析时间字符串为秒（避免命名冲突）"""
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

def _try_extract_speed_from_ffmpeg_output_a(output: str) -> float | None:
    """从ffmpeg输出提取速度（避免命名冲突）"""
    def parse_size_value_a(value_str: str, unit: str | None) -> float:
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

    try:
        total_bytes = 0.0
        m_video = re.search(r"video:\s*([0-9]+(?:\.[0-9]+)?)\s*(KiB|MiB|kB|B|kb|KB)?", output, re.IGNORECASE)
        m_audio = re.search(r"audio:\s*([0-9]+(?:\.[0-9]+)?)\s*(KiB|MiB|kB|B|kb|KB)?", output, re.IGNORECASE)
        if m_video:
            total_bytes += parse_size_value_a(m_video.group(1), m_video.group(2))
        if m_audio:
            total_bytes += parse_size_value_a(m_audio.group(1), m_audio.group(2))

        m_time = re.search(r"time=\s*([0-9:\.]+)", output)
        if total_bytes > 0 and m_time:
            secs = _parse_time_to_seconds_a(m_time.group(1))
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
            size_bytes = parse_size_value_a(m_lsize.group(1), m_lsize.group(2))
        elif m_size:
            size_bytes = parse_size_value_a(m_size.group(1), m_size.group(2))
        if size_bytes > 0 and m_time:
            secs = _parse_time_to_seconds_a(m_time.group(1))
            if secs > 0:
                return size_bytes / secs / 1024.0 / 1024.0
    except Exception:
        pass

    try:
        m_bitrate = re.search(r"bitrate=\s*([0-9\.]+)\s*k?bits/s", output)
        if m_bitrate:
            kbps = float(m_bitrate.group(1))
            return kbps / 8.0 / 1024.0
    except Exception:
        pass

    return None

async def ffmpeg_url_a(url, headers=None, timeout=10):
    """执行ffmpeg获取输出（避免命名冲突）"""
    headers_str = "".join(f"{k}: {v}\r\n" for k, v in (headers or {}).items())

    args = ["ffmpeg", "-t", str(timeout)]
    if headers_str:
        args += ["-headers", headers_str]
    args += ["-http_persistent", "0", "-stats", "-i", url, "-f", "null", "-"]

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

async def get_speed_with_download_a(url: str, headers: dict = None, timeout: int = 10) -> dict[str, float | None]:
    """异步下载测速（避免命名冲突）"""
    start_time = time()
    delay = -1
    total_size = 0
    session = ClientSession(connector=TCPConnector(ssl=False), trust_env=True)
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
        await session.close()
        return {
            'speed': total_size / total_time / 1024 / 1024 if total_time > 0 else 0,
            'delay': delay,
            'size': total_size,
            'time': total_time,
        }

async def get_m3u8_speed_a(url: str, headers: dict = None, timeout: int = 10) -> float:
    """获取m3u8链接的测速结果（适配代码A）"""
    try:
        # 下载并解析M3U8文件
        async with ClientSession(connector=TCPConnector(ssl=False), trust_env=True) as session:
            async with session.get(url, headers=headers, timeout=timeout) as response:
                if response.status != 200:
                    return 0.0
                m3u8_content = await response.text()
        
        m3u8_obj = m3u8.loads(m3u8_content)
        playlists = m3u8_obj.playlists
        segments = m3u8_obj.segments
        segment_urls = []

        # 处理多级M3U8（选择带宽最高的子playlist）
        if playlists:
            best_playlist = max(playlists, key=lambda p: p.stream_info.bandwidth)
            playlist_url = urljoin(url, best_playlist.uri)
            async with ClientSession(connector=TCPConnector(ssl=False), trust_env=True) as session:
                async with session.get(playlist_url, headers=headers, timeout=timeout) as response:
                    if response.status == 200:
                        playlist_content = await response.text()
                        media_playlist = m3u8.loads(playlist_content)
                        segment_urls = [urljoin(playlist_url, seg.uri) for seg in media_playlist.segments]
        else:
            segment_urls = [urljoin(url, seg.uri) for seg in segments]

        # 测速逻辑：优先测TS片段，无片段则测M3U8本身
        if not segment_urls:
            res = await get_speed_with_download_a(url, headers, timeout)
            speed = res['speed']
        else:
            # 测试前5个TS片段（异步并发）
            tasks = [get_speed_with_download_a(ts_url, headers, timeout) for ts_url in segment_urls[:5]]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            total_size = sum(r['size'] for r in results if isinstance(r, dict))
            total_time = sum(r['time'] for r in results if isinstance(r, dict))
            
            speed = total_size / total_time / 1024 / 1024 if total_time > 0 else 0.0

            # 片段测速为0时，用FFmpeg辅助测速
            if round(speed, 2) == 0:
                ff_out = await ffmpeg_url_a(url, headers, timeout)
                if ff_out:
                    parsed_speed = _try_extract_speed_from_ffmpeg_output_a(ff_out)
                    if parsed_speed is not None and parsed_speed > 0:
                        speed = parsed_speed

        return speed
    except Exception as e:
        print(f"测速失败 {url}: {e}")
        return 0.0
# ========== 新增结束 ==========

def get_url(name):
    # proxy = get_valid_proxies()  # 如需代理请取消注释
    user_agents = [
        'Mozilla/5.0 (Windows; U; Windows NT 5.1; it; rv:1.8.1.11) Gecko/20071127 Firefox/2.0.0.11',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:117.0) Gecko/20100101 Firefox/117.0',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.5845.179 Safari/537.36 Edg/116.0.1938.69',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 12_6_3) AppleWebKit/537.36 (KHTML, like Gecko) Version/15.6 Safari/537.36',
        'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
        'Mozilla/5.0 (Linux; Android 12; Pixel 5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.5845.179 Mobile Safari/537.36',
        'Mozilla/5.0 (Android 12; Mobile; rv:117.0) Gecko/117.0 Firefox/117.0',
        'Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)',
        'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.5845.179 Safari/537.36',
        'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:117.0) Gecko/20100101 Firefox/117.0',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Ubuntu Chromium/116.0.5845.179 Chrome/116.0.5845.179 Safari/537.36',
        'Mozilla/5.0 (compatible; Konqueror/4.14; Linux) KHTML/4.14.2 (like Gecko)',
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Epiphany/42.3 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.5845.179 Safari/537.36 OPR/103.0.4928.47",
    ]
    user_agent = random.choice(user_agents)
    # 配置ChromeOptions以启用无头模式
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument(f"user-agent={user_agent}")
    # chrome_options.add_argument(f"--proxy-server={proxy}")  # 如需代理请取消注释

    # 设置ChromeDriver
    driver = webdriver.Chrome(options=chrome_options)

    try:
        # 打开指定页面
        driver.get('http://tonkiang.us/')
        # 等待直到 ID 为 'search' 的元素可被点击
        username_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, 'search'))
        )
        username_input.send_keys(f'{name}')
        submit_button = driver.find_element(By.NAME, 'Submit')
        submit_button.click()
    except Exception as e:
        print(f"找不到元素: {e}")

    try:
        # 获取页面的源代码
        page_source = driver.page_source
        m3u8_list = []
        # 将 HTML 转换为 Element 对象
        root = etree.HTML(page_source)
        result_divs = root.xpath("//div[@class='resultplus']")
        print(f"获取数据: {len(result_divs)}")
        # 提取m3u8链接
        for div in result_divs:
            for element in div.xpath(".//tba"):
                if element.text is not None:
                    m3u8_url = element.text.strip()
                    print(m3u8_url)
                    m3u8_list.append(m3u8_url)
                    with open('m3u8_list.txt', 'a', encoding='utf-8') as f:
                        f.write(f'{name},{m3u8_url}' + '\n')
    except requests.exceptions.RequestException as e:
        print(f"Error: 请求异常. Exception: {e}")
        pass

    # 关闭WebDriver
    driver.quit()
    return m3u8_list

# ========== 核心修改：替换download_m3u8的测速逻辑 ==========
def download_m3u8(url, name, initial_url=None):
    try:
        # 验证M3U8链接有效性（仅下载头部，不完整下载）
        response = requests.get(url, stream=True, timeout=15)
        response.raise_for_status()  # 检查请求是否成功
        m3u8_content = response.text
    except requests.exceptions.Timeout as e:
        print(f"{url}\nError: 请求超时. Exception: {e}")
        return
    except requests.exceptions.RequestException as e:
        print(f"{url}\nError: 请求异常. Exception: {e}")
        return
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return
    else:
        # 使用代码B的异步测速逻辑
        try:
            # 执行异步测速函数（同步调用异步）
            average_speed = asyncio.run(get_m3u8_speed_a(url, headers=None, timeout=15))
            print(f"---{name}---Average Download Speed: {average_speed:.2f} MB/s")
        except Exception as e:
            print(f"测速异常 {url}: {e}")
            average_speed = 0.0

        # 速度阈值判断（保留原逻辑）
        if average_speed >= speed:
            valid_url = initial_url if initial_url is not None else url
            if not os.path.exists(f'{TV_name}'):
                os.makedirs(f'{TV_name}')
            with open(os.path.join(f'{TV_name}', f'{name}.txt'), 'a', encoding='utf-8') as file:
                file.write(f'{name},{valid_url}\n')
            print(f"---{name}---链接有效源已保存---\n"
                  f"----{valid_url}---")
            return

def detectLinks(name, m3u8_list):
    thread = []
    for m3u8_url in m3u8_list:
        t = threading.Thread(target=download_m3u8, args=(m3u8_url, name,))
        t.daemon = True  # 设置为守护线程
        t.start()
        thread.append(t)
    # 等待所有线程完成
    for t in thread:
        try:
            print(f"Waiting for thread {t} to finish")
            t.join(timeout=10)  # 等待线程超时
        except Exception as e:
            print(f"Thread {t.name} raised an exception: {e}")

def mer_links(tv):
    # 获取文件夹中的所有 txt 文件
    txt_files = [f for f in os.listdir(os.path.join(current_directory, f'{tv}'))]
    print(txt_files)
    # 打开合并后的文件
    with open(output_file_path, 'a', encoding='utf-8') as output_file:
        output_file.write(f'{tv},#genre#' + '\n')
        for txt_file in txt_files:
            file_path = os.path.join(os.path.join(current_directory, f'{tv}'), txt_file)
            # 读取并写入内容
            with open(file_path, 'r', encoding='utf-8') as input_file:
                file_content = input_file.read()
                output_file.write(file_content)
                output_file.write('\n')

    print(f'Merged content from {len(txt_files)} files into {output_file_path}')

def re_dup_ordered(filepath):
    from collections import OrderedDict
    # 读取文本文件
    with open(filepath, 'r', encoding='utf-8') as file:
        lines = file.readlines()
    # 保持原始顺序的去重
    unique_lines_ordered = list(OrderedDict.fromkeys(lines))
    # 写回文件
    with open(filepath, 'w', encoding='utf-8') as file:
        file.writelines(unique_lines_ordered)
    print('-----直播源去重完成！------')

def re_dup(filepath):
    # 读取文本文件
    with open(filepath, 'r', encoding='utf-8') as file:
        lines = file.readlines()

    # 过滤掉包含 'null' 的行
    filtered_lines = [line for line in lines if 'null' not in line]

    # 字典去重
    unique_lines = {}
    for line in filtered_lines:
        parts = line.strip().split(',')
        if len(parts) == 2:
            channel_name, url = parts[0].strip(), parts[1].strip()
            if url not in unique_lines:
                unique_lines[url] = line

    # 写回文件
    unique_lines_ordered = list(unique_lines.values())
    with open(filepath, 'w', encoding='utf-8') as file:
        file.writelines(unique_lines_ordered)
    print('-----直播源去重完成！------')

if __name__ == '__main__':
    speed = 1  # 速度阈值（MB/s）
    # 获取当前工作目录
    current_directory = os.getcwd()
    # 构造上级目录的路径
    parent_dir = os.path.dirname(current_directory)
    output_file_path = os.path.join(parent_dir, 'live.txt')
    # 清空文件
    with open(output_file_path, 'w', encoding='utf-8') as f:
        pass
    with open('m3u8_list.txt', 'w', encoding='utf-8') as file:
        pass
    tv_dict = {}
    # 目标频道分类
    TV_names = ['🇨🇳央视频道']
    for TV_name in TV_names:
        # 删除历史测试记录
        if os.path.exists(TV_name):
            import shutil
            try:
                shutil.rmtree(TV_name)
                print(f"Folder '{TV_name}' deleted successfully.")
            except OSError as e:
                print(f"Error deleting folder '{TV_name}': {e}")
        time.sleep(1)
        # 创建目录
        if not os.path.exists(TV_name):
            os.makedirs(TV_name)
        # 读取频道名称
        with open(f'{TV_name}.txt', 'r', encoding='utf-8') as file:
            names = [line.strip() for line in file]
            for name in names:
                m3u8_list = get_url(name)
                tv_dict[name] = m3u8_list
                print(name)
            print('---------字典加载完成！------------')
        # 多线程测速
        for name, m3u8_list in tv_dict.items():
            detectLinks(name, m3u8_list)
        # 合并有效直播源
        mer_links(TV_name)
        tv_dict.clear()

    time.sleep(10)
    # 清理临时文件（代码B逻辑不生成video.ts，可注释）
    if os.path.exists('video.ts'):
        os.remove('video.ts')
    # 直播源去重
    re_dup_ordered(output_file_path)

    sys.exit()
