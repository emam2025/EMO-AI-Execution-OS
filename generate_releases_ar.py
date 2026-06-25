#!/usr/bin/env python3
"""Generate EMO AI Releases Guide — Arabic Version"""

from fpdf import FPDF
import os

FONT_PATH = "/Library/Fonts/Arial Unicode.ttf"
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "EMO_AI_RELEASES_AR.pdf")

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    HAVE_ARABIC = True
except ImportError:
    HAVE_ARABIC = False


def ar(text):
    if HAVE_ARABIC:
        reshaped = arabic_reshaper.reshape(text)
        return get_display(reshaped)
    return text


class PDF(FPDF):
    def header(self):
        if self.page_no() > 1:
            self.set_font("Unicode", "", 8)
            self.set_text_color(140, 140, 140)
            self.cell(0, 6, ar("EMO AI — Releases Guide"), align="C")
            self.ln(8)

    def footer(self):
        self.set_y(-15)
        self.set_font("Unicode", "", 8)
        self.set_text_color(140, 140, 140)
        self.cell(0, 8, ar(f"Page {self.page_no()}/{{nb}}"), align="C")

    def section_title(self, title):
        self.set_font("Unicode", "B", 16)
        self.set_text_color(139, 92, 246)
        self.cell(0, 12, ar(title), new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(139, 92, 246)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(5)

    def sub_title(self, title):
        self.set_font("Unicode", "B", 12)
        self.set_text_color(60, 60, 80)
        self.cell(0, 9, ar(title), new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def body(self, text):
        self.set_font("Unicode", "", 10)
        self.set_text_color(40, 40, 40)
        self.multi_cell(0, 5.5, ar(text))
        self.ln(2)

    def bullet(self, text, indent=10):
        self.set_font("Unicode", "", 10)
        self.set_text_color(40, 40, 40)
        x0 = self.l_margin
        self.set_x(x0 + indent)
        self.multi_cell(self.w - self.l_margin - self.r_margin - indent, 5.5, ar("  \u2022  " + text))

    def code_block(self, text):
        self.set_fill_color(240, 240, 248)
        self.set_font("Unicode", "", 8.5)
        self.set_text_color(30, 30, 60)
        lines = text.split("\n")
        for line in lines:
            self.set_x(self.l_margin)
            self.cell(self.w - self.l_margin - self.r_margin, 4.5, "  " + ar(line), fill=True, new_x="END", new_y="NEXT")
        self.ln(3)

    def component_table(self, items):
        for comp, status, desc in items:
            self.set_text_color(40, 40, 40)
            self.set_x(self.l_margin + 5)
            self.set_font("Unicode", "B", 9.5)
            self.cell(45, 5.5, ar(comp))
            self.set_font("Unicode", "", 9.5)
            self.cell(25, 5.5, ar(status))
            w = self.w - self.l_margin - self.r_margin - 75
            self.multi_cell(w, 5.5, ar(desc))
            self.ln(1)
        self.ln(3)


pdf = PDF()
pdf.alias_nb_pages()
pdf.set_auto_page_break(auto=True, margin=20)
pdf.add_font("Unicode", "", FONT_PATH)
pdf.add_font("Unicode", "B", FONT_PATH)

# ===================== COVER PAGE =====================
pdf.add_page()
pdf.ln(40)
pdf.set_font("Unicode", "B", 36)
pdf.set_text_color(139, 92, 246)
pdf.cell(0, 16, ar("EMO AI"), align="C", new_x="LMARGIN", new_y="NEXT")
pdf.set_font("Unicode", "", 18)
pdf.set_text_color(120, 120, 160)
pdf.cell(0, 12, ar("Releases Map Guide"), align="C", new_x="LMARGIN", new_y="NEXT")
pdf.ln(5)
pdf.set_draw_color(139, 92, 246)
pdf.line(50, pdf.get_y(), 160, pdf.get_y())
pdf.ln(8)
pdf.set_font("Unicode", "", 11)
pdf.set_text_color(100, 100, 120)
pdf.cell(0, 7, ar("From Runtime OS to Big EMO AI OS"), align="C", new_x="LMARGIN", new_y="NEXT")
pdf.cell(0, 7, ar("Five Generations of Evolution"), align="C", new_x="LMARGIN", new_y="NEXT")
pdf.ln(35)
pdf.set_font("Unicode", "", 10)
pdf.set_text_color(100, 100, 120)
pdf.cell(0, 7, ar("Prepared by: Eng. Emam Abdullaziz"), align="C", new_x="LMARGIN", new_y="NEXT")
pdf.cell(0, 7, "2026", align="C", new_x="LMARGIN", new_y="NEXT")

# Intellectual property
pdf.ln(20)
pdf.set_font("Unicode", "", 9)
pdf.set_text_color(140, 140, 140)
pdf.multi_cell(0, 5,
    ar("All intellectual property rights are reserved to Eng. Emam Abdullaziz. This document and the EMO AI "
       "system described herein are protected by applicable intellectual property laws. Unauthorized copying, distribution, "
       "or modification is prohibited."),
    align="C"
)

# ===================== TABLE OF CONTENTS =====================
pdf.add_page()
pdf.section_title("Contents")
toc = [
    "1.  Introduction",
    "2.  R1 — Runtime OS Operating System",
    "3.  R2 — Memory OS Operating System",
    "4.  R3 — Skill OS Operating System",
    "5.  R4 — Cognitive OS Operating System",
    "6.  R5 — Big EMO AI OS Full Intelligence Operating System",
    "7.  Platform Support Matrix",
    "8.  Summary and Future Vision",
]
for item in toc:
    pdf.set_font("Unicode", "", 11)
    pdf.set_text_color(40, 40, 40)
    pdf.cell(0, 7, ar(item), new_x="LMARGIN", new_y="NEXT")

# ===================== INTRODUCTION =====================
pdf.add_page()
pdf.section_title("1. Introduction")
pdf.body(
    "EMO AI is a multi-generational AI operating system, designed to evolve from a simple task execution platform "
    "to a fully independent digital workforce platform. The system is built across five major releases, each release "
    "adding a new layer of intelligence, autonomy, and capabilities."
)
pdf.body(
    "Each release is a standalone product, containing a frozen core engine, an independent user interface built "
    "with the Tauri framework (for cross-platform desktop applications), a dedicated test suite, deployment configurations, "
    "and digital signing certificates. This architecture ensures backward compatibility and allows independent evolution "
    "of each generation."
)
pdf.ln(3)
pdf.sub_title("Five Releases at a Glance")
overview = [
    ("R1 — Runtime OS",     "Task execution, agent coordination, model gateway, monitoring"),
    ("R2 — Memory OS",      "Hierarchical memory, context assembly, knowledge maps, long-term retrieval"),
    ("R3 — Skill OS",       "Automatic skill extraction, pattern learning, reusable skill library"),
    ("R4 — Cognitive OS",   "Strategic planning, goal analysis, self-assessment, reasoning loops"),
    ("R5 — Big EMO AI OS",  "Independent digital workforce, self-building tools, self-healing infrastructure"),
]
for name, desc in overview:
    pdf.set_font("Unicode", "B", 10)
    pdf.set_text_color(139, 92, 246)
    pdf.cell(55, 6, ar(name))
    pdf.set_font("Unicode", "", 9.5)
    pdf.set_text_color(60, 60, 80)
    pdf.multi_cell(0, 6, ar(desc))
    pdf.ln(2)

# ===================== R1 — RUNTIME OS =====================
pdf.add_page()
pdf.section_title("2. R1 — Runtime OS Operating System")
pdf.body(
    "The foundational release. Runtime OS transforms EMO AI from a simple chat application into a production-grade "
    "multi-agent orchestration platform. It manages agents, tasks, workflows, and model routing across local and distributed environments."
)
pdf.ln(2)
pdf.sub_title("Core Capabilities")
pdf.bullet("Multi-agent execution — PlannerAgent, CriticAgent, OptimizerAgent with coordination state machine (8 states, 9 transitions)")
pdf.bullet("Execution engine — Divided into 5 specific services: Scheduler, State Store, Dispatcher, Retry Handler, Lease Manager")
pdf.bullet("Control layer — CompositionRoot with dependency injection and factory services")
pdf.bullet("Model gateway — Smart provider router based on weight/latency/cost, automatic failover (<=500ms), rate limiting, metrics aggregation")
pdf.bullet("Monitoring — Real-time CPU/memory/queue monitoring, execution explorer, routing dashboard")
pdf.bullet("Security — OS keychain integration (macOS/Windows/Linux), temporary credential injection (auto-clear 5s), no plain text keys")
pdf.bullet("User interface — Cross-platform Tauri shell with 7 live routes, design system (glass), command palette (Ctrl+K), first-run wizard")
pdf.bullet("IPC contract — Structured protocol (v1.2.0) for all runtime communications with strict forward-compatibility rules")
pdf.ln(2)
pdf.sub_title("Components")
pdf.component_table([
    ("Agent Coordination",        "Complete",  "41/41 tests, 8 transitions G-P1-G-P8"),
    ("Execution Engine",          "Complete",  "5 specific services, 358 tests"),
    ("Model Gateway",             "Complete",  "47/47 tests, 8 quality criteria"),
    ("User Interface",             "P1-P4",    "7 routes, 130/130 tests"),
    ("Governance (RBAC/Audit)",   "Pending",   "Planned for R1 final closure"),
    ("Platform",                  "macOS",     "Cross-platform Tauri structure ready"),
])
pdf.ln(2)
pdf.body(
    "R1 is 75% complete. Remaining work includes governance (RBAC, audit trails, tenant isolation policies) and full UI integration with live data."
)

# ===================== R2 — MEMORY OS =====================
pdf.add_page()
pdf.section_title("3. R2 — Memory OS Operating System")
pdf.body(
    "Memory OS transforms EMO from a task-executing system into a system that remembers, learns, and evolves from its history. "
    "This release adds persistent memory layers enabling context-aware decision making and long-term knowledge retention."
)
pdf.ln(2)
pdf.sub_title("Core Capabilities")
pdf.bullet("Hierarchical memory — Multi-level memory architecture with store/retrieve/prune operations, optimized for over 126K operations per second")
pdf.bullet("Context assembler — Intelligent context compression with token budget and SHA-256 integrity verification")
pdf.bullet("Skill graph manager — Records and organizes learned skills as a navigable knowledge graph")
pdf.bullet("Memory state machine — 6 states with 7 transitions (G-M1 to G-M6), 0% tenant leakage")
pdf.bullet("Cognitive trace anchor — SHA-256 deployment across all memory operations for full audit")
pdf.ln(2)
pdf.sub_title("Planned Components")
pdf.component_table([
    ("Project Memory",               "Planned",   "Isolated memory spaces per project"),
    ("Agent Memory",                 "Planned",   "Historical context per agent"),
    ("Long-term Memory",             "Planned",   "Persistent storage with intelligent retrieval"),
    ("Knowledge Graph",              "Planned",   "Graph-based knowledge representation"),
    ("Memory Compression",           "Planned",   "Memory optimization to reduce tokens"),
    ("Semantic Indexing",            "Planned",   "Context-based intelligent retrieval"),
    ("Context Reconstruction",       "Planned",   "Context reconstruction from fragmented memory"),
])
pdf.ln(2)
pdf.body(
    "R2 is 30% complete with 5 core components already built in core/memory/. "
    "Seven additional components plus a dedicated UI for the memory explorer are planned."
)

# ===================== R3 — SKILL OS =====================
pdf.add_page()
pdf.section_title("4. R3 — Skill OS Operating System")
pdf.body(
    "Skill OS transforms accumulated knowledge and experience into reusable, composable skills. "
    "Instead of manually programming solutions, EMO automatically extracts patterns from past executions "
    "and builds a library of deployable skills."
)
pdf.ln(2)
pdf.sub_title("Core Capabilities")
pdf.bullet("Skill extraction — Automatic identification of reusable patterns from successful task executions")
pdf.bullet("Workflow learning — Learning multi-step work sequences by monitoring repeated execution sequences")
pdf.bullet("Pattern recognition — Detecting recurring problem-solution patterns across different contexts")
pdf.bullet("Tool usage learning — Analyzing how tools are used and generalizing invocation patterns")
pdf.bullet("Skill library — Indexed and versioned repository of extracted skills")
pdf.bullet("Skill ranking — Prioritizing skills by relevance, success rate, and usage frequency")
pdf.bullet("Skill evolution — Automatically updating and improving skills as new patterns emerge")
pdf.ln(2)
pdf.body(
    "Example: After fixing 5 React issues, EMO automatically extracts a 'React Debugging Skill' and proactively "
    "applies it in future React tasks."
)
pdf.ln(2)
pdf.body(
    "R3 has not started yet (0%). All seven components need to be built from scratch, in addition to "
    "a dedicated UI for the skill library."
)

# ===================== R4 — COGNITIVE OS =====================
pdf.add_page()
pdf.section_title("5. R4 — Cognitive OS Operating System")
pdf.body(
    "Cognitive OS adds strategic thinking and long-term planning. EMO advances from individual task execution "
    "to formulating multi-step strategies, analyzing complex goals, self-assessing its performance, "
    "and adapting its approach over time."
)
pdf.ln(2)
pdf.sub_title("Core Capabilities")
pdf.bullet("Strategic planning — Formulating multi-step long-term strategies aligned with high-level goals")
pdf.bullet("Goal analysis — Decomposing complex goals into manageable, hierarchically organized sub-goals")
pdf.bullet("Self-assessment — Critically evaluating self-outputs and identifying areas for improvement")
pdf.bullet("Multi-step reasoning — Executing reasoning chains with intermediate verification")
pdf.bullet("Thinking loops — Iteratively refining solutions through self-reflection cycles")
pdf.bullet("Adaptive policies — Dynamically adjusting behavior based on environmental feedback")
pdf.ln(2)
pdf.sub_title("Foundational Assets (from Phase G)")
pdf.component_table([
    ("PlannerAgent",     "Available",   "DAG synthesis, oscillation prevention"),
    ("CriticAgent",      "Available",   "Plan evaluation, scope verification"),
    ("OptimizerAgent",   "Available",   "Linear cost optimization"),
    ("State Machine",    "Available",   "8 states, 9 transitions, G-P1-G-P8"),
])
pdf.ln(2)
pdf.body(
    "R4 is 20% complete. Planner/Critic/Optimizer agents from Phase G provide task-level cognitive "
    "capabilities. R4 expands these capabilities to long-term strategic cognition with 6 additional "
    "components and a strategic dashboard."
)

# ===================== R5 — BIG EMO AI OS =====================
pdf.add_page()
pdf.section_title("6. R5 — Big EMO AI OS Full Intelligence Operating System")
pdf.body(
    "The final release. Big EMO AI OS is a fully independent digital workforce platform. It builds its own tools, "
    "learns without human intervention, hardens its boundaries, and runs across macOS, Windows, Linux, and Android "
    "with a unified intelligence layer."
)
pdf.ln(2)
pdf.sub_title("Core Capabilities")
pdf.bullet("Specialized agent teams — Dynamic formation of agent teams optimized for specific project types")
pdf.bullet("Independent project execution — Comprehensive project management from requirements to delivery")
pdf.bullet("Cross-project learning — Transferring knowledge and patterns across unrelated projects")
pdf.bullet("Enterprise memory — Organization-level memory with role-based access control")
pdf.bullet("Skill marketplace — Ecosystem for sharing, evaluating, and discovering community skills")
pdf.bullet("Enterprise-level intelligence — Learning team dynamics, coding standards, and organizational patterns")
pdf.bullet("Self-optimizing operation — Automatic optimization of its own execution pipeline")
pdf.bullet("Self-tool building — Generating new tools as needed to solve novel problems")
pdf.bullet("Self-healing infrastructure — Detecting and fixing operational issues without human intervention")
pdf.bullet("Self-hardening security — Continuous adaptation of security posture against emerging threats")
pdf.ln(2)
pdf.body(
    "R5 has not started yet (0%) with 10+ components needing to be built. This release represents the culmination of the EMO AI vision: "
    "a fully independent AI operating system that builds, learns, and protects itself."
)

# ===================== PLATFORM SUPPORT =====================
pdf.add_page()
pdf.section_title("7. Platform Support Matrix")
pdf.ln(2)
pdf.sub_title("Desktop and Mobile Support Per Release")
pdf.ln(1)
headers = [ar("Release"), ar("macOS"), ar("Windows"), ar("Linux"), ar("Android")]
col_w = [50, 30, 30, 30, 30]
pdf.set_font("Unicode", "B", 9.5)
pdf.set_fill_color(139, 92, 246)
pdf.set_text_color(255, 255, 255)
for i, h in enumerate(headers):
    pdf.cell(col_w[i], 8, h, border=1, fill=True, align="C")
pdf.ln()

rows = [
    [ar("R1 Runtime OS"),     ar("Yes (Tauri)"), ar("Yes (Tauri)"),   ar("Yes (Tauri)"),   ar("No")],
    [ar("R2 Memory OS"),      ar("Planned"),     ar("Planned"),        ar("Planned"),        ar("Planned")],
    [ar("R3 Skill OS"),       ar("Planned"),     ar("Planned"),        ar("Planned"),        ar("Planned")],
    [ar("R4 Cognitive OS"),   ar("Planned"),     ar("Planned"),        ar("Planned"),        ar("Planned")],
    [ar("R5 Big EMO AI OS"),  ar("Yes"),         ar("Yes"),            ar("Yes"),            ar("Yes")],
]
pdf.set_font("Unicode", "", 9.5)
pdf.set_text_color(40, 40, 40)
for row in rows:
    for i, cell in enumerate(row):
        pdf.cell(col_w[i], 7, cell, border=1, align="C")
    pdf.ln()

pdf.ln(5)
pdf.body(
    "The Tauri v2 framework provides native cross-platform support for macOS, Windows, and Linux operating systems. "
    "Android support requires additional Tauri Mobile or Capacitor configuration, planned from R2 onward."
)

# ===================== SUMMARY =====================
pdf.add_page()
pdf.section_title("8. Summary and Future Vision")
pdf.body(
    "The five-release roadmap of EMO AI charts a clear evolution from a task execution engine to a fully independent "
    "digital workforce. Each release builds on its predecessor while remaining an independent, self-contained product."
)
pdf.ln(3)
pdf.sub_title("Releases Summary")
pdf.ln(1)
sum_headers = [ar("Release"), ar("Status"), ar("Tests"), ar("Components")]
sum_col_w = [48, 30, 30, 82]
pdf.set_font("Unicode", "B", 9.5)
pdf.set_fill_color(139, 92, 246)
pdf.set_text_color(255, 255, 255)
for i, h in enumerate(sum_headers):
    pdf.cell(sum_col_w[i], 8, h, border=1, fill=True, align="C")
pdf.ln()

rows_data = [
    ("R1 Runtime OS",      "75% Complete",  "3047+",   "Multi-agent, execution, gateway, monitoring, security, UI"),
    ("R2 Memory OS",       "30% Complete",  "25+",     "Hierarchical memory, context assembler, skill graph, state machine"),
    ("R3 Skill OS",        "0% Not Started","0",       "Extraction, learning, recognition, library, ranking, evolution"),
    ("R4 Cognitive OS",    "20% Basic",     "41+",     "Strategic planning, goal analysis, self-assessment, reasoning"),
    ("R5 Big EMO AI OS",   "0% Not Started","0",       "Independent teams, self-building, self-healing, enterprise memory"),
]

for row in rows_data:
    y0 = pdf.get_y()
    row_h = 18
    if pdf.get_y() + row_h > pdf.h - 25:
        pdf.add_page()
        y0 = pdf.get_y()
    pdf.set_font("Unicode", "", 9)
    pdf.set_text_color(40, 40, 40)
    for i, cell in enumerate(row):
        pdf.set_xy(10 + sum(sum_col_w[:i]), y0)
        pdf.multi_cell(sum_col_w[i], 6, ar(cell), border=1, align="C")
    pdf.set_y(y0 + row_h)

pdf.ln(5)
pdf.sub_title("Vision")
pdf.body(
    "Big EMO AI OS represents the final form: an AI operating system that builds its own tools, learns "
    "from its history without human intervention, hardens its boundaries, and works seamlessly across desktop and mobile platforms. "
    "Each release brings us closer to this vision, delivering tangible value at every step while maintaining full "
    "backward compatibility and independent product integrity."
)
pdf.ln(5)
pdf.sub_title("Target Structure")
pdf.code_block(
    "releases/\n"
    "  runtime-os/       (R1)  Frozen engine + Tauri UI + deployment\n"
    "  memory-os/        (R2)  Frozen engine + Memory UI + deployment\n"
    "  skill-os/         (R3)  Frozen engine + Skills UI + deployment\n"
    "  cognitive-os/     (R4)  Frozen engine + Cognitive UI + deployment\n"
    "  big-emo/          (R5)  Frozen engine + Workforce UI + mobile"
)

# ===================== CREDITS =====================
pdf.ln(10)
pdf.set_draw_color(139, 92, 246)
pdf.line(50, pdf.get_y(), 160, pdf.get_y())
pdf.ln(8)
pdf.set_font("Unicode", "B", 16)
pdf.set_text_color(139, 92, 246)
pdf.cell(0, 10, ar("Intellectual Property Rights"), align="C", new_x="LMARGIN", new_y="NEXT")
pdf.ln(3)
pdf.set_font("Unicode", "", 10)
pdf.set_text_color(100, 100, 120)
pdf.multi_cell(0, 6,
    ar("All intellectual property rights, including but not limited to copyrights, trademarks, and patents, in the EMO AI system "
       "and its source code, architecture, design, documentation, and any related materials, are exclusively owned by "
       "Eng. Emam Abdullaziz. Unauthorized copying, distribution, modification, or commercial use without prior written consent is prohibited."),
    align="C"
)
pdf.ln(5)
pdf.set_font("Unicode", "B", 14)
pdf.set_text_color(139, 92, 246)
pdf.cell(0, 8, ar("Eng. Emam Abdullaziz"), align="C", new_x="LMARGIN", new_y="NEXT")
pdf.set_font("Unicode", "", 10)
pdf.set_text_color(100, 100, 120)
pdf.cell(0, 7, ar("System Architect and Lead Developer"), align="C", new_x="LMARGIN", new_y="NEXT")
pdf.ln(5)
pdf.set_font("Unicode", "", 9)
pdf.set_text_color(140, 140, 140)
pdf.cell(0, 6, "2026", align="C", new_x="LMARGIN", new_y="NEXT")

pdf.output(OUTPUT_PATH)
print(f"PDF generated: {OUTPUT_PATH}")
print(f"Size: {os.path.getsize(OUTPUT_PATH):,} bytes")
print(f"Pages: {pdf.page_no()}")
