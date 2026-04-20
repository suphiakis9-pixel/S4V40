import telebot, requests, io, pypdf, re, time, queue, os
from flask import Flask
from threading import Thread

# ==============================
# ⚙️ SUNUCU (Render Port Ayarı)
# ==============================
app = Flask('')

@app.route('/')
def home():
    return f"Sistem Aktif - {time.strftime('%H:%M:%S')}"

def run_web():
    try:
        # Render'ın verdiği portu otomatik yakalar, yoksa 10000 kullanır
        port = int(os.environ.get('PORT', 10000))
        app.run(host='0.0.0.0', port=port)
    except: pass

# ==============================
# ⚙️ TOKEN VE AYARLAR
# ==============================
API_TOKEN = "8738306341:AAEdLn9E5L7LpdvPQpwRYvcp4w6lwsVCHH4"
PIXEL_KEY = "8e258cec-7a6e-4328-abcd-82096e5ab2f3"

bot = telebot.TeleBot(API_TOKEN, threaded=False)

# ==============================
# 🔥 QUEUE SİSTEMİ (SENİN ORİJİNAL YAPIN)
# ==============================
task_queue = queue.Queue()

def worker():
    while True:
        message = task_queue.get()
        try:
            islem_yap(message)
        except: pass
        finally:
            task_queue.task_done()

# ==============================
# 🧠 v32 ANALİZ MOTORU (BİREBİR KORUNDU)
# ==============================
CLEAN_RE = re.compile(r'[^A-ZÇĞİÖŞÜ ]')
YASAKLI = {"ALICI","HESAP","GÖNDEREN","SAYIN","HESABI","ÜNVANI","UNVANI","LEHTAR","MÜŞTERİ","İSİM","AD","SOYAD","TR","AÇIKLAMA","BİREYSEL","ÖDEME","MASRAF","KOMİSYON","ÜCRET","VERGİ","DAİRESİ","NO","TCKN","VKN","ADRESİ","ŞUBE","VADESİZ","TUTARI","IBAN","KART","KARTI","KARTINIZDAN","PARA","CİNSİ","FİŞ","BANK","BANKASI","A.Ş","ELEKTRONİK","HİZMETLERİ","AŞ","MÜDÜRLÜĞÜ","FAİZ","VERGİSİ","ALACAKLI","ADİ","SOYADI","BORÇLU","İŞLEM","YALNIZ","TUTAR","EFT","HAVALE","MERKEZİ","ŞUBESİ","ADI","AŞAĞIDAKİ","TC","KİMLİK","NUMARASI","FAST","DEKONT"}

def parse_number(text):
    if not text: return None
    text = re.sub(r'[^0-9,.]', '', text.replace(" ", ""))
    if text.count(",") > 0 and text.count(".") == 0: text = text.replace(",", "")
    elif text.count(".") > 0 and text.count(",") == 0: text = text.replace(".", "")
    elif text.count(",") > 0 and text.count(".") > 0:
        if text.find(",") < text.find("."): text = text.replace(",", "")
        else: text = text.replace(".", "").replace(",", ".")
    try: return float(text)
    except: return None

def ismi_temizle(metin):
    if not metin: return None
    t = re.sub(r'(SAYIN|ALACAKLI|GÖNDEREN|ALICI|MÜŞTERİ|ÜNVANI|ALACAKLI ADI SOYADI|ADI SOYADI|AD SOYAD|ADI)\s*[:]*', '', metin.upper())
    t = CLEAN_RE.sub(' ', re.sub(r'\d+', '', t))
    parcalar = [x for x in t.split() if x not in YASAKLI and len(x) > 1]
    if any(k in t for k in ["ŞUBE","MÜDÜRLÜĞÜ","VALÖR","A.Ş.","BANKASI"]): return None
    if len(parcalar) >= 2: return " ".join(parcalar[:3])
    return None

def tutar_bul_final(full_text):
    patterns = [r'(?:TL|TUTARI|TUTAR|Tutar)\s*[:]*\s*([\d.,]{4,20})', r'B\s+TL\s+([\d.,]{4,20})', r'İŞLEM TUTARI\s*\(TL\)\s*:\s*([\d.,]{4,20})', r'Havale Tutarı\s*:\s*([\d.,]{4,20})']
    for pattern in patterns:
        matches = re.findall(pattern, full_text, re.IGNORECASE)
        for m in matches:
            val = parse_number(m)
            if val and 5 < val < 10000000:
                return "{:,.2f}".format(val).replace(',', 'X').replace('.', ',').replace('X', '.') + " TRY"
    return "Bulunamadı"

def analiz_et_v32(file_bytes):
    try:
        pdf = pypdf.PdfReader(io.BytesIO(file_bytes))
        txt = "".join([page.extract_text() + "\n" for page in pdf.pages])
        lns = [l.strip() for l in txt.split('\n') if l.strip()]
        g, a = "Bilinmiyor", "Bilinmiyor"
        for i, l in enumerate(lns):
            l_up = l.upper()
            if "GÖNDEREN:" in l_up:
                res = ismi_temizle(l_up.split("GÖNDEREN:")[1].split("AÇIKLAMA:")[0])
                if res: g = res
            elif "ALICI ÜNVANI:" in l_up:
                res = ismi_temizle(l_up.split("ALICI ÜNVANI:")[1].split("ALICI IBAN:")[0])
                if res: a = res
            if "ALACAKLI ADI SOYADI" in l_up and ":" in l_up:
                res = ismi_temizle(l_up.split(":")[1])
                if res: a = res
        return g, a, tutar_bul_final(txt)
    except: return "Hata","Hata","Bulunamadı"

# ==============================
# 🤖 İŞLEM YAP (ORİJİNAL AKIŞ)
# ==============================
def islem_yap(message):
    try:
        waiting = bot.reply_to(message, "⏳ **İşleniyor...**")
        file_id = message.photo[-1].file_id if message.content_type == 'photo' else message.document.file_id
        is_pdf = message.content_type == 'document' and message.document.file_name.lower().endswith(".pdf")
        
        file_info = bot.get_file(file_id)
        raw = bot.download_file(file_info.file_path)
        
        # Pixeldrain yükleme
        r = requests.post("https://pixeldrain.com/api/file", auth=("", PIXEL_KEY), files={"file": (f"i_{int(time.time())}.{'pdf' if is_pdf else 'jpg'}", raw)}, timeout=15)
        link = f"https://pixeldrain.com/api/file/{r.json().get('id')}" if r.status_code in [200,201] else "⚠️ Link Alınamadı"

        if is_pdf:
            g, a, t = analiz_et_v32(raw)
            msg = f"🏦 **ONAY ✅**\n━━━━━━━━━━━━\n👤 **G:** `{g}`\n👤 **A:** `{a}`\n💰 **T:** `{t}`\n━━━━━━━━━━━━\n📋 `{link}`"
        else:
            msg = f"📸 **Görsel Linki ✅**\n\n📋 `{link}`"
            
        bot.edit_message_text(msg, message.chat.id, waiting.message_id, parse_mode="Markdown")
    except: pass

@bot.message_handler(content_types=['photo','document'])
def handle(m): task_queue.put(m)

# ==============================
# 🚀 BAŞLATICI
# ==============================
if __name__ == "__main__":
    # Webhook temizliği
    requests.get(f"https://api.telegram.org/bot{API_TOKEN}/deleteWebhook")
    
    # Render'da thread'ler daha rahat çalışır
    Thread(target=run_web, daemon=True).start()
    Thread(target=worker, daemon=True).start()

    print("--- v32 MOTORU RENDER'DA AKTİF ---")
    
    bot.infinity_polling(timeout=30, long_polling_timeout=15)
