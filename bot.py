import telebot, requests, io, pypdf, re, time, queue, os
from flask import Flask
from threading import Thread
from telebot import types

# ==============================
# ⚙️ SUNUCU VE AYARLAR (KORUNDU)
# ==============================
app = Flask('')
@app.route('/')
def home(): return f"Bot Aktif! {time.strftime('%H:%M:%S')}"

def run_web():
    try:
        port = int(os.environ.get('PORT', 7860))
        app.run(host='0.0.0.0', port=port)
    except: pass

def keep_alive():
    while True:
        try:
            port = os.environ.get('PORT', '7860')
            requests.get(f"http://127.0.0.1:{port}/", timeout=5)
        except: pass
        time.sleep(15)

# 🔑 GÜNCEL API AYARLARI
API_TOKEN = "8637392837:AAHnXyyKcSfe8Mic4kePRuQz80iMiruRcBI"
PIXELDRAIN_API_KEY = "df660474-7351-4307-a661-a5657f2ebfc12"

bot = telebot.TeleBot(API_TOKEN, threaded=True, num_threads=25)
task_queue = queue.Queue()

# ==============================
# 🧠 v32 ANALİZ MOTORU (DOKUNULMADI)
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
    t = re.sub(r'(SAYIN|ALACAKLI|GÖNDEREN|ALICI HESAP|ALICI|MÜŞTERİ|ÜNVANI|ALACAKLI ADI SOYADI|ADI SOYADI|AD SOYAD|ADI|ALICI ADI SOYADI)\s*[:]*', '', metin.upper())
    t = CLEAN_RE.sub(' ', re.sub(r'\d+', '', t))
    parcalar = [x for x in t.split() if x not in YASAKLI and len(x) > 1]
    if any(k in t for k in ["ŞUBE","MÜDÜRLÜĞÜ","VALÖR","A.Ş.","BANKASI"]): return None
    if len(parcalar) >= 2: return " ".join(parcalar[:3])
    return None

def tutar_bul_final(full_text):
    patterns = [r'(?:TL|TUTARI|TUTAR|Tutar)\s*[:]*\s*([\d.,]{4,20})', r'B\s+TL\s+([\d.,]{4,20})', r'İŞLEM TUTARI\s*\(TL\)\s*:\s*([\d.,]{4,20})', r'Havale Tutarı\s*:\s*([\d.,]{4,20})', r'Tutar\s*([\d.,]{4,20})\s*TL', r'İşlem Tutarı\s*:\s*([\d.,]{4,20})', r'EFT TUTARI\s*:\s*([\d.,]{4,20})']
    for p in patterns:
        m = re.findall(p, full_text, re.IGNORECASE)
        for val_str in m:
            val = parse_number(val_str)
            if val and 5 < val < 10000000:
                return "{:,.2f}".format(val).replace(',', 'X').replace('.', ',').replace('X', '.') + " TRY"
    return "Bulunamadı"

def analiz_et_v32(file_bytes):
    try:
        pdf = pypdf.PdfReader(io.BytesIO(file_bytes))
        txt = ""
        for page in pdf.pages: txt += page.extract_text() + "\n"
        lns = [l.strip() for l in txt.split('\n') if l.strip()]
        g, a = "Bilinmiyor", "Bilinmiyor"
        for i, l in enumerate(lns):
            l_up = l.upper()
            if "ADI SOYADI" in l_up and i < 10:
                res = ismi_temizle(l_up); 
                if res: g = res
            if "GÖNDEREN:" in l_up:
                res = ismi_temizle(l_up.split("GÖNDEREN:")[1].split("AÇIKLAMA:")[0].strip())
                if res: g = res
            if any(k in l_up for k in ["ALICI ADI SOYADI", "ALICI HESAP", "ALICI:", "ALICI ÜNVANI"]):
                res = ismi_temizle(l_up)
                if "ALICI ÜNVANI:" in l_up and (not res or len(res.split()) < 2):
                    res = ismi_temizle(l_up.split("ALICI ÜNVANI:")[1].split("ALICI IBAN")[0].strip())
                if (not res or len(res.split()) < 2) and i+1 < len(lns): res = ismi_temizle(lns[i+1])
                if res: a = res
            if "ALACAKLI ADI SOYADI" in l_up and ":" in l_up:
                res = ismi_temizle(l_up.split(":")[1].strip())
                if res: a = res
            if "SAYIN" in l_up and g == "Bilinmiyor":
                comb = l_up.replace("SAYIN", "").strip()
                if i+1 < len(lns): comb += " " + lns[i+1].upper()
                res = ismi_temizle(comb)
                if res: g = res
        return g, a, tutar_bul_final(txt)
    except: return "Hata","Hata","Bulunamadı"

# ==============================
# ☁️ BULUT YÜKLEME (DÜZELTİLDİ)
# ==============================
def dosya_yukle_yedekli(raw_file, uzanti):
    fn = f"is_f_{int(time.time())}{uzanti}"
    
    # --- 1. DURAK: PIXELDRAIN ---
    try:
        # io.BytesIO(raw_file) ile her seferinde veriyi sıfırdan okutuyoruz
        r = requests.post(
            "https://pixeldrain.com/api/file", 
            auth=("", PIXELDRAIN_API_KEY), 
            files={"file": (fn, io.BytesIO(raw_file))}, 
            timeout=5
        )
        if r.status_code in [200, 201]:
            d = r.json()
            if d.get("id"): return f"https://pixeldrain.com/api/file/{d.get('id')}"
    except:
        pass

    # --- 2. DURAK: CATBOX (Yedek) ---
    try:
        # Pixeldrain patlarsa, taze veriyle burası devreye girer
        r_c = requests.post(
            "https://catbox.moe/user/api.php", 
            data={"reqtype": "fileupload"}, 
            files={"fileToUpload": (fn, io.BytesIO(raw_file))}, 
            timeout=10
        )
        if r_c.status_code == 200:
            return r_c.text.strip()
    except:
        pass
        
    return None

# ==============================
# ⚙️ İŞLEM YÖNETİCİSİ (KORUNDU)
# ==============================
def islem_yap(message):
    waiting = None
    try:
        waiting = bot.reply_to(message, "⌛")
        file_id = message.photo[-1].file_id if message.content_type == 'photo' else message.document.file_id
        is_pdf = message.content_type == 'document' and message.document.file_name.lower().endswith(".pdf")
        
        file_info = bot.get_file(file_id)
        raw = bot.download_file(file_info.file_path)
        
        g, a, t = ("Görsel", "Görsel", "Yok") if not is_pdf else analiz_et_v32(raw)
        link = dosya_yukle_yedekli(raw, ".pdf" if is_pdf else ".jpg")

        markup = types.InlineKeyboardMarkup()
        if link: markup.add(types.InlineKeyboardButton("👁‍🗨 Görüntüle", url=link))

        if is_pdf:
            msg = (f"🏦 **ONAY ✅**\n━━━━━━━━━━━━━━━━━━━━\n"
                   f"👤 **G:** `{g}`\n👤 **A:** `{a}`\n💰 **T:** `{t}`\n"
                   f"━━━━━━━━━━━━━━━━━━━━\n📋 **Kopyala:** `{link if link else 'Link Alınamadı'}`")
        else:
            msg = f"📸 **Görsel Linki ✅**\n\n📋 `{link if link else 'Link Alınamadı'}`"

        bot.edit_message_text(msg, message.chat.id, waiting.message_id, parse_mode="Markdown", reply_markup=markup)
    except:
        if waiting:
            try: bot.delete_message(message.chat.id, waiting.message_id)
            except: pass

def worker():
    while True:
        try:
            m = task_queue.get()
            islem_yap(m)
            task_queue.task_done()
        except:
            time.sleep(1)

@bot.message_handler(content_types=['photo','document'])
def handle(m):
    task_queue.put(m)

# ==============================
# 🚀 BAŞLATICI (KORUNDU)
# ==============================
if __name__ == "__main__":
    try: bot.delete_webhook()
    except: pass
    
    Thread(target=run_web, daemon=True).start()
    Thread(target=keep_alive, daemon=True).start()
    
    for _ in range(3):
        Thread(target=worker, daemon=True).start()
    
    while True:
        try:
            bot.infinity_polling(
                timeout=20, 
                long_polling_timeout=15, 
                logger_level=1, 
                skip_pending=True # Eski mesajları atlama koruması
            )
        except Exception as e:
            time.sleep(5)
    
