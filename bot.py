import os
import re
import asyncio
from playwright.async_api import async_playwright
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

TELEGRAM_BOT_TOKEN = os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
active_targets = {}

def log(text):
    print(text, flush=True)

def extract_numbers(text):
    if text.startswith("/"):
        text = text.split(" ", 1)[-1] if " " in text else ""
    return re.findall(r"\+?\d{8,15}", text)

# উন্নত ব্রাউজার ও সঠিক রেজিস্ট্রেশন লিংক সহ হিট ফাংশন
async def send_hkticketing_otp(number):
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-infobars",
                    "--window-size=1920,1080",
                    "--disable-blink-features=AutomationControlled"
                ]
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                locale="en-US"
            )
            
            await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            page = await context.new_page()

            log(f"🌐 Hitting HK Ticketing for: {number}")
            
            # সরাসরি HK Ticketing এর লগইন বা অ্যাকাউন্ট পেজে যাওয়া (যেখানে ফোন ইনপুট থাকে)
            await page.goto("https://www.hkticketing.com/account/login", wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(4000)

            clean_num = number.replace("+", "")
            
            # একাধিক সম্ভাব্য ইনপুট সিলেক্টর চেক করা
            phone_input = None
            selectors = ['input[type="tel"]', 'input[name*="phone"]', 'input[id*="mobile"]', 'input[name*="mobile"]', 'input.phone-input', 'input[placeholder*="Mobile"]']
            
            for sel in selectors:
                try:
                    phone_input = await page.query_selector(sel)
                    if phone_input:
                        break
                except:
                    continue

            if phone_input:
                await phone_input.click()
                await page.wait_for_timeout(500)
                await phone_input.fill(clean_num)
                await page.wait_for_timeout(1000)

                # সাবমিট বা ওটিপি সেন্ড বাটন খোঁজা
                submit_btn = None
                btn_selectors = ['button:has-text("OTP")', 'button:has-text("Send")', 'button:has-text("Continue")', 'button[type="submit"]', 'input[type="submit"]']
                
                for bsel in btn_selectors:
                    try:
                        submit_btn = await page.query_selector(bsel)
                        if submit_btn:
                            break
                    except:
                        continue

                if submit_btn:
                    await submit_btn.click()
                    await page.wait_for_timeout(3000)
                    log(f"✅ Successfully sent request for {number}")
                    await browser.close()
                    return True

            log(f"⚠️ Input or Submit button not found on page for {number}")
            await browser.close()
            return False

    except Exception as e:
        log(f"❌ Error hitting {number}: {e}")
        return False

async def start_hkticketing_loop(context: ContextTypes.DEFAULT_TYPE, chat_id: int, numbers: list):
    for number in numbers:
        clean_num = number.replace("+", "")
        active_targets[clean_num] = {"chat_id": chat_id, "otp_found": False, "last_otp": None}

        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🚀 *Trying HK Ticketing:* `{number}`\n⏳ Watching Feed Channel for OTP...",
            parse_mode="Markdown"
        )

        hit_success = await send_hkticketing_otp(number)
        
        if not hit_success:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"❌ Request failed for `{number}`. Moving to next...",
                parse_mode="Markdown"
            )
            del active_targets[clean_num]
            continue

        for _ in range(12):
            await asyncio.sleep(5)
            if active_targets[clean_num]["otp_found"]:
                break

        if active_targets[clean_num]["otp_found"]:
            otp_code = active_targets[clean_num]["last_otp"]
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🔥 *OTP MATCHED & LIVE!* 🔥\n📱 Number: `{number}`\n💬 Code: `{otp_code}`\n\n♻️ *এই নাম্বারে ১ মিনিট পর পর অটো-হিট চালু থাকবে...*",
                parse_mode="Markdown"
            )

            while True:
                await asyncio.sleep(60)
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"⚡ *Re-hitting Live Number:* `{number}`",
                    parse_mode="Markdown"
                )
                await send_hkticketing_otp(number)
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⏱️ No OTP in feed for `{number}` within limit. Moving to next...",
                parse_mode="Markdown"
            )
            del active_targets[clean_num]

async def handle_channel_feed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_text = ""
    if update.channel_post:
        message_text = update.channel_post.text or ""
    elif update.message:
        message_text = update.message.text or ""

    if not message_text:
        return

    found_numbers = re.findall(r"\+?\d{8,15}", message_text)
    
    for num in found_numbers:
        clean_num = num.replace("+", "")
        if clean_num in active_targets:
            otp_match = re.search(r"\b\d{4,6}\b", message_text)
            otp_code = otp_match.group(0) if otp_match else "OTP Received"

            active_targets[clean_num]["otp_found"] = True
            active_targets[clean_num]["last_otp"] = otp_code
            log(f"✅ OTP Feed Match Found for {clean_num}: {otp_code}")

async def handle_user_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.channel_post:
        return

    text = update.message.text.strip()
    numbers = extract_numbers(text)

    if not numbers:
        await update.message.reply_text("⚠️ কোনো নাম্বার পাওয়া যায়নি! Country code সহ নাম্বার পেস্ট করুন।")
        return

    await update.message.reply_text(
        f"📥 মোট `{len(numbers)}` টি নাম্বার লোড করা হয়েছে। অটো-হিট ও Feed Check শুরু হচ্ছে...",
        parse_mode="Markdown"
    )

    asyncio.create_task(start_hkticketing_loop(context, update.message.chat_id, numbers))

def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    app.add_handler(MessageHandler(filters.ChatType.CHANNEL, handle_channel_feed))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_messages))
    app.add_handler(CommandHandler("start", handle_user_messages))

    log("HK Ticketing Clean Stealth Bot Running...")
    app.run_polling()

if __name__ == "__main__":
    main()
