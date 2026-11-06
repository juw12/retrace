"""Image forensics: recover the AI generator, prompt and settings from file metadata.

Reads PNG text chunks, EXIF, XMP and C2PA (Content Credentials) with the standard
library only. It can only recover what the file still carries: screenshots and most
social-media re-uploads strip metadata.
"""

import html
import json
import re
import struct
import zlib

from .report import Report

EXIF_TEXT_TAGS = {
    0x010E: "ImageDescription",
    0x010F: "Make",
    0x0110: "Model",
    0x0131: "Software",
    0x013B: "Artist",
    0x8298: "Copyright",
    0x9286: "UserComment",
    0x9C9B: "XPTitle",
    0x9C9C: "XPComment",
    0x9C9E: "XPKeywords",
    0x9C9F: "XPSubject",
}
EXIF_IFD_POINTER = 0x8769
SOF_MARKERS = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
XMP_HEADER = b"http://ns.adobe.com/xap/1.0/\x00"
TOOL_FIELD = re.compile(r"software|creatortool|creator|make|model|author|credit|source|generator|artist", re.I)

# (candidate name, regex). Matched against metadata and C2PA manifests.
GENERATORS = [
    ("Midjourney", r"midjourney|job id:\s*[0-9a-f-]{36}"),
    ("OpenAI (ChatGPT / DALL·E / GPT-image)", r"openai|chatgpt|dall[·\-\s]?e|gpt-image|gpt-4o"),
    ("Adobe Firefly", r"firefly"),
    ("Google (Gemini / Imagen)", r"made with google ai|\bimagen\b|gemini|google ai|nano.?banana"),
    ("Microsoft (Designer / Bing Image Creator / Copilot)",
     r"microsoft designer|bing image creator|image creator from microsoft|microsoft copilot|azure openai"),
    ("Meta AI", r"meta ai|imagined with ai"),
    ("Stability AI (DreamStudio / Stable Assistant)", r"dreamstudio|stability\.ai|stable assistant"),
    ("Leonardo.Ai", r"leonardo\.ai|leonardo ai"),
    ("Ideogram", r"ideogram"),
    ("Black Forest Labs Flux", r"\bflux[\.\-_ ]?(1|dev|schnell|pro|kontext)|black forest labs"),
    ("Runway", r"runwayml|runway gen"),
    ("NovelAI", r"novelai"),
    ("Draw Things", r"draw things"),
    ("DiffusionBee", r"diffusionbee"),
    ("Krita AI Diffusion", r"krita ai"),
    ("xAI Grok (Aurora)", r"\bgrok\b|\bx\.ai\b"),
    ("Freepik / Magnific", r"freepik|magnific"),
    ("Recraft", r"recraft"),
    ("Playground AI", r"playground ?ai|playgroundai"),
    ("Kling", r"\bkling\b"),
    ("OpenAI Sora", r"\bsora\b"),
    ("Tencent Hunyuan", r"hunyuan"),
    ("Alibaba Qwen / Wan", r"tongyi|wanx|qwen-image"),
    ("ByteDance Seedream / Doubao", r"seedream|doubao|jimeng"),
]

COMMON_SIZES = {
    (1024, 1024): "square 1024 (DALL·E 3, GPT-image, SDXL, Flux, Midjourney…)",
    (1792, 1024): "DALL·E 3 wide",
    (1024, 1792): "DALL·E 3 tall",
    (1536, 1024): "GPT-image / ChatGPT landscape",
    (1024, 1536): "GPT-image / ChatGPT portrait",
    (1456, 816): "Midjourney 16:9",
    (816, 1456): "Midjourney 9:16",
    (1232, 928): "Midjourney 4:3",
    (928, 1232): "Midjourney 3:4",
    (1344, 896): "Midjourney 3:2",
    (896, 1344): "Midjourney 2:3",
    (512, 512): "Stable Diffusion 1.x default",
    (512, 768): "Stable Diffusion 1.x portrait",
    (768, 512): "Stable Diffusion 1.x landscape",
    (1216, 832): "SDXL / Flux bucket",
    (832, 1216): "SDXL / Flux bucket",
    (1152, 896): "SDXL / Flux bucket",
    (896, 1152): "SDXL / Flux bucket",
    (1344, 768): "SDXL / Flux bucket",
    (768, 1344): "SDXL / Flux bucket",
}

A1111_SETTING = re.compile(r'\s*([\w ]+):\s*("(?:\\.|[^\\"])+"|[^,]*)(?:,|$)')
COMFY_TEXT_KEYS = ("text", "text_g", "text_l", "t5xxl", "clip_l", "prompt", "string", "value")


# --------------------------------------------------------------------------- entry point

def analyze_image(data, filename=""):
    image_format = detect_format(data)
    metadata = {}
    c2pa_blobs = []
    readers = {"png": _read_png, "jpeg": _read_jpeg, "webp": _read_webp}
    if image_format in readers:
        width, height = readers[image_format](data, metadata, c2pa_blobs)
    else:
        width = height = None
    if not c2pa_blobs:
        index = data.find(b"c2pa")
        if index != -1:
            c2pa_blobs.append(data[max(0, index - 256):index + 65536])

    report = Report("image")
    report.details["File"] = filename or "(unnamed)"
    report.details["Format"] = image_format
    if width:
        report.details["Dimensions"] = f"{width} × {height}"

    c2pa = _summarize_c2pa(c2pa_blobs)
    if c2pa:
        generators = ", ".join(c2pa["claim_generators"]) or "unnamed"
        report.details["C2PA Content Credentials"] = f"present (claim generator: {generators})"
        if c2pa["actions"]:
            report.details["C2PA actions"] = ", ".join(c2pa["actions"])

    _extract_generation_data(metadata, report)
    _match_generators(metadata, c2pa, report)
    _check_ai_declarations(metadata, c2pa, report)
    _size_hint(width, height, report)
    if not report.prompt:
        _fallback_prompt(metadata, report)

    if not metadata and not c2pa:
        report.notes.append(
            "No metadata at all — typical of screenshots, social-media re-uploads or stripped files. "
            "Tick 'Ask my LLM' for a visual reverse-prompt, or try a pixel classifier such as Hive Moderation."
        )
    report.raw["metadata"] = {key: value[:20000] for key, value in metadata.items()}
    if c2pa:
        report.raw["c2pa"] = c2pa
    return report.to_dict(fallback_label="No AI signature in metadata")


def detect_format(data):
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8"):
        return "jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[4:12] in (b"ftypavif", b"ftypheic", b"ftypmif1"):
        return "avif/heic"
    return "unknown"


# --------------------------------------------------------------------------- container readers

def _read_png(data, metadata, c2pa_blobs):
    width = height = None
    position = 8
    while position + 8 <= len(data):
        length, chunk_type = struct.unpack(">I4s", data[position:position + 8])
        body = data[position + 8:position + 8 + length]
        position += 12 + length
        if chunk_type == b"IHDR":
            width, height = struct.unpack(">II", body[:8])
        elif chunk_type == b"tEXt":
            key, _, value = body.partition(b"\x00")
            _store_text(metadata, key.decode("latin-1"), value.decode("latin-1"))
        elif chunk_type == b"zTXt":
            key, _, rest = body.partition(b"\x00")
            _store_text(metadata, key.decode("latin-1"), _inflate(rest[1:]).decode("latin-1", "replace"))
        elif chunk_type == b"iTXt":
            key, _, rest = body.partition(b"\x00")
            compressed = rest[:1] == b"\x01"
            _language, _, rest = rest[2:].partition(b"\x00")
            _translated_key, _, text = rest.partition(b"\x00")
            if compressed:
                text = _inflate(text)
            _store_text(metadata, key.decode("latin-1"), text.decode("utf-8", "replace"))
        elif chunk_type == b"eXIf":
            _parse_exif(body, metadata)
        elif chunk_type == b"caBX":
            c2pa_blobs.append(body)
        elif chunk_type == b"IEND":
            break
    return width, height


def _read_jpeg(data, metadata, c2pa_blobs):
    width = height = None
    position = 2
    while position + 4 <= len(data):
        if data[position] != 0xFF:
            break
        marker = data[position + 1]
        if marker == 0xFF:
            position += 1
            continue
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            position += 2
            continue
        if marker == 0xD9:
            break
        length = struct.unpack(">H", data[position + 2:position + 4])[0]
        segment = data[position + 4:position + 2 + length]
        if marker == 0xE1 and segment.startswith(b"Exif\x00\x00"):
            _parse_exif(segment[6:], metadata)
        elif marker == 0xE1 and segment.startswith(XMP_HEADER):
            _add_xmp(segment[len(XMP_HEADER):].decode("utf-8", "replace"), metadata)
        elif marker == 0xEB:
            c2pa_blobs.append(segment)
        elif marker == 0xFE:
            metadata["JPEG comment"] = segment.decode("utf-8", "replace")
        elif marker in SOF_MARKERS and len(segment) >= 5:
            height, width = struct.unpack(">HH", segment[1:5])
        elif marker == 0xDA:
            break
        position += 2 + length
    return width, height


def _read_webp(data, metadata, c2pa_blobs):
    width = height = None
    position = 12
    while position + 8 <= len(data):
        chunk_type = data[position:position + 4]
        size = struct.unpack("<I", data[position + 4:position + 8])[0]
        body = data[position + 8:position + 8 + size]
        position += 8 + size + (size & 1)
        if chunk_type == b"VP8X" and len(body) >= 10:
            width = 1 + int.from_bytes(body[4:7], "little")
            height = 1 + int.from_bytes(body[7:10], "little")
        elif chunk_type == b"VP8 " and width is None and len(body) >= 10:
            width, height = struct.unpack("<HH", body[6:10])
            width &= 0x3FFF
            height &= 0x3FFF
        elif chunk_type == b"VP8L" and width is None and len(body) >= 5:
            bits = int.from_bytes(body[1:5], "little")
            width = (bits & 0x3FFF) + 1
            height = ((bits >> 14) & 0x3FFF) + 1
        elif chunk_type == b"EXIF":
            _parse_exif(body[6:] if body.startswith(b"Exif\x00\x00") else body, metadata)
        elif chunk_type == b"XMP ":
            _add_xmp(body.decode("utf-8", "replace"), metadata)
        elif chunk_type == b"C2PA":
            c2pa_blobs.append(body)
    return width, height


def _store_text(metadata, key, value):
    if key == "XML:com.adobe.xmp":
        _add_xmp(value, metadata)
    else:
        metadata[key] = value


def _inflate(blob):
    try:
        return zlib.decompress(blob)
    except zlib.error:
        return b""


def _parse_exif(tiff, metadata):
    if len(tiff) < 8 or tiff[:2] not in (b"II", b"MM"):
        return
    endian = "<" if tiff[:2] == b"II" else ">"
    visited = set()

    def walk(offset):
        if offset in visited or offset + 2 > len(tiff):
            return
        visited.add(offset)
        count = struct.unpack(endian + "H", tiff[offset:offset + 2])[0]
        for index in range(count):
            entry = offset + 2 + 12 * index
            if entry + 12 > len(tiff):
                return
            tag, value_type, value_count = struct.unpack(endian + "HHI", tiff[entry:entry + 8])
            pointer = struct.unpack(endian + "I", tiff[entry + 8:entry + 12])[0]
            if tag == EXIF_IFD_POINTER:
                walk(pointer)
                continue
            name = EXIF_TEXT_TAGS.get(tag)
            if not name or value_type not in (1, 2, 7):
                continue
            raw = tiff[entry + 8:entry + 8 + value_count] if value_count <= 4 else tiff[pointer:pointer + value_count]
            text = _decode_exif_text(name, raw)
            if text:
                metadata["EXIF:" + name] = text

    walk(struct.unpack(endian + "I", tiff[4:8])[0])

    # ComfyUI stores its graph in EXIF Make/ImageDescription as "prompt:{...}" / "workflow:{...}".
    for field in ("EXIF:Make", "EXIF:ImageDescription", "EXIF:Model"):
        value = metadata.get(field, "")
        for key in ("prompt", "workflow"):
            if value.lower().startswith(key + ":"):
                metadata.setdefault(key, value[len(key) + 1:])


def _decode_exif_text(name, raw):
    if name.startswith("XP"):
        return raw.decode("utf-16-le", "replace").rstrip("\x00").strip()
    if name == "UserComment":
        prefix, body = raw[:8], raw[8:]
        if prefix.startswith(b"UNICODE"):
            options = [body.decode("utf-16-be", "replace"), body.decode("utf-16-le", "replace")]
            text = max(options, key=lambda candidate: sum(ord(ch) < 256 for ch in candidate))
        else:
            text = body.decode("utf-8", "replace")
        return text.rstrip("\x00").strip()
    return raw.decode("utf-8", "replace").rstrip("\x00").strip()


def _add_xmp(xml, metadata):
    for match in re.finditer(r"<([A-Za-z][\w.-]*:[\w.-]+)(\s[^>]*)?>", xml):
        tag = match.group(1)
        if tag.split(":")[0] in ("rdf", "x"):
            continue
        end = xml.find(f"</{tag}>", match.end())
        if end == -1:
            continue
        inner = re.sub(r"<[^>]+>", " ", xml[match.end():end])
        inner = html.unescape(" ".join(inner.split()))
        if inner:
            metadata.setdefault("XMP:" + tag, inner)
    for match in re.finditer(r'\s([A-Za-z][\w.-]*:[\w.-]+)="([^"]*)"', xml):
        key = match.group(1)
        if key.split(":")[0] in ("xmlns", "rdf", "x", "xml"):
            continue
        metadata.setdefault("XMP:" + key, html.unescape(match.group(2)))


# --------------------------------------------------------------------------- C2PA

def _cbor_text_after(blob, index):
    """Read a CBOR text string that starts at blob[index]."""
    if index >= len(blob):
        return None
    head = blob[index]
    if 0x60 <= head <= 0x77:
        length, start = head - 0x60, index + 1
    elif head == 0x78 and index + 1 < len(blob):
        length, start = blob[index + 1], index + 2
    elif head == 0x79 and index + 2 < len(blob):
        length, start = int.from_bytes(blob[index + 1:index + 3], "big"), index + 3
    else:
        return None
    return blob[start:start + length].decode("utf-8", "replace")


def _summarize_c2pa(blobs):
    if not blobs:
        return None
    joined = b"".join(blobs)
    generators = []
    for match in re.finditer(rb"claim_generator(?!_)", joined):
        value = _cbor_text_after(joined, match.end())
        if value:
            generators.append(value)
    for match in re.finditer(rb"claim_generator_info", joined):
        window = joined[match.end():match.end() + 300]
        name_index = window.find(b"name")
        if name_index != -1:
            value = _cbor_text_after(window, name_index + 4)
            if value:
                generators.append(value)
    strings = []
    for run in re.findall(rb"[\x20-\x7e]{5,}", joined):
        text = run.decode("ascii")[:200]
        if text not in strings:
            strings.append(text)
    return {
        "claim_generators": list(dict.fromkeys(generators)),
        "source_types": sorted(set(
            item.decode() for item in re.findall(rb"digitalsourcetype/(\w+)", joined, re.I)
        )),
        "actions": sorted(set(item.decode() for item in re.findall(rb"c2pa\.(\w+)", joined))),
        "strings": strings[:300],
    }


# --------------------------------------------------------------------------- generation data

def _extract_generation_data(metadata, report):
    params = metadata.get("parameters")
    user_comment = metadata.get("EXIF:UserComment", "")
    if not params and "Steps:" in user_comment:
        params = user_comment
    if params:
        if params.lstrip().startswith("{"):
            _from_json_parameters(params, report)
        else:
            _from_a1111(params, report)
    if "prompt" in metadata or "workflow" in metadata:
        _from_comfyui(metadata, report)
    comment = metadata.get("Comment", "")
    if metadata.get("Software", "").lower().startswith("novelai") or '"uc"' in comment:
        _from_novelai(metadata, report)
    for key in ("invokeai_metadata", "sd-metadata", "Dream"):
        if key in metadata:
            _from_invokeai(key, metadata[key], report)
            break
    if "fooocus_scheme" in metadata:
        report.add("Fooocus", "strong", "fooocus_scheme chunk", metadata["fooocus_scheme"])

    for key in ("Description", "XMP:dc:description", "EXIF:ImageDescription"):
        description = metadata.get(key, "")
        if re.search(r"Job ID:\s*[0-9a-f-]{36}", description, re.I):
            prompt = re.split(r"\s*Job ID:", description, flags=re.I)[0].strip()
            report.add("Midjourney", "strong", f"Midjourney Job ID in {key}", description[:200])
            _set_prompt(report, prompt, "", key)
            break


def _from_a1111(text, report):
    lines = text.strip().split("\n")
    settings_line = lines.pop() if lines and re.match(r"\s*Steps:", lines[-1]) else ""
    positive, _, negative = "\n".join(lines).partition("Negative prompt:")
    settings = {key.strip(): value.strip().strip('"') for key, value in A1111_SETTING.findall(settings_line)}
    if "Civitai resources" in settings or "civitai" in text.lower():
        tool = "Stable Diffusion — Civitai generator"
    elif settings.get("Version", "").startswith("f"):
        tool = "Stable Diffusion — Forge WebUI"
    else:
        tool = "Stable Diffusion — AUTOMATIC1111 WebUI"
    report.add(tool, "strong", "A1111-style 'parameters' metadata", settings_line[:300])
    _set_prompt(report, positive.strip(), negative.strip(), "parameters")
    for key in ("Model", "Model hash", "Sampler", "Schedule type", "Steps", "CFG scale", "Seed", "Size",
                "Denoising strength", "Hires upscaler", "Clip skip", "VAE", "Version"):
        if key in settings:
            report.details[key] = settings[key]
    loras = re.findall(r"<lora:([^:>]+)", positive)
    if loras:
        report.details["LoRAs"] = ", ".join(dict.fromkeys(loras))


def _from_json_parameters(text, report):
    data = _loads(text)
    if not isinstance(data, dict):
        return
    if isinstance(data.get("sui_image_params"), dict):
        params = data["sui_image_params"]
        report.add("SwarmUI", "strong", "sui_image_params JSON", "")
        _set_prompt(report, params.get("prompt", ""), params.get("negativeprompt", ""), "SwarmUI parameters")
        _copy(params, report, {"model": "Model", "seed": "Seed", "steps": "Steps", "cfgscale": "CFG scale",
                               "sampler": "Sampler", "width": "Width", "height": "Height"})
    elif "prompt" in data:
        tool = "Fooocus" if "fooocus" in text.lower() else "Stable Diffusion (JSON parameters)"
        report.add(tool, "strong", "JSON 'parameters' metadata", data.get("version", ""))
        _set_prompt(report, data.get("prompt", ""), data.get("negative_prompt", ""), "parameters JSON")
        _copy(data, report, {"base_model": "Model", "refiner_model": "Refiner", "seed": "Seed", "steps": "Steps",
                             "guidance_scale": "CFG scale", "sampler": "Sampler", "performance": "Performance",
                             "styles": "Styles", "resolution": "Size", "version": "Version"})


def _from_comfyui(metadata, report):
    report.add("ComfyUI (Stable Diffusion / Flux workflow)", "strong", "ComfyUI graph embedded in file", "")
    graph = _loads(metadata.get("prompt", ""))
    if not isinstance(graph, dict):
        return
    nodes = {str(key): node for key, node in graph.items() if isinstance(node, dict) and "class_type" in node}

    positives, negatives = [], []
    for node in nodes.values():
        inputs = node.get("inputs", {})
        if "Sampler" not in node["class_type"] or not ("positive" in inputs or "guider" in inputs):
            continue
        guider = inputs.get("guider")
        if _is_link(guider, nodes):
            inputs = nodes[str(guider[0])].get("inputs", {})
        positives += _comfy_texts(nodes, inputs.get("positive") or inputs.get("conditioning"))
        negatives += _comfy_texts(nodes, inputs.get("negative"))
        for key, label in (("seed", "Seed"), ("noise_seed", "Seed"), ("steps", "Steps"), ("cfg", "CFG scale"),
                           ("sampler_name", "Sampler"), ("scheduler", "Scheduler"), ("denoise", "Denoise")):
            if key in node.get("inputs", {}) and not isinstance(node["inputs"][key], list):
                report.details.setdefault(label, str(node["inputs"][key]))
    if not positives:
        positives = [node["inputs"]["text"] for node in nodes.values()
                     if node["class_type"].startswith("CLIPTextEncode")
                     and isinstance(node.get("inputs", {}).get("text"), str)]
    _set_prompt(report, "\n".join(dict.fromkeys(positives)), "\n".join(dict.fromkeys(negatives)), "ComfyUI graph")

    models, loras = [], []
    for node in nodes.values():
        for key, value in node.get("inputs", {}).items():
            if isinstance(value, str) and key in ("ckpt_name", "unet_name", "model_name"):
                models.append(value)
            if isinstance(value, str) and key == "lora_name":
                loras.append(value)
    if models:
        report.details["Model"] = ", ".join(dict.fromkeys(models))
    if loras:
        report.details["LoRAs"] = ", ".join(dict.fromkeys(loras))


def _is_link(value, nodes):
    return isinstance(value, list) and len(value) == 2 and str(value[0]) in nodes


def _comfy_texts(nodes, link, depth=0):
    if not _is_link(link, nodes) or depth > 6:
        return []
    found = []
    for key, value in nodes[str(link[0])].get("inputs", {}).items():
        if key in COMFY_TEXT_KEYS and isinstance(value, str) and value.strip():
            found.append(value.strip())
        elif isinstance(value, list):
            found += _comfy_texts(nodes, value, depth + 1)
    return found


def _from_novelai(metadata, report):
    info = _loads(metadata.get("Comment", "")) or {}
    report.add("NovelAI", "strong", "NovelAI Software/Comment metadata",
               metadata.get("Source", metadata.get("Software", "")))
    _set_prompt(report, info.get("prompt") or metadata.get("Description", ""), info.get("uc", ""), "NovelAI metadata")
    _copy(info, report, {"steps": "Steps", "seed": "Seed", "sampler": "Sampler", "scale": "CFG scale"})
    if "Source" in metadata:
        report.details["Model"] = metadata["Source"]


def _from_invokeai(key, text, report):
    report.add("InvokeAI", "strong", f"InvokeAI '{key}' metadata", "")
    data = _loads(text) or {}
    if key == "invokeai_metadata":
        _set_prompt(report, data.get("positive_prompt", ""), data.get("negative_prompt", ""), key)
        model = data.get("model")
        if isinstance(model, dict):
            model = model.get("name") or model.get("model_name")
        if model:
            report.details["Model"] = str(model)
        _copy(data, report, {"seed": "Seed", "steps": "Steps", "cfg_scale": "CFG scale", "scheduler": "Sampler"})
    elif key == "sd-metadata":
        image = data.get("image", {})
        prompt = image.get("prompt", "")
        if isinstance(prompt, list):
            prompt = " ".join(part.get("prompt", "") for part in prompt if isinstance(part, dict))
        _set_prompt(report, prompt, "", key)
        if data.get("model_weights"):
            report.details["Model"] = str(data["model_weights"])
        _copy(image, report, {"seed": "Seed", "steps": "Steps", "cfg_scale": "CFG scale", "sampler": "Sampler"})
    else:
        _set_prompt(report, text, "", key)


# --------------------------------------------------------------------------- matching

def _match_generators(metadata, c2pa, report):
    tool_text = "\n".join(value for key, value in metadata.items() if TOOL_FIELD.search(key) and len(value) < 2000)
    claim_text = "\n".join(c2pa["claim_generators"]) if c2pa else ""
    c2pa_text = "\n".join(c2pa["strings"]) if c2pa else ""
    other_text = "\n".join(value[:5000] for value in metadata.values())
    places = [
        (claim_text, "strong", "C2PA claim generator"),
        (tool_text, "strong", "Software / creator metadata field"),
        (c2pa_text, "medium", "C2PA manifest or signing certificate"),
        (other_text, "weak", "Mentioned somewhere in metadata (could be prompt text)"),
    ]
    for name, pattern in GENERATORS:
        regex = re.compile(pattern, re.I)
        for text, strength, signal in places:
            match = regex.search(text)
            if match:
                start = max(0, match.start() - 60)
                report.add(name, strength, signal, text[start:match.end() + 60])
                break


def _check_ai_declarations(metadata, c2pa, report):
    joined = "\n".join(list(metadata.values()) + (c2pa["source_types"] if c2pa else []))
    declared = set(re.findall(
        r"compositeWithTrainedAlgorithmicMedia|trainedAlgorithmicMedia|algorithmicMedia", joined, re.I))
    if declared:
        report.details["Declared AI-generated"] = ", ".join(sorted(declared))
        candidate = None if report.scores else "AI-generated (tool not named)"
        report.add(candidate, "medium", "IPTC / C2PA digitalSourceType declares AI generation", ", ".join(declared))
    elif re.search(r"digitalCapture|computationalCapture", joined, re.I):
        report.notes.append("Content Credentials / IPTC declare a camera capture, not AI generation.")


def _size_hint(width, height, report):
    hint = COMMON_SIZES.get((width, height))
    if hint:
        report.add(None, "weak", "Image size matches a common generator output (hint only)", hint)


def _fallback_prompt(metadata, report):
    for key in ("Description", "XMP:dc:description", "EXIF:ImageDescription", "EXIF:UserComment",
                "XMP:exif:UserComment", "Comment", "EXIF:XPComment", "JPEG comment", "Title", "XMP:dc:title"):
        value = metadata.get(key, "").strip()
        if len(value) > 15:
            _set_prompt(report, value, "", f"{key} (possible prompt — unverified)")
            return


# --------------------------------------------------------------------------- helpers

def _set_prompt(report, positive, negative, source):
    if positive and "positive" not in report.prompt:
        report.prompt = {"positive": positive, "negative": negative, "source": source}


def _copy(source, report, mapping):
    for key, label in mapping.items():
        value = source.get(key)
        if value not in (None, "", []):
            report.details[label] = value if isinstance(value, str) else json.dumps(value)


def _loads(text):
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None
