"""
LLM API 封装 —— DeepSeek API（兼容 OpenAI 格式）
"""

import json
import os
import requests


API_KEY = os.environ["DEEPSEEK_API_KEY"]
API_URL = "https://api.deepseek.com/v1/chat/completions"
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_MAX_TOKENS = 8192
DEFAULT_TEMPERATURE = 0.1


def _build_payload(messages: list, system_prompt: str,
                   temperature: float, stream: bool) -> str:
    """构建 API 请求体（返回编码后的 bytes）"""
    full_messages = []
    if system_prompt:
        full_messages.append({"role": "system", "content": system_prompt})
    full_messages.extend(messages)

    payload = {
        "model": DEFAULT_MODEL,
        "messages": full_messages,
        "max_tokens": DEFAULT_MAX_TOKENS,
        "temperature": temperature,
        "stream": stream,
    }
    # ensure_ascii=True 防止 Windows surrogate 字符导致 400 错误
    return json.dumps(payload, ensure_ascii=True).encode("utf-8")


def _error_context(resp=None) -> str:
    """提取响应中的错误详情"""
    try:
        return f" | {resp.text[:300]}"
    except Exception:
        return ""


def call_llm(messages: list, system_prompt: str = "",
             temperature: float = DEFAULT_TEMPERATURE) -> str:
    """调用 LLM，返回完整响应文本"""
    try:
        resp = requests.post(
            API_URL, headers=HEADERS,
            data=_build_payload(messages, system_prompt, temperature, stream=False),
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except requests.exceptions.Timeout:
        return "【API 请求超时，请重试】"
    except requests.exceptions.HTTPError as e:
        return f"【API 请求失败：{e}{_error_context(resp)}】"
    except Exception as e:
        return f"【调用 LLM 时出错：{e}】"


def call_llm_stream(messages: list, system_prompt: str = "",
                    temperature: float = DEFAULT_TEMPERATURE):
    """调用 LLM，流式逐 token yield（SSE 协议）"""
    try:
        resp = requests.post(
            API_URL, headers=HEADERS,
            data=_build_payload(messages, system_prompt, temperature, stream=True),
            timeout=60, stream=True,
        )
        resp.raise_for_status()

        for line in resp.iter_lines(decode_unicode=True):
            if not line or line.startswith(":") or line == "data: [DONE]":
                continue
            if line.startswith("data: "):
                try:
                    chunk = json.loads(line[6:])
                    content = chunk["choices"][0].get("delta", {}).get("content", "")
                    if content:
                        yield content
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue

    except requests.exceptions.Timeout:
        yield "【API 请求超时，请重试】"
    except requests.exceptions.HTTPError as e:
        yield f"【API 请求失败：{e}{_error_context(resp)}】"
    except Exception as e:
        yield f"【调用 LLM 时出错：{e}】"
