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

# Loglama
logging.basicConfig(level=logging.INFO)

app = Flask('')
@app.route('/')
def home(): return "Bot Aktif!"

def run_web():
    app.run(host='0.0.0.0', port=10000)

def keep_alive():
    Thread(target=run_web, daemon=True).start()

# ==============================
# ⚙️ AYARLAR
# ==============================
API_TOKEN = "8595291883:AAF6czvMBcQRKPtb0eljwKUuoK-9zKchKwE"
PIXELDRAIN_KEY = "ffc1f7d6-fd72-4ebf-a8d9-386c36ae4582"

bot = telebot.TeleBot(API_TOKEN, threaded=True, num_threads=40)
executor = ThreadPoolExecutor(max_workers=20)

# Temizlik ve Filtre Listesi
CLEAN_RE = re.compile(r'[^A-ZÇĞİÖŞÜ ]')
YASAKLI = {
    "SAYIN", "ALICI", "GÖNDEREN", "MÜŞTERİ", "ÜNVANI", "ADI", "SOYADI", "İSİM", 
    "HESAP", "TR", "IBAN", "BANK", "BANKASI", "A.Ş", "ŞUBE", "MÜDÜRLÜĞÜ", 
    "TUTAR", "TUTARI", "TARİH", "SAAT", "İŞLEM", "NO", "AÇIKLAMA", "DEKONT",
    "MAKBUZ", "BİREYSEL", "ÖDEME", "EFT", "HAVALE", "FAST", "TÜRKİYE", "VAKIF",
    "ZİRAAT", "GARANTİ", "YAPI", "KREDİ", "AKBANK", "HALKBANK", "DENİZBANK",
    "ENPARA", "QNB", "FİNANSBANK", "MAHALLESİ", "CADDE", "SOKAK", "NO", "DAİRE"
}

def parse_number(text):
    if not text: return None
    t = re.sub(r'[^0-9,.]', '', text.replace(" ", ""))
    if "," in t and "." in t:
        if t.find(",") < t.find("."): t = t.replace(",", "")
        else: t = t.replace(".", "").replace(",", ".")
    elif "," in t: t = t.replace(",", ".")
    try:
        val = float(t)
        return val if 1 < val < 1000000 else None
    except: return None

def isim_ayikla(line):
    if not line: return None
    line = line.upper()
    # Adres veya Şube içeren satırları direkt ele
    if any(x in line for x in ["MAH.", "CAD.", "SOK.", "ŞUBESİ", "MÜDÜRLÜĞÜ", "A.Ş."]):
        return None
        
    t = re.sub(r'(SAYIN|ADI SOYADI|ALICI|GÖNDEREN|ÜNVANI|MÜŞTERİ|ADI)\s*[:]*', '', line)
    t = CLEAN_RE.sub(' ', t).strip()
    parcalar = [p for p in t.split() if p not in YASAKLI and len(p) > 1]
    
    if 2 <= len(parcalar) <= 4:
        return " ".join(parcalar)
    return None

def analiz_v4(file_bytes):
    try:
        with io.BytesIO(file_bytes) as pdf_stream:
            pdf = pypdf.PdfReader(pdf_stream)
            text = ""
            for page in pdf.pages:
                text += page.extract_text() + "\n"
            
            lines = [l.strip() for l in text.split('\n') if len(l.strip()) > 3]
            g, a, t = "Bilinmiyor", "Bilinmiyor", "Bulunamadı"
            
            # Tutar Bulma
            tutar_match = re.findall(r'(?:TUTAR|TL|TOPLAM)\s*[:]*\s*([\d.,]{4,20})', text.upper())
            for m in tutar_match:
                val = parse_number(m)
                if val:
                    t = "{:,.2f} TRY".format(val).replace(",", "X").replace(".", ",").replace("X", ".")
                    break

            # İsim Bulma (Daha agresif tarama)
            for i, line in enumerate(lines):
                up = line.upper()
                # Gönderen için SAYIN veya GÖNDEREN anahtar kelimeleri
                if g == "Bilinmiyor":
                    if "SAYIN" in up or "GÖNDEREN" in up:
                        # Satırın kendisinde veya sonraki 2 satırda isim ara
                        for offset in range(0, 3):
                            if i + offset < len(lines):
                                res = isim_ayikla(lines[i+offset])
                                if res: g = res; break

                # Alıcı için ALICI veya LEHTAR anahtar kelimeleri
                if a == "Bilinmiyor":
                    if any(x in up for x in ["ALICI", "LEHTAR", "IBAN"]):
                        for offset in range(0, 2):
                            if i + offset < len(lines):
                                res = isim_ayikla(lines[i+offset])
                                if res: a = res; break
            
            return g, a, t
    except Exception as e:
        return "Hata", "Hata", "Bulunamadı"

def pixeldrain_yukle(raw_file):
    try:
        name = f"dk_{int(time.time())}.pdf"
        res = requests.post("https://pixeldrain.com/api/file", 
                             files={'file': (name, raw_file)}, 
                             auth=HTTPBasicAuth('', PIXELDRAIN_KEY), timeout=20)
        return f"https://pixeldrain.com/u/{res.json().get('id')}" if res.status_code < 300 else "⚠️ Hata"
    except: return "⚠️ Hata"

@bot.message_handler(content_types=['photo', 'document'])
def handle(message):
    try:
        if int(time.time()) - message.date > 60: return
        
        waiting = bot.reply_to(message, "⏳ **İşleniyor...**", parse_mode="Markdown")
        fid = message.photo[-1].file_id if message.content_type == 'photo' else message.document.file_id
        finfo = bot.get_file(fid)
        raw = bot.download_file(finfo.file_path)
        
        link_task = executor.submit(pixeldrain_yukle, raw)
        
        if message.content_type == 'document' and message.document.file_name.lower().endswith('.pdf'):
            g, a, t = analiz_v4(raw)
            link = link_task.result()
            msg = f"🏦 **ONAY ✅**\n━━━━━━━━━━━━━━\n👤 **G:** `{g}`\n👤 **A:** `{a}`\n💰 **T:** `{t}`\n━━━━━━━━━━━━━━\n📋 `{link}`"
        else:
            link = link_task.result()
            msg = f"📸 **Link:** `{link}`"

        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🌍 Görüntüle", url=link))
        bot.edit_message_text(msg, chat_id=message.chat.id, message_id=waiting.message_id, 
                              parse_mode="Markdown", reply_markup=markup)
    except: pass

if __name__ == "__main__":
    keep_alive()
    bot.infinity_polling(skip_pending=True)
