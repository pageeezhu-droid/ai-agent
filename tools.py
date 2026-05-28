"""
工具模块 —— Agent 可调用的所有工具
"""

import os
import re
import time
import random
import urllib.parse
import requests


# ── 工具 1：计算器 ───────────────────────────────────────

def calculate(expression: str) -> str:
    """执行纯数学计算（安全沙箱）"""
    try:
        result = eval(expression, {"__builtins__": {}}, {
            "abs": abs, "round": round, "min": min, "max": max, "pow": pow,
        })
        return str(result)
    except Exception as e:
        return f"计算出错：{e}"


# ── 工具 2：网页搜索（360 → 搜狗 → 必应 三引擎）─────────

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
]

# 搜狗 Session（复用 cookie 减少反爬）
_sogou_session = None
_last_sogou_time = 0.0


def _clean_html(text: str) -> str:
    """去除 HTML 标签和实体，压缩空白"""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&[a-z]+;|&#[0-9]+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# ── 搜索引擎 1：360 搜索（so.com，中文首选）─────────────


def _search_360(query: str) -> str | None:
    """360 搜索，失败返回 None"""
    try:
        url = f"https://www.so.com/s?q={urllib.parse.quote(query)}"
        headers = {
            "User-Agent": random.choice(_USER_AGENTS),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return None

        text = resp.text
        FILTER_KW = ["推荐", "登录", "设置", "反馈", "意见",
                      "其他人还搜了", "相关搜索", "搜索"]

        snippets = []
        for h3_html in re.findall(r"<h3[^>]*>(.*?)</h3>", text, re.DOTALL):
            title = _clean_html(h3_html)
            if not title or len(title) < 4:
                continue
            if title in FILTER_KW:
                continue
            snippets.append(title)

        return "\n\n".join(snippets[:6]) if snippets else None

    except Exception:
        return None


# ── 搜索引擎 2：搜狗（中文次选，可能 403/反爬）─────────


def _is_blocked(html: str) -> bool:
    """检测搜狗是否返回反爬/验证页面"""
    if "请输入验证码" in html:
        return True
    if "antispider" in html.lower():
        return True
    if len(html) < 30000:
        return True
    return False


def _search_sogou(query: str) -> str | None:
    """搜狗搜索（带 Session 和频率控制），失败返回 None"""
    global _sogou_session, _last_sogou_time

    try:
        # 频率控制：两次请求间隔 >= 1.8 秒
        elapsed = time.time() - _last_sogou_time
        if elapsed < 1.8:
            time.sleep(1.8 - elapsed)

        if _sogou_session is None:
            _sogou_session = requests.Session()
            _sogou_session.headers.update({
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            })
        _sogou_session.headers["User-Agent"] = random.choice(_USER_AGENTS)

        url = f"https://www.sogou.com/web?query={urllib.parse.quote(query)}"
        resp = _sogou_session.get(url, timeout=15)
        _last_sogou_time = time.time()

        # 403 → 重建 Session
        if resp.status_code == 403:
            _sogou_session = None
            return None

        if resp.status_code != 200:
            return None

        text = resp.text

        # 反爬 → 换 UA 重试一次
        if _is_blocked(text):
            _sogou_session.headers["User-Agent"] = random.choice(_USER_AGENTS)
            time.sleep(2)
            resp = _sogou_session.get(url, timeout=15)
            _last_sogou_time = time.time()
            if resp.status_code != 200 or _is_blocked(resp.text):
                _sogou_session = None
                return None
            text = resp.text

        FILTER_KW = ["推荐", "登录", "设置", "反馈", "搜狗", "意见"]
        snippets = []
        for h3_html in re.findall(r"<h3[^>]*>(.*?)</h3>", text, re.DOTALL):
            title = _clean_html(h3_html)
            if not title or len(title) < 4:
                continue
            if any(kw in title for kw in FILTER_KW):
                continue
            snippets.append(title)

        return "\n\n".join(snippets[:6]) if snippets else None

    except Exception:
        _sogou_session = None
        return None


# ── 搜索引擎 3：必应（最后兜底，中文效果差）─────────────


_BING_JUNK_KW = [
    "汉语汉字", "漢語漢字", "汉典", "漢典", "汉语国学", "漢語國學",
    "百度百科", "字的意思", "字的解釋", "字的解释", "字的拼音",
    "字的部首", "字的笔顺", "字的筆順", "说文解字", "說文解字",
    "甲骨文", "读音", "讀音", "本义", "本義", "部首", "笔画",
    "筆畫", "繁体字", "繁體字", "康熙字典", "什么意思", "什麼意思",
    "怎么读", "怎麼讀", "怎么念", "怎麼唸",
]


def _is_junk_result(text: str) -> bool:
    """检测是否为单字词典释义垃圾"""
    for kw in _BING_JUNK_KW:
        if kw in text:
            return True
    return False


def _search_bing_smart(query: str) -> str | None:
    """必应搜索，过滤词典垃圾，失败返回 None"""
    try:
        url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}"
        headers = {
            "User-Agent": random.choice(_USER_AGENTS),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return None

        text = resp.text
        snippets = []

        blocks = text.split("<li ")
        for block in blocks:
            if "b_algo" not in block:
                continue
            parts = []
            for h2 in re.findall(r"<h2[^>]*>(.*?)</h2>", block, re.DOTALL):
                t = _clean_html(h2)
                if t and len(t) > 3:
                    parts.append(t)
            for p in re.findall(r"<p[^>]*>(.*?)</p>", block, re.DOTALL):
                t = _clean_html(p)
                if t and len(t) > 20:
                    parts.append(t)
            if parts:
                merged = " | ".join(parts)
                if not _is_junk_result(merged):
                    snippets.append(merged)

        if snippets:
            return "\n\n".join(snippets[:5])

        # meta description 兜底
        match = re.search(r'<meta\s+name="description"\s+content="([^"]+)"', text)
        if match:
            desc = match.group(1)
            if not _is_junk_result(desc):
                return desc

        return None

    except Exception:
        return None


# ── 统一入口 ───────────────────────────────────────────


def search_web(query: str) -> str:
    """搜索互联网（360 → 搜狗 → 必应 三引擎级联）"""
    query = re.sub(r"\s+", " ", query).strip()

    # 1) 360 搜索（中文首选）
    result = _search_360(query)
    if result:
        return result

    # 2) 搜狗（中文次选）
    result = _search_sogou(query)
    if result:
        return result

    # 3) 必应（最后兜底）
    result = _search_bing_smart(query)
    if result:
        return result

    return f"关于「{query}」未找到相关信息，请尝试换一个搜索词"


# ── 工具 3：天气查询（wttr.in，免费免 key）───────────────

def get_weather(city: str) -> str:
    """查询城市实时天气"""
    try:
        resp = requests.get(
            f"https://wttr.in/{city}?format=%C|%t|%h|%w", timeout=10
        )
        if resp.status_code != 200:
            return f"无法查询到{city}的天气"

        parts = resp.text.strip().split("|")
        if len(parts) >= 3:
            return f"{city}天气：{parts[0]}，温度{parts[1]}，湿度{parts[2]}"
        return f"{city}天气：{resp.text}"
    except Exception as e:
        return f"查询天气出错：{e}"


# ── 工具 4-6：文件操作（限制在 workspace/ 沙箱内）─────────

WORKSPACE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "workspace")


def _ensure_workspace():
    """确保工作目录存在"""
    os.makedirs(WORKSPACE_DIR, exist_ok=True)


def _safe_path(filename: str) -> str:
    """路径安全校验，防止穿越攻击"""
    _ensure_workspace()
    full = os.path.normpath(os.path.join(WORKSPACE_DIR, filename))
    if not full.startswith(os.path.normpath(WORKSPACE_DIR)):
        raise PermissionError("不允许访问 workspace 目录外的文件")
    return full


def read_file(filename: str) -> str:
    """读取文件内容"""
    try:
        with open(_safe_path(filename), "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return f"文件「{filename}」不存在"
    except Exception as e:
        return f"读取文件出错：{e}"


def write_file(filename: str, content: str) -> str:
    """写入文件内容"""
    try:
        with open(_safe_path(filename), "w", encoding="utf-8") as f:
            f.write(content)
        return f"已成功写入文件「{filename}」"
    except Exception as e:
        return f"写入文件出错：{e}"


def list_files(path: str = "") -> str:
    """列出工作目录下的文件和文件夹"""
    try:
        target = _safe_path(path) if path else WORKSPACE_DIR
        if not os.path.exists(target):
            return f"路径「{path or '.'}」不存在"
        items = os.listdir(target)
        if not items:
            return "目录为空"
        lines = []
        for name in sorted(items):
            tag = "[DIR]" if os.path.isdir(os.path.join(target, name)) else "[FILE]"
            lines.append(f"  {tag}  {name}")
        return "\n".join(lines)
    except PermissionError:
        return f"没有权限访问「{path or '.'}」"
    except Exception as e:
        return f"列出文件出错：{e}"


# ── 工具 7：Python 代码执行（沙箱）────────────────────────

def run_python(code: str) -> str:
    """在沙箱中执行 Python 代码，捕获 stdout/stderr，10 秒超时"""
    import sys as _sys
    import io as _io
    import threading as _threading

    stdout = _io.StringIO()
    stderr = _io.StringIO()
    old_stdout, old_stderr = _sys.stdout, _sys.stderr
    _sys.stdout, _sys.stderr = stdout, stderr

    result = [None]

    # 安全模块白名单
    _SAFE_MODULES = {
        "math", "cmath", "statistics", "fractions", "decimal",
        "json", "csv", "re", "string", "textwrap", "difflib",
        "collections", "itertools", "functools", "operator",
        "random", "datetime", "time", "calendar",
        "hashlib", "base64", "binascii", "uuid",
        "typing", "dataclasses", "enum", "copy",
        "heapq", "bisect", "array", "struct", "io",
        "pprint", "inspect", "os", "shutil",
    }

    def _safe_import(name, *args, **kwargs):
        if name not in _SAFE_MODULES:
            raise ImportError(f"模块 '{name}' 不在安全白名单中")
        return __import__(name, *args, **kwargs)

    def _execute():
        try:
            safe_builtins = {
                "print": print, "len": len, "range": range, "int": int,
                "float": float, "str": str, "bool": bool, "list": list,
                "dict": dict, "tuple": tuple, "set": set, "abs": abs,
                "round": round, "min": min, "max": max, "sum": sum,
                "sorted": sorted, "enumerate": enumerate, "zip": zip,
                "map": map, "filter": filter, "reversed": reversed,
                "all": all, "any": any, "ord": ord, "chr": chr,
                "bin": bin, "oct": oct, "hex": hex, "divmod": divmod,
                "isinstance": isinstance, "issubclass": issubclass,
                "True": True, "False": False, "None": None,
                "Exception": Exception, "ValueError": ValueError,
                "TypeError": TypeError, "KeyError": KeyError,
                "open": lambda *a, **kw: open(_safe_path(a[0]) if a else "", *a[1:], **kw) if a and a[0] else open(*a, **kw),
                "__import__": _safe_import,
            }
            old_cwd = os.getcwd()
            os.chdir(WORKSPACE_DIR)
            try:
                exec(code, {"__builtins__": safe_builtins, "__name__": "__main__"})
            finally:
                os.chdir(old_cwd)
        except Exception as exc:
            result[0] = f"执行出错：{exc}"

    t = _threading.Thread(target=_execute, daemon=True)
    t.start()
    t.join(timeout=10)

    _sys.stdout, _sys.stderr = old_stdout, old_stderr

    if t.is_alive():
        return "执行超时（超过 10 秒），已终止"

    if result[0]:
        err = stderr.getvalue()
        return result[0] + (f"\nstderr: {err}" if err else "")

    out = stdout.getvalue()
    err = stderr.getvalue()
    parts = []
    if out:
        parts.append(out.rstrip())
    if err:
        parts.append(f"[stderr] {err.rstrip()}")
    return "\n".join(parts) if parts else "(代码执行完毕，无输出)"


# ── 工具注册表 ────────────────────────────────────────────

TOOL_REGISTRY = {
    "calculate":     calculate,
    "search_web":    search_web,
    "get_weather":   get_weather,
    "read_file":     read_file,
    "write_file":    write_file,
    "list_files":    list_files,
    "run_python":    run_python,
}


def get_tool_descriptions() -> str:
    """生成结构化工具描述，嵌入系统提示词"""
    return "\n\n".join([
        _desc("calculate", "执行纯数学计算",
              ["expression (字符串) — 数学表达式，如 \"3*4+5\"、\"1955-1879\"、\"2**10\""],
              returns="计算结果字符串",
              example='{"action": "calculate", "args": {"expression": "3*4+5"}}',
              warn="严格禁止传入 Python 代码、import、exec/eval/__builtins__ 等"),

        _desc("search_web", "搜索互联网获取实时信息（360搜索+搜狗+必应三引擎级联）",
              ["query (字符串) — 搜索关键词，如 \"周杰伦2026新专辑\""],
              returns="搜索结果标题列表（最多 6 条）",
              example='{"action": "search_web", "args": {"query": "量子计算最新进展"}}',
              warn="中文优先 360 搜索，失败回退搜狗，最后兜底必应"),

        _desc("get_weather", "查询城市实时天气（wttr.in）",
              ["city (字符串) — 城市名，如 \"杭州\"、\"Beijing\""],
              returns="天气状况、温度、湿度",
              example='{"action": "get_weather", "args": {"city": "杭州"}}'),

        _desc("read_file", "读取工作目录中的文件内容",
              ["filename (字符串) — 具体文件名，如 \"weather.txt\""],
              returns="文件内容字符串",
              example='{"action": "read_file", "args": {"filename": "weather.txt"}}',
              warn="禁止传入 \".\" \"/\" 等路径，查看目录请用 list_files"),

        _desc("write_file", "写入内容到工作目录中的文件",
              ["filename (字符串) — 文件名",
               "content (字符串) — 文件内容"],
              returns="写入成功或失败信息",
              example='{"action": "write_file", "args": {"filename": "result.txt", "content": "..."}}',
              warn="写入代码时注意 JSON 转义：双引号 → \\\"，换行 → \\n，反斜杠 → \\\\"),

        _desc("run_python", "在沙箱中执行 Python 代码（10 秒超时），捕获输出",
              ["code (字符串) — Python 代码，print() 输出会被捕获返回"],
              returns="stdout 输出或错误信息",
              example='{"action": "run_python", "args": {"code": "for i in range(5):\\n    print(i)"}}',
              warn="代码在受限环境中运行，文件读写限定在 workspace 目录；超 10 秒自动终止"),

        _desc("list_files", "列出工作目录中的文件和文件夹",
              ["path (字符串，可选) — 子目录路径，留空列出根目录"],
              returns="文件和目录列表，标注 [FILE] 或 [DIR]",
              example='{"action": "list_files", "args": {"path": ""}}'),
    ])


def _desc(name: str, purpose: str, params: list, returns: str = "",
          example: str = "", warn: str = "") -> str:
    """格式化单个工具的描述（System Prompt 用，双花括号转义）"""
    lines = [f"### {name} — {purpose}"]
    for p in params:
        lines.append(f"- 参数：{p}")
    if returns:
        lines.append(f"- 返回：{returns}")
    lines.append(f"- 示例：{_escape_braces(example)}")
    if warn:
        lines.append(f"- ⚠️ {warn}")
    return "\n".join(lines)


def _escape_braces(s: str) -> str:
    """将 JSON 示例中的 { } 转为 {{ }}，供 .format() 安全使用"""
    return s.replace("{", "{{").replace("}", "}}")


def call_tool(name: str, args: dict) -> str:
    """根据名称调用工具"""
    fn = TOOL_REGISTRY.get(name)
    if fn is None:
        return f"错误：未知工具「{name}」，可用：{', '.join(TOOL_REGISTRY)}"
    try:
        return str(fn(**args))
    except TypeError as e:
        return f"参数错误：{e}"
    except Exception as e:
        return f"工具执行出错：{e}"
