"""Optional LLM helper (any OpenAI-compatible endpoint: OpenAI, OpenRouter, Ollama, LM Studio, Groq…).

Used for the visual / textual reverse-prompt guess and for the endpoint probe.
The API key comes from the browser with each request and is never stored on disk.
"""

import base64
import json
import re
import urllib.error
import urllib.request
from urllib.parse import urlparse

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # local models must skip corporate proxies

IMAGE_INSTRUCTIONS = """You are an AI-image forensics assistant. Study the image and answer ONLY with JSON:
{"prompt": "the most likely text-to-image prompt that produced it, written in generator style",
 "negative_prompt": "likely negative prompt or empty",
 "generator_guess": "most likely generator/model family (e.g. Midjourney v6, DALL-E 3, GPT-image, SDXL, Flux, Imagen, Firefly) or 'probably a real photo'",
 "confidence": "low | medium | high",
 "reasons": ["visual clues behind the guess"],
 "style_keywords": ["artist/style/camera/lighting keywords a user would type"]}"""

TEXT_INSTRUCTIONS = """You are an AI-text forensics assistant. Study the text and answer ONLY with JSON:
{"likely_prompt": "the user prompt that most likely produced this text",
 "system_prompt_hints": "persona, rules or formatting instructions the writer seems to follow",
 "model_guess": "most likely model family (GPT-4o/GPT-5, Claude, Gemini, Llama, DeepSeek, Grok…) or 'probably human'",
 "confidence": "low | medium | high",
 "reasons": ["clues behind the guess"],
 "tools_or_skills": ["tools the writer seems to have used, e.g. web search citations, code execution, file reading"]}

TEXT:
"""


def chat(config, messages, max_tokens=900):
    """Call /chat/completions. Returns (reply_text, response_json, response_headers)."""
    base_url = (config.get("base_url") or "https://api.openai.com/v1").rstrip("/")
    if not config.get("model"):
        raise ValueError("Set a model name in Settings first.")
    headers = {"Content-Type": "application/json"}
    if config.get("api_key"):
        headers["Authorization"] = f"Bearer {config['api_key']}"
    payload = {"model": config["model"], "messages": messages, "max_tokens": max_tokens, "temperature": 0}
    try:
        body, response_headers = _post(base_url + "/chat/completions", payload, headers)
    except RuntimeError as error:
        # Some newer models reject max_tokens/temperature; retry with the bare minimum.
        if not re.search(r"max_tokens|temperature|unsupported", str(error), re.I):
            raise
        body, response_headers = _post(base_url + "/chat/completions",
                                       {"model": config["model"], "messages": messages}, headers)
    reply = body.get("choices", [{}])[0].get("message", {}).get("content") or ""
    return reply, body, response_headers


def _post(url, payload, headers):
    request = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers)
    try:
        opener = DIRECT if urlparse(url).hostname in LOCAL_HOSTS else urllib.request.build_opener()
        with opener.open(request, timeout=180) as response:
            return json.loads(response.read()), dict(response.headers.items())
    except urllib.error.HTTPError as error:
        detail = error.read()[:800].decode("utf-8", "replace")
        raise RuntimeError(f"HTTP {error.code} from {url}: {detail}") from None


def parse_json_reply(text):
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(cleaned[start:end + 1])
        except ValueError:
            pass
    return {"answer": text}


def reverse_image(config, image_bytes, mime_type):
    data_url = f"data:{mime_type or 'image/png'};base64,{base64.b64encode(image_bytes).decode()}"
    messages = [{"role": "user", "content": [
        {"type": "text", "text": IMAGE_INSTRUCTIONS},
        {"type": "image_url", "image_url": {"url": data_url}},
    ]}]
    reply, _, _ = chat(config, messages)
    return parse_json_reply(reply)


def reverse_text(config, text):
    reply, _, _ = chat(config, [{"role": "user", "content": TEXT_INSTRUCTIONS + text[:20000]}])
    return parse_json_reply(reply)
