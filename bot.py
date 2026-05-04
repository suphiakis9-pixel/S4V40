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
from concurrent.futures import ThreadPoolExecutor

# LOGLAMA: Sadece kritik hataları göster
logging.basicConfig(level=logging.ERROR)

# SİGORTA: Render CPU'sunu korumak için aynı anda max 4 analiz
executor = ThreadPoolExecutor(max_workers=4)

# --- KONFİGÜRASYON ---
API_TOKEN = "8637392837:AAHnXyyKcSfe8Mic4kePRuQz80iMiruRcBI" # Güncel Token
PIXELDRAIN_API_KEY = "3be0c64a-e583-4296-990a-a0d0c6e2a6c9" # Kurtarılan Key
bot = AsyncTeleBot(API_TOKEN)

app = Flask('')
@app.route('/')
def home(): return "SİSTEM ÇİFT HATLI VE AKTİF", 200

# ======================================================
# 🧠 v32 ANALİZ MOTORU - (TUTAR VE İSİM DOKUNULMADI)
# ======================================================
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
# ======================================================

def process_pdf_blocking(file_bytes):
    try:
        pdf = pypdf.PdfReader(io.BytesIO(file_bytes))
        txt = "".join([(page.extract_text() or "") + "\n" for page in pdf.pages])
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
                if (not res or len(res.split()) < 2) and i+1 < len(lns): res = ismi_temizle(lns[i+1])
                if res: a = res
            if "ALACAKLI ADI SOYADI" in l_up and ":" in l_up:
                res = ismi_temizle(l_up.split(":")[1].strip())
                if res: a = res
        return g, a, tutar_bul_final(txt)
    except: return "Hata", "Hata", "Bulunamadı"

async def multi_upload(file_bytes, ext):
    filename = f"dec_{int(time.time())}{ext}"
    async with aiohttp.ClientSession() as session:
        # HAT 1: Pixeldrain
        try:
            data = aiohttp.FormData()
            data.add_field('file', file_bytes, filename=filename)
            auth = aiohttp.BasicAuth("", PIXELDRAIN_API_KEY)
            async with session.post("https://pixeldrain.com/api/file", data=data, auth=auth, timeout=8) as r:
                if r.status in [200, 201]:
                    res = await r.json()
                    return f"https://pixeldrain.com/api/file/{res.get('id')}"
        except: pass

        # HAT 2: Catbox (Pixeldrain patlarsa devreye girer)
        try:
            cat_data = aiohttp.FormData()
            cat_data.add_field('reqtype', 'fileupload')
            cat_data.add_field('fileToUpload', file_bytes, filename=filename)
            async with session.post("https://catbox.moe/user/api.php", data=cat_data, timeout=12) as r:
                if r.status == 200:
                    link = await r.text()
                    if "https" in link: return link.strip()
        except: pass
    return None

@bot.message_handler(content_types=['photo', 'document'])
async def handle_files(message):
    waiting = await bot.reply_to(message, "⌛")
    try:
        is_pdf = message.content_type == 'document' and message.document.file_name.lower().endswith('.pdf')
        file_id = message.document.file_id if is_pdf else message.photo[-1].file_id
        
        file_info = await bot.get_file(file_id)
        raw = await bot.download_file(file_info.file_path)

        if is_pdf:
            # SİGORTA: Max 4 işlemi executor ile yapıyoruz
            g, a, t = await asyncio.get_event_loop().run_in_executor(executor, process_pdf_blocking, raw)
        else:
            g, a, t = "Görsel", "Görsel", "Yok"

        # Çift hatlı yükleme
        link = await multi_upload(raw, ".pdf" if is_pdf else ".jpg")
        
        markup = types.InlineKeyboardMarkup()
        if link: markup.add(types.InlineKeyboardButton("👁‍🗨 Görüntüle", url=link))
        
        msg = (f"🏦 **ONAY ✅**\n━━━━━━━━━━━━━━━━━━━━\n👤 **G:** `{g}`\n👤 **A:** `{a}`\n💰 **T:** `{t}`\n"
               f"━━━━━━━━━━━━━━━━━━━━\n📋 **Kopyala:** `{link if link else 'Hata: Sunucular Yanıt Vermiyor'}`")
        await bot.edit_message_text(msg, message.chat.id, waiting.message_id, parse_mode="Markdown", reply_markup=markup)
    except:
        try: await bot.delete_message(message.chat.id, waiting.message_id)
        except: pass

def start_flask():
    try:
        port = int(os.environ.get('PORT', 7860))
        app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
    except: pass

async def main():
    Thread(target=start_flask, daemon=True).start()
    print("Bot yeni token ve garantili yedek hat ile hazır!")
    while True:
        try:
            # 'skip_pending' False ile geçmiş mesajları da toplar
            await bot.infinity_polling(timeout=40, request_timeout=40, skip_pending=False)
        except:
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
        
