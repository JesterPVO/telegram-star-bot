from telegram import Update, LabeledPrice
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    PreCheckoutQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# Updated with your new token
BOT_TOKEN = "8927845242:AAESu-AEV_piXtE5iP4e-NqIrG-Ujw9xY0s"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends an invoice based on the requested amount of Stars."""
    amount = 10  # Default amount if no argument is provided

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
        provider_token="",  # Must be empty for Telegram Stars
        currency="XTR",     # Currency code for Telegram Stars
        prices=prices,
        start_parameter="create-stars-invoice",
    )

async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Answers the pre-checkout query to confirm payment."""
    query = update.pre_checkout_query
    if query.invoice_payload != "custom-stars-payload":
        await query.answer(ok=False, error_message="Something went wrong...")
    else:
        await query.answer(ok=True)

async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles successful payment confirmation."""
    await update.message.reply_text("Payment successful! Access granted.")

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))

    print("Bot is starting...")
    app.run_polling()
