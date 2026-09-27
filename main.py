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

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8371120664:AAHZfOa6GiDGtFe8N34oT6e7cb57zvfFTmU")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Default amount if none provided
    amount = 10
    
    # Check if an integer argument was passed with /start (e.g., /start 59)
    if context.args and context.args[0].isdigit():
        amount = int(context.args[0])

    try:
        # Generate direct invoice link for Telegram Stars (XTR)
        invoice_link = await context.bot.create_invoice_link(
            title="Star Purchase",
            description=f"Payment for {amount} Stars",
            payload=f"stars-payload-{amount}",
            provider_token="",  # Must be empty for Telegram Stars
            currency="XTR",     # Currency code for Telegram Stars
            prices=[{"label": "Stars", "amount": amount}]
        )
        
        await update.message.reply_text(f"Here is your payment link:\n{invoice_link}")
    except Exception as e:
        await update.message.reply_text(f"Error creating invoice link: {e}")

async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)

async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Thank you for your payment!")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))

    app.run_polling()

if __name__ == "__main__":
    main()
