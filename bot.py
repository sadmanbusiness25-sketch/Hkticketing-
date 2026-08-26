
import os
import re
import asyncio
import requests
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Environment Variables
TELEGRAM_BOT_TOKEN = os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
PUBLIC_CHANNEL_ID = os.environ.get("CHAT_ID")
LAMIX_API_URL = os.environ.get("LAMIX_API_URL")
LAMIX_TOKEN = os.environ.get("LAMIX_TOKEN")

def log(text):
    print(text, flush=True)

# টেক্সট থেকে অনেকগুলো নাম্বার বা রেঞ্জ ফিল্টার করে লিস্ট বানানো
function_numbers_cache = []

def extract_numbers_from_text(raw_text):
    if raw_text.startswith("/"):
        raw_text = raw_text.split(" ", 1)[-1] if " " in raw_text else ""
    
    # সব ধরনের ফোন নম্বর বা রেঞ্জ প্যাটার্ন খুঁজে বের করা
    found_nums = re.findall(r"\+?\d{6,15}", raw_text)
    return found_nums

# প্যানেল থেকে নির্দিষ্ট নাম্বার নিয়ে অর্ডার তৈরি করা
def get_number_by_specific_range(service_name, target_range):
    params = {
        "action": "getNumber",
        "token": LAMIX_TOKEN,
        "service": service_name,
        "range": target_range,
    }
    try:
        res = requests.get(LAMIX_API_URL, params=params, timeout=10).json()
        if res.get("status") == "success":
            return res.get("id"), res.get("number")
    except Exception as e:
        log(f"Get Number Error: {e}")
    return None, None

# OTP চেক করা
def check_otp(order_id):
    params = {"action": "getStatus", "token": LAMIX_TOKEN, "id": order_id}
    try:
        res = requests.get(LAMIX_API_URL, params=params, timeout=10).json()
        if res.get("status") == "STATUS_OK":
            return res.get("sms")
    except Exception as e:
        log(f"Check OTP Error: {e}")
    return None

# অর্ডার ক্যানসেল করা
def cancel_order(order_id):
    params = {
        "action": "setStatus",
        "token": LAMIX_TOKEN,
        "id": order_id,
        "status": "8",
    }
    try:
        requests.get(LAMIX_API_URL, params=params, timeout=10)
    except Exception as e:
        log(f"Cancel Error: {e}")

# মূল অটোমেশন লুপ (HK Ticketing এর জন্য)
async def hkticketing_loop(context: ContextTypes.DEFAULT_TYPE, chat_id: int, number_list: list):
    service_name = "hkticketing"
    
    # বিকল্প রেঞ্জ বা দেশ (যেমন: 60 কোড এবং Israel)
    fallback_ranges = ["60", "Israel", "972"] 
    
    index = 0
    while True:
        if not number_list:
            break
            
        current_target = number_list[index % len(number_list)]
        index += 1

        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🔄 *HK Ticketing:* Trying with Target/Range: `{current_target}`",
            parse_mode="Markdown",
        )

        order_id, number = get_number_by_specific_range(service_name, str(current_target))
        
        if not order_id or not number:
            # যদি সরাসরি নাম্বারে না পায়, তবে অল্টারনেটিভ রেঞ্জ দিয়ে ট্রাই করবে
            for alt in fallback_ranges:
                order_id, number = get_number_by_specific_range(service_name, alt)
                if order_id and number:
                    break
        
        if not order_id or not number:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ Stock unavailable for `{current_target}`. Retrying next...",
            )
            await asyncio.sleep(3)
            continue

        await context.bot.send_message(
            chat_id=chat_id,
            text=f"📱 *Testing Number:* `{number}`\n⏳ Waiting for OTP (1 min timeout)...",
            parse_mode="Markdown",
        )

        otp_received = None
        # ১ মিনিট অপেক্ষা করার লুপ (১২ বার x ৫ সেকেন্ড = ৬০ সেকেন্ড)
        for _ in range(12):
            await asyncio.sleep(5)
            otp = check_otp(order_id)
            if otp:
                otp_received = otp
                break

        if otp_received:
            success_msg = (
                f"🚨 *HK TICKETING OTP SUCCESS!* 🚨\n\n"
                f"📱 *Number:* `{number}`\n"
                f"💬 *OTP Code:* `{otp_received}`\n\n"
                f"🔥 *এই নাম্বারে বারবার হিট করা হচ্ছে!*"
            )
            if PUBLIC_CHANNEL_ID:
                await context.bot.send_message(
                    chat_id=PUBLIC_CHANNEL_ID,
                    text=success_msg,
                    parse_mode="Markdown",
                )
            await context.bot.send_message(
                chat_id=chat_id,
                text=success_msg,
                parse_mode="Markdown",
            )
            
            # যেটাতে ওটিপি আসবে, ১ মিনিট পর পর ওই একই নাম্বারে বারবার ট্রাই চালিয়ে যাওয়ার লুপ
            while True:
                await asyncio.sleep(60)
                await context.bot.send_message(chat_id=chat_id, text=f"♻️ Re-testing successful number: `{number}` after 1 min...")
                # এখানে দরকার হলে একই অর্ডারের জন্য পুনরায় স্ট্যাটাস বা রিকুয়েস্ট পাঠানো যাবে
        else:
            cancel_order(order_id)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"❌ No OTP on `{number}`. Switching to next number...",
            )
        
        await asyncio.sleep(2)

async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    numbers = extract_numbers_from_text(text)

    if not numbers:
        await update.message.reply_text("⚠️ কোনো সঠিক নাম্বার বা রেঞ্জ লিস্ট পাওয়া যায়নি। একসাথে অনেকগুলো নাম্বার পেস্ট করুন।")
        return

    await update.message.reply_text(
        f"🚀 মোট `{len(numbers)}` টি নাম্বার বা রেঞ্জ লোড করা হয়েছে। HK Ticketing-এ অটো-হিট শুরু হলো...",
        parse_mode="Markdown",
    )

    asyncio.create_task(hkticketing_loop(context, update.message.chat_id, numbers))

def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_messages))
    log("HK Ticketing Auto-Hit Bot is Running...")
    app.run_polling()

if __name__ == "__main__":
    main()
