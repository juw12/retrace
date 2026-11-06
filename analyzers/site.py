"""Website scan: which AI chatbots, agents, SDKs or AI site-builders a site uses,
plus its public AI files (robots.txt AI-crawler rules, llms.txt, plugin manifests,
A2A agent cards with their skills).

Only client-visible tech can be seen. A chatbot whose model is called from the
site's own server is invisible here — fingerprint it from a chat transcript instead.
"""

import json
import re
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlparse

from .report import Report

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/130.0 Safari/537.36 ReverseAI/1.0")
MAX_SCRIPTS = 12
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


def fetch(url, limit=2_000_000, timeout=12):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
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
        url = "https://" + url
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
    scripts_to_read = (first_party + third_party)[:MAX_SCRIPTS]

    with ThreadPoolExecutor(max_workers=8) as pool:
        script_jobs = {src: pool.submit(fetch, src, 3_000_000) for src in scripts_to_read}
        policy_jobs = {key: pool.submit(fetch, origin + path, 300_000) for key, path in POLICY_FILES.items()}
    haystacks = {"page HTML": page_code(html_text)}
    for src, job in script_jobs.items():
        body = job.result()["text"]
        if body:
            label = "first-party script" if src in first_party else "third-party script"
            haystacks[f"{label} {src}"] = body.lower()

    _match_signatures(haystacks, report)
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
    return report.to_dict(fallback_label="No AI tooling visible on the page")


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
            break


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
