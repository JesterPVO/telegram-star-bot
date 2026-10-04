import os
import ast
import operator
import sqlite3
from datetime import datetime
import pytz
from telegram import Update, LabeledPrice
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    PreCheckoutQueryHandler,
    MessageHandler,
    filters,
)

# Configuration
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8851024830:AAEDXVzHsQVSveR3j0oiavGPFMnwkqfVAY8")
DB_FILE = "bot_data.db"

# Timezone Configuration
KARACHI_TZ = pytz.timezone("Asia/Karachi")

# ---------------------------------------------------------
# Database Operations (SQLite)
# ---------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            stars INTEGER DEFAULT 0
        )
    """)
    
    # Transactions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount INTEGER,
            hour INTEGER,
            timestamp TEXT
        )
    """)
    
    conn.commit()
    conn.close()

def record_payment(user_id: int, user_name: str, amount: int, hour: int, timestamp: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Update or insert user record
    cursor.execute("""
        INSERT INTO users (user_id, name, stars)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            name = excluded.name,
            stars = stars + excluded.stars
    """, (user_id, user_name, amount))
    
    # Log transaction
    cursor.execute("""
        INSERT INTO transactions (user_id, amount, hour, timestamp)
        VALUES (?, ?, ?, ?)
    """, (user_id, amount, hour, timestamp))
    
    conn.commit()
    conn.close()

def get_top_users(limit: int = 50):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name, stars FROM users
        ORDER BY stars DESC
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_peak_hours():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT hour, SUM(amount) as total_stars
        FROM transactions
        GROUP BY hour
        ORDER BY total_stars DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows

# ---------------------------------------------------------
# Safe Calculator Helper (AST Parsing)
# ---------------------------------------------------------
SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

def safe_eval(node):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError("Unsupported constant type")
    elif isinstance(node, ast.BinOp):
        left = safe_eval(node.left)
        right = safe_eval(node.right)
        op_type = type(node.op)
        if op_type in SAFE_OPERATORS:
            return SAFE_OPERATORS[op_type](left, right)
        raise ValueError(f"Unsupported binary operator: {op_type.__name__}")
    elif isinstance(node, ast.UnaryOp):
        operand = safe_eval(node.operand)
        op_type = type(node.op)
        if op_type in SAFE_OPERATORS:
            return SAFE_OPERATORS[op_type](operand)
        raise ValueError(f"Unsupported unary operator: {op_type.__name__}")
    else:
        raise ValueError("Invalid mathematical expression")

def calculate_expression(expr: str):
    parsed = ast.parse(expr, mode='eval')
    return safe_eval(parsed.body)

# ---------------------------------------------------------
# Telegram Bot Handlers
# ---------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amount = 10
    if context.args and context.args[0].isdigit():
        amount = int(context.args[0])

    try:
        invoice_link = await context.bot.create_invoice_link(
            title="Star Purchase",
            description=f"Payment for {amount} Stars",
            payload=f"stars-payload-{amount}",
            provider_token="",  # Telegram Stars requires empty string
            currency="XTR",
            prices=[LabeledPrice(label="Stars", amount=amount)]
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

    now_karachi = datetime.now(KARACHI_TZ)
    timestamp_str = now_karachi.strftime("%Y-%m-%d %H:%M:%S")

    # Record into SQLite database
    record_payment(user_id, user_name, amount, now_karachi.hour, timestamp_str)

    await update.message.reply_text(
        f"Thank you for your payment of {amount} Stars!\n\n"
        f"Contact @jasonpvo for your stuff."
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    top_50 = get_top_users(50)
    if not top_50:
        await update.message.reply_text("Abhi tak kisi ne stars nahi diye hain.")
        return

    text = f"⭐ **Top {len(top_50)} Star Contributors** ⭐\n\n"
    for idx, (name, stars) in enumerate(top_50, start=1):
        medal = "🥇 " if idx == 1 else "🥈 " if idx == 2 else "🥉 " if idx == 3 else f"{idx}. "
        text += f"{medal}{name} - **{stars}** Stars\n"

    # Send long texts safely
    if len(text) > 4000:
        chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
        for chunk in chunks:
            await update.message.reply_text(chunk, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, parse_mode="Markdown")

async def peak_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    peaks = get_peak_hours()
    if not peaks:
        await update.message.reply_text("Abhi tak koi payment record nahi hai.")
        return

    top_peaks = peaks[:4]

    text = "⏰ **Peak Star Activity Hours (Asia/Karachi)** ⏰\n\n"
    for idx, (hour, total) in enumerate(top_peaks, start=1):
        dt_start = datetime.strptime(str(hour), "%H")
        time_str_start = dt_start.strftime("%I:00 %p")
        dt_end = datetime.strptime(str((hour + 1) % 24), "%H")
        time_str_end = dt_end.strftime("%I:00 %p")

        text += f"🏆 **#{idx} Peak**: `{time_str_start} - {time_str_end}` → **{total} Stars**\n"

    await update.message.reply_text(text, parse_mode="Markdown")

async def calc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/calc <expression>`\nExample: `/calc 25 * 4 + 10`", parse_mode="Markdown")
        return

    expression = " ".join(context.args)
    try:
        result = calculate_expression(expression)
        await update.message.reply_text(f"🧮 **Result:** `{result}`", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Invalid expression. Error: `{e}`", parse_mode="Markdown")

async def hourly_ping(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.chat_id
    await context.bot.send_message(chat_id=chat_id, text="🏓 Ping-Pong! (Bot is running fine)")

async def start_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    if not context.job_queue:
        await update.message.reply_text("JobQueue is not initialized. Make sure 'python-telegram-bot[job-queue]' is installed.")
        return

    current_jobs = context.job_queue.get_jobs_by_name(str(chat_id))
    if current_jobs:
        await update.message.reply_text("Har ghante ping-pong pehle se active hai.")
        return

    context.job_queue.run_repeating(hourly_ping, interval=3600, first=10, chat_id=chat_id, name=str(chat_id))
    await update.message.reply_text("Har ghante 'Ping-Pong' notification start ho gaya hai!")

def main():
    # Initialize SQLite Database
    init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("peak", peak_time))
    app.add_handler(CommandHandler("calc", calc))
    app.add_handler(CommandHandler("ping", start_ping))
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))

    app.run_polling()

if __name__ == "__main__":
    main()
