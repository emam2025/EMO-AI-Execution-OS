# EMO AI — دليل التثبيت
## Installation Guide v1.0

### متطلبات النظام
| المنصة | المتطلبات |
|---|---|
| **macOS** | macOS 13+ (Ventura) |
| **Windows** | Windows 10+ |
| **Linux** | Ubuntu 22.04+ / Fedora 38+ |

### التثبيت

#### macOS
1. حمل ملف `EMO-AI.dmg`
2. افتح DMG → اسحب `EMO AI` إلى مجلد التطبيقات
3. افتح التطبيق من Launchpad
4. إذا ظهر تحذير "Unidentified Developer": اذهب إلى System Settings → Privacy & Security → Open Anyway

#### Windows
1. حمل ملف `EMO-AI-Setup.exe`
2. شغّل المثبّت → اتبع التعليمات
3. افتح EMO AI من Start Menu

#### Linux
1. حمل `EMO-AI.AppImage`
2. `chmod +x EMO-AI.AppImage`
3. `./EMO-AI.AppImage`
   أو: `sudo dpkg -i emo-ai.deb` (إذا كنت تستخدم .deb)

### الإعداد الأول
1. عند أول تشغيل، سيظهر **First Run Wizard**
2. اتبع الخطوات:
   - **Welcome** → ابدأ
   - **Choose AI Mode** → Local / Hybrid / Cloud
   - **Connect Model** → أضف مفتاح API (OpenRouter، OpenAI، إلخ) عبر Keychain
   - **Create Project** → سمِّ مشروعك الأول
   - **Launch** → ابدأ!
3. مبروك! EMO AI جاهز للاستخدام 🎉

### التحديثات
- التطبيق يتحقق من التحديثات تلقائياً عند التشغيل
- يمكنك تفعيل التحديث التلقائي من Settings → Updates

### إلغاء التثبيت
- **macOS**: اسحب `EMO AI` من مجلد التطبيقات إلى المهملات
- **Windows**: Control Panel → Programs → Uninstall
- **Linux**: `sudo apt remove emo-ai` أو احذف AppImage
