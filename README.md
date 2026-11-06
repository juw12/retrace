# ReverseAI

Find the AI, prompt, model, tools and settings behind an **image**, a **text**, a **website** or a **chatbot API**.
A local desktop app: Python 3.10+ standard library only, no installs, nothing leaves your PC except the lookups you ask for.

```
git clone https://github.com/juw12/reverse-ai && cd reverse-ai
python app.py              # opens ReverseAI in its own window (Edge/Chrome app mode)
python app.py --install    # Windows: add ReverseAI to the Start menu (runs without a console)
python app.py --browser    # or use a normal browser tab
python -m unittest discover -s tests
```

Closing the window stops the app. It's also an installable PWA (browser menu → Install ReverseAI).

## What it does

| Input | What you get |
|---|---|
| Image (PNG/JPEG/WebP) | Generator (A1111/Forge, ComfyUI, NovelAI, InvokeAI, Fooocus, SwarmUI, Midjourney, ChatGPT/DALL·E, Firefly, Gemini/Imagen…), **exact prompt + negative prompt**, seed, steps, sampler, model, LoRAs, C2PA Content Credentials, IPTC "AI-generated" flags |
| Text | Which chatbot wrote it (ChatGPT citation tokens / `utm_source=chatgpt.com`, self-ID, `<think>` tags, style markers), hidden Unicode payloads (TAG-character & variation-selector smuggling), heuristic AI-likelihood |
| URL | AI chat widgets & agents (Intercom Fin, Zendesk, Tidio, Botpress, Voiceflow…), AI APIs called from the browser, AI site builders (Lovable, v0, Replit, Base44, Manus…), `llms.txt`, AI-crawler rules in `robots.txt`, plugin manifests, A2A agent cards **with skills**, plus matching leaked prompts |
| App name | Leaked system prompts, tool definitions and skills from public GitHub collections |
| Endpoint probe | Fingerprints the model behind an OpenAI-compatible API (API model field, provider headers, self-ID), lists tools, and measures how much of **your** system prompt leaks |

Optional **"Ask my LLM"** (Settings tab; OpenAI, OpenRouter, Gemini, Anthropic, Groq, Ollama, LM Studio) adds a
visual/textual reverse-prompt guess for files with no metadata.

## Limits (be honest with yourself)
- Exact prompts only survive if the file kept its metadata. Screenshots and social-media re-uploads strip it; then you only get the LLM's guess.
- AI-text detection is probabilistic and easy to fool.
- Website scans see client-side code only (no headless browser); server-side AI is invisible.
- Library search uses the GitHub API (60 req/h anonymous, cached 24 h in `cache/`). Set `GITHUB_TOKEN` for more.
- Use the endpoint probe only on APIs you own or are authorized to test.
