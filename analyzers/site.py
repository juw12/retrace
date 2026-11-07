"""Website scan: which AI chatbots, agents, SDKs or AI site-builders a site uses,
plus its public AI files (robots.txt AI-crawler rules, llms.txt, plugin manifests,
A2A agent cards with their skills).

Only client-visible tech can be seen. A chatbot whose model is called from the
site's own server is invisible here — fingerprint it from a chat transcript instead.
"""

import html
import json
import re
from datetime import datetime, timezone
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlparse

from .net import is_local_host, opener_for
from .report import Report

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/130.0 Safari/537.36 Retrace/1.0")
MAX_SCRIPTS = 40  # chat widgets are often loaded late (Intercom's loader is script 19 of 38 on intercom.com)
MAX_SCRIPT_BYTES = 1_500_000
FIRST_PARTY_ONLY = ("AI API in client code", "AI framework")

# (name, category, lowercase patterns)
SIGNATURES = [
    ("Intercom (Fin AI agent)", "AI support chat", ["widget.intercom.io", "intercomsettings", "js.intercomcdn.com"]),
    ("Zendesk (AI agents)", "AI support chat", ["static.zdassets.com", "zendesk.com/embeddable"]),
    ("Drift / Salesloft", "AI support chat", ["js.driftt.com", "drift.com/include"]),
    ("HubSpot chat (Breeze AI)", "AI support chat", ["js.usemessages.com", "hubspot-messages"]),
    ("Tidio (Lyro AI)", "AI support chat", ["code.tidio.co"]),
    ("Crisp (AI chatbot)", "AI support chat", ["client.crisp.chat"]),
    ("Freshchat (Freddy AI)", "AI support chat", ["wchat.freshchat.com", "freshworks.com/widgets"]),
    ("Ada", "AI support chat", ["static.ada.support"]),
    ("LivePerson", "AI support chat", ["lpcdn.lpsnmedia.net", "liveperson.net"]),
    ("Gorgias", "AI support chat", ["gorgias.chat"]),
    ("Zoho SalesIQ (Zobot)", "AI support chat", ["salesiq.zoho"]),
    ("Kommunicate", "AI support chat", ["widget.kommunicate.io"]),
    ("Yellow.ai", "AI support chat", ["cloud.yellow.ai", "yellowmessenger"]),
    ("Chatbase (GPT chatbot)", "AI chatbot builder", ["chatbase.co"]),
    ("Botpress", "AI chatbot builder", ["cdn.botpress.cloud", "webchat.botpress"]),
    ("Voiceflow", "AI chatbot builder", ["cdn.voiceflow.com"]),
    ("Landbot", "AI chatbot builder", ["landbot.io"]),
    ("Typebot", "AI chatbot builder", ["typebot.io"]),
    ("Flowise", "AI chatbot builder", ["flowise-embed", "flowiseai"]),
    ("Dify", "AI chatbot builder", ["udify.app", "dify.ai"]),
    ("CustomGPT.ai", "AI chatbot builder", ["customgpt.ai"]),
    ("SiteGPT", "AI chatbot builder", ["sitegpt.ai"]),
    ("DocsBot AI", "AI chatbot builder", ["docsbot.ai"]),
    ("Chatling", "AI chatbot builder", ["chatling.ai"]),
    ("Kapa.ai (docs assistant)", "AI docs assistant", ["kapa.ai"]),
    ("Inkeep (docs assistant)", "AI docs assistant", ["inkeep.com", "@inkeep/"]),
    ("Mendable (docs assistant)", "AI docs assistant", ["mendable.ai"]),
    ("Microsoft Copilot Studio / Bot Framework", "Enterprise bot", ["botframework", "powerva.microsoft.com"]),
    ("Google Dialogflow", "Enterprise bot", ["df-messenger", "dialogflow"]),
    ("IBM watsonx Assistant", "Enterprise bot", ["assistant.watson", "watsonplatform"]),
    ("Amazon Lex", "Enterprise bot", ["lex-web-ui"]),
    ("Kore.ai", "Enterprise bot", ["kore.ai"]),
    ("ElevenLabs voice agent", "Voice AI", ["elevenlabs-convai", "@elevenlabs/convai", "api.elevenlabs.io"]),
    ("Vapi voice agent", "Voice AI", ["vapi.ai"]),
    ("Retell AI voice agent", "Voice AI", ["retellai.com"]),
    ("OpenAI API (called from the browser)", "AI API in client code", ["api.openai.com"]),
    ("Anthropic API (called from the browser)", "AI API in client code", ["api.anthropic.com"]),
    ("Google Gemini API", "AI API in client code", ["generativelanguage.googleapis.com"]),
    ("Mistral API", "AI API in client code", ["api.mistral.ai"]),
    ("Groq API", "AI API in client code", ["api.groq.com"]),
    ("OpenRouter", "AI API in client code", ["openrouter.ai/api"]),
    ("DeepSeek API", "AI API in client code", ["api.deepseek.com"]),
    ("xAI Grok API", "AI API in client code", ["api.x.ai"]),
    ("Hugging Face Inference", "AI API in client code", ["api-inference.huggingface.co"]),
    ("Replicate", "AI API in client code", ["api.replicate.com"]),
    ("Vercel AI SDK", "AI framework", ["@ai-sdk/"]),
    ("LangChain", "AI framework", ["langchain"]),
    ("Lovable (AI app builder)", "AI site builder", ["cdn.gpteng.co", "gptengineer.js", "lovable-tagger"]),
    ("v0 by Vercel (AI app builder)", "AI site builder", ["vusercontent.net"]),
    ("Replit (AI agent builder)", "AI site builder", ["replit-dev-banner", "replit.com/public/js"]),
    ("Base44 (AI app builder)", "AI site builder", ["@base44/sdk", "base44.app"]),
    ("Durable (AI website builder)", "AI site builder", ["durable.co"]),
    ("Framer (offers AI site generation)", "Site builder", ["framerusercontent.com"]),
    ("Wix (offers AI site builder)", "Site builder", ["static.wixstatic.com"]),
    ("Webflow (offers AI site builder)", "Site builder", ["website-files.com", "webflow.com"]),
    ("Hostinger / Zyro AI builder", "Site builder", ["zyrosite", "zyro.com"]),
]

HOST_SUFFIXES = {
    "lovable.app": "Lovable (AI app builder)",
    "replit.app": "Replit (AI agent builder)",
    "repl.co": "Replit (AI agent builder)",
    "base44.app": "Base44 (AI app builder)",
    "manus.space": "Manus (AI agent)",
    "bolt.host": "Bolt.new (AI app builder)",
    "vusercontent.net": "v0 by Vercel (AI app builder)",
}

AI_CRAWLERS = ["GPTBot", "ChatGPT-User", "OAI-SearchBot", "ClaudeBot", "Claude-Web", "Claude-User",
               "Claude-SearchBot", "anthropic-ai", "Google-Extended", "PerplexityBot", "Perplexity-User",
               "CCBot", "Bytespider", "Applebot-Extended", "meta-externalagent", "Amazonbot", "cohere-ai",
               "Diffbot", "YouBot", "DuckAssistBot", "MistralAI-User"]

POLICY_FILES = {
    "robots": "/robots.txt",
    "llms": "/llms.txt",
    "plugin": "/.well-known/ai-plugin.json",
    "agent": "/.well-known/agent.json",
    "agent_card": "/.well-known/agent-card.json",
}

# Categories that put an AI system in conversation with visitors (the "chatbot" case of
# EU AI Act Article 50(1)). Used only to group evidence, never to judge compliance.
CHAT_CATEGORIES = ("AI support chat", "AI chatbot builder", "AI docs assistant", "Enterprise bot", "Voice AI")
OTHER_AI_CATEGORIES = ("AI API in client code", "AI framework", "AI site builder")

# Wording that tells a visitor AI is involved. Matched in the page's visible text only.
# Finding none is reported as "none found in the page HTML", never as a missing notice:
# chat widgets usually show their own notice after they open, which a page scan can't see.
AI_WORDING_PATTERNS = [
    r"(?<![\w-])(?:ai|a\.i\.)[- ](?:generated|created|assisted|powered|written|produced)(?![\w-])",
    r"(?<![\w-])(?:generated|created|written|produced) (?:by|with|using) (?:an? )?(?:ai|artificial intelligence)(?![\w-])",
    r"(?<![\w-])powered by (?:ai|gpt[\w.-]*|openai|chatgpt|artificial intelligence)(?![\w-])",
    r"(?<![\w-])(?:ai|virtual|digital) (?:assistant|agent|chat ?bot)(?![\w-])",
    r"(?<![\w-])(?:you are|you're) (?:chatting|talking|speaking) (?:with|to) (?:an? )?(?:ai|bot|chat ?bot|virtual assistant)(?![\w-])",
    r"(?<![\w-])chat ?bot(?![\w-])",
    r"(?<![\w-])artificial intelligence(?![\w-])",
    r"(?<![\w-])ki[- ](?:generiert|erstellt|gestützt|assistent)\w*",
    r"(?<![\w-])(?:von|durch|mit) (?:einer )?ki (?:generiert|erstellt)\w*",
    r"(?<![\w-])künstliche[rn]? intelligenz(?![\w-])",
    r"(?<![\w-])générée?s? (?:par|avec) (?:l'|une )?(?:ia|intelligence artificielle)(?![\w-])",
    r"(?<![\w-])intelligence artificielle(?![\w-])",
    r"(?<![\w-])assistant (?:virtuel|ia)(?![\w-])",
    r"(?<![\w-])generad[oa]s? (?:por|con) (?:la )?(?:ia|inteligencia artificial)(?![\w-])",
    r"(?<![\w-])inteligencia artificial(?![\w-])",
    r"(?<![\w-])gegenereerd (?:door|met) (?:ai|kunstmatige intelligentie)(?![\w-])",
    r"(?<![\w-])kunstmatige intelligentie(?![\w-])",
    r"(?<![\w-])intelligenza artificiale(?![\w-])",
    r"(?<![\w-])generat[oa] (?:da|con) (?:l'|un'?)?(?:ia|intelligenza artificiale)(?![\w-])",
]
AI_WORDING_RE = re.compile("|".join(f"(?:{pattern})" for pattern in AI_WORDING_PATTERNS), re.I)
MAX_WORDING_MATCHES = 6
TRANSPARENCY_DISCLAIMER = (
    "Technical evidence, not legal advice. Whether a site needs an AI notice, and whether its wording "
    "is enough (EU AI Act Article 50), is a legal question for the site owner and their adviser."
)
IMAGES_NOTE = ("Not checked by a site scan. Drop an image into Retrace to read its C2PA content "
               "credentials and AI metadata.")


def fetch(url, limit=2_000_000, timeout=12):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    try:
        with opener_for(url).open(request, timeout=timeout) as response:
            raw = response.read(limit)
            charset = response.headers.get_content_charset() or "utf-8"
            return {
                "url": response.geturl(),
                "status": response.status,
                "headers": {key.lower(): value for key, value in response.headers.items()},
                "text": raw.decode(charset, "replace"),
                "error": None,
            }
    except urllib.error.HTTPError as error:
        return {"url": url, "status": error.code, "headers": {}, "text": "", "error": f"HTTP {error.code}"}
    except Exception as error:  # network failures are reported, not fatal
        return {"url": url, "status": None, "headers": {}, "text": "", "error": str(error)}


def analyze_site(url):
    url = url.strip()
    if not re.match(r"https?://", url, re.I):
        host = re.split(r"[:/?#]", url, maxsplit=1)[0]
        url = ("http://" if is_local_host(host) else "https://") + url  # local dev servers rarely have TLS
    page = fetch(url)
    if page["error"]:
        raise RuntimeError(f"Could not fetch {url}: {page['error']}")

    final_url = page["url"]
    parsed = urlparse(final_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    html_text = page["text"]
    report = Report("site")
    report.details["URL"] = final_url
    title = re.search(r"<title[^>]*>(.*?)</title>", html_text, re.I | re.S)
    if title:
        report.details["Title"] = " ".join(title.group(1).split())[:200]
    generator = re.search(r'<meta[^>]+name=["\']generator["\'][^>]+content=["\']([^"\']+)', html_text, re.I)
    if generator:
        report.details["Generator meta tag"] = generator.group(1)
    for header in ("server", "x-powered-by"):
        if page["headers"].get(header):
            report.details[f"HTTP {header}"] = page["headers"][header]

    script_sources = [urljoin(final_url, src) for src in
                      re.findall(r"<script[^>]+src=[\"']([^\"']+)", html_text, re.I)]
    script_sources += [f"https://www.googletagmanager.com/gtm.js?id={gtm_id}"
                       for gtm_id in sorted(set(re.findall(r"GTM-[A-Z0-9]{4,10}", html_text)))]
    report.details["Scripts on page"] = len(script_sources)
    site_domain = base_domain(parsed.hostname or "")
    first_party = [src for src in script_sources if base_domain(urlparse(src).hostname or "") == site_domain]
    third_party = [src for src in script_sources if src not in first_party]
    scripts_to_read = list(dict.fromkeys(first_party + third_party))[:MAX_SCRIPTS]

    with ThreadPoolExecutor(max_workers=12) as pool:
        script_jobs = {src: pool.submit(fetch, src, MAX_SCRIPT_BYTES) for src in scripts_to_read}
        policy_jobs = {key: pool.submit(fetch, origin + path, 300_000) for key, path in POLICY_FILES.items()}
    haystacks = {"page HTML": page_code(html_text)}
    scripts_read = 0
    for src, job in script_jobs.items():
        body = job.result()["text"]
        if body:
            scripts_read += 1
            label = "first-party script" if src in first_party else "third-party script"
            haystacks[f"{label} {src}"] = body.lower()
    unique_scripts = len(set(script_sources))
    if scripts_read < unique_scripts:
        report.notes.append(
            f"Read {scripts_read} of {unique_scripts} scripts (the rest were skipped or failed to load), "
            "so a tool loaded by an unread script may be missing."
        )

    found_tools = _match_signatures(haystacks, report)
    host = parsed.hostname or ""
    for suffix, name in HOST_SUFFIXES.items():
        if host == suffix or host.endswith("." + suffix):
            report.add(name, "strong", "Hosted on the builder's default domain", host)
    if generator and re.search(r"lovable|v0|bolt|framer|wix|webflow|durable|base44", generator.group(1), re.I):
        report.add(None, "medium", "Generator meta tag names a site builder", generator.group(1))

    _policy_files({key: job.result() for key, job in policy_jobs.items()}, report)
    report.notes.append(
        "A page scan only sees client-side tech. If a chatbot's model is called from the site's own server, "
        "paste a chat transcript into Reverse (text) or use Endpoint probe on an API you own."
    )
    result = report.to_dict(fallback_label="No AI tooling visible on the page")
    result["transparency"] = transparency_evidence(found_tools, html_text, report.details, final_url)
    return result


SNIPPET_CHARS = 180
BLOCK_TAG_RE = re.compile(
    r"</?(?:p|div|li|ul|ol|h[1-6]|br|tr|td|th|section|article|header|footer|nav|main|aside|"
    r"button|label|option|figcaption|blockquote|dt|dd)\b[^>]*>",
    re.I,
)


def visible_text(html_text):
    """Text a visitor can read on the page, plus alt / aria-label / title values
    (chat launchers often carry their label there). Scripts, styles and comments are dropped.
    Each block (paragraph, heading, list item, link, button...) ends up on its own line, so a
    quote can stay inside the sentence it came from instead of running into the next menu item."""
    labels = re.findall(r"\b(?:alt|aria-label|title)=[\"']([^\"']{1,300})[\"']", html_text, re.I)
    body = re.sub(r"<!--.*?-->", " ", html_text, flags=re.S)
    body = re.sub(r"<(script|style|template|svg|noscript|head)\b[^>]*>.*?</\1\s*>", " ", body, flags=re.I | re.S)
    # icon-font ligatures ("arrow_right_alt") are not words a visitor reads
    body = re.sub(r"<(span|i)\b[^>]*class=[\"'][^\"']*(?:material-(?:icons|symbols)|icon)[^\"']*[\"'][^>]*>[\w\s]{0,40}</\1>",
                  " ", body, flags=re.I)
    body = re.sub(BLOCK_TAG_RE, "\n", body)
    body = re.sub(r"<[^>]+>", " ", body)
    lines = html.unescape("\n".join([body, *labels])).split("\n")
    return "\n".join(line for line in (" ".join(raw.split()) for raw in lines) if line)


def _prose_score(line):
    """Higher for a line that reads like a sentence, lower for a menu or button label."""
    words = line.split()
    lower_words = sum(1 for word in words if word[:1].islower())
    return (len(words) >= 6) * 2 + (lower_words >= 3) + bool(re.search(r"[.!?:]", line))


def _quote_around(line, start, end):
    """The sentence holding line[start:end]. Long sentences are cut to about SNIPPET_CHARS
    on word boundaries, with an ellipsis only where a sentence was cut."""
    left = max(line.rfind(stop, 0, start) for stop in (". ", "! ", "? "))
    left = 0 if left < 0 else left + 2
    right_candidates = [pos for pos in (line.find(stop, end) for stop in (". ", "! ", "? ")) if pos >= 0]
    right = min(right_candidates) + 1 if right_candidates else len(line)
    cut_left = cut_right = False
    if right - left > SNIPPET_CHARS:
        half = max(20, (SNIPPET_CHARS - (end - start)) // 2)
        if start - left > half:
            left = start - half
            left = line.index(" ", left) + 1 if " " in line[left:start] else left
            cut_left = True
        if right - end > half:
            right = end + half
            right = line.rindex(" ", end, right) if " " in line[end:right] else right
            cut_right = True
    quote = line[left:right].strip()
    return ("…" if cut_left else "") + quote + ("…" if cut_right else "")


def ai_wording(text_value):
    """Phrases that tell a visitor AI is involved, each quoted inside the sentence it appears in.
    When a phrase appears several times, the occurrence that reads most like a sentence is quoted
    (a disclosure line rather than a navigation label)."""
    occurrences = {}
    for line in text_value.split("\n"):
        for match in AI_WORDING_RE.finditer(line):
            phrase = " ".join(match.group(0).split())
            occurrences.setdefault(phrase.lower(), []).append((phrase, line, match.start(), match.end()))
            if len(occurrences) > MAX_WORDING_MATCHES * 4:
                break
    best = [max(found, key=lambda item: _prose_score(item[1])) for found in occurrences.values()]
    best.sort(key=lambda item: -_prose_score(item[1]))  # sentences before bare menu labels
    return [{"phrase": phrase, "snippet": _quote_around(line, start, end)}
            for phrase, line, start, end in best[:MAX_WORDING_MATCHES]]


def transparency_evidence(found_tools, html_text, details, url, checked_at=None):
    """What a reviewer needs for an AI-transparency check, as evidence only (no verdicts)."""
    chatbots = [name for name, category in found_tools if category in CHAT_CATEGORIES]
    other_ai = [name for name, category in found_tools if category in OTHER_AI_CATEGORIES]
    checked_at = checked_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "url": url,
        "checked_at": checked_at,
        "chatbots": chatbots,
        "other_ai": other_ai,
        "ai_wording": ai_wording(visible_text(html_text)),
        "ai_crawlers": details.get("AI crawlers in robots.txt", "robots.txt not found"),
        "llms_txt": details.get("llms.txt") == "present",
        "images": IMAGES_NOTE,
        "disclaimer": TRANSPARENCY_DISCLAIMER,
    }


def page_code(html_text):
    """Only the parts of a page that load or run code: tag URLs, meta values, custom
    element names and inline scripts (minus JSON data blobs). Links and visible text
    are skipped so that a page merely *mentioning* a product doesn't count."""
    parts = re.findall(r"<(?:script|iframe|img)[^>]+src=[\"']([^\"']+)", html_text, re.I)
    parts += re.findall(r"<link[^>]+href=[\"']([^\"']+)", html_text, re.I)
    parts += re.findall(r"<meta[^>]+content=[\"']([^\"']+)", html_text, re.I)
    parts += re.findall(r"<([a-z][\w]*-[\w-]+)", html_text, re.I)
    for attributes, body in re.findall(r"<script([^>]*)>(.*?)</script>", html_text, re.I | re.S):
        if re.search(r"json|__NEXT_DATA__", attributes, re.I) or "self.__next_f" in body:
            continue
        parts.append(body)
    return "\n".join(parts).lower()


def _match_signatures(haystacks, report):
    """Add evidence for every known tool found; return [(name, category)] in signature order."""
    found = []
    for name, category, patterns in SIGNATURES:
        for where, haystack in haystacks.items():
            if category in FIRST_PARTY_ONLY and where.startswith("third-party"):
                continue  # vendor bundles mention AI APIs they call themselves
            if category.endswith("site builder") and where != "page HTML":
                continue  # builders leave traces in the page itself, not deep inside bundles
            pattern = next((candidate for candidate in patterns if candidate in haystack), None)
            if not pattern:
                continue
            if category == "Site builder":
                strength = "weak"
            elif where == "page HTML" and category not in FIRST_PARTY_ONLY:
                strength = "strong"
            else:
                strength = "medium"
            index = haystack.find(pattern)
            report.add(name, strength, f"{category}: '{pattern}' in {where[:120]}",
                       haystack[max(0, index - 80):index + 80])
            found.append((name, category))
            break
    return found


def base_domain(hostname):
    labels = hostname.lower().split(".")
    if len(labels) >= 3 and labels[-2] in ("co", "com", "org", "net", "ac", "gov"):
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def _is_text_file(result):
    content_type = result["headers"].get("content-type", "")
    return (result["status"] == 200 and result["text"].strip()
            and "html" not in content_type and not result["text"].lstrip().startswith("<"))


def _policy_files(results, report):
    robots = results["robots"]
    if _is_text_file(robots):
        policy = ai_crawler_policy(robots["text"])
        if policy:
            report.details["AI crawlers in robots.txt"] = ", ".join(f"{bot}: {rule}" for bot, rule in policy.items())
        else:
            report.details["AI crawlers in robots.txt"] = "none named (default rules apply)"

    llms = results["llms"]
    if _is_text_file(llms):
        report.details["llms.txt"] = "present"
        report.add(None, "medium", "Site publishes /llms.txt (guidance written for LLMs)", llms["text"][:200])
        report.section("llms.txt — what the site tells AI models", llms["text"][:6000])

    plugin = _json_of(results["plugin"])
    if plugin:
        report.details["AI plugin manifest"] = plugin.get("name_for_human", "present")
        report.section("ai-plugin.json — description_for_model (a prompt the site gives AI)",
                       plugin.get("description_for_model") or json.dumps(plugin, indent=2)[:4000])

    card = _json_of(results["agent"]) or _json_of(results["agent_card"])
    if card:
        report.details["A2A agent card"] = card.get("name", "present")
        skills = card.get("skills") or []
        lines = [f"- {skill.get('name', skill.get('id', '?'))}: {skill.get('description', '')}"
                 for skill in skills if isinstance(skill, dict)]
        report.section("Agent card — declared skills", "\n".join(lines) or json.dumps(card, indent=2)[:4000])
        report.add(None, "strong", "Site exposes an AI agent (A2A agent card)", card.get("description", ""))


def _json_of(result):
    if result["status"] != 200:
        return None
    try:
        data = json.loads(result["text"])
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def ai_crawler_policy(robots_text):
    """Return {bot: 'allowed' | 'partly blocked' | 'blocked'} for AI crawlers named in robots.txt."""
    policy = {}
    agents, in_rules = [], False
    lookup = {bot.lower(): bot for bot in AI_CRAWLERS}
    for line in robots_text.splitlines():
        line = line.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        field, value = (part.strip() for part in line.split(":", 1))
        field = field.lower()
        if field == "user-agent":
            if in_rules:
                agents, in_rules = [], False
            agents.append(value)
        elif field in ("allow", "disallow"):
            in_rules = True
            for agent in agents:
                bot = lookup.get(agent.lower())
                if not bot:
                    continue
                current = policy.setdefault(bot, "allowed")
                if field == "disallow" and value == "/":
                    policy[bot] = "blocked"
                elif field == "disallow" and value and current != "blocked":
                    policy[bot] = "partly blocked"
    return policy
