# backend/ai.py
# ============================================================
#  ATLAS — AI Research Assistant
#  Features:
#   • Confidence / Accuracy scoring with user warnings
#   • Source citation with URLs
#   • Query intent detection (news / factual / technical / opinion)
#   • Adaptive answer structure (report / quick / comparison)
#   • Temporal relevance scoring (boosts fresh sources)
#   • Source diversity check (warns on single-domain bias)
#   • Follow-up question suggestions
#   • Mistral-7B-Instruct replaces Zephyr for better accuracy
#   • Clean markdown output with section headers
# ============================================================

import os
import re
from datetime import date, datetime
from urllib.parse import urlparse
from dataclasses import dataclass, field
from dotenv import load_dotenv
from collections import Counter

from tavily import TavilyClient
from huggingface_hub import InferenceClient
from google import genai
from google.genai import types

# ─────────────────────────────────────────
# Environment
# ─────────────────────────────────────────
load_dotenv()

TAVILY_API_KEY  = os.getenv("TAVILY_API_KEY")
HF_API_KEY      = os.getenv("HUGGINGFACEHUB_API_KEY")
GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY")
GROQ_API_KEY    = os.getenv("GROQ_API_KEY")

if not TAVILY_API_KEY:
    raise ValueError("Missing TAVILY_API_KEY in .env")

# ─────────────────────────────────────────
# Clients
# ─────────────────────────────────────────
tavily = TavilyClient(api_key=TAVILY_API_KEY)

gemini_client = None
if GEMINI_API_KEY:
    try:
        from google import genai
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
        print("[ATLAS] Primary model: Gemini 2.0 Flash")
    except ImportError:
        pass
else:
    print("[ATLAS] GEMINI_API_KEY not set.")

groq_client = None
if GROQ_API_KEY:
    try:
        from groq import Groq
        groq_client = Groq(api_key=GROQ_API_KEY)
        print("[ATLAS] Groq fallback: Llama 3.1 (llama-3.1-8b-instant)")
    except ImportError:
        print("[ATLAS] Groq package missing. Run: pip install groq")

hf = None
if HF_API_KEY:
    # Use official HuggingFace Inference API which supports standard top-tier models
    hf = InferenceClient(token=HF_API_KEY)
    print("[ATLAS] HuggingFace fallback: Enabled")


# ─────────────────────────────────────────
# Data Structures
# ─────────────────────────────────────────
@dataclass
class Source:
    url:     str
    title:   str
    content: str
    domain:  str  = ""
    score:   float = 0.0   # Tavily relevance score
    age_days: int  = 999   # days since published (999 = unknown)

    def __post_init__(self):
        self.domain = urlparse(self.url).netloc.replace("www.", "") if self.url else "unknown"


@dataclass
class ResearchResult:
    sources:         list[Source] = field(default_factory=list)
    confidence:      float        = 0.0   # 0–1
    confidence_label: str         = "Unknown"
    low_confidence:  bool         = False
    warnings:        list[str]    = field(default_factory=list)
    query_intent:    str          = "general"   # news | factual | technical | opinion | general
    follow_ups:      list[str]    = field(default_factory=list)
    answer:          str          = ""
    citations:       list[dict]   = field(default_factory=list)


@dataclass
class ChatMemory:
    history: list = field(default_factory=list)

    def add(self, role: str, content: str):
        self.history.append({"role": role, "content": content})
        self.history = self.history[-4:]   # keep last 2 turns (4 messages)


# ─────────────────────────────────────────
# Query Intent Detection
# ─────────────────────────────────────────
_INTENT_PATTERNS = {
    "news":      r"\b(latest|today|today\'s|todays|breaking|just|now|recent|update|announce|happen|current|2024|2025|2026)\b",
    "technical": r"\b(how to|how does|explain|architecture|algorithm|implement|code|api|framework|model|train|deploy)\b",
    "opinion":   r"\b(best|worst|should|recommend|opinion|think|vs|compare|versus|better|pros|cons)\b",
    "factual":   r"\b(who|what|when|where|which|define|meaning|history|list of|number of)\b",
}

def detect_intent(query: str) -> str:
    q = query.lower()
    for intent, pattern in _INTENT_PATTERNS.items():
        if re.search(pattern, q):
            return intent
    return "general"


# ─────────────────────────────────────────
# Research — Tavily with intent-aware tuning
# ─────────────────────────────────────────
def research(query: str, intent: str) -> list[Source]:
    sources: list[Source] = []

    def _parse_sources(results: list, is_news: bool) -> list[Source]:
        parsed = []
        for r in results:
            url     = r.get("url", "")
            title   = r.get("title", "Untitled")
            content = r.get("content", "")
            score   = float(r.get("score", 0.5))
            # If Tavily doesn't return a date, assume it's recent if it came from a news search
            age_days = 15 if is_news else 999
            pub = r.get("published_date") or r.get("publishedDate")
            if pub:
                try:
                    # Handle various ISOish formats
                    pub_clean = re.sub(r'T.*', '', pub) 
                    pub_dt   = datetime.strptime(pub_clean, "%Y-%m-%d")
                    age_days = (datetime.today() - pub_dt).days
                except Exception:
                    try:
                        # Fallback for other common formats
                        pub_dt = datetime.fromisoformat(pub.replace('Z', '+00:00'))
                        age_days = (datetime.today() - pub_dt.replace(tzinfo=None)).days
                    except Exception:
                        pass
            if content:
                parsed.append(Source(url=url, title=title, content=content,
                                     score=score, age_days=age_days))
        return parsed

    # ── Strategy A: news search for time-sensitive intents ──
    if intent in ("news", "general"):
        try:
            res = tavily.search(query=query, max_results=8, topic="news", days=30)
            sources = _parse_sources(res.get("results", []), is_news=True)
        except Exception as e:
            print(f"[Research] News search failed: {e}")

    # ── Strategy B: general web search ──
    if not sources or intent in ("factual", "technical", "opinion"):
        try:
            enriched_query = f"{query} {date.today().year}" if intent == "news" else query
            res = tavily.search(query=enriched_query, max_results=8)
            extra = _parse_sources(res.get("results", []), is_news=False)
            # Merge, deduplicate by URL
            existing_urls = {s.url for s in sources}
            sources += [s for s in extra if s.url not in existing_urls]
        except Exception as e:
            print(f"[Research] General search failed: {e}")

    # Sort by Tavily relevance score descending
    sources.sort(key=lambda s: s.score, reverse=True)
    return sources[:10]


# ─────────────────────────────────────────
# Confidence Scoring
# ─────────────────────────────────────────
def compute_confidence(sources: list[Source]) -> tuple[float, str, list[str]]:
    """
    Returns (score 0–1, label, list of warning strings).

    Factors:
      • Source count          (≥5 = good)
      • Average Tavily score  (>0.7 = strong relevance)
      • Recency               (most sources <30 days old = good)
      • Domain diversity      (≥3 unique domains = good)
    """
    warnings: list[str] = []

    if not sources:
        return 0.0, "None", ["⚠️ No sources were found for this query. The answer is entirely generated from the model's training data and may be outdated or inaccurate."]

    n          = len(sources)
    avg_score  = sum(s.score for s in sources) / n
    fresh      = sum(1 for s in sources if s.age_days <= 60)
    domains    = {s.domain for s in sources}
    n_domains  = len(domains)
    stale_count = sum(1 for s in sources if s.age_days > 60 and s.age_days < 999)

    # ── Compute weighted score ──
    count_score    = min(n / 8, 1.0)          # saturates at 8 sources
    relevance_score = min(avg_score / 0.8, 1.0)
    recency_score  = fresh / n
    diversity_score = min(n_domains / 4, 1.0)

    confidence = (
        0.35 * relevance_score +
        0.25 * count_score     +
        0.25 * recency_score   +
        0.15 * diversity_score
    )
    confidence = round(min(confidence, 1.0), 3)

    # ── Generate human-readable warnings ──
    if n < 3:
        warnings.append(f"⚠️ Only {n} source(s) found — answer may lack coverage.")
    if avg_score < 0.5:
        warnings.append(f"⚠️ Source relevance is low (avg score: {avg_score:.2f}). Results may not directly address your query.")
    if stale_count > 0:
        source_word = "source is" if stale_count == 1 else "sources are"
        warnings.append(f"⚠️ {stale_count} {source_word} older than 60 days.")
    
    if n_domains <= 1:
        warnings.append(f"⚠️ All sources are from a single domain ({list(domains)[0]}). Perspective may be one-sided.")
    elif n_domains == 2:
        warnings.append("⚠️ Sources come from only 2 domains — consider cross-referencing.")

    # ── Label ──
    if confidence >= 0.75:
        label = "High ✅"
    elif confidence >= 0.50:
        label = "Moderate 🟡"
    elif confidence >= 0.30:
        label = "Low 🟠"
    else:
        label = "Very Low 🔴"

    return confidence, label, warnings


# ─────────────────────────────────────────
# Deduplicate & Format Reference Block
# ─────────────────────────────────────────
def build_reference_block(sources: list[Source]) -> str:
    combined = " ".join(s.content for s in sources)
    sentences = re.split(r'(?<=[.!?])\s+', combined)
    seen: set[str] = set()
    unique: list[str] = []
    for s in sentences:
        key = s.strip().lower()
        if key and key not in seen:
            seen.add(key)
            unique.append(s.strip())
    # Group into paragraphs of 5 sentences
    paragraphs = []
    for i in range(0, len(unique), 5):
        paragraphs.append(" ".join(unique[i:i+5]))
    return "\n\n".join(paragraphs)


# ─────────────────────────────────────────
# Build Numbered Citation Map
# ─────────────────────────────────────────
def build_citation_map(sources: list[Source]) -> tuple[str, list[dict]]:
    """Returns (citation footer string, list of citation dicts)."""
    citations = []
    lines = []
    for i, s in enumerate(sources[:6], start=1):   # cap at 6 citations
        citations.append({"num": i, "title": s.title, "url": s.url, "domain": s.domain})
        lines.append(f"[{i}] {s.title} — {s.domain}  \n    {s.url}")
    return "\n".join(lines), citations


# ─────────────────────────────────────────
# Prompt Factory — intent-aware
# ─────────────────────────────────────────
def build_prompt(query: str, ref_block: str, intent: str, today: str) -> str:
    structure_guide = {
        "news": """Structure your response as:
## Summary
A 2–3 sentence overview of the latest developments.

## Key Developments
- Bullet 1 (most recent / most important)
- Bullet 2
- Bullet 3
- Bullet 4 (if applicable)

## Context & Background
1–2 sentences explaining why this matters.""",

        "technical": """Structure your response as:
## Overview
A concise explanation of the concept or technology.

## How It Works
Step-by-step or layered explanation (use sub-bullets if needed).

## Key Takeaways
- 3–5 bullet points summarising critical facts or best practices.""",

        "opinion": """Structure your response as:
## Summary
1–2 sentences capturing the consensus or dominant view.

## Perspectives
| Aspect | View A | View B |
|--------|--------|--------|
(Fill in a comparison table if the query involves comparing two things.)

## Verdict / Recommendation
A balanced, evidence-based conclusion.""",

        "factual": """Structure your response as:
## Answer
A direct, precise answer to the question.

## Supporting Facts
- Fact 1
- Fact 2
- Fact 3

## Additional Context
1–2 sentences of helpful background.""",

        "general": """Structure your response as:
## Summary
A clear 2–3 sentence summary.

## Key Points
- Point 1
- Point 2
- Point 3
- Point 4

## Further Notes
Any caveats, nuances, or related context.""",
    }

    structure = structure_guide.get(intent, structure_guide["general"])

    return f"""Reference Information (live web data as of {today}):
{ref_block}

Question: {query}

IMPORTANT INSTRUCTIONS:
- Answer ONLY from the Reference Information above.
- Do NOT hallucinate or add facts not in the sources.
- If the sources are insufficient, say so clearly.
- {structure}
- After the structured answer, add a line: "---" then "**Suggested follow-up questions:**" followed by 3 numbered research questions the user might want to explore next.
- Do NOT include any preamble, meta-commentary, or repeat these instructions."""


# ─────────────────────────────────────────
# Generate Answer via LLM
# ─────────────────────────────────────────
def generate_answer(query: str, sources: list[Source], memory: ChatMemory, intent: str) -> str:
    today       = date.today().strftime("%B %d, %Y")
    ref_block   = build_reference_block(sources) if sources else "No live reference data was found."
    prompt      = build_prompt(query, ref_block, intent, today)

    system_instruction = (
        f"You are ATLAS, an elite AI research assistant. Today is {today}. "
        "You answer questions with precision, cite evidence, and structure responses for maximum clarity. "
        "You never fabricate information. When sources are limited, you say so transparently. "
        "You write in clear, formal but accessible English. Markdown formatting is encouraged."
    )

    # ── Build message history ──
    messages = [{"role": "system", "content": system_instruction}]
    if memory.history:
        last_user = next((m["content"] for m in memory.history if m["role"] == "user"), "")
        overlap   = set(query.lower().split()) & set(last_user.lower().split())
        if len(overlap) > 2 or len(query.split()) < 4:
            for msg in memory.history:
                messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": prompt})

    # ── Gemini path ──
    if gemini_client:
        for model_name in ["gemini-2.0-flash", "gemini-1.5-flash"]:
            try:
                response = gemini_client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=0.25,          # lower temp = more factual
                        max_output_tokens=1500,
                    )
                )
                print(f"[ATLAS] Gemini model used: {model_name}")
                return response.text.strip()
            except Exception as e:
                print(f"[ATLAS] {model_name} failed: {e}")
                continue

    # ── Groq path ──
    if groq_client:
        try:
            response = groq_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=messages,
                temperature=0.25,
                max_tokens=1500,
            )
            print("[ATLAS] Groq used: llama-3.1-8b-instant")
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"[ATLAS] Groq failed: {e}")

    # ── HuggingFace fallback — Zephyr-7B ──
    if hf:
        try:
            response = hf.chat.completions.create(
                model="HuggingFaceH4/zephyr-7b-beta",
                messages=messages,
                temperature=0.25,
                max_tokens=1500,
                frequency_penalty=1.2,
                presence_penalty=0.4,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"[ATLAS] Zephyr failed: {e}")

    return (
        "**Error:** No AI model is configured or all models failed. "
        "Please add a `GEMINI_API_KEY` or `HUGGINGFACEHUB_API_KEY` to your `.env` file."
    )


# ─────────────────────────────────────────
# Extract Follow-up Questions from answer
# ─────────────────────────────────────────
def extract_follow_ups(answer: str) -> tuple[str, list[str]]:
    """Splits the LLM answer into (main_answer, follow_up_questions)."""
    parts = re.split(r'\n---\s*\n', answer, maxsplit=1)
    if len(parts) == 2:
        main  = parts[0].strip()
        block = parts[1]
        qs    = re.findall(r'\d+\.\s+(.+)', block)
        return main, [q.strip() for q in qs[:3]]
    return answer.strip(), []


# ─────────────────────────────────────────
# Post-processing / Sanitise
# ─────────────────────────────────────────
def sanitize(text: str) -> str:
    # Remove model artefact tokens
    text = re.sub(r"<\|.*?\|>",                        "", text)
    text = re.sub(r"\[/?(?:USER|ASSISTANT|INST)\]",    "", text, flags=re.I)
    text = re.sub(r"\[/?s\]",                          "", text)
    # Strip hallucinated identity preambles
    text = re.sub(
        r"^(chatgpt|answer|assistant|ai|you are a\b.{0,120})\s*[\n:]*",
        "", text, flags=re.I
    )
    # Remove filler sign-off lines
    text = re.sub(r"\n\s*Is there anything else.*",    "", text, flags=re.I | re.S)
    text = re.sub(r"\n\s*Feel free to ask.*",          "", text, flags=re.I | re.S)
    # Deduplicate identical lines
    lines = text.split("\n")
    seen: set[str] = set()
    deduped: list[str] = []
    for line in lines:
        key = line.strip().lower()
        if key not in seen:
            seen.add(key)
            deduped.append(line)
    return "\n".join(deduped).strip()


# ─────────────────────────────────────────
# Format Final Response
# ─────────────────────────────────────────
def format_response(result: ResearchResult) -> str:
    """
    Assembles the complete, formatted response string that gets returned
    to the caller (API route / CLI). Includes confidence badge,
    warnings, the main answer, sources, and follow-up questions.
    """
    lines: list[str] = []

    # ── Confidence badge ──
    pct = int(result.confidence * 100)
    lines.append(f"**Research Confidence: {result.confidence_label}** ({pct}%)\n")

    # ── Warnings ──
    if result.warnings:
        for w in result.warnings:
            lines.append(f"> {w}")
        lines.append("")   # blank line after warnings

    # ── Intent badge ──
    intent_emoji = {
        "news": "📰", "technical": "⚙️",
        "opinion": "💬", "factual": "📖", "general": "🔍"
    }
    emoji = intent_emoji.get(result.query_intent, "🔍")
    lines.append(f"*Query type detected: {emoji} {result.query_intent.capitalize()}*\n")
    lines.append("---\n")

    # ── Main answer ──
    lines.append(result.answer)
    lines.append("")

    # ── Sources ──
    if result.citations:
        lines.append("---")
        lines.append("### 📚 Sources")
        for c in result.citations:
            lines.append(f"**[{c['num']}]** [{c['title']}]({c['url']})  _{c['domain']}_")
        lines.append("")

    # ── Follow-up questions ──
    if result.follow_ups:
        lines.append("---")
        lines.append("### 💡 Suggested Follow-up Questions")
        for i, q in enumerate(result.follow_ups, 1):
            lines.append(f"{i}. {q}")

    return "\n".join(lines)


# ─────────────────────────────────────────
# Main Entry Point
# ─────────────────────────────────────────
def get_response(user_query: str, memory: ChatMemory) -> str:
    """
    Full pipeline:
      1. Detect query intent
      2. Research (Tavily)
      3. Compute confidence & warnings
      4. Generate structured answer (Gemini / Mistral)
      5. Sanitise & extract follow-ups
      6. Format & return complete response
    """
    intent  = detect_intent(user_query)
    sources = research(user_query, intent)

    confidence, conf_label, warnings = compute_confidence(sources)

    raw_answer = generate_answer(user_query, sources, memory, intent)
    raw_answer = sanitize(raw_answer)

    main_answer, follow_ups = extract_follow_ups(raw_answer)

    _, citations = build_citation_map(sources)

    result = ResearchResult(
        sources          = sources,
        confidence       = confidence,
        confidence_label = conf_label,
        low_confidence   = confidence < 0.45,
        warnings         = warnings,
        query_intent     = intent,
        follow_ups       = follow_ups,
        answer           = main_answer,
        citations        = citations,
    )

    # Update memory with clean main answer (not the full formatted block)
    memory.add("user",      user_query)
    memory.add("assistant", main_answer)

    return format_response(result)


# ─────────────────────────────────────────
# Optional: expose raw ResearchResult
# ─────────────────────────────────────────
def get_research_result(user_query: str, memory: ChatMemory) -> ResearchResult:
    """
    Same as get_response but returns the structured ResearchResult object
    instead of a formatted string — useful for API routes that want to
    render the UI themselves.
    """
    intent  = detect_intent(user_query)
    sources = research(user_query, intent)

    confidence, conf_label, warnings = compute_confidence(sources)

    raw_answer = generate_answer(user_query, sources, memory, intent)
    raw_answer = sanitize(raw_answer)

    main_answer, follow_ups = extract_follow_ups(raw_answer)
    _, citations = build_citation_map(sources)

    result = ResearchResult(
        sources          = sources,
        confidence       = confidence,
        confidence_label = conf_label,
        low_confidence   = confidence < 0.45,
        warnings         = warnings,
        query_intent     = intent,
        follow_ups       = follow_ups,
        answer           = main_answer,
        citations        = citations,
    )

    memory.add("user",      user_query)
    memory.add("assistant", main_answer)

    return result