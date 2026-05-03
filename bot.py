import asyncio
import io
import re
import time
import os
import logging
import aiohttp
import pypdf
from flask import Flask
from telebot.async_telebot import AsyncTeleBot
from telebot import types
from threading import Thread

# Kritik hataları izlemek için sade loglama
logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s')

# --- KONFİGÜRASYON ---
API_TOKEN = "8637392837:AAHnXyyKcSfe8Mic4kePRuQz80iMiruRcBI"
PIXELDRAIN_API_KEY = "3be0c64a-e583-4296-990a-a0d0c6e2a6c9"
bot = AsyncTeleBot(API_TOKEN)

# Flask (Render'ın portu açık tutması için)
app = Flask('')
@app.route('/')
def home(): return "Sistem Aktif", 200

# --- v32 ANALİZ MOTORU (MANTIĞI KORUNDU) ---
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

# --- ASYNC İŞLEMCİLER ---
async def upload_file(raw_file, extension):
    filename = f"up_{int(time.time())}{extension}"
    async with aiohttp.ClientSession() as session:
        try:
            # Pixeldrain (Hızlı ve stabil)
            auth = aiohttp.BasicAuth("", PIXELDRAIN_API_KEY)
            data = aiohttp.FormData()
            data.add_field('file', raw_file, filename=filename)
            async with session.post("https://pixeldrain.com/api/file", data=data, auth=auth, timeout=15) as r:
                if r.status == 200 or r.status == 201:
                    res = await r.json()
                    return f"https://pixeldrain.com/api/file/{res.get('id')}"
        except: pass
    return None

def process_pdf_blocking(file_bytes):
    """CPU tüketen bu fonksiyonu executor ile çalıştırıyoruz"""
    try:
        pdf = pypdf.PdfReader(io.BytesIO(file_bytes))
        txt = ""
        for page in pdf.pages: txt += (page.extract_text() or "") + "\n"
        lns = [l.strip() for l in txt.split('\n') if l.strip()]
        g, a = "Bilinmiyor", "Bilinmiyor"
        for i, l in enumerate(lns):
            l_up = l.upper()
            if "ADI SOYADI" in l_up and i < 10:
                res = ismi_temizle(l_up)
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
    except Exception as e:
        logging.error(f"PDF Analiz Hatası: {e}")
        return "Hata", "Hata", "Bulunamadı"

@bot.message_handler(content_types=['photo', 'document'])
async def handle_docs(message):
    waiting = await bot.reply_to(message, "⌛")
    try:
        if message.content_type == 'photo':
            file_id = message.photo[-1].file_id
            ext = ".jpg"
            is_pdf = False
        else:
            if not message.document.file_name.lower().endswith('.pdf'): return
            file_id = message.document.file_id
            ext = ".pdf"
            is_pdf = True

        # Dosyayı indir
        file_info = await bot.get_file(file_id)
        downloaded_file = await bot.download_file(file_info.file_path)

        # Analiz (Bloklamayı önlemek için executor kullanıyoruz)
        if is_pdf:
            loop = asyncio.get_event_loop()
            g, a, t = await loop.run_in_executor(None, process_pdf_blocking, downloaded_file)
        else:
            g, a, t = "Görsel", "Görsel", "Yok"

        # Yükleme (Async)
        link = await upload_file(downloaded_file, ext)
        
        markup = types.InlineKeyboardMarkup()
        if link: markup.add(types.InlineKeyboardButton("👁‍🗨 Görüntüle", url=link))

        if is_pdf:
            msg = (f"🏦 **ONAY ✅**\n━━━━━━━━━━━━━━━━━━━━\n"
                   f"👤 **G:** `{g}`\n👤 **A:** `{a}`\n💰 **T:** `{t}`\n"
                   f"━━━━━━━━━━━━━━━━━━━━\n📋 **Kopyala:** `{link if link else 'Hata'}`")
        else:
            msg = f"📸 **Görsel Linki ✅**\n\n📋 `{link if link else 'Hata'}`"

        await bot.edit_message_text(msg, message.chat.id, waiting.message_id, parse_mode="Markdown", reply_markup=markup)
    except Exception as e:
        logging.error(f"Genel İşlem Hatası: {e}")
        await bot.delete_message(message.chat.id, waiting.message_id)

# --- RUNTIME ---
def start_flask():
    port = int(os.environ.get('PORT', 7860))
    app.run(host='0.0.0.0', port=port)

async def main():
    # Flask'ı ayrı bir thread'de başlat
    Thread(target=start_flask, daemon=True).start()
    
    # Botu başlat
    print("Bot başlatılıyor...")
    while True:
        try:
            # infinity_polling asenkron yapıda daha stabildir
            await bot.infinity_polling(timeout=60, request_timeout=60)
        except Exception as e:
            logging.error(f"Polling koptu, yeniden deneniyor: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
            
