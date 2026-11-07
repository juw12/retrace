# Retrace

Find the AI, prompt, model, tools and settings behind an **image**, a **text**, a **website** or a **chatbot API**.
**Try the online demo:** https://juw12.github.io/retrace/ (runs three recorded examples; the full app runs on your computer).

A local desktop app: Python 3.10+ standard library only, no installs, nothing leaves your PC except the lookups you ask for.

```
git clone https://github.com/juw12/retrace && cd retrace
python app.py              # opens Retrace in its own window (Edge/Chrome app mode)
python app.py --install    # Windows: add Retrace to the Start menu (runs without a console)
python app.py --browser    # or use a normal browser tab
python -m unittest discover -s tests
python tests/ui_smoke.py http://127.0.0.1:8765/   # optional browser check (needs Playwright)
```

Closing the window stops the app. It is also an installable PWA (browser menu, Install Retrace), with light and dark themes.

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

## Website evidence report

A website scan now ends with an **AI transparency evidence** block: the AI chatbots and assistants seen in the page code, any wording about AI in the visible page text (with the sentence around it), the site's AI-crawler rules in robots.txt, and whether it publishes llms.txt. **Print / save PDF** turns any result into a one-page report with the date and URL.

It is evidence, not a verdict. Finding no AI wording on the page doesn't mean a notice is missing: chat widgets usually show their own notice once opened, which a page scan can't see. Whether a site needs a notice under EU AI Act Article 50 is a legal question. This is not legal advice.

**Look after many client sites?** Retrace Agency (batch scans, a branded report per client, local only) is being tested. [Join the waitlist](https://github.com/juw12/retrace/issues/new?title=Retrace%20Agency%20waitlist&body=Thanks%20for%20your%20interest%20in%20Retrace%20Agency%20%28batch%20AI-transparency%20evidence%20reports%20for%20client%20websites%29.%0A%0APlease%20don%27t%20post%20private%20or%20client%20data%20here.%20This%20issue%20is%20public.%0A%0A-%20Roughly%20how%20many%20client%20websites%20do%20you%20maintain%3F%0A-%20Country%3A%0A-%20Would%20you%20take%20the%20founding%20offer%20%28EUR%2015/month%20for%20life%2C%2030-day%20refund%29%3F%20yes%20/%20maybe%20/%20no%0A-%20What%20would%20you%20want%20in%20the%20client%20report%3F%0A) by opening a prefilled public issue. Please don't post private or client data there.

## Limits (be honest with yourself)
- Exact prompts only survive if the file kept its metadata. Screenshots and social-media re-uploads strip it; then you only get the LLM's guess.
- AI-text detection is probabilistic and easy to fool.
- Website scans see client-side code only (no headless browser); server-side AI is invisible.
- Library search uses the GitHub API (60 req/h anonymous, cached 24 h in `cache/`). Set `GITHUB_TOKEN` for more.
- Use the endpoint probe only on APIs you own or are authorized to test.
