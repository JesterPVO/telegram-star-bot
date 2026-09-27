import os
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    PreCheckoutQueryHandler,
    MessageHandler,
    filters,
)

# Aapka naya Telegram Bot Token
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8371120664:AAH0UE_8Oljqjnb3uLHVjxX-Y7StBUEQq9k")

# Users ke stars tracking ke liye dictionary
user_stars_db = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amount = 10
    if context.args and context.args[0].isdigit():
        amount = int(context.args[0])

    try:
        invoice_link = await context.bot.create_invoice_link(
            title="Star Purchase",
            description=f"Payment for {amount} Stars",
            payload=f"stars-payload-{amount}",
            provider_token="",  # Telegram Stars ke liye empty rakhein
            currency="XTR",
            prices=[{"label": "Stars", "amount": amount}]
        )
        await update.message.reply_text(f"Here is your payment link:\n{invoice_link}")
    except Exception as e:
        await update.message.reply_text(f"Error creating invoice link: {e}")

async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)

async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    amount = payment.total_amount
    user = update.message.from_user
    user_id = user.id
    user_name = user.full_name or user.username or "Unknown"

    # Stars database update
    if user_id not in user_stars_db:
        user_stars_db[user_id] = {"name": user_name, "stars": 0}
    
    user_stars_db[user_id]["stars"] += amount
    user_stars_db[user_id]["name"] = user_name

    # Successful payment message
    await update.message.reply_text(
        f"Thank you for your payment of {amount} Stars!\n\n"
        f"Contact @jasonpvo for your stuff."
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not user_stars_db:
        await update.message.reply_text("Abhi tak kisi ne stars nahi diye hain.")
        return

    sorted_users = sorted(user_stars_db.values(), key=lambda x: x["stars"], reverse=True)
    
    text = "⭐ **Top Star Contributors** ⭐\n\n"
    for idx, udata in enumerate(sorted_users[:10], start=1):
        text += f"{idx}. {udata['name']} - {udata['stars']} Stars\n"

    await update.message.reply_text(text, parse_mode="Markdown")

async def hourly_ping(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.chat_id
    await context.bot.send_message(chat_id=chat_id, text="🏓 Ping-Pong! (Bot is running fine)")

async def start_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    current_jobs = context.job_queue.get_jobs_by_name(str(chat_id))
    if current_jobs:
        await update.message.reply_text("Har ghante ping-pong pehle se active hai.")
        return

    context.job_queue.run_repeating(hourly_ping, interval=3600, first=10, chat_id=chat_id, name=str(chat_id))
    await update.message.reply_text("Har ghante 'Ping-Pong' notification start ho gaya hai!")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("ping", start_ping))
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))

    app.run_polling()

if __name__ == "__main__":
    main()
