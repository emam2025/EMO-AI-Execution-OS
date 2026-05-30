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
            self.cell(0, 6, ar("EMO AI — دليل الإصدارات"), align="C")
            self.ln(8)

    def footer(self):
        self.set_y(-15)
        self.set_font("Unicode", "", 8)
        self.set_text_color(140, 140, 140)
        self.cell(0, 8, ar(f"الصفحة {self.page_no()}/{{nb}}"), align="C")

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
pdf.cell(0, 12, ar("دليل خريطة الإصدارات"), align="C", new_x="LMARGIN", new_y="NEXT")
pdf.ln(5)
pdf.set_draw_color(139, 92, 246)
pdf.line(50, pdf.get_y(), 160, pdf.get_y())
pdf.ln(8)
pdf.set_font("Unicode", "", 11)
pdf.set_text_color(100, 100, 120)
pdf.cell(0, 7, ar("من Runtime OS إلى Big EMO AI OS"), align="C", new_x="LMARGIN", new_y="NEXT")
pdf.cell(0, 7, ar("خمسة أجيال من التطور"), align="C", new_x="LMARGIN", new_y="NEXT")
pdf.ln(35)
pdf.set_font("Unicode", "", 10)
pdf.set_text_color(100, 100, 120)
pdf.cell(0, 7, ar("إعداد: المهندس إمام عبدالعزيز"), align="C", new_x="LMARGIN", new_y="NEXT")
pdf.cell(0, 7, "2026", align="C", new_x="LMARGIN", new_y="NEXT")

# Intellectual property
pdf.ln(20)
pdf.set_font("Unicode", "", 9)
pdf.set_text_color(140, 140, 140)
pdf.multi_cell(0, 5,
    ar("جميع حقوق الملكية الفكرية محفوظة للمهندس إمام عبدالعزيز. هذا المستند ونظام EMO AI "
       "الموصوف فيه محميان بموجب قوانين الملكية الفكرية المعمول بها. يُحظر النسخ أو التوزيع "
       "أو التعديل غير المصرح به."),
    align="C"
)

# ===================== TABLE OF CONTENTS =====================
pdf.add_page()
pdf.section_title("المحتويات")
toc = [
    "1.  مقدمة",
    "2.  R1 — Runtime OS نظام تشغيل التشغيل",
    "3.  R2 — Memory OS نظام تشغيل الذاكرة",
    "4.  R3 — Skill OS نظام تشغيل المهارات",
    "5.  R4 — Cognitive OS نظام تشغيل الإدراك",
    "6.  R5 — Big EMO AI OS نظام تشغيل الذكاء الكامل",
    "7.  مصفوفة دعم المنصات",
    "8.  ملخص والرؤية المستقبلية",
]
for item in toc:
    pdf.set_font("Unicode", "", 11)
    pdf.set_text_color(40, 40, 40)
    pdf.cell(0, 7, ar(item), new_x="LMARGIN", new_y="NEXT")

# ===================== INTRODUCTION =====================
pdf.add_page()
pdf.section_title("1. مقدمة")
pdf.body(
    "EMO AI هو نظام تشغيل ذكاء اصطناعي متعدد الأجيال، مصمم ليتطور من منصة تشغيل مهام بسيطة "
    "إلى منصة قوة عمل رقمية مستقلة بالكامل. تم بناء النظام عبر خمسة إصدارات رئيسية، كل إصدار "
    "يضيف طبقة جديدة من الذكاء والاستقلالية والقدرات."
)
pdf.body(
    "كل إصدار هو منتج منعزل بذاته، يحتوي على محرك أساسي مجمد، واجهة مستخدم مستقلة مبنية "
    "بإطار Tauri (لتطبيقات سطح المكتب عبر المنصات)، مجموعة اختبارات مخصصة، إعدادات نشر "
    "وشهادات توقيع رقمية. تضمن هذه البنية التوافق مع الإصدارات السابقة وتسمح بالتطور المستقل "
    "لكل جيل."
)
pdf.ln(3)
pdf.sub_title("الإصدارات الخمسة بنظرة سريعة")
overview = [
    ("R1 — Runtime OS",     "تشغيل المهام، التنسيق بين الوكلاء، بوابة النماذج، المراقبة"),
    ("R2 — Memory OS",      "الذاكرة الهرمية، تجميع السياق، خرائط المعرفة، الاسترجاع طويل المدى"),
    ("R3 — Skill OS",       "استخراج المهارات تلقائياً، تعلم الأنماط، مكتبة مهارات قابلة لإعادة الاستخدام"),
    ("R4 — Cognitive OS",   "التخطيط الاستراتيجي، تحليل الأهداف، التقييم الذاتي، حلقات التفكير"),
    ("R5 — Big EMO AI OS",  "قوة عمل رقمية مستقلة، بناء أدوات ذاتياً، بنية تحتية ذاتية الشفاء"),
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
pdf.section_title("2. R1 — Runtime OS نظام تشغيل التشغيل")
pdf.body(
    "الإصدار الأساسي. يحول Runtime OS نظام EMO AI من برنامج محادثة بسيط إلى منصة تنسيق "
    "وكلاء متعددي المهام على مستوى إنتاجي. يدير الوكلاء والمهام وسير العمل وتوجيه النماذج "
    "عبر البيئات المحلية والموزعة."
)
pdf.ln(2)
pdf.sub_title("القدرات الأساسية")
pdf.bullet("تشغيل متعدد الوكلاء — PlannerAgent، CriticAgent، OptimizerAgent مع آلة حالة للتنسيق (8 حالات، 9 انتقالات)")
pdf.bullet("محرك التنفيذ — مقسم إلى 5 خدمات محددة: المجدول، مخزن الحالة، الموزع، معالج إعادة المحاولة، مدير الترخيص")
pdf.bullet("طبقة التحكم — CompositionRoot مع حقن التبعيات وخدمات المصانع")
pdf.bullet("بوابة النماذج — موجه ذكي لاختيار المزود بناءً على الوزن/زمن الاستجابة/التكلفة، تجاوز تلقائي (<=500ms)، تحديد معدل، تجميع القياسات")
pdf.bullet("المراقبة — مراقبة实时 CPU/الذاكرة/قائمة الانتظار، مستكشف التنفيذ، لوحة تحكم التوجيه")
pdf.bullet("الأمان — تكامل مع keychain نظام التشغيل (macOS/Windows/Linux)، حقن بيانات اعتماد مؤقتة (مسح تلقائي 5 ثوان)، بدون مفاتيح نصية")
pdf.bullet("واجهة المستخدم — غلاف Tauri عبر المنصات مع 7 مسارات حية، نظام تصميم (زجاج)، لوحة أوامر (Ctrl+K)، معالج التشغيل الأول")
pdf.bullet("عقد IPC — بروتوكول منظم (v1.2.0) لكل اتصالات التشغيل مع قواعد توافق مستقبلي صارمة")
pdf.ln(2)
pdf.sub_title("المكونات")
pdf.component_table([
    ("التنسيق بين الوكلاء",        "مكتمل",  "41/41 اختبار، 8 انتقالات G-P1-G-P8"),
    ("محرك التنفيذ",              "مكتمل",  "5 خدمات محددة، 358 اختبار"),
    ("بوابة النماذج",             "مكتمل",  "47/47 اختبار، 8 معايير جودة"),
    ("واجهة المستخدم",             "P1-P4",  "7 مسارات، 130/130 اختبار"),
    ("الحوكمة (RBAC/التدقيق)",    "قيد الانتظار", "مخطط للإغلاق النهائي لـ R1"),
    ("المنصة",                    "macOS",  "هيكل Tauri عبر المنصات جاهز"),
])
pdf.ln(2)
pdf.body(
    "R1 مكتمل بنسبة 75%. العمل المتبقي يشمل الحوكمة (RBAC، مسارات التدقيق، سياسات عزل "
    "المستأجرين) والتكامل الكامل لواجهة المستخدم مع البيانات الحية."
)

# ===================== R2 — MEMORY OS =====================
pdf.add_page()
pdf.section_title("3. R2 — Memory OS نظام تشغيل الذاكرة")
pdf.body(
    "يحول Memory OS نظام EMO من نظام ينفذ المهام إلى نظام يتذكر ويتعلم ويتطور من تاريخه. "
    "يضيف هذا الإصدار طبقات ذاكرة دائمة تمكن اتخاذ القرارات بوعي سياقي والاحتفاظ بالمعرفة "
    "طويلة المدى."
)
pdf.ln(2)
pdf.sub_title("القدرات الأساسية")
pdf.bullet("الذاكرة الهرمية — بنية ذاكرة متعددة المستويات مع عمليات تخزين/استرجاع/تهذيب، محسنة لأكثر من 126 ألف عملية في الثانية")
pdf.bullet("مجمّع السياق — ضغط ذكي للسياق مع ميزانية توكنات والتحقق من السلامة عبر SHA-256")
pdf.bullet("مدير الرسم البياني للمهارات — يسجل وينظم المهارات المستفادة كرسم بياني معرفي قابل للتنقل")
pdf.bullet("آلة حالة الذاكرة — 6 حالات مع 7 انتقالات (G-M1 إلى G-M6)، 0% تسرب بين المستأجرين")
pdf.bullet("مربط التتبع المعرفي — نشر SHA-256 عبر جميع عمليات الذاكرة للتدقيق الكامل")
pdf.ln(2)
pdf.sub_title("المكونات المخطط لها")
pdf.component_table([
    ("ذاكرة المشروع",                "مخطط",   "مساحات ذاكرة معزولة لكل مشروع"),
    ("ذاكرة الوكيل",                 "مخطط",   "سياق تاريخي لكل وكيل"),
    ("الذاكرة طويلة المدى",          "مخطط",   "تخزين دائم مع استرجاع ذكي"),
    ("رسم المعرفة البياني",          "مخطط",   "تمثيل معرفي قائم على الرسوم البيانية"),
    ("ضغط الذاكرة",                  "مخطط",   "تحسين الذاكرة لتقليل التوكنات"),
    ("الفهرسة الدلالية",             "مخطط",   "استرجاع ذكي قائم على السياق"),
    ("إعادة بناء السياق",            "مخطط",   "إعادة بناء السياق من الذاكرة المجزأة"),
])
pdf.ln(2)
pdf.body(
    "R2 مكتمل بنسبة 30% مع 5 مكونات أساسية مبنية بالفعل في core/memory/. "
    "سبعة مكونات إضافية بالإضافة إلى واجهة مستخدم مخصصة لمستكشف الذاكرة مخطط لها."
)

# ===================== R3 — SKILL OS =====================
pdf.add_page()
pdf.section_title("4. R3 — Skill OS نظام تشغيل المهارات")
pdf.body(
    "يحول Skill OS المعرفة والخبرات المتراكمة إلى مهارات قابلة لإعادة الاستخدام والتجميع. "
    "بدلاً من برمجة الحلول يدوياً، يقوم EMO باستخراج الأنماط من التنفيذات السابقة بشكل "
    "تلقائي وبناء مكتبة من المهارات القابلة للنشر."
)
pdf.ln(2)
pdf.sub_title("القدرات الأساسية")
pdf.bullet("استخراج المهارات — تحديد تلقائي للأنماط القابلة لإعادة الاستخدام من تنفيذات المهام الناجحة")
pdf.bullet("تعلم سير العمل — تعلم تسلسلات العمل متعددة الخطوات بمراقبة تسلسلات التنفيذ المتكررة")
pdf.bullet("التعرف على الأنماط — كشف أنماط المشكلة-الحل المتكررة عبر سياقات مختلفة")
pdf.bullet("تعلم استخدام الأدوات — تحليل كيفية استخدام الأدوات وتعميم أنماط استدعائها")
pdf.bullet("مكتبة المهارات — مستودع مفهرس ومرقم للإصدارات من المهارات المستخرجة")
pdf.bullet("ترتيب المهارات — تحديد أولويات المهارات حسب الصلة ومعدل النجاح وتكرار الاستخدام")
pdf.bullet("تطور المهارات — تحديث وتحسين المهارات تلقائياً مع ظهور أنماط جديدة")
pdf.ln(2)
pdf.body(
    "مثال: بعد إصلاح 5 مشكلات React، يستخرج EMO تلقائياً 'مهارة تصحيح React' ويطبقها "
    "بشكل استباقي في مهام React المستقبلية."
)
pdf.ln(2)
pdf.body(
    "R3 لم يبدأ بعد (0%). جميع المكونات السبعة بحاجة إلى البناء من الصفر، بالإضافة إلى "
    "واجهة مستخدم مخصصة لمكتبة المهارات."
)

# ===================== R4 — COGNITIVE OS =====================
pdf.add_page()
pdf.section_title("5. R4 — Cognitive OS نظام تشغيل الإدراك")
pdf.body(
    "يضيف Cognitive OS التفكير الاستراتيجي والتخطيط طويل المدى. يتقدم EMO من تنفيذ المهام "
    "الفردية إلى صياغة استراتيجيات متعددة الخطوات، وتحليل الأهداف المعقدة، وتقييم أدائه "
    "الذاتي، وتكييف منهجه بمرور الوقت."
)
pdf.ln(2)
pdf.sub_title("القدرات الأساسية")
pdf.bullet("التخطيط الاستراتيجي — صياغة استراتيجيات متعددة الخطوات طويلة المدى متوائمة مع الأهداف عالية المستوى")
pdf.bullet("تحليل الأهداف — تقسيم الأهداف المعقدة إلى أهداف فرعية قابلة للإدارة ومنظمة هرمياً")
pdf.bullet("التقييم الذاتي — تقييم نقدي للمخرجات الذاتية وتحديد مجالات التحسين")
pdf.bullet("الاستدلال متعدد الخطوات — تنفيذ سلاسل استدلال مع تحقق وسيط")
pdf.bullet("حلقات التفكير — تحسين الحلول بشكل تكراري من خلال دورات التفكير الذاتي")
pdf.bullet("السياسات التكيفية — تعديل ديناميكي للسلوك بناءً على ردود الفعل البيئية")
pdf.ln(2)
pdf.sub_title("الأصول التأسيسية (من المرحلة G)")
pdf.component_table([
    ("PlannerAgent",     "متاح",   "توليف DAG، منع التذبذب"),
    ("CriticAgent",      "متاح",   "تقييم الخطة، التحقق من النطاق"),
    ("OptimizerAgent",   "متاح",   "تحسين التكلفة العشرية"),
    ("آلة الحالة",       "متاح",   "8 حالات، 9 انتقالات، G-P1-G-P8"),
])
pdf.ln(2)
pdf.body(
    "R4 مكتمل بنسبة 20%. وكلاء Planner/Critic/Optimizer من المرحلة G يوفرون قدرات إدراكية "
    "على مستوى المهام. يوسع R4 هذه القدرات إلى الإدراك الاستراتيجي طويل المدى مع 6 مكونات "
    "إضافية ولوحة تحكم استراتيجية."
)

# ===================== R5 — BIG EMO AI OS =====================
pdf.add_page()
pdf.section_title("6. R5 — Big EMO AI OS نظام تشغيل الذكاء الكامل")
pdf.body(
    "الإصدار النهائي. Big EMO AI OS هو منصة قوة عمل رقمية مستقلة بالكامل. يبني أدواته "
    "بنفسه، ويتعلم دون تدخل بشري، ويحصّن حدوده، ويعمل عبر macOS وWindows وLinux وAndroid "
    "بطبقة ذكاء موحدة."
)
pdf.ln(2)
pdf.sub_title("القدرات الأساسية")
pdf.bullet("فرق وكلاء متخصصة — تشكيل ديناميكي لفرق وكلاء محسَّنة لأنواع مشاريع محددة")
pdf.bullet("تنفيذ مشاريع مستقل — إدارة مشاريع شاملة من المتطلبات إلى التسليم")
pdf.bullet("تعلم عبر المشاريع — نقل المعرفة والأنماط عبر مشاريع غير مرتبطة")
pdf.bullet("ذاكرة مؤسسية — ذاكرة على مستوى المؤسسة مع تحكم في الوصول قائم على الأدوار")
pdf.bullet("سوق المهارات — نظام بيئي لمشاركة وتقييم واكتشاف مهارات المجتمع")
pdf.bullet("ذكاء على مستوى المؤسسة — تعلم ديناميكيات الفريق ومعايير البرمجة والأنماط التنظيمية")
pdf.bullet("تشغيل ذاتي التحسين — تحسين تلقائي لخط أنابيب التنفيذ الخاص به")
pdf.bullet("بناء أدوات ذاتي — توليد أدوات جديدة عند الحاجة لحل مشكلات جديدة")
pdf.bullet("بنية تحتية ذاتية الشفاء — كشف وإصلاح مشكلات التشغيل دون تدخل بشري")
pdf.bullet("أمن ذاتي التحصين — تكيف مستمر للوضع الأمني مع التهديدات الناشئة")
pdf.ln(2)
pdf.body(
    "R5 لم يبدأ بعد (0%) مع 10+ مكونات بحاجة للبناء. يمثل هذا الإصدار تتويجاً لرؤية EMO AI: "
    "نظام تشغيل ذكاء اصطناعي مستقل بالكامل يبني ويتعلم ويحمي نفسه."
)

# ===================== PLATFORM SUPPORT =====================
pdf.add_page()
pdf.section_title("7. مصفوفة دعم المنصات")
pdf.ln(2)
pdf.sub_title("دعم سطح المكتب والجوال لكل إصدار")
pdf.ln(1)
headers = [ar("الإصدار"), ar("macOS"), ar("Windows"), ar("Linux"), ar("Android")]
col_w = [50, 30, 30, 30, 30]
pdf.set_font("Unicode", "B", 9.5)
pdf.set_fill_color(139, 92, 246)
pdf.set_text_color(255, 255, 255)
for i, h in enumerate(headers):
    pdf.cell(col_w[i], 8, h, border=1, fill=True, align="C")
pdf.ln()

rows = [
    [ar("R1 Runtime OS"),     ar("نعم (Tauri)"), ar("نعم (Tauri)"),   ar("نعم (Tauri)"),   ar("لا")],
    [ar("R2 Memory OS"),      ar("مخطط"),        ar("مخطط"),           ar("مخطط"),           ar("مخطط")],
    [ar("R3 Skill OS"),       ar("مخطط"),        ar("مخطط"),           ar("مخطط"),           ar("مخطط")],
    [ar("R4 Cognitive OS"),   ar("مخطط"),        ar("مخطط"),           ar("مخطط"),           ar("مخطط")],
    [ar("R5 Big EMO AI OS"),  ar("نعم"),         ar("نعم"),            ar("نعم"),            ar("نعم")],
]
pdf.set_font("Unicode", "", 9.5)
pdf.set_text_color(40, 40, 40)
for row in rows:
    for i, cell in enumerate(row):
        pdf.cell(col_w[i], 7, cell, border=1, align="C")
    pdf.ln()

pdf.ln(5)
pdf.body(
    "إطار Tauri v2 يوفر دعماً أصلياً عبر المنصات لنظام التشغيل macOS وWindows وLinux. "
    "دعم Android يتطلب تكوين Tauri Mobile أو Capacitor إضافي، مخطط له من R2 فصاعداً."
)

# ===================== SUMMARY =====================
pdf.add_page()
pdf.section_title("8. ملخص والرؤية المستقبلية")
pdf.body(
    "خريطة الإصدارات الخمسة لـ EMO AI ترسم تطوراً واضحاً من محرك تنفيذ مهام إلى قوة عاملة "
    "رقمية مستقلة بالكامل. كل إصدار يبني على سابقه مع البقاء منتجاً مستقلاً ومكتفياً بذاته."
)
pdf.ln(3)
pdf.sub_title("ملخص الإصدارات")
pdf.ln(1)
sum_headers = [ar("الإصدار"), ar("الحالة"), ar("الاختبارات"), ar("المكونات")]
sum_col_w = [48, 30, 30, 82]
pdf.set_font("Unicode", "B", 9.5)
pdf.set_fill_color(139, 92, 246)
pdf.set_text_color(255, 255, 255)
for i, h in enumerate(sum_headers):
    pdf.cell(sum_col_w[i], 8, h, border=1, fill=True, align="C")
pdf.ln()

rows_data = [
    ("R1 Runtime OS",      "75% مكتمل",     "3047+",   "وكلاء متعددون، تنفيذ، بوابة، مراقبة، أمان، واجهة مستخدم"),
    ("R2 Memory OS",       "30% مكتمل",     "25+",     "ذاكرة هرمية، مجمّع سياق، رسم مهارات، آلة حالة"),
    ("R3 Skill OS",        "0% لم يبدأ",    "0",       "استخراج، تعلم، تعرف، مكتبة، ترتيب، تطوّر"),
    ("R4 Cognitive OS",    "20% أساسي",     "41+",     "تخطيط استراتيجي، تحليل أهداف، تقييم ذاتي، تفكير"),
    ("R5 Big EMO AI OS",   "0% لم يبدأ",    "0",       "فرق مستقلة، بناء ذاتي، شفاء ذاتي، ذاكرة مؤسسية"),
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
pdf.sub_title("الرؤية")
pdf.body(
    "يمثل Big EMO AI OS الشكل النهائي: نظام تشغيل ذكاء اصطناعي يبني أدواته بنفسه، ويتعلم "
    "من تاريخه دون تدخل بشري، ويُحصّن حدوده، ويعمل بسلاسة عبر منصات سطح المكتب والجوال. "
    "كل إصدار يُقرّبنا من هذه الرؤية، مُقدّماً قيمة ملموسة في كل خطوة مع الحفاظ على التوافق "
    "الكامل مع الإصدارات السابقة وسلامة المنتج المستقلة."
)
pdf.ln(5)
pdf.sub_title("الهيكل المستهدف")
pdf.code_block(
    "releases/\n"
    "  runtime-os/       (R1)  محرك مجمد + واجهة Tauri + نشر\n"
    "  memory-os/        (R2)  محرك مجمد + واجهة ذاكرة + نشر\n"
    "  skill-os/         (R3)  محرك مجمد + واجهة مهارات + نشر\n"
    "  cognitive-os/     (R4)  محرك مجمد + واجهة إدراك + نشر\n"
    "  big-emo/          (R5)  محرك مجمد + واجهة قوة عمل + جوال"
)

# ===================== CREDITS =====================
pdf.ln(10)
pdf.set_draw_color(139, 92, 246)
pdf.line(50, pdf.get_y(), 160, pdf.get_y())
pdf.ln(8)
pdf.set_font("Unicode", "B", 16)
pdf.set_text_color(139, 92, 246)
pdf.cell(0, 10, ar("حقوق الملكية الفكرية"), align="C", new_x="LMARGIN", new_y="NEXT")
pdf.ln(3)
pdf.set_font("Unicode", "", 10)
pdf.set_text_color(100, 100, 120)
pdf.multi_cell(0, 6,
    ar("جميع حقوق الملكية الفكرية، بما في ذلك على سبيل المثال لا الحصر حقوق النشر والعلامات "
       "التجارية وبراءات الاختراع، في نظام EMO AI وشفرة مصدره وهندسته المعمارية وتصميمه "
       "ووثائقه وأي مواد مرتبطة به، مملوكة حصرياً للمهندس إمام عبدالعزيز. يُحظر النسخ أو "
       "التوزيع أو التعديل أو الاستخدام التجاري غير المصرح به دون موافقة خطية مسبقة."),
    align="C"
)
pdf.ln(5)
pdf.set_font("Unicode", "B", 14)
pdf.set_text_color(139, 92, 246)
pdf.cell(0, 8, ar("المهندس إمام عبدالعزيز"), align="C", new_x="LMARGIN", new_y="NEXT")
pdf.set_font("Unicode", "", 10)
pdf.set_text_color(100, 100, 120)
pdf.cell(0, 7, ar("مهندس النظام والمطور الرئيسي"), align="C", new_x="LMARGIN", new_y="NEXT")
pdf.ln(5)
pdf.set_font("Unicode", "", 9)
pdf.set_text_color(140, 140, 140)
pdf.cell(0, 6, "2026", align="C", new_x="LMARGIN", new_y="NEXT")

pdf.output(OUTPUT_PATH)
print(f"PDF generated: {OUTPUT_PATH}")
print(f"Size: {os.path.getsize(OUTPUT_PATH):,} bytes")
print(f"Pages: {pdf.page_no()}")
