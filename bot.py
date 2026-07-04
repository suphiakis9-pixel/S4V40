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

# LOGLAMA
logging.basicConfig(level=logging.ERROR)

# SİGORTA
executor = ThreadPoolExecutor(max_workers=4)
upload_semaphore = asyncio.Semaphore(3) # Aynı anda max 3 yükleme

# --- KONFİGÜRASYON ---
API_TOKEN = "8637392837:AAGwMQdmPsB7hwu4ayk-ILdy1hYc_WvCf7Q"
PIXELDRAIN_API_KEY = "5f506736-f934-4871-99ce-b145dc96279d"
bot = AsyncTeleBot(API_TOKEN)

app = Flask('')
@app.route('/')
def home(): return f"SİSTEM AKTİF - UPLOAD MOTORU GÜÇLENDİRİLDİ - {time.strftime('%H:%M:%S')}", 200

# ======================================================
# 🧠 v32 ANALİZ MOTORU (DOKUNULMADI - BİREBİR KORUNDU)
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

def process_pdf_blocking(file_bytes):
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
            if "GÖNDEREN" in l_up:
                parts = re.split(r'GÖNDEREN\s*[:]*', l_up)
                target = parts[1] if len(parts) > 1 else l_up
                res = ismi_temizle(target.split("AÇIKLAMA:")[0].strip())
                if res: g = res
            if "SAYIN" in l_up and g == "Bilinmiyor":
                comb = l_up.replace("SAYIN", "").strip()
                if i+1 < len(lns): comb += " " + lns[i+1].upper()
                res = ismi_temizle(comb)
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
        return g, a, tutar_bul_final(txt)
    except: return "Hata", "Hata", "Bulunamadı"

# ======================================================
# ☁️ OPTİMİZE EDİLMİŞ GLOBAL UPLOAD MOTORU
# ======================================================
_session = None

async def get_session():
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25))
    return _session

async def multi_upload(file_bytes, ext):
    filename = f"dec_{int(time.time())}{ext}"
    session = await get_session()
    
    async with upload_semaphore: # Aynı anda çok fazla yüklemeyi engeller
        # 1. Deneme Hattı: PIXELDRAIN
        for attempt in range(2): # 2 kez dene
            try:
                data = aiohttp.FormData()
                data.add_field('file', file_bytes, filename=filename)
                auth = aiohttp.BasicAuth("", PIXELDRAIN_API_KEY)
                async with session.post("https://pixeldrain.com/api/file", data=data, auth=auth) as r:
                    if r.status in [200, 201]:
                        res = await r.json()
                        if res.get('id'): return f"https://pixeldrain.com/api/file/{res.get('id')}"
            except:
                await asyncio.sleep(1)

        # 2. Deneme Hattı: CATBOX
        try:
            data = aiohttp.FormData()
            data.add_field('reqtype', 'fileupload')
            data.add_field('fileToUpload', file_bytes, filename=filename)
            async with session.post("https://catbox.moe/user/api.php", data=data) as r:
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
        
        # Link alma (Akıllı motor)
        link = await multi_upload(raw, ".pdf" if is_pdf else ".jpg")
        link_str = f"`{link}`" if link else "_Yükleme zaman aşımına uğradı_"
        
        if is_pdf:
            g, a, t = await asyncio.get_event_loop().run_in_executor(executor, process_pdf_blocking, raw)
            markup = types.InlineKeyboardMarkup()
            if link: markup.add(types.InlineKeyboardButton("👁‍🗨 Görüntüle", url=link))
            
            msg = (f"🏦 **ONAY ✅**\n━━━━━━━━━━━━━━━━━━━━\n"
                   f"👤 **G:** `{g}`\n👤 **A:** `{a}`\n💰 **T:** `{t}`\n"
                   f"━━━━━━━━━━━━━━━━━━━━\n📋 **Kopyala:** {link_str}")
            await bot.edit_message_text(msg, message.chat.id, waiting.message_id, parse_mode="Markdown", reply_markup=markup)
        else:
            msg = f"📸 **Görsel Linki ✅**\n\n📋 {link_str}"
            await bot.edit_message_text(msg, message.chat.id, waiting.message_id, parse_mode="Markdown")
            
    except Exception as e:
        try: await bot.edit_message_text(f"❌ Bağlantı hatası oluştu, lütfen tekrar deneyin.", message.chat.id, waiting.message_id)
        except: pass

def start_flask():
    try:
        port = int(os.environ.get('PORT', 7860))
        app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
    except: pass

async def main():
    Thread(target=start_flask, daemon=True).start()
    while True:
        try:
            await bot.infinity_polling(timeout=60, request_timeout=60, skip_pending=True)
        except:
            await asyncio.sleep(5)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    
