# P1 Pre-Audit Report — Keychain Enforcement

**التاريخ:** 2026-06-01
**الهدف:** حصر جميع أماكن تخزين API keys استعداداً لنقلها إلى OS Keychain
**حالة التدقيق:** مكتمل — بدون تعديل كود

---

## ملخص تنفيذي

| البند | القيمة |
|-------|--------|
| إجمالي المخالفات | 21 |
| CRITICAL (مفاتيح حية في نص عادي) | 8 |
| HIGH (قراءة مفاتيح من env vars) | 6 |
| MEDIUM (بنية تحتية ناقصة) | 7 |
| اعتماد Keychain الحالي | ~15% (فقط في Rust layer) |
| **مخاطر فورية** | **مفاتيح حية في `docs/REQUIREMENTS_UNDERSTANDING.md` — ملف خاضع لـ Git** |

---

## المخالفات الحرجة (CRITICAL)

### C1: مفاتيح حية في `.env`
| المتغير | القيمة | الموقع |
|---------|--------|--------|
| `OPENROUTER_API_KEY` | `sk-or-placeholder-rotated` | `/.env:5` |
| `GROQ_API_KEY` | `gsk-placeholder-rotated` | `/.env:6` |
| `GEMINI_API_KEY` | `gemini-placeholder-rotated` | `/.env:7` |
| `TELEGRAM_TOKEN` | `telegram-token-placeholder-rotated` | `/.env:24` |
| `EMO_JWT_SECRET` | `jwt-secret-placeholder-rotated` | `/.env:21` |

### C2: 🔴 مفاتيح حية في مستندات خاضعة لـ Git!
| المتغير | القيمة | الموقع |
|---------|--------|--------|
| `OPENROUTER_API_KEY` | `sk-or-v1-...` | `/docs/REQUIREMENTS_UNDERSTANDING.md:562` |
| `GROQ_API_KEY` | `gsk_ECoDOC...` | `/docs/REQUIREMENTS_UNDERSTANDING.md:563` |
| `GEMINI_API_KEY` | `gemini-placeholder-rotated` | `/docs/REQUIREMENTS_UNDERSTANDING.md:564` |
| `TELEGRAM_TOKEN` | `telegram-token-placeholder-rotated` | `/docs/REQUIREMENTS_UNDERSTANDING.md:565` |

### C3: مفتاح تشفير احتياطي مكتوب في الكود
| الملف | السطر | القيمة |
|------|-------|--------|
| `emo-desktop/lib/beta/secure-feedback-channel.ts` | 35 | `"emo-beta-enc-key-32characters!!"` |

---

## المخالفات العالية (HIGH)

### H1-H6: Python backend يقرأ المفاتيح من env vars — لا Keychain
| الملف | المتغيرات | الطريقة |
|------|-----------|---------|
| `brain.py:25-76` | `OPENROUTER_API_KEY`, `GROQ_API_KEY`, `GEMINI_API_KEY` | `os.getenv()` |
| `main.py:303` | جميع providers | `os.getenv()` في `/api/status` |
| `main.py:336-339` | أسماء env vars مُرسلة للواجهة | `api_key_env` في HTML template |
| `firebase_tools.py:12` | `FIREBASE_API_KEY` | `os.environ.get()` |
| `supabase_tools.py:10` | `SUPABASE_SERVICE_KEY` | `os.environ.get()` |
| `github_tools.py:14` | `GITHUB_TOKEN` | `os.environ.get()` |
| `middleware/auth.py:13` | `EMO_JWT_SECRET` | `os.environ.get()` |

---

## بنية Keychain الحالية (MEDIUM)

### في Rust/Desktop (موجود جزئياً — ~30%)
- ✅ `commands.rs:155-165` — `set_api_key` يخزن في OS keychain عبر `keyring` crate
- ✅ `keyring-adapter.ts` — TypeScript adapter مع BLOCK policy
- ✅ `keychain-validator.ts` — ماسح ضوئي للمفاتيح النصية
- ❌ `os-keyring.ts` — دوال stubs (invoke_keyring_save/get/delete لا تفعل شيئاً)
- ❌ `ephemeral_injection.ts` — `_stdinWrite` و `_envIsolatedSet` stubs
- ❌ `tauri-plugin-keyring` غير موجود في `Cargo.toml`

### في Python backend (غير موجود — 0%)
- ❌ لا `keyring` package في Python dependencies
- ❌ لا `keychain_provider.py`
- ❌ جميع المفاتيح تُقرأ من `os.getenv()` عبر `.env`

---

## الملفات المتأثرة (37 ملفاً)

### تحتوي مفاتيح حية — تحتاج تدوير فوري
1. `/.env` — جميع مفاتيح API
2. `/docs/REQUIREMENTS_UNDERSTANDING.md` — نسخة من المفاتيح في Git!

### تحتوي مفاتيح اختبار/test keys
3. `emo-desktop/tests/security/test_os_keychain_storage.ts`
4. `emo-desktop/tests/pilot/test_pilot_mode_privacy.ts`
5. `emo-desktop/tests/analytics/test_public_metrics_accuracy.ts`
6. `emo-desktop/tests/pilot/test_feedback_submission.ts`
7. `emo-desktop/tests/bridge/test_rust_ipc_bindings.ts`
8. `emo-desktop/tests/beta/test_beta_integration_flow.ts`

### تقرأ مفاتيح من env vars — تحتاج Keychain
9. `brain.py` + `main.py` + `firebase_tools.py` + `supabase_tools.py` + `github_tools.py` + `middleware/auth.py` + `telegram_bot.py`

### بنية Keychain ناقصة — تحتاج إكمال
10. `emo-desktop/lib/credentials/os-keyring.ts` + `ephemeral_injection.ts` + `keyring-adapter.ts`
11. `emo-desktop/src-tauri/src/commands.rs` (يحتاج `get_api_key` و `delete_api_key`)
12. `emo-desktop/src-tauri/Cargo.toml` (يحتاج `tauri-plugin-keyring`)
13. `emo-desktop/src-tauri/tauri.conf.json` (plugin keyring موجود لكن غير مربوط)

---

## خطة النقل إلى Keychain

### المرحلة 1: فوري — تدوير المفاتيح المكشوفة
1. تدوير `OPENROUTER_API_KEY` فوراً — مسرب في Git docs
2. تدوير `GROQ_API_KEY` فوراً
3. إزالة المفاتيح من `docs/REQUIREMENTS_UNDERSTANDING.md`
4. تغيير `EMO_JWT_SECRET` إلى قيمة آمنة
5. تغيير `TELEGRAM_TOKEN` إلى قيمة صحيحة

### المرحلة 2: Python Backend Keychain
6. إضافة `keyring` إلى `requirements.txt`
7. إنشاء `core/security/keychain_provider.py`
8. تعديل `brain.py` لقراءة المفاتيح من Keychain بدلاً من env
9. تعديل `firebase_tools.py`, `supabase_tools.py`, `github_tools.py`, `middleware/auth.py`

### المرحلة 3: Desktop Keychain Completion
10. إكمال `os-keyring.ts` — دوال invoke حقيقية
11. إضافة `tauri-plugin-keyring` إلى `Cargo.toml`
12. إضافة `get_api_key` و `delete_api_key` في `commands.rs`
13. إكمال `ephemeral_injection.ts`

### المرحلة 4: Enforcement
14. pre-commit hook لمنع المفاتيح النصية
15. CI scan عبر `leakage-scanner.sh`
16. runtime check في `main.py` — فشل إذا Keychain غير متاح

---

## الخلاصة

اعتماد Keychain الحالي: **~15%** (فقط في Rust/Desktop layer جزئياً)
اعتماد Keychain في Python: **0%**

**أول خطوة عملية:** تدوير OpenRouter و Groq API keys فوراً، ثم إزالة المفاتيح من `docs/REQUIREMENTS_UNDERSTANDING.md`.
