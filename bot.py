import telebot
import requests
import io
import pypdf
import re
import time
import logging
import random
from requests.auth import HTTPBasicAuth
from concurrent.futures import ThreadPoolExecutor
from flask import Flask
from threading import Thread
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

logging.basicConfig(level=logging.INFO)

# ==============================
# ⚙️ CANLI TUTMA (KEEP-ALIVE) SİSTEMİ
# ==============================
app = Flask('')

@app.route('/')
def home():
    # UptimeRobot buraya ulaşınca "Bot Aktif!" yazısını görecek ve bot uyanık kalacak.
    return "Bot Aktif!"

def run_web():
    try:
        import os
        port = int(os.environ.get("PORT", 5000))
        app.run(host='0.0.0.0', port=port, threaded=True)
    except Exception as e:
        print(f"Flask Hatası: {e}")

def self_ping():
    """Botun 15 dakikada bir uyumasını engellemek için her 5 dakikada bir ping atar."""
    time.sleep(20)
    while True:
        try:
            # Buradaki linki Render'daki kendi linkinle değiştirirsen daha sağlam olur
            requests.get("http://127.0.0.1:5000/", timeout=5)
        except:
            pass
        time.sleep(300) # 5 dakikada bir

def keep_alive():
    Thread(target=run_web, daemon=True).start()
    Thread(target=self_ping, daemon=True).start()

# ==============================
# ⚙️ AYARLAR (EN GÜNCEL TOKEN)
# ==============================
API_TOKEN = "8738306341:AAEdLn9E5L7LpdvPQpwRYvcp4w6lwsVCHH4"

bot = telebot.TeleBot(API_TOKEN, threaded=True, num_threads=10)
executor = ThreadPoolExecutor(max_workers=5)

CLEAN_RE = re.compile(r'[^A-ZÇĞİÖŞÜ ]')
YASAKLI = {"ALICI", "HESAP", "GÖNDEREN", "SAYIN", "HESABI", "ÜNVANI", "LEHTAR", "MÜŞTERİ", "TR", "IBAN", "BANKASI", "MARDİN", "ARTUKLU", "KIZILTEPE"}

# ==============================
# 🛠 YÜKLEME SERVİSİ (CATBOX)
# ==============================
def catbox_yukle(raw_file):
    """Pixeldrain yerine Catbox kullanır. Key gerektirmez, ücretsizdir."""
    try:
        unique_filename = f"dk_{int(time.time())}.pdf"
        files = {'fileToUpload': (unique_filename, raw_file)}
        data = {'reqtype': 'fileupload'}
        res = requests.post("https://catbox.moe/user/api.php", files=files, data=data, timeout=35)
        
        if res.status_code == 200 and res.text.startswith("https://"):
            return res.text.strip()
        return "ERROR"
    except:
        return "ERROR"

# ==============================
# 🛠 ANALİZ VE PARSING
# ==============================
def parse_number(text):
    if not text: return None
    text = re.sub(r'[^0-9,.]', '', text.replace(" ", ""))
    try:
        if "," in text and "." in text:
            if text.find(",") < text.find("."): text = text.replace(",", "")
            else: text = text.replace(".", "").replace(",", ".")
        return float(text.replace(",", "."))
    except: return None

def ismi_temizle(metin):
    if not metin: return None
    t = CLEAN_RE.sub(' ', metin.upper())
    p = [x for x in t.split() if x not in YASAKLI and len(x) > 1]
    return " ".join(p[:3]) if len(p) >= 2 else None

def analiz_et(file_bytes):
    try:
        with io.BytesIO(file_bytes) as pdf_stream:
            pdf = pypdf.PdfReader(pdf_stream)
            txt = "\n".join([p.extract_text() for p in pdf.pages])
            
            g, a = "Bilinmiyor", "Bilinmiyor"
            lns = [l.strip() for l in txt.split('\n') if l.strip()]
            
            for i, l in enumerate(lns):
                if any(k in l.upper() for k in ["GÖNDEREN", "SAYIN"]) and g == "Bilinmiyor":
                    g = ismi_temizle(l) or (ismi_temizle(lns[i+1]) if i+1 < len(lns) else "Bilinmiyor")
                if any(k in l.upper() for k in ["ALICI", "LEHTAR"]) and a == "Bilinmiyor":
                    a = ismi_temizle(l) or (ismi_temizle(lns[i+1]) if i+1 < len(lns) else "Bilinmiyor")
            
            # Tutar Bulma
            tutar = "Bulunamadı"
            m = re.search(r'(?:TL|TUTAR)\s*[:]*\s*([\d.,]{4,20})', txt, re.I)
            if m:
                val = parse_number(m.group(1))
                if val: tutar = "{:,.2f} TRY".format(val).replace(",", "X").replace(".", ",").replace("X", ".")

            return g, a, tutar
    except: return "Hata", "Hata", "Bulunamadı"

# ==============================
# 🤖 BOT MESAJ YÖNETİMİ
# ==============================
@bot.message_handler(content_types=['photo', 'document'])
def handle_incoming(message):
    waiting_msg = None
    try:
        waiting_msg = bot.reply_to(message, "⏳ **İnceleniyor... (Catbox)**", parse_mode="Markdown")
        
        file_id = message.photo[-1].file_id if message.content_type == 'photo' else message.document.file_id
        is_pdf = message.content_type == 'document' and message.document.file_name.lower().endswith(".pdf")
        
        file_info = bot.get_file(file_id)
        current_raw_file = bot.download_file(file_info.file_path)
        
        link = catbox_yukle(current_raw_file)
        
        if is_pdf:
            g, a, t = analiz_et(current_raw_file)
            msg = f"🏦 **ONAY ✅**\n━━━━━━━━━━━━\n👤 **G:** `{g}`\n👤 **A:** `{a}`\n💰 **T:** `{t}`\n━━━━━━━━━━━━\n📋 **Link:** `{link if link != 'ERROR' else 'Yükleme Başarısız'}`"
        else:
            msg = f"📸 **Görsel ✅**\n\n📋 `{link if link != 'ERROR' else 'Yükleme Başarısız'}`"

        markup = InlineKeyboardMarkup()
        if link != "ERROR":
            markup.add(InlineKeyboardButton("🌍 Görüntüle", url=link))
        
        bot.edit_message_text(msg, chat_id=message.chat.id, message_id=waiting_msg.message_id, 
                              parse_mode="Markdown", reply_markup=markup, disable_web_page_preview=True)
    except Exception as e:
        if waiting_msg: bot.edit_message_text("❌ İşlem hatası.", chat_id=message.chat.id, message_id=waiting_msg.message_id)

def start_bot():
    while True:
        try:
            bot.remove_webhook()
            bot.infinity_polling(timeout=90, skip_pending=True)
        except:
            time.sleep(10)

if __name__ == "__main__":
    keep_alive()
    start_bot()
        
