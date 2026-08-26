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

# Global Tracking State
active_targets = {}

def log(text):
    print(text, flush=True)

def extract_numbers(text):
    if text.startswith("/"):
        text = text.split(" ", 1)[-1] if " " in text else ""
    return re.findall(r"\+?\d{8,15}", text)

# Playwright Browser Automation for HK Ticketing
async def send_hkticketing_otp(number):
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"]
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            log(f"🌐 Hitting HK Ticketing for: {number}")
            await page.goto("https://www.hkticketing.com/", wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(2500)

            clean_num = number.replace("+", "")
            
            phone_input = await page.query_selector('input[type="tel"], input[name*="phone"], input[id*="mobile"]')
            if phone_input:
                await phone_input.fill(clean_num)
                await page.wait_for_timeout(1000)

                submit_btn = await page.query_selector('button:has-text("OTP"), button:has-text("Send"), input[type="submit"]')
                if submit_btn:
                    await submit_btn.click()
                    await page.wait_for_timeout(2000)
                    await browser.close()
                    return True

            await browser.close()
            return False

    except Exception as e:
        log(f"❌ Error hitting {number}: {e}")
        return False

# OTP Tracking and Loop Execution
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

        for _ in range(10):
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

            # Re-hitting loop for live numbers
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

# Feed Channel Listener
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

# User Inbox Handler
async def handle_user_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.channel_post:
        return

    text = update.message.text.strip()
    numbers = extract_numbers(text)

    if not numbers:
        await update.message.reply_text("⚠️ কোনো নাম্বার পাওয়া যায়নি! Country code সহ (+972... / +60...) নাম্বার পেস্ট করুন।")
        return

    await update.message.reply_text(
        f"📥 মোট `{len(numbers)}` টি নাম্বার লোড করা হয়েছে। HK Ticketing-এ হিট এবং Feed Check শুরু হচ্ছে...",
        parse_mode="Markdown"
    )

    asyncio.create_task(start_hkticketing_loop(context, update.message.chat_id, numbers))

def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    app.add_handler(MessageHandler(filters.ChatType.CHANNEL, handle_channel_feed))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_messages))
    app.add_handler(CommandHandler("start", handle_user_messages))

    log("HK Ticketing Auto-Hit Bot Running...")
    app.run_polling()

if __name__ == "__main__":
    main()
