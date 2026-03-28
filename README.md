# Nexus AI — Research Assistant

Nexus AI is an elite, intent-aware research assistant designed to provide precise, cited, and real-time information. It leverages the **Tavily Search API** for deep web research and uses state-of-the-art LLMs (Gemini 2.0 Flash, Llama 3.1, or Mistral) to synthesize findings into structured, readable reports.

<img width="100%" alt="Nexus AI Interface Preview" src="https://github.com/user-attachments/assets/09f887f2-4417-4a64-a952-b8e18d4a84e9" />

## 🌟 Why Nexus AI? — What Makes It Unique?

Unlike standard chatbot interfaces, **Nexus AI** is built from the ground up as a **specialized research engine**. It doesn't just guess; it investigates.

-   **🧠 Intent-Aware Intelligence**: Nexus AI detects the *nature* of your query. If you ask for news, it searches for recent headlines. If you ask for a technical explanation, it focuses on architectural documentation. The response structure adapts to provide the most useful format (tables for comparisons, bullets for lists, or deep-dive reports).
-   **🛡️ Fact-First Transparency**: Every answer includes a **Confidence Score** and **Source citations**. No more guessing where the data came from. You get a direct path to the evidence.
-   **📅 Temporal Awareness (Anti-Stale Logic)**: In a world of fast-moving information, Nexus AI specifically monitors the age of its sources. If the data is older than 60 days, you get an automatic "Stale Information" warning, keeping you ahead of outdated facts.
-   **⚡ Multi-Model Orchestration**: To ensure 100% uptime and the best reasoning, Nexus AI uses an adaptive fallback system. It prefers **Gemini 2.0 Flash** for its massive context and speed, with seamless fallbacks to **Groq (Llama 3.1)** and **Mistral** if needed.
-   **💎 Premium UX/UI**: Designed for focus. Featuring a modern glassmorphic interface, smooth Dark/Light mode transitions, and interactive follow-up suggestions that anticipate your next research step.

## ✨ Key Features
- **Real-time Research**: Uses Tavily's specialized search for high-relevance results.
- **Intent-Aware Synthesis**: Automatically detects if a query is News, Technical, Factual, or Opinion-based and adjusts the answer structure accordingly.
- **Confidence Scoring**: Each answer includes a confidence rating (%) based on source count, relevance, and recency.
- **Stale Source Detection**: Automatically warns if research data is older than 60 days to ensure temporal accuracy.
- **Dynamic UI**: 
  - Premium Dark/Light mode toggle.
  - Interactive "Explore Further" follow-up suggestions.
  - Numbered citations with direct source links.
  - Collapsible sidebar for conversation management.

## 🎥 Demo

<vi<video src="research-agent_x3rmx3C2.mp4" width="100%" controls></video>

> [!TIP]
> This video is hosted directly in the repository. If it doesn't play automatically in some browsers, you can also view the raw file [here](research-agent_x3rmx3C2.mp4).

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.10 or higher.
- API Keys for the following:
  - [Tavily API](https://tavily.com/) (Required)
  - [Google Gemini API](https://aistudio.google.com/) (Primary)
  - [Groq API](https://console.groq.com/) (Optional fallback)
  - [HuggingFace API](https://huggingface.co/settings/tokens) (Optional fallback)

### 2. Installation
Clone the repository and install dependencies:
```bash
pip install -r requirements.txt
```

### 3. Configuration
Create a `.env` file in the root directory (use `eg.env.txt` as a template):
```env
TAVILY_API_KEY=your_tavily_key
GEMINI_API_KEY=your_gemini_key
GROQ_API_KEY=your_groq_key
HUGGINGFACEHUB_API_KEY=your_hf_key
```

### 4. Running the App
Start the backend server:
```bash
python backend/app.py
```
Or use uvicorn directly:
```bash
uvicorn backend.app:app --reload
```
Then open `http://localhost:8000` in your browser.

## 🛠 Tech Stack
- **Backend**: FastAPI (Python)
- **Frontend**: Vanilla JS, HTML5, Modern CSS (Glassmorphism, CSS Variables)
- **Search**: Tavily Search API (REST)
- **AI Models**: Gemini 2.0 Flash, Llama 3.1 (via Groq), Mistral-7B (via HF)
- **Theming**: Dynamic CSS System (Light/Dark Support)


