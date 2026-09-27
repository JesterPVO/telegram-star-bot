from telegram import Update, LabeledPrice
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    PreCheckoutQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# Aap ka naya secret token
BOT_TOKEN = "8371120664:AAGtlUk0nVxSTdRZ_j17ZklniSOGBCOhBB0"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Jab user /start likhay ga toh Stars ka invoice bhejega."""
    # XTR Telegram Stars ka official currency code hai
    prices = [LabeledPrice("Digital Product", 10)]  # 10 Stars

    await context.bot.send_invoice(
        chat_id=update.effective_chat.id,
        title="Buy Access",
        description="Get instant digital access or service",
        payload="user-purchase-payload",
        provider_token="",  # Telegram Stars ke liye yeh khali rehna chahiye
        currency="XTR",     # Must be XTR for Telegram Stars
        prices=prices,
    )

async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Payment approve karne ke liye Telegram ko instant answer bhejta hai."""
    query = update.pre_checkout_query
    await query.answer(ok=True)

async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Payment successful hone par yeh message dikhayega."""
    await update.message.reply_text("Thank you for your payment! Your access has been unlocked.")

if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))

    print("Bot starting...")
    app.run_polling()
