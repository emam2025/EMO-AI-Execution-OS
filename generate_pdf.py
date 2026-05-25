#!/usr/bin/env python3
"""Generate project reference PDF for Emo AI Orchestrator"""

from fpdf import FPDF
import os

UNICODE_FONT = "/Library/Fonts/Arial Unicode.ttf"
if not os.path.exists(UNICODE_FONT):
    UNICODE_FONT = "/System/Library/Fonts/SFArabic.ttf"
if not os.path.exists(UNICODE_FONT):
    UNICODE_FONT = None

PDF_PATH = os.path.join(os.path.dirname(__file__), "EMO_AI_ORCHESTRATOR_REFERENCE.pdf")


class PDF(FPDF):
    def header(self):
        if self.page_no() > 1:
            self.set_font("Helvetica", "I", 8)
            self.set_text_color(140, 140, 140)
            self.cell(0, 8, "Emo AI Orchestrator - Project Reference", align="C")
            self.ln(12)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(140, 140, 140)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")

    def chapter_title(self, title):
        self.set_font("Helvetica", "B", 16)
        self.set_text_color(139, 92, 246)
        self.cell(0, 12, title, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(139, 92, 246)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(6)

    def sub_title(self, title):
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(60, 60, 80)
        self.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def body_text(self, text):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(40, 40, 40)
        self.set_x(self.l_margin)
        self.multi_cell(self.w - self.l_margin - self.r_margin, 5.5, text)
        self.ln(3)

    def bullet(self, text, indent=10):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(40, 40, 40)
        x0 = self.l_margin
        self.set_x(x0 + indent)
        self.multi_cell(self.w - self.l_margin - self.r_margin - indent, 5.5, "- " + text)

    def code_block(self, text):
        self.set_fill_color(240, 240, 248)
        self.set_font("Courier", "", 8.5)
        self.set_text_color(30, 30, 60)
        lines = text.split("\n")
        for line in lines:
            self.set_x(self.l_margin)
            self.cell(self.w - self.l_margin - self.r_margin, 4.5, "  " + line, fill=True, new_x="END", new_y="NEXT")
        self.ln(3)

    def key_value(self, key, value):
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(60, 60, 80)
        self.cell(50, 5.5, key, new_x="END", new_y="NEXT")
        self.set_x(self.l_margin + 52)
        self.set_font("Helvetica", "", 10)
        self.set_text_color(40, 40, 40)
        self.multi_cell(self.w - self.l_margin - self.r_margin - 52, 5.5, value)


pdf = PDF()
pdf.alias_nb_pages()
pdf.set_auto_page_break(auto=True, margin=20)

# ===================== COVER PAGE =====================
pdf.add_page()
pdf.ln(50)
pdf.set_font("Helvetica", "B", 32)
pdf.set_text_color(139, 92, 246)
pdf.cell(0, 15, "Emo AI Orchestrator", align="C", new_x="LMARGIN", new_y="NEXT")
pdf.set_font("Helvetica", "", 16)
pdf.set_text_color(120, 120, 160)
pdf.cell(0, 10, "Multi-Agent Intelligence Orchestration System", align="C", new_x="LMARGIN", new_y="NEXT")
pdf.ln(10)
pdf.set_draw_color(139, 92, 246)
pdf.line(60, pdf.get_y(), 150, pdf.get_y())
pdf.ln(10)
pdf.set_font("Helvetica", "", 11)
pdf.set_text_color(100, 100, 120)
pdf.cell(0, 7, "Project Reference Document", align="C", new_x="LMARGIN", new_y="NEXT")
pdf.cell(0, 7, "Version 1.0", align="C", new_x="LMARGIN", new_y="NEXT")
pdf.ln(30)
pdf.set_font("Helvetica", "I", 10)
pdf.set_text_color(100, 100, 120)
pdf.cell(0, 7, "Prepared by: Eng. Emam Abdullaziz", align="C", new_x="LMARGIN", new_y="NEXT")

# ===================== TABLE OF CONTENTS =====================
pdf.add_page()
pdf.chapter_title("Table of Contents")
toc_items = [
    "1. Project Overview",
    "2. System Architecture",
    "3. Technology Stack",
    "4. Project Structure & Files",
    "5. Core Components",
    "   5.1 main.py - FastAPI Server",
    "   5.2 brain.py - LLM Interface",
    "   5.3 agent.py - Agent System",
    "   5.4 tools.py - Tool Registry (68 Tools)",
    "   5.5 memory.py - Memory System",
    "   5.6 i18n.py - Internationalization",
    "   5.7 templates/index.html - Web UI",
    "6. Complete Tools List",
    "7. API Endpoints",
    "8. Installation & Setup",
    "9. Credits",
]
for item in toc_items:
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(40, 40, 40)
    pdf.cell(0, 6.5, item, new_x="LMARGIN", new_y="NEXT")

# ===================== SECTION 1: PROJECT OVERVIEW =====================
pdf.add_page()
pdf.chapter_title("1. Project Overview")
pdf.body_text(
    "Emo AI Orchestrator is a multi-agent AI orchestration system designed to distribute "
    "complex tasks among specialized AI agents. The system serves as a smart intermediary "
    "that receives user requests, analyzes them using an LLM planner, breaks them into "
    "subtasks, assigns each subtask to the most appropriate agent, and aggregates the "
    "results into a coherent final response."
)
pdf.body_text(
    "The system features a modern web interface built with FastAPI and TailwindCSS, "
    "supporting both Arabic and English languages, real-time execution logging via "
    "Server-Sent Events (SSE), and a comprehensive library of 68 tools organized into "
    "11 categories."
)
pdf.sub_title("Key Features")
pdf.bullet("Multi-agent architecture with 4 specialized agents (Planner, Coder, Writer, Researcher)")
pdf.bullet("Hybrid task routing: LLM classifies tasks, routes to specialized agents")
pdf.bullet("Dynamic execution: parallel (threading) and sequential task execution")
pdf.bullet("68 built-in tools across 11 categories")
pdf.bullet("Dual LLM provider support: OpenRouter and Groq")
pdf.bullet("Arabic/English bilingual interface with RTL support")
pdf.bullet("Dark/Light theme support")
pdf.bullet("Real-time execution log streaming via SSE")
pdf.bullet("Persistent memory with ChromaDB vector store")
pdf.bullet("Modern responsive web UI built with TailwindCSS")

# ===================== SECTION 2: SYSTEM ARCHITECTURE =====================
pdf.add_page()
pdf.chapter_title("2. System Architecture")
pdf.body_text(
    "The system follows a hub-and-spoke architecture where the Orchestrator (main.py) "
    "acts as the central coordinator. User requests flow through the following pipeline:"
)
pdf.ln(3)
pdf.sub_title("Request Flow")
pdf.body_text(
    "User Input -> Planner Agent (classify & break down) -> Agent Assignment "
    "-> Parallel/Sequential Execution -> Result Aggregation -> Final Response"
)
pdf.ln(2)
pdf.sub_title("Architecture Diagram")
pdf.code_block(
    "+---------------------------------------------------------+\n"
    "|                    User (Web UI)                         |\n"
    "+---------------------+-----------------------------------+\n"
    "                      |\n"
    "                      v\n"
    "+---------------------------------------------------------+\n"
    "|              FastAPI Server (main.py)                    |\n"
    "|              Port 8080 | 11 API Endpoints                |\n"
    "+---------+-----------+-----------+-----------------------+\n"
    "          |           |           |\n"
    "          v           v           v\n"
    "+--------------+ +----------+ +--------------+\n"
    "|  SSE Stream  | | REST API | |  Template    |\n"
    "|  (real-time) | | (CRUD)   | |  Engine      |\n"
    "+--------------+ +-----+----+ +--------------+\n"
    "                        |\n"
    "           +------------+------------+\n"
    "           v            v            v\n"
    "+--------------+ +----------+ +--------------+\n"
    "|  Planner     | |  Coder   | |  Writer/Res  |\n"
    "|  Agent       | |  Agent   | |  Agents      |\n"
    "|  (OpenRouter)| |  (Groq)  | |  (OpenRouter)|\n"
    "+------+-------+ +----+-----+ +------+-------+\n"
    "       |              |              |\n"
    "       v              v              v\n"
    "+---------------------------------------------------------+\n"
    "|             68 Tools | 11 Categories                     |\n"
    "|  Core AI | Coding | Design | Docs | Web | Math | ...    |\n"
    "+---------------------------------------------------------+\n"
    "       |              |              |\n"
    "       v              v              v\n"
    "+---------------------------------------------------------+\n"
    "|            Memory (JSON + ChromaDB)                      |\n"
    "+---------------------------------------------------------+\n"
)

# ===================== SECTION 3: TECHNOLOGY STACK =====================
pdf.add_page()
pdf.chapter_title("3. Technology Stack")
tech_stack = [
    ("Backend Framework", "FastAPI (Python 3.14)"),
    ("Web Server", "Uvicorn 0.47.0"),
    ("Template Engine", "Custom (regex-based)"),
    ("LLM Integration", "OpenAI Python SDK v2.37.0"),
    ("LLM Providers", "OpenRouter (GPT-4o-mini) / Groq (Llama 3.3-70B)"),
    ("Vector Database", "ChromaDB (PersistentClient)"),
    ("Frontend Styling", "TailwindCSS (CDN)"),
    ("Icons", "Font Awesome 6.5.1"),
    ("Fonts", "Inter / Cairo (Google Fonts)"),
    ("PDF Generation", "fpdf2"),
    ("Real-time Streaming", "Server-Sent Events (SSE)"),
]
for key, val in tech_stack:
    pdf.key_value(key + ":", val)

# ===================== SECTION 4: PROJECT STRUCTURE =====================
pdf.add_page()
pdf.chapter_title("4. Project Structure & Files")
pdf.code_block(
    "ai-agent-controller/\n"
    "|-- main.py                    FastAPI server + APIs + template engine\n"
    "|-- brain.py                   LLM interface (OpenRouter/Groq)\n"
    "|-- agent.py                   Agent classes + provider mapping\n"
    "|-- tools.py                   68 tools in 11 categories\n"
    "|-- memory.py                  JSON + ChromaDB memory store\n"
    "|-- i18n.py                    Arabic/English translations\n"
    "|-- generate_pdf.py            PDF document generator\n"
    "|-- .emo_settings.json         Persisted settings (auto-created)\n"
    "|-- templates/\n"
    "|   +-- index.html             Web UI (TailwindCSS + JS)\n"
    "|-- static/                    Static assets directory\n"
    "|-- .memory/                   Memory store (auto-created)\n"
    "+-- venv/                      Python virtual environment\n"
)
pdf.ln(2)
pdf.sub_title("File Descriptions")
files_desc = [
    ("main.py", "FastAPI application with custom regex-based template engine. Serves the web UI (GET /), manages settings (GET/POST /api/settings), processes chat messages asynchronously (POST /api/chat), streams execution logs via SSE (GET /api/stream/{task_id}), lists tools and history."),
    ("brain.py", "LLM abstraction layer. Supports OpenRouter and Groq providers through OpenAI-compatible API. Uses lazy initialization - API keys are only checked at first use, allowing the server to start without configured keys. Reads OPENROUTER_API_KEY and GROQ_API_KEY from environment or .env file."),
    ("agent.py", "Defines 4 agent types: Planner (classifies tasks, outputs JSON plan), Coder (writes/debugs code via Groq), Writer (docs/text via OpenRouter), Researcher (web search via OpenRouter). Each agent has a custom system prompt, allowed tools list, and provider assignment."),
    ("tools.py", "Comprehensive tool registry with 68 tools across 11 categories. Each tool extends the Tool base class with name, description, category, icon, and run() method. Tools range from simple (Calculator, StatsTool) to complex (WebSearch with real DuckDuckGo scraping, ScreenCapture via macOS screencapture)."),
    ("memory.py", "Two-tier memory system: Memory class provides JSON file-based persistence for simple key-value storage with search/recent methods. VectorMemory class (optional, requires chromadb) provides semantic search via ChromaDB persistent client."),
    ("i18n.py", "Internationalization module with complete English and Arabic translations for all UI strings. Exposes T dictionary keyed by language code and a helper function t(key, lang)."),
]
for name, desc in files_desc:
    pdf.sub_title(name)
    pdf.body_text(desc)

# ===================== SECTION 5: CORE COMPONENTS =====================
pdf.add_page()
pdf.chapter_title("5.1 main.py - FastAPI Server")
pdf.body_text(
    "The entry point and HTTP server. Built with FastAPI, it exposes 11 routes including "
    "the main page, RESTful settings management, chat processing with background threading, "
    "and Server-Sent Events streaming for real-time execution logs."
)
pdf.sub_title("Key Classes & Functions")
pdf.bullet("AppState: Singleton holding tools registry, agents, memory, settings, active tasks, and chat history")
pdf.bullet("render_template(): Custom regex-based template engine replacing {{ var }} placeholders")
pdf.bullet("_process_task(): Background thread that runs the full orchestration pipeline")
pdf.bullet("_parse_plan(): Extracts JSON task plan from LLM planner output with fallback")
pdf.ln(2)
pdf.sub_title("Chat Processing Flow")
pdf.body_text(
    "1. POST /api/chat creates a task ID and spawns a background thread\n"
    "2. The thread calls Planner agent to analyze the request\n"
    "3. Parse the JSON plan into task list\n"
    "4. Execute each task through the appropriate agent (with threading for parallel groups)\n"
    "5. Aggregate results using a dedicated aggregator agent\n"
    "6. Store result and chat history\n"
    "7. Client receives real-time updates via GET /api/stream/{task_id} (SSE)"
)

# ===================== SECTION 5.2 =====================
pdf.add_page()
pdf.chapter_title("5.2 brain.py - LLM Interface")
pdf.body_text(
    "Provides a unified interface to multiple LLM providers. Currently supports "
    "OpenRouter (default, model: gpt-4o-mini) and Groq (model: llama-3.3-70b-versatile). "
    "Uses lazy initialization to defer API key validation until the first ask() call."
)
pdf.sub_title("Provider Configuration")
pdf.code_block(
    "PROVIDERS = {\n"
    '    "openrouter": {\n'
    '        "base_url": "https://openrouter.ai/api/v1",\n'
    '        "api_key_env": "OPENROUTER_API_KEY",\n'
    '        "default_model": "gpt-4o-mini",\n'
    "    },\n"
    '    "groq": {\n'
    '        "base_url": "https://api.groq.com/openai/v1",\n'
    '        "api_key_env": "GROQ_API_KEY",\n'
    '        "default_model": "llama-3.3-70b-versatile",\n'
    "    },\n"
    "}"
)
pdf.body_text(
    "The Brain class exposes an ask() method accepting system prompt, user prompt, "
    "temperature (default 0.7), and max_tokens. Errors are caught and returned as "
    "strings to prevent crashes."
)

# ===================== SECTION 5.3 =====================
pdf.chapter_title("5.3 agent.py - Agent System")
pdf.body_text(
    "Defines the Agent class and factory function. Each agent has a type (planner, coder, "
    "writer, researcher), an assigned LLM provider, a system prompt, and a list of allowed "
    "tools. Agents can run tasks with or without tool access."
)
pdf.sub_title("Agent Configuration")
pdf.code_block(
    "AGENT_PROVIDERS = {\n"
    '    "planner": "openrouter",   # Classification & planning\n'
    '    "coder": "groq",           # Code generation (fast)\n'
    '    "writer": "openrouter",    # Documentation & text\n'
    '    "researcher": "openrouter",# Web research\n'
    "}\n"
    "\n"
    "AGENT_TOOLS = {\n"
    "    # Each agent type has access to specific tools\n"
    '    "coder": ["code_writer", "run_python", "shell_execute",\n'
    '              "file_reader", "file_writer", ...],\n'
    '    "writer": ["doc_writer", "report_generator", "email_writer", ...],\n'
    '    "researcher": ["web_search", "web_scraper", "fact_checker", ...],\n'
    "}"
)
pdf.sub_title("Tool Execution")
pdf.body_text(
    "When an agent runs with tools, the system prompt includes available tool descriptions "
    "and usage format. The agent can invoke tools using TOOL:/ENDTOOL markers in its "
    "response. The _execute_tool_calls() method parses these markers, calls the "
    "appropriate tool, and injects results back into the response."
)

# ===================== SECTION 5.4 =====================
pdf.add_page()
pdf.chapter_title("5.4 tools.py - Tool Registry (68 Tools)")
pdf.body_text(
    "The tool system uses a registry pattern. Each tool extends the Tool base class and "
    "registers itself with a name, description, category, and icon. The ToolRegistry "
    "provides lookup by name and organization by category."
)
pdf.sub_title("Tool Base Class")
pdf.code_block(
    "class Tool:\n"
    '    name = ""              # Unique identifier\n'
    '    description = ""       # Human-readable description\n'
    '    category = "General"   # Category grouping\n'
    '    icon = ""              # Emoji icon for UI\n'
    "    parameters = {}        # Parameter schema\n"
    "\n"
    "    def run(self, **kwargs) -> str:\n"
    "        raise NotImplementedError\n"
    "\n"
    "    def to_dict(self):\n"
    "        return { ... }  # Serialize for API\n"
)
pdf.body_text(
    "The create_registry() factory function instantiates and registers all 68 tools. "
    "The registry is accessible via API at GET /api/tools which returns all tools "
    "organized by category with icons and descriptions."
)

# ===================== SECTION 6: ALL TOOLS =====================
pdf.add_page()
pdf.chapter_title("6. Complete Tools List")

tools_by_category = {
    "Core AI": ["llm_chat", "planner", "router", "memory_save", "memory_search", "context_builder"],
    "Coding": ["code_writer", "code_explainer", "code_debugger", "code_refactor", "code_review", "test_generator", "run_python"],
    "Design": ["ui_designer", "ux_suggester", "color_palette_generator", "layout_builder", "image_prompt_builder", "branding_tool"],
    "Documents": ["doc_writer", "doc_summarizer", "doc_formatter", "report_generator", "email_writer", "cv_builder", "ppt_outline_builder"],
    "Web & Search": ["web_search", "web_scraper", "url_reader", "fact_checker"],
    "Math & Data": ["calculator", "data_analyzer", "csv_reader", "json_parser", "stats_tool"],
    "Management": ["task_manager", "goal_tracker", "decision_maker", "priority_ranker", "self_reflection"],
    "File System": ["file_reader", "file_writer", "file_editor", "file_organizer", "folder_creator", "file_search", "file_delete", "file_move", "file_copy", "folder_scan"],
    "Screen & Vision": ["screen_capture", "screen_analyze", "ui_element_detector", "screen_ocr", "screen_watch_mode"],
    "Browser": ["browser_open", "browser_navigate", "browser_click", "browser_type", "browser_scroll", "browser_extract_text", "browser_take_screenshot", "browser_login_helper", "browser_automation_script"],
    "System": ["system_info", "process_list", "shell_execute", "background_task"],
}

for category, tools in tools_by_category.items():
    pdf.sub_title(f"{category} ({len(tools)} tools)")
    for tool in tools:
        pdf.bullet(tool)
    pdf.ln(2)

# ===================== SECTION 7: API ENDPOINTS =====================
pdf.add_page()
pdf.chapter_title("7. API Endpoints")
api_endpoints = [
    ("GET /", "HTML Response", "Main web interface"),
    ("GET /api/settings", "JSON", "Get current settings (lang, theme, API keys, etc.)"),
    ("POST /api/settings", "JSON", "Update a setting by key/value"),
    ("GET /api/tools", "JSON", "List all 68 tools organized by category"),
    ("GET /api/history", "JSON", "Get chat history (last 50 messages)"),
    ("POST /api/chat", "JSON", "Send a message, returns task_id for streaming"),
    ("GET /api/stream/{task_id}", "SSE", "Server-Sent Events stream for execution log"),
]
for endpoint, response_type, desc in api_endpoints:
    pdf.sub_title(endpoint)
    pdf.key_value("Response:", response_type)
    pdf.body_text(desc)

# ===================== SECTION 8: INSTALLATION =====================
pdf.add_page()
pdf.chapter_title("8. Installation & Setup")
pdf.sub_title("Prerequisites")
pdf.bullet("Python 3.14+")
pdf.bullet("OpenRouter API key (https://openrouter.ai)")
pdf.bullet("Groq API key (https://groq.com)")
pdf.ln(3)
pdf.sub_title("Setup Steps")
pdf.body_text("1. Clone or navigate to the project directory:")
pdf.code_block("cd ai-agent-controller")
pdf.body_text("2. Create and activate virtual environment (already done):")
pdf.code_block("python3 -m venv venv\nsource venv/bin/activate")
pdf.body_text("3. Install dependencies:")
pdf.code_block("pip install fastapi uvicorn openai chromadb jinja2 python-multipart python-dotenv fpdf2")
pdf.body_text("4. Set API keys (either method):")
pdf.code_block("# Method 1: Export environment variables\nexport OPENROUTER_API_KEY=\"sk-or-v1-...\"\nexport GROQ_API_KEY=\"gsk_...\"\nexport LLM_PROVIDER=\"openrouter\"  # or \"groq\"\n\n# Method 2: Create .env file\n# OPENROUTER_API_KEY=sk-or-v1-...\n# GROQ_API_KEY=gsk_...\n")
pdf.body_text("5. Run the server:")
pdf.code_block("python3 main.py")
pdf.body_text("6. Open your browser to:")
pdf.code_block("http://localhost:8080")
pdf.ln(2)
pdf.sub_title("Alternative: Using the virtual environment directly")
pdf.code_block("./venv/bin/python3 main.py")
pdf.ln(2)
pdf.sub_title("Setting API Keys via the Web UI")
pdf.body_text(
    "Once the server is running, you can set API keys directly from the Settings panel "
    "in the left sidebar. Enter your keys and click Save. The server will automatically "
    "recreate agents with the new credentials."
)

# ===================== SECTION 9: CREDITS =====================
pdf.add_page()
pdf.chapter_title("9. Credits")
pdf.ln(10)
pdf.set_font("Helvetica", "", 14)
pdf.set_text_color(60, 60, 80)
pdf.cell(0, 10, "Project Development", align="C", new_x="LMARGIN", new_y="NEXT")
pdf.ln(5)
pdf.set_font("Helvetica", "B", 18)
pdf.set_text_color(139, 92, 246)
pdf.cell(0, 12, "Eng. Emam Abdullaziz", align="C", new_x="LMARGIN", new_y="NEXT")
pdf.ln(3)
if UNICODE_FONT:
    pdf.add_font("Unicode", "", UNICODE_FONT)
    pdf.set_font("Unicode", "", 12)
else:
    pdf.set_font("Helvetica", "", 12)
pdf.set_text_color(100, 100, 120)
pdf.cell(0, 8, "المهندس إمام عبدالعزيز", align="C", new_x="LMARGIN", new_y="NEXT")
pdf.ln(10)
pdf.set_draw_color(139, 92, 246)
pdf.line(60, pdf.get_y(), 150, pdf.get_y())
pdf.ln(10)
pdf.set_font("Helvetica", "", 10)
pdf.set_text_color(100, 100, 120)
pdf.cell(0, 7, "System Architecture & Design: Eng. Emam Abdullaziz", align="C", new_x="LMARGIN", new_y="NEXT")
pdf.cell(0, 7, "Full Stack Development: Eng. Emam Abdullaziz", align="C", new_x="LMARGIN", new_y="NEXT")
pdf.cell(0, 7, "AI Integration & Agent Design: Eng. Emam Abdullaziz", align="C", new_x="LMARGIN", new_y="NEXT")
pdf.cell(0, 7, "UI/UX Design: Eng. Emam Abdullaziz", align="C", new_x="LMARGIN", new_y="NEXT")
pdf.ln(15)
pdf.set_font("Helvetica", "I", 10)
pdf.set_text_color(140, 140, 140)
pdf.cell(0, 7, "Thank you for using Emo AI Orchestrator", align="C", new_x="LMARGIN", new_y="NEXT")
pdf.cell(0, 7, "2026", align="C", new_x="LMARGIN", new_y="NEXT")

# Save PDF
pdf.output(PDF_PATH)
print(f"PDF generated: {PDF_PATH}")
print(f"Size: {os.path.getsize(PDF_PATH):,} bytes")
print(f"Pages: {pdf.page_no()}")
