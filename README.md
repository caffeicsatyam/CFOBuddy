<p align="center">
<img alt="CFO Buddy" src="./static/cfobuddy.png" width="512">
<br>
<em>An AI-Powered Multi-Agent Orchestration for CFOs - transforming raw financial data into actionable insights through conversational analysis and dynamic charting.</em>
<br><br>
<a title="License MIT" target="_blank" href="https://opensource.org/licenses/MIT"><img src="http://img.shields.io/badge/license-MIT-orange.svg?style=flat-square"></a>
<a title="Python" target="_blank" href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.10+-blue.svg?style=flat-square"></a>
<a title="Next.js" target="_blank" href="https://nextjs.org/"><img src="https://img.shields.io/badge/Next.js-15+-black.svg?style=flat-square"></a>
<a title="FastAPI" target="_blank" href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/FastAPI-teal.svg?style=flat-square"></a>
<a title="React" target="_blank" href="https://react.dev/"><img src="https://img.shields.io/badge/React-lightblue.svg?style=flat-square"></a>
<br>
<a title="LangChain" target="_blank" href="https://python.langchain.com/"><img src="https://img.shields.io/badge/LangChain-darkgreen.svg?style=flat-square"></a>
<a title="LlamaIndex" target="_blank" href="https://www.llamaindex.ai/"><img src="https://img.shields.io/badge/LlamaIndex-purple.svg?style=flat-square"></a>
<a title="PostgreSQL" target="_blank" href="https://www.postgresql.org/"><img src="https://img.shields.io/badge/PostgreSQL-blue.svg?style=flat-square"></a>
<a title="Neon Serverless Postgres" target="_blank" href="https://neon.tech/"><img src="https://img.shields.io/badge/Neon-green.svg?style=flat-square"></a>
<a title="Groq" target="_blank" href="https://groq.com/"><img src="https://img.shields.io/badge/Groq-red.svg?style=flat-square"></a>
</p>

---

## Table of Contents

* [Introduction](#introduction)
* [Core Features](#core-features)
* [Graph Structure](#graph-structure)
* [Agent Workflow](#agent-workflow)
* [System Architecture](#system-architecture)
* [Tech Stack](#tech-stack)
* [Quick Start](#quick-start)

---

## Introduction

CFO Buddy is a **next-generation financial intelligence assistant** that blends the power of LLMs with real-time data, multi-agent reasoning, and a sleek ChatGPT-style interface.

Upload your data. Ask questions. Get insights.  
Simple on the surface — **deeply intelligent underneath.**

---

## Core Features

- **Conversational Finance** — Ask anything, get expert-level insights  
- **Multi-File Intelligence** — CSV, PDF, Excel, Word support  
- **Auto Charts** — Plotly-powered visualizations generated on the fly  
- **Agentic Reasoning** — Transparent thinking + decision flow  
- **Memory System** — Resume conversations anytime  
- **Hybrid Retrieval Engine** — Semantic + keyword search fusion  
- **Live Financial Data** — Powered by yfinance + APIs  

---


 
## Graph Structure

The "brain" of CFO Buddy is a multi-agent state machine built with **LangGraph**. It uses a specialized router to delegate queries to expert agents, each equipped with its own suite of professional tools.

---
```mermaid
graph TD
    START((START)) --> Upload[upload_node]
    
    Upload --> Router{LLM Router}
    
    Router -->|General| Model[model_node]
    Router -->|SQL Query| SQL[sql_node]
    Router -->|Finance Data| Finance[finance_node]
    Router -->|Web Search| Web[web_search_node]
    
    subgraph Tools ["Expert Toolkits"]
        Model <--> ITools[internal_tools]
        SQL <--> STools[sql_tools]
        Finance <--> FTools[finance_tools]
        Web <--> WTools[web_search_tools]
    end
    
    Model -.-> END((END))
    SQL -.-> END
    Finance -.-> END
    Web -.-> END
```

## Agent Workflow

The "brain" of CFO Buddy is a multi-agent orchestration layer. A **Supervisor** node manages a team of specialized experts, deciding who to delegate tasks to and verifying results before responding.



---
```mermaid
graph TD
    Start(( )) -->|User Query| Supervisor[Supervisor Agent]
    
    subgraph Brain ["Agent Thinking Process"]
        direction TB
        Planning[Planning] --> Delegation[Delegation]
        Delegation --> Execution[Execution]
        Execution --> Reflection[Reflection]
        Reflection -->|Need more info?| Planning
    end
    
    Supervisor --> Planning
    Reflection -->|Answer Ready| End(( ))
```

## System Architecture

CFO Buddy is built with a modern, high-performance stack designed for scalability and intelligence. It separates the presentation layer, the orchestration "brain," and the data/external tool layers.

---
```mermaid
graph LR
    User((User)) --> UI[Next.js Frontend]
    UI <--> API[FastAPI Backend]
    
    subgraph "Core Intelligence"
        API <--> LG[LangGraph 'Brain']
        LG <--> RAG[LlamaIndex RAG]
    end
    
    subgraph "Data & Persistence"
        LG <--> Neon[(Neon PostgreSQL)]
        RAG <--> Vector[(pgvector)]
    end
    
    subgraph "External Integration"
        LG <--> Fin[yfinance / 12Data]
        LG <--> Search[DuckDuckGo]
    end
```

## Tech Stack

| Component | Technology |
|-----------|------------|
| **LLM** | Groq (Llama 3 / Mixtral) |
| **Orchestration** | LangGraph |
| **Vector DB** | Neon (PostgreSQL + pgvector) |
| **Framework** | FastAPI (Backend) / Next.js (Frontend) |
| **Search** | LlamaIndex + BM25 |
| **Charts** | Plotly + HTML Components |

---

## Quick Start

### 1. Backend Setup
```bash
git clone https://github.com/caffeicsatyam/cfobuddy.git
cd cfobuddy
python -m venv venv
source venv/bin/activate  # venv\Scripts\activate on Windows
pip install -r requirements.txt
```

### 2. Environment Variables
Create a `.env` in the root:
```env
GROQ_API_KEY=your_key
DATABASE_URL=your_neon_url
TWELVE_DATA_API_KEY=your_key
```

### 3. Build & Run
```bash
python build_index.py  # Initialize vector store

python api/main.py     # Start API
```

### 4. Frontend Setup
```bash
cd frontend
npm install
npm run dev


uvicorn api.main:app --reload --host 0.0.0.0
```
