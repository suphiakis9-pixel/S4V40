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

# ==============================
# ⚙️ RENDER İÇİN CANLI TUTMA SİSTEMİ
# ==============================
app = Flask('')

@app.route('/')
def home():
    return "Bot Aktif!"

def run_web():
    try:
        # Render port ayarı
        app.run(host='0.0.0.0', port=10000, threaded=True)
    except Exception as e:
        print(f"Flask Hatası: {e}")

def keep_alive():
    Thread(target=run_web, daemon=True).start()

# ==============================
# ⚙️ GÜNCEL AYARLAR (YENİ TOKEN VE KEY)
# ==============================
API_TOKEN = "8595291883:AAF6czvMBcQRKPtb0eljwKUuoK-9zKchKwE"
PIXELDRAIN_KEY = "ffc1f7d6-fd72-4ebf-a8d9-386c36ae4582"

bot = telebot.TeleBot(API_TOKEN, threaded=True, num_threads=40)
executor = ThreadPoolExecutor(max_workers=20)

CLEAN_RE = re.compile(r'[^A-ZÇĞİÖŞÜ ]')

YASAKLI = {
    "ALICI", "HESAP", "GÖNDEREN", "SAYIN", "HESABI", "ÜNVANI", "UNVANI", "LEHTAR", 
    "MÜŞTERİ", "İSİM", "AD", "SOYAD", "TR", "AÇIKLAMA", "BİREYSEL", "ÖDEME", 
    "MASRAF", "KOMİSYON", "ÜCRET", "VERGİ", "DAİRESİ", "NO", "TCKN", "VKN", 
    "ADRESİ", "ŞUBE", "VADESİZ", "TUTARI", "IBAN", "KART", "PARA", "CİNSİ", 
    "FİŞ", "BANK", "BANKASI", "A.Ş", "ELEKTRONİK", "HİZMETLERİ", "AŞ", 
    "MÜDÜRLÜĞÜ", "FAİZ", "VERGİSİ", "ALACAKLI", "ADİ", "SOYADI", "BORÇLU", 
    "İŞLEM", "YALNIZ", "TUTAR", "EFT", "HAVALE", "MERKEZİ", "ŞUBESİ", "ADI",
    "İSTANBUL", "ANKARA", "İZMİR", "BURSA", "ANTALYA", "KONYA", "ADANA", 
    "GAZİANTEP", "ŞANLIURFA", "KOCAELİ", "MERSİN", "DİYARBAKIR", "HATAY", "MARDİN"
}

# ==============================
# 🛠 YARDIMCI FONKSİYONLAR
# ==============================
def parse_number(text):
    if not text: return None
    text = re.sub(r'[^0-9,.]', '', text.replace(" ", ""))
    if text.count(",") > 0 and text.count(".") == 0:
        text = text.replace(",", "")
    elif text.count(".") > 0 and text.count(",") == 0:
        text = text.replace(".", "")
    elif text.count(",") > 0 and text.count(".") > 0:
        if text.find(",") < text.find("."):
            text = text.replace(",", "")
        else:
            text = text.replace(".", "").replace(",", ".")
    try:
        return float(text)
    except:
        return None

def ismi_temizle(metin):
    if not metin: return None
    t = re.sub(r'(SAYIN|ALACAKLI|GÖNDEREN|ALICI|MÜŞTERİ|ÜNVANI|ALACAKLI ADI SOYADI|ADI SOYADI|ADI)\s*[:]*', '', metin.upper())
    t = CLEAN_RE.sub(' ', re.sub(r'\d+', '', t))
    p = [x for x in t.split() if x not in YASAKLI and len(x) > 1]
    
    if any(k in t for k in ["ŞUBE", "MÜDÜRLÜĞÜ", "VALÖR", "A.Ş.", "BANKASI"]):
        return None

    if len(p) >= 2:
        return " ".join(p[:3])
    return None

def tutar_bul_final(full_text):
    patterns = [
        r'(?:TL|TUTARI|TUTAR|Tutar)\s*[:]*\s*([\d.,]{4,20})',
        r'B\s+TL\s+([\d.,]{4,20})',
        r'Havale Tutarı\s*:\s*([\d.,]{4,20})'
    ]
    for pattern in patterns:
        matches = re.findall(pattern, full_text, re.IGNORECASE)
        for m in matches:
            val = parse_number(m)
            if val and 5 < val < 5000000:
                return "{:,.2f}".format(val).replace(',', 'X').replace('.', ',').replace('X', '.') + " TRY"
    return "Bulunamadı"

def analiz_et_v32(file_bytes):
    try:
        with io.BytesIO(file_bytes) as pdf_stream:
            pdf = pypdf.PdfReader(pdf_stream)
            txt = ""
            for page in pdf.pages:
                txt += page.extract_text() + "\n"
            
            lns = [l.strip() for l in txt.split('\n') if l.strip()]
            g, a = "Bilinmiyor", "Bilinmiyor"
            
            for i, l in enumerate(lns):
                l_up = l.upper()
                if g == "Bilinmiyor" and "SAYIN" in l_up:
                    for offset in range(1, 3):
                        if i + offset < len(lns):
                            res = ismi_temizle(lns[i+offset])
                            if res: g = res; break
                if a == "Bilinmiyor" and any(k in l_up for k in ["ALICI", "LEHTAR", "ALACAKLI ADI SOYADI"]):
                    res = ismi_temizle(l)
                    if (not res) and i+1 < len(lns): 
                        res = ismi_temizle(lns[i+1])
                    if res: a = res
            return g, a, tutar_bul_final(txt)
    except: return "Hata", "Hata", "Bulunamadı"

def pixeldrain_yukle(raw_file):
    try:
        unique_name = f"dk_{int(time.time())}_{random.randint(10,99)}.pdf"
        res = requests.post("https://pixeldrain.com/api/file", 
                             files={'file': (unique_name, raw_file)}, 
                             auth=HTTPBasicAuth('', PIXELDRAIN_KEY), timeout=25)
        if res.status_code in [200, 201]:
            return f"https://pixeldrain.com/u/{res.json().get('id')}"
        return "⚠️ Hata"
    except: return "⚠️ Hata"

# ==============================
# 🤖 BOT MESAJ YÖNETİMİ
# ==============================
@bot.message_handler(content_types=['photo', 'document'])
def handle_incoming(message):
    try:
        if int(time.time()) - message.date > 120:
            return

        waiting_msg = bot.reply_to(message, "⏳ **İnceleniyor...**", parse_mode="Markdown")
        
        file_id = message.photo[-1].file_id if message.content_type == 'photo' else message.document.file_id
        is_pdf = message.content_type == 'document' and message.document.file_name.lower().endswith(".pdf")
        
        file_info = bot.get_file(file_id)
        current_raw_file = bot.download_file(file_info.file_path)
        fut_link = executor.submit(pixeldrain_yukle, current_raw_file)
        
        if is_pdf:
            gonderen, alici, tutar = analiz_et_v32(current_raw_file)
            link = fut_link.result()
            msg = (
                "🏦 **ONAY ✅**\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 **G:** `{gonderen}`\n"
                f"👤 **A:** `{alici}`\n"
                f"💰 **T:** `{tutar}`\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"📋 **Kopyala:** `{link}`"
            )
        else:
            link = fut_link.result()
            msg = f"📸 **Görsel Linki ✅**\n\n📋 `{link}`"

        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🌍 Görüntüle", url=link))
        bot.edit_message_text(msg, chat_id=message.chat.id, message_id=waiting_msg.message_id, 
                              parse_mode="Markdown", disable_web_page_preview=True, reply_markup=markup)
        del current_raw_file
    except Exception as e:
        logging.error(f"Hata: {e}")

# ==============================
# 🚀 BAŞLATMA
# ==============================
def start_bot():
    while True:
        try:
            bot.remove_webhook()
            bot.infinity_polling(timeout=90, long_polling_timeout=90, skip_pending=True)
        except:
            time.sleep(5)

if __name__ == "__main__":
    keep_alive()
    start_bot()
