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
# ⚙️ CANLI TUTMA VE SELF-PING SİSTEMİ
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
    except Exception as e:
        print(f"Flask Hatası: {e}")

def self_ping():
    time.sleep(20)
    while True:
        try:
            requests.get("http://127.0.0.1:5000/", timeout=5)
        except:
            pass
        time.sleep(180)

def keep_alive():
    Thread(target=run_web, daemon=True).start()
    Thread(target=self_ping, daemon=True).start()

# ==============================
# ⚙️ AYARLAR VE YAPILANDIRMA
# ==============================
# Senin yeni Tokenin
API_TOKEN = "8738306341:AAEdLn9E5L7LpdvPQpwRYvcp4w6lwsVCHH4"

bot = telebot.TeleBot(API_TOKEN, threaded=True, num_threads=10)
executor = ThreadPoolExecutor(max_workers=5)

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
    t = re.sub(r'(SAYIN|ALACAKLI|GÖNDEREN|ALICI|MÜŞTERİ|ÜNVANI|ALACAKLI ADI SOYADI|ADI SOYADI|AD SOYAD|ADI)\s*[:]*', '', metin.upper())
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
        r'İŞLEM TUTARI\s*\(TL\)\s*:\s*([\d.,]{4,20})',
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
                if any(k in l_up for k in ["SAYIN", "GÖNDEREN", "AD SOYAD"]) and g == "Bilinmiyor":
                    res = ismi_temizle(l) 
                    if not res and i+1 < len(lns): 
                        res = ismi_temizle(lns[i+1]) 
                    if res: g = res
                
                if any(k in l_up for k in ["ALICI", "LEHTAR", "ALACAKLI ADI SOYADI"]) and a == "Bilinmiyor":
                    res = ismi_temizle(l)
                    if (not res) and i+1 < len(lns): 
                        res = ismi_temizle(lns[i+1])
                    if res: a = res
            return g, a, tutar_bul_final(txt)
    except: return "Hata", "Hata", "Bulunamadı"

# PIXELDRAIN YERİNE CATBOX KULLANIYORUZ (ENGELLEMEYİ AŞMAK İÇİN)
def catbox_yukle(raw_file):
    try:
        # Rastgele dosya adı oluştur
        file_ext = ".pdf" # Varsayılan pdf, görsel olsa da sorun olmaz
        unique_filename = f"dk_{int(time.time())}{file_ext}"
        
        # Catbox API isteği
        files = {'fileToUpload': (unique_filename, raw_file)}
        data = {'reqtype': 'fileupload'}
        
        res = requests.post("https://catbox.moe/user/api.php", files=files, data=data, timeout=35)
        
        if res.status_code == 200 and res.text.startswith("https://"):
            return res.text.strip() # Yüklenen dosyanın URL'sini döndürür
        return "ERROR"
    except:
        return "ERROR"

# ==============================
# 🤖 BOT MESAJ YÖNETİMİ
# ==============================
@bot.message_handler(content_types=['photo', 'document'])
def handle_incoming(message):
    waiting_msg = None
    try:
        if int(time.time()) - message.date > 180:
            return

        waiting_msg = bot.reply_to(message, "⏳ **İnceleniyor...**", parse_mode="Markdown")
        
        if message.content_type == 'photo':
            file_id = message.photo[-1].file_id
            is_pdf = False
        else:
            file_id = message.document.file_id
            is_pdf = message.document.file_name.lower().endswith(".pdf")
        
        file_info = bot.get_file(file_id)
        current_raw_file = bot.download_file(file_info.file_path)
        
        # ARTIK CATBOX'A YÜKLÜYORUZ
        link = catbox_yukle(current_raw_file)
        
        if link != "ERROR":
            link_text = f"`{link}`"
            show_button = True
        else:
            link_text = "⚠️ *Yükleme başarısız (Sunucu engeli)*"
            show_button = False
        
        if is_pdf:
            gonderen, alici, tutar = analiz_et_v32(current_raw_file)
            msg = (
                "🏦 **ONAY ✅**\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 **G:** `{gonderen}`\n"
                f"👤 **A:** `{alici}`\n"
                f"💰 **T:** `{tutar}`\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"📋 **Kopyala:** {link_text}"
            )
        else:
            msg = f"📸 **Görsel Linki ✅**\n\n📋 {link_text}"

        markup = InlineKeyboardMarkup()
        if show_button:
            markup.add(InlineKeyboardButton("🌍 Görüntüle", url=link))
        
        bot.edit_message_text(msg, chat_id=message.chat.id, message_id=waiting_msg.message_id, 
                              parse_mode="Markdown", disable_web_page_preview=True, reply_markup=markup)
        
    except Exception as e:
        if waiting_msg:
            bot.edit_message_text(f"❌ İşlem hatası oluştu.", chat_id=message.chat.id, message_id=waiting_msg.message_id)

def start_botu():
    while True:
        try:
            bot.remove_webhook()
            bot.infinity_polling(timeout=90, long_polling_timeout=90, skip_pending=True)
        except:
            time.sleep(10)

if __name__ == "__main__":
    keep_alive()
    start_botu()
