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

# Loglama ayarı
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

# ==============================
# ⚙️ AYARLAR VE BOT BAŞLATMA
# ==============================
API_TOKEN = "8738306341:AAEdLn9E5L7LpdvPQpwRYvcp4w6lwsVCHH4"
bot = telebot.TeleBot(API_TOKEN, threaded=True, num_threads=40)
# İşlemciyi yormamak için limitli executor
executor = ThreadPoolExecutor(max_workers=10)

CLEAN_RE = re.compile(r'[^A-ZÇĞİÖŞÜ ]')
YASAKLI = {"ALICI", "HESAP", "GÖNDEREN", "SAYIN", "HESABI", "ÜNVANI", "UNVANI", "LEHTAR", "MÜŞTERİ", "İSİM", "AD", "SOYAD", "TR", "AÇIKLAMA", "BİREYSEL", "ÖDEME", "MASRAF", "KOMİSYON", "ÜCRET", "VERGİ", "DAİRESİ", "NO", "TCKN", "VKN", "ADRESİ", "ŞUBE", "VADESİZ", "TUTARI", "IBAN", "KART", "PARA", "CİNSİ", "FİŞ", "BANK", "BANKASI", "A.Ş", "ELEKTRONİK", "HİZMETLERİ", "AŞ", "MÜDÜRLÜĞÜ", "FAİZ", "VERGİSİ", "ALACAKLI", "ADİ", "SOYADI", "BORÇLU", "İŞLEM", "YALNIZ", "TUTAR", "EFT", "HAVALE", "MERKEZİ", "ŞUBESİ", "ADI"}

# ==============================
# 🛠 YARDIMCI FONKSİYONLAR
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

def tutar_bul(full_text):
    patterns = [r'(?:TL|TUTARI|TUTAR|Tutar)\s*[:]*\s*([\d.,]{4,20})', r'B\s+TL\s+([\d.,]{4,20})', r'İŞLEM TUTARI\s*\(TL\)\s*:\s*([\d.,]{4,20})']
    for p in patterns:
        m = re.findall(p, full_text, re.IGNORECASE)
        for val_str in m:
            v = parse_number(val_str)
            if v and 5 < v < 5000000:
                return "{:,.2f}".format(v).replace(',', 'X').replace('.', ',').replace('X', '.') + " TRY"
    return "Bulunamadı"

def catbox_yukle(raw_file):
    """Zaman aşımı çok kısa tutuldu ki bot kilitlenmesin."""
    try:
        files = {'fileToUpload': (f"dk_{int(time.time())}.pdf", raw_file)}
        res = requests.post("https://catbox.moe/user/api.php", files=files, data={'reqtype': 'fileupload'}, timeout=10)
        if res.status_code == 200: return res.text.strip()
    except: pass
    return None

# ==============================
# 🤖 ANA MESAJ İŞLEME
# ==============================
def process_file(message):
    waiting_msg = None
    try:
        waiting_msg = bot.reply_to(message, "⏳ **İnceleniyor...**")
        
        file_id = message.photo[-1].file_id if message.content_type == 'photo' else message.document.file_id
        file_info = bot.get_file(file_id)
        raw_data = bot.download_file(file_info.file_path)
        
        # Link ve analiz işlemleri
        link = catbox_yukle(raw_data)
        
        if message.content_type == 'document' and message.document.file_name.lower().endswith('.pdf'):
            pdf = pypdf.PdfReader(io.BytesIO(raw_data))
            txt = "\n".join([p.extract_text() for p in pdf.pages])
            tutar = tutar_bul(txt)
            final_msg = f"🏦 **ONAY ✅**\n💰 **T:** `{tutar}`\n📋 **Kopyala:** `{link if link else 'Yüklenemedi'}`"
        else:
            final_msg = f"📸 **Görsel Linki ✅**\n\n📋 `{link if link else 'Yüklenemedi'}`"

        bot.edit_message_text(final_msg, message.chat.id, waiting_msg.message_id, parse_mode="Markdown")
    except Exception as e:
        if waiting_msg:
            bot.edit_message_text("⚠️ **İşlem sırasında bir hata oluştu veya süre doldu.**", message.chat.id, waiting_msg.message_id)

@bot.message_handler(content_types=['photo', 'document'])
def handle_docs(message):
    # Mesajı bir thread içinde işle ki botun ana döngüsü bloklanmasın
    executor.submit(process_file, message)

if __name__ == "__main__":
    Thread(target=run_web, daemon=True).start()
    Thread(target=self_ping, daemon=True).start()
    while True:
        try: bot.infinity_polling(timeout=60, skip_pending=True)
        except: time.sleep(5)
        
