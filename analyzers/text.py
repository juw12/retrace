"""Text forensics: guess whether (and which) AI wrote a text.

Looks for leftover tool artifacts (ChatGPT citation tokens, reasoning tags, tracking
parameters), self-identification, hidden Unicode payloads, model-specific phrasing and
style statistics. All of it is heuristic — treat results as leads, not proof.
"""

import re
import statistics
import unicodedata

from .report import Report

# (candidate or None, strength, regex, signal)
ARTIFACTS = [
    ("OpenAI ChatGPT", "strong", r"utm_source=chatgpt\.com", "ChatGPT web-search link tag (utm_source=chatgpt.com)"),
    ("OpenAI ChatGPT", "strong", r"utm_source=openai", "OpenAI link tag (utm_source=openai)"),
    ("OpenAI ChatGPT", "strong", r"contentReference\[oaicite|oaicite:\d+", "ChatGPT citation placeholder (oaicite)"),
    ("OpenAI ChatGPT", "strong", r"\bturn\d+(?:search|news|view|file|image)\d+", "ChatGPT search citation token"),
    ("OpenAI ChatGPT", "strong", r"【\d+(?::\d+)?†[^】]*】", "ChatGPT file/browse citation mark"),
    ("Perplexity", "medium", r"utm_source=perplexity|perplexity\.ai/search", "Perplexity link tag"),
    ("Google Gemini", "medium", r"utm_source=gemini|gemini\.google\.com", "Gemini link tag"),
    ("Microsoft Copilot", "medium", r"utm_source=copilot|copilot\.microsoft\.com", "Copilot link tag"),
    ("Reasoning model (DeepSeek-R1 / QwQ style)", "strong", r"</?think>", "Reasoning tags left in the output"),
    ("Anthropic Claude", "strong", r"\bI(?:'m| am) Claude\b|\bcreated by Anthropic\b|\bmade by Anthropic\b",
     "Self-identifies as Claude"),
    ("OpenAI ChatGPT", "strong", r"\bI(?:'m| am) ChatGPT\b|\b(?:developed|trained|created) by OpenAI\b",
     "Self-identifies as ChatGPT/OpenAI"),
    ("Google Gemini", "strong", r"\bI(?:'m| am) Gemini\b|\btrained by Google\b", "Self-identifies as Gemini/Google"),
    ("Meta Llama", "strong", r"\bI(?:'m| am) (?:Llama|Meta AI)\b", "Self-identifies as Llama/Meta AI"),
    ("DeepSeek", "strong", r"\bI(?:'m| am) DeepSeek\b", "Self-identifies as DeepSeek"),
    (None, "medium", r"\bas an ai(?: language)? model\b|\bas a large language model\b|\bmy knowledge cutoff\b",
     "Generic AI disclaimer"),
    (None, "medium", r"\bI hope this helps\b|\blet me know if you(?:'d like| need| have| want)\b|\bfeel free to ask\b",
     "Assistant-style closer"),
    (None, "weak", r"^(?:certainly|absolutely|great question|sure thing)[!,.]", "Assistant-style opener"),
]

STYLE_MARKERS = {
    "OpenAI ChatGPT": ["delve", "tapestry", "testament to", "in the realm of", "embark", "seamless", "vibrant",
                       "it's important to note", "in today's fast-paced", "game-changer", "unlock the",
                       "elevate your", "navigate the", "ever-evolving", "let's dive in", "no fluff",
                       "here's the kicker", "bottom line:"],
    "Anthropic Claude": ["i'd be happy to", "i should note", "i want to be direct", "genuinely", "i notice that",
                         "straightforward", "i'd suggest", "that said,", "nuanced", "i'm not able to verify"],
    "Google Gemini": ["here's a breakdown", "it's worth noting", "key takeaways", "in essence",
                      "let's break down", "keep in mind", "here are some key"],
    "Meta Llama": ["i can't fulfill that request", "i cannot provide", "i'm happy to help!",
                   "is there anything else i can help you with"],
    "DeepSeek": ["okay, so", "alright, let's", "hmm,", "wait,", "let me think"],
}

INVISIBLE_CHARS = {
    0x200B: "zero-width space",
    0x200C: "zero-width non-joiner",
    0x200D: "zero-width joiner",
    0x2060: "word joiner",
    0xFEFF: "zero-width no-break space (BOM)",
    0x202F: "narrow no-break space",
    0x00A0: "no-break space",
    0x00AD: "soft hyphen",
    0x180E: "Mongolian vowel separator",
    0x202A: "bidi control", 0x202B: "bidi control", 0x202C: "bidi control",
    0x202D: "bidi control", 0x202E: "bidi control",
    0x2066: "bidi isolate", 0x2067: "bidi isolate", 0x2068: "bidi isolate", 0x2069: "bidi isolate",
}
VARIATION_RUN = re.compile("[\uFE00-\uFE0F\U000E0100-\U000E01EF]{4,}")


def analyze_text(text):
    report = Report("text")
    hidden = _hidden_characters(text, report)
    strong_artifact, generic_hits = _artifacts(text, report)
    style_hits = _style_markers(text, report)
    stats = _statistics(text)
    report.details.update(stats["display"])

    score = 45 if strong_artifact else 0
    score += min(25, 15 * generic_hits)
    score += min(25, 4 * style_hits)
    score += 10 if stats["markdown"] >= 3 else 0
    if stats["variation"] is not None and stats["sentences"] >= 6:
        score += 15 if stats["variation"] < 0.35 else 7 if stats["variation"] < 0.45 else 0
    score += 5 if stats["em_dash_per_k"] >= 5 else 0
    score += 5 if hidden else 0
    if stats["words"] < 50:
        score = int(score * 0.6)
        report.notes.append("Very short text — every detector is unreliable below ~50 words.")
    score = min(100, score)

    report.details["Heuristic AI-likelihood"] = f"{score}/100"
    report.notes.append(
        "AI-text detection is probabilistic: edited, translated or prompted-to-sound-human text fools every "
        "detector. Treat the model guess as a lead, not proof."
    )
    if score >= 50:
        result = report.to_dict("Likely AI-written (model unclear)", "low")
    else:
        result = report.to_dict("No clear AI fingerprint", "none")
    result["ai_likelihood"] = score
    return result


def _hidden_characters(text, report):
    counts = {}
    for character in text:
        code = ord(character)
        name = INVISIBLE_CHARS.get(code)
        if name is None and 0xE0000 <= code <= 0xE007F:
            name = "Unicode TAG character"
        elif name is None and (0xFE00 <= code <= 0xFE0F or 0xE0100 <= code <= 0xE01EF):
            name = "variation selector"
        if name:
            counts[name] = counts.get(name, 0) + 1
    if not counts:
        return False
    report.details["Hidden / invisible characters"] = ", ".join(f"{name} ×{count}" for name, count in counts.items())

    tag_text = "".join(chr(ord(ch) - 0xE0000) for ch in text if 0xE0020 <= ord(ch) <= 0xE007E)
    if tag_text:
        report.add(None, "strong", "Hidden text smuggled in Unicode TAG characters", tag_text)
        report.section("Decoded hidden TAG-character text", tag_text)
    for run in VARIATION_RUN.findall(text):
        payload = bytes(ord(ch) - 0xFE00 if ord(ch) <= 0xFE0F else ord(ch) - 0xE0100 + 16 for ch in run)
        decoded = payload.decode("utf-8", "replace")
        report.add(None, "strong", "Data hidden in variation selectors", decoded)
        report.section("Decoded variation-selector payload", decoded)
    if counts.get("narrow no-break space"):
        report.add("OpenAI ChatGPT", "weak", "Narrow no-break spaces (U+202F)",
                   "Reported in some o3/o4-mini outputs; OpenAI says it is not a watermark.")
    zero_width = sum(count for name, count in counts.items() if "zero-width" in name or "bidi" in name)
    if zero_width:
        report.add(None, "medium", "Zero-width / bidi control characters present", f"{zero_width} found")
    return True


def _artifacts(text, report):
    strong_artifact = False
    generic_hits = 0
    for candidate, strength, pattern, signal in ARTIFACTS:
        match = re.search(pattern, text, re.I | re.M)
        if not match:
            continue
        start = max(0, match.start() - 50)
        report.add(candidate, strength, signal, text[start:match.end() + 50])
        if candidate and strength == "strong":
            strong_artifact = True
        if candidate is None:
            generic_hits += 1
    return strong_artifact, generic_hits


def _style_markers(text, report):
    lowered = text.lower()
    total = 0
    for family, phrases in STYLE_MARKERS.items():
        hits = [phrase for phrase in phrases if phrase in lowered]
        total += len(hits)
        if len(hits) >= 2:
            strength = "medium" if len(hits) >= 4 else "weak"
            report.add(family, strength, f"Typical {family} phrasing ({len(hits)} markers)", ", ".join(hits))
    return total


def _statistics(text):
    words = re.findall(r"[A-Za-z']+", text)
    sentences = [part for part in re.split(r"(?<=[.!?])\s+|\n+", text) if len(part.split()) >= 3]
    lengths = [len(sentence.split()) for sentence in sentences]
    mean = statistics.mean(lengths) if lengths else 0
    variation = statistics.pstdev(lengths) / mean if len(lengths) >= 2 and mean else None
    em_dash_per_k = text.count("—") * 1000 / max(len(words), 1)
    markdown = len(re.findall(r"^\s{0,3}(?:#{1,6}\s|[-*•]\s|\d+[.)]\s)", text, re.M))
    markdown += len(re.findall(r"\*\*[^*\n]+\*\*", text))
    symbols = sum(1 for ch in text if unicodedata.category(ch) == "So")
    diversity = len({word.lower() for word in words}) / len(words) if words else 0
    return {
        "words": len(words),
        "sentences": len(lengths),
        "variation": variation,
        "em_dash_per_k": em_dash_per_k,
        "markdown": markdown,
        "display": {
            "Words": len(words),
            "Sentences": len(lengths),
            "Avg sentence length": f"{mean:.1f} words",
            "Sentence-length variation (burstiness)": "n/a" if variation is None else f"{variation:.2f} (human text is usually > 0.5)",
            "Em dashes per 1,000 words": f"{em_dash_per_k:.1f}",
            "Markdown elements": markdown,
            "Emoji / symbols": symbols,
            "Vocabulary diversity": f"{diversity:.2f}",
        },
    }
