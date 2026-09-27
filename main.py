from telegram import Update, LabeledPrice
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    PreCheckoutQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# Aap ka bot token
BOT_TOKEN = "8371120664:AAGtlUkOnVxSTdR_j17ZklniSOGBCoHbBO"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User se amount lekar utne Stars ka invoice bhejtah hai."""
    amount = 10  # Default amount agar koi number na mile

    # Agar user ne /start 99 jaisa command bheja hai
    if context.args:
        try:
            amount = int(context.args[0])
        except ValueError:
            await update.message.reply_text("Please enter a valid number.")
            return

    prices = [LabeledPrice("Premium Access", amount)]

    await context.bot.send_invoice(
        chat_id=update.effective_chat.id,
        title="Access Purchase",
        description=f"Premium access for {amount} Stars",
        payload="custom-stars-payload",
        provider_token="",  # Telegram Stars ke liye blank chhodna hota hai
        currency="XTR",     # Telegram Stars ka currency code
        prices=prices,
        start_parameter="create-stars-invoice",
    )

async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Payment confirm karne ke liye callback handler."""
    query = update.pre_checkout_query
    if query.invoice_payload != "custom-stars-payload":
        await query.answer(ok=False, error_message="Something went wrong...")
    else:
        await query.answer(ok=True)

async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Payment complete hone par response."""
    await update.message.reply_text("Payment successful! Access granted.")

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))

    print("Bot chalo ho gaya hai...")
    app.run_polling()
