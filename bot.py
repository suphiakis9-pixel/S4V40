import telebot
import requests
import io
import pypdf
import re
import time
import logging
from concurrent.futures import ThreadPoolExecutor
from flask import Flask
from threading import Thread
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# Loglama
logging.basicConfig(level=logging.INFO)

# ==============================
# ⚙️ CANLI TUTMA SİSTEMİ
# ==============================
app = Flask('')

@app.route('/')
def home():
    return "Bot Aktif!"

def run_web():
    try:
        import os
        port = int(os.environ.get("PORT", 5000))
        app.run(host='0.0.0.0', port=port, threaded=True)
    except: pass

def self_ping():
    time.sleep(30)
    while True:
        try:
            requests.get("https://s4v40.onrender.com/", timeout=10)
        except: pass
        time.sleep(120)

def keep_alive():
    Thread(target=run_web, daemon=True).start()
    Thread(target=self_ping, daemon=True).start()

# ==============================
# ⚙️ AYARLAR
# ==============================
API_TOKEN = "8738306341:AAEdLn9E5L7LpdvPQpwRYvcp4w6lwsVCHH4"
bot = telebot.TeleBot(API_TOKEN, threaded=True, num_threads=40)
executor = ThreadPoolExecutor(max_workers=20)

CLEAN_RE = re.compile(r'[^A-ZÇĞİÖŞÜ ]')
YASAKLI = {"ALICI", "HESAP", "GÖNDEREN", "SAYIN", "HESABI", "ÜNVANI", "UNVANI", "LEHTAR", "MÜŞTERİ", "İSİM", "AD", "SOYAD", "TR", "AÇIKLAMA", "BİREYSEL", "ÖDEME", "MASRAF", "KOMİSYON", "ÜCRET", "VERGİ", "DAİRESİ", "NO", "TCKN", "VKN", "ADRESİ", "ŞUBE", "VADESİZ", "TUTARI", "IBAN", "KART", "PARA", "CİNSİ", "FİŞ", "BANK", "BANKASI", "A.Ş", "ELEKTRONİK", "HİZMETLERİ", "AŞ", "MÜDÜRLÜĞÜ", "FAİZ", "VERGİSİ", "ALACAKLI", "ADİ", "SOYADI", "BORÇLU", "İŞLEM", "YALNIZ", "TUTAR", "EFT", "HAVALE", "MERKEZİ", "ŞUBESİ", "ADI", "İSTANBUL", "ANKARA", "İZMİR", "BURSA", "ANTALYA", "KONYA", "ADANA", "GAZİANTEP", "ŞANLIURFA", "KOCAELİ", "MERSİN", "DİYARBAKIR", "HATAY", "MARDİN"}

# ==============================
# 🛠 FONKSİYONLAR
# ==============================
def parse_number(text):
    if not text: return None
    text = re.sub(r'[^0-9,.]', '', text.replace(" ", ""))
    if "," in text and "." not in text: text = text.replace(",", "")
    elif "." in text and "," not in text: text = text.replace(".", "")
    elif "," in text and "." in text:
        if text.find(",") < text.find("."): text = text.replace(",", "")
        else: text = text.replace(".", "").replace(",", ".")
    try: return float(text)
    except: return None

def ismi_temizle(metin):
    if not metin: return None
    t = re.sub(r'(SAYIN|ALACAKLI|GÖNDEREN|ALICI|MÜŞTERİ|ÜNVANI|ALACAKLI ADI SOYADI|ADI SOYADI|AD SOYAD|ADI)\s*[:]*', '', metin.upper())
    t = CLEAN_RE.sub(' ', re.sub(r'\d+', '', t))
    p = [x for x in t.split() if x not in YASAKLI and len(x) > 1]
    if any(k in t for k in ["ŞUBE", "MÜDÜRLÜĞÜ", "VALÖR", "A.Ş.", "BANKASI"]): return None
    return " ".join(p[:3]) if len(p) >= 2 else None

def tutar_bul_final(full_text):
    patterns = [r'(?:TL|TUTARI|TUTAR|Tutar)\s*[:]*\s*([\d.,]{4,20})', r'B\s+TL\s+([\d.,]{4,20})', r'İŞLEM TUTARI\s*\(TL\)\s*:\s*([\d.,]{4,20})', r'Havale Tutarı\s*:\s*([\d.,]{4,20})']
    for pattern in patterns:
        matches = re.findall(pattern, full_text, re.IGNORECASE)
        for m in matches:
            val = parse_number(m)
            if val and 5 < val < 5000000:
                return "{:,.2f}".format(val).replace(',', 'X').replace('.', ',').replace('X', '.') + " TRY"
    return "Bulunamadı"

def catbox_yukle(raw_file):
    for _ in range(2): # Sadece 2 deneme, botun donmaması için
        try:
            files = {'fileToUpload': (f"dk_{int(time.time())}.pdf", raw_file)}
            res = requests.post("https://catbox.moe/user/api.php", files=files, data={'reqtype': 'fileupload'}, timeout=15)
            if res.status_code == 200 and "https://" in res.text:
                return res.text.strip()
        except: time.sleep(1)
    return "⚠️ Hata"

def analiz_et(file_bytes):
    try:
        pdf = pypdf.PdfReader(io.BytesIO(file_bytes))
        txt = "\n".join([p.extract_text() for p in pdf.pages])
        lns = [l.strip() for l in txt.split('\n') if l.strip()]
        g, a = "Bilinmiyor", "Bilinmiyor"
        for i, l in enumerate(lns):
            l_up = l.upper()
            if any(k in l_up for k in ["SAYIN", "GÖNDEREN"]) and g == "Bilinmiyor":
                res = ismi_temizle(l) or (ismi_temizle(lns[i+1]) if i+1<len(lns) else None)
                if res: g = res
            if any(k in l_up for k in ["ALICI", "LEHTAR"]) and a == "Bilinmiyor":
                res = ismi_temizle(l) or (ismi_temizle(lns[i+1]) if i+1<len(lns) else None)
                if res: a = res
        return g, a, tutar_bul_final(txt)
    except: return "Hata", "Hata", "Bulunamadı"

# ==============================
# 🤖 ANA MANTIK
# ==============================
@bot.message_handler(content_types=['photo', 'document'])
def handle_incoming(message):
    try:
        # 3 dakikadan eski mesajları görmezden gel
        if int(time.time()) - message.date > 180: return

        waiting_msg = bot.reply_to(message, "⏳ **İnceleniyor...**")
        
        file_id = message.photo[-1].file_id if message.content_type == 'photo' else message.document.file_id
        is_pdf = message.content_type == 'document' and message.document.file_name.lower().endswith(".pdf")
        
        file_info = bot.get_file(file_id)
        current_raw_file = bot.download_file(file_info.file_path)
        
        # Link yükleme ve analizi paralel yap
        fut_link = executor.submit(catbox_yukle, current_raw_file)
        
        if is_pdf:
            g, a, t = analiz_et(current_raw_file)
            link = fut_link.result()
            msg = f"🏦 **ONAY ✅**\n━━━━━━━━━━━━━━━━━━━━\n👤 **G:** `{g}`\n👤 **A:** `{a}`\n💰 **T:** `{t}`\n━━━━━━━━━━━━━━━━━━━━\n📋 **Kopyala:** `{link}`"
        else:
            link = fut_link.result()
            msg = f"📸 **Görsel Linki ✅**\n\n📋 `{link}`"

        markup = InlineKeyboardMarkup()
        if "https://" in link: markup.add(InlineKeyboardButton("🌍 Görüntüle", url=link))
        
        bot.edit_message_text(msg, message.chat.id, waiting_msg.message_id, parse_mode="Markdown", reply_markup=markup, disable_web_page_preview=True)
    except Exception as e:
        logging.error(f"Hata: {e}")

if __name__ == "__main__":
    keep_alive()
    while True:
        try: bot.infinity_polling(timeout=90, skip_pending=True)
        except: time.sleep(5)
        
