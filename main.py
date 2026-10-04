import os
import ast
import operator
import sqlite3
import asyncio
from datetime import datetime, timedelta
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
from telegram.error import TelegramError

# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8371120664:AAEXFlDG_YpGUO8wAcjNOh2owwxelrCBjC0")
DB_FILE = "bot_data.db"
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "8581")

ADMIN_IDS = {
    int(x.strip())
    for x in os.environ.get("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
}

KARACHI_TZ = pytz.timezone("Asia/Karachi")

if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN environment variable is required.")

# Tracks user_ids (not chat_ids) that have authenticated via password
UNLOCKED_USERS: set[int] = set()


# ---------------------------------------------------------
# Database Operations
# ---------------------------------------------------------
def get_db():
    return sqlite3.connect(DB_FILE)


def init_db():
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                stars INTEGER DEFAULT 0
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount INTEGER,
                hour INTEGER,
                day TEXT,
                timestamp TEXT
            )
        """)
        cur.execute("PRAGMA table_info(transactions)")
        cols = [r[1] for r in cur.fetchall()]
        if "day" not in cols:
            cur.execute("ALTER TABLE transactions ADD COLUMN day TEXT")
            cur.execute("UPDATE transactions SET day = substr(timestamp, 1, 10) WHERE day IS NULL")


def record_payment(user_id: int, user_name: str, amount: int, hour: int, day: str, timestamp: str):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO users (user_id, name, stars)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                name = excluded.name,
                stars = stars + excluded.stars
        """, (user_id, user_name, amount))
        cur.execute("""
            INSERT INTO transactions (user_id, amount, hour, day, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, amount, hour, day, timestamp))


def get_top_users(limit=50):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT name, stars FROM users ORDER BY stars DESC LIMIT ?", (limit,))
        return cur.fetchall()


def get_peak_hours():
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT hour, SUM(amount) AS total_stars
            FROM transactions
            GROUP BY hour
            ORDER BY total_stars DESC
        """)
        return cur.fetchall()


def get_stars_between(start_date: str, end_date: str):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT COALESCE(SUM(amount), 0), COUNT(*), COUNT(DISTINCT user_id)
            FROM transactions
            WHERE day BETWEEN ? AND ?
        """, (start_date, end_date))
        return cur.fetchone()


def get_buyers_since(start_date: str):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT user_id FROM transactions WHERE day >= ?", (start_date,))
        return [r[0] for r in cur.fetchall()]


def get_all_buyer_ids():
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT user_id FROM transactions")
        return [r[0] for r in cur.fetchall()]


def get_daily_breakdown(days=7):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT day, SUM(amount), COUNT(*), COUNT(DISTINCT user_id)
            FROM transactions
            GROUP BY day
            ORDER BY day DESC
            LIMIT ?
        """, (days,))
        return cur.fetchall()


# ---------------------------------------------------------
# Safe Calculator
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
    if isinstance(node, ast.BinOp):
        left = safe_eval(node.left)
        right = safe_eval(node.right)
        op = type(node.op)
        if op == ast.Pow:
            if right > 1000 or left > 1000:  # Prevent DoS attacks with huge exponentiation
                raise ValueError("Exponent or base too large")
        if op in SAFE_OPERATORS:
            return SAFE_OPERATORS[op](left, right)
        raise ValueError(f"Unsupported binary operator: {op.__name__}")
    if isinstance(node, ast.UnaryOp):
        operand = safe_eval(node.operand)
        op = type(node.op)
        if op in SAFE_OPERATORS:
            return SAFE_OPERATORS[op](operand)
        raise ValueError(f"Unsupported unary operator: {op.__name__}")
    raise ValueError("Invalid mathematical expression")


def calculate_expression(expr: str):
    parsed = ast.parse(expr, mode="eval")
    return safe_eval(parsed.body)


# ---------------------------------------------------------
# Admin Authentication
# ---------------------------------------------------------
def is_admin(update: Update) -> bool:
    user = update.effective_user
    if not user:
        return False
    if user.id in ADMIN_IDS or user.id in UNLOCKED_USERS:
        return True
    return False


async def admin_only(update: Update) -> bool:
    if not is_admin(update):
        await update.message.reply_text(
            "🔒 Admin panel locked.\nUnlock with: `/admin <password>`",
            parse_mode="Markdown",
        )
        return False
    return True


# ---------------------------------------------------------
# Handlers
# ---------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amount = 10
    if context.args and context.args[0].isdigit():
        amount = max(1, int(context.args[0]))

    try:
        invoice_link = await context.bot.create_invoice_link(
            title="Star Purchase",
            description=f"Payment for {amount} Stars",
            payload=f"stars-payload-{amount}",
            provider_token="",  # Blank for Telegram Stars (XTR)
            currency="XTR",
            prices=[LabeledPrice(label="Stars", amount=amount)],
            start_parameter="buy-stars",
        )
        await update.message.reply_text(f"Here is your payment link:\n{invoice_link}")
    except Exception as e:
        await update.message.reply_text(f"Error creating invoice link: {e}")


async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)


async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    amount = payment.total_amount
    user = update.message.from_user

    now = datetime.now(KARACHI_TZ)
    record_payment(
        user_id=user.id,
        user_name=user.full_name or user.username or "Unknown",
        amount=amount,
        hour=now.hour,
        day=now.strftime("%Y-%m-%d"),
        timestamp=now.strftime("%Y-%m-%d %H:%M:%S"),
    )

    await update.message.reply_text(
        f"Thank you for your payment of {amount} Stars!\n\n"
        f"Contact @jasonpvo for your access."
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    top_50 = get_top_users(50)
    if not top_50:
        await update.message.reply_text("No stars recorded yet.")
        return

    text = f"⭐ *Top {len(top_50)} Star Contributors* ⭐\n\n"
    for idx, (name, stars_count) in enumerate(top_50, start=1):
        medal = "🥇 " if idx == 1 else "🥈 " if idx == 2 else "🥉 " if idx == 3 else f"{idx}. "
        text += f"{medal}{name} - *{stars_count}* Stars\n"

    for i in range(0, len(text), 4000):
        await update.message.reply_text(text[i:i + 4000], parse_mode="Markdown")


async def peak_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    peaks = get_peak_hours()
    if not peaks:
        await update.message.reply_text("No payment activity recorded yet.")
        return

    text = "⏰ *Peak Star Activity Hours (Asia/Karachi)* ⏰\n\n"
    for idx, (hour, total) in enumerate(peaks[:4], start=1):
        s = datetime.strptime(str(hour), "%H").strftime("%I:00 %p")
        e = datetime.strptime(str((hour + 1) % 24), "%H").strftime("%I:00 %p")
        text += f"🏆 *#{idx} Peak*: `{s} - {e}` → *{total} Stars*\n"

    await update.message.reply_text(text, parse_mode="Markdown")


async def calc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Usage: `/calc <expression>`\nExample: `/calc 25 * 4 + 10`",
            parse_mode="Markdown",
        )
        return
    try:
        expr = " ".join(context.args)
        result = calculate_expression(expr)
        await update.message.reply_text(f"🧮 *Result:* `{result}`", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Invalid expression. Error: `{e}`", parse_mode="Markdown")


async def hourly_ping(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        chat_id=context.job.chat_id,
        text="🏓 Ping-Pong! (Bot status active)",
    )


async def start_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.job_queue:
        await update.message.reply_text("JobQueue not initialized.")
        return
    chat_id = update.effective_chat.id
    if context.job_queue.get_jobs_by_name(str(chat_id)):
        await update.message.reply_text("Hourly ping is already running.")
        return
    context.job_queue.run_repeating(
        hourly_ping, interval=3600, first=10, chat_id=chat_id, name=str(chat_id)
    )
    await update.message.reply_text("Hourly ping notifications enabled!")


# ---------------------------------------------------------
# Admin Panel Commands
# ---------------------------------------------------------
async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args or []

    if not args:
        status = "🔓 Unlocked" if is_admin(update) else "🔒 Locked"
        await update.message.reply_text(
            f"🛠 *Admin Panel* — {status}\n\n"
            "Unlock: `/admin <password>`\n"
            "Lock: `/admin lock`\n\n"
            "*Commands:*\n"
            "`/admin_daily` – Today's summary\n"
            "`/admin_weekly` – 7-day total\n"
            "`/admin_breakdown [days]` – Daily breakdown\n"
            "`/admin_broadcast <msg>` – DM all buyers\n"
            "`/admin_msg_today <msg>` – DM today's buyers\n",
            parse_mode="Markdown",
        )
        return

    sub = args[0].lower()

    if sub == "lock":
        UNLOCKED_USERS.discard(user.id)
        await update.message.reply_text("🔒 Admin panel locked.")
        return

    if args[0] == ADMIN_PASSWORD:
        UNLOCKED_USERS.add(user.id)
        await update.message.reply_text(
            "🔓 *Admin panel unlocked.*\nUse `/admin` to list available commands.",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text("❌ Wrong password.")


async def admin_daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update):
        return
    today = datetime.now(KARACHI_TZ).strftime("%Y-%m-%d")
    total, txns, buyers = get_stars_between(today, today)
    await update.message.reply_text(
        f"📅 *Daily Report* ({today}, Asia/Karachi)\n\n"
        f"⭐ Stars earned: *{total}*\n"
        f"💳 Transactions: *{txns}*\n"
        f"👥 Unique buyers: *{buyers}*",
        parse_mode="Markdown",
    )


async def admin_weekly(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update):
        return
    now = datetime.now(KARACHI_TZ)
    end = now.strftime("%Y-%m-%d")
    start_date = (now - timedelta(days=6)).strftime("%Y-%m-%d")
    total, txns, buyers = get_stars_between(start_date, end)
    await update.message.reply_text(
        f"🗓 *Weekly Report* ({start_date} → {end}, Asia/Karachi)\n\n"
        f"⭐ Stars earned: *{total}*\n"
        f"💳 Transactions: *{txns}*\n"
        f"👥 Unique buyers: *{buyers}*",
        parse_mode="Markdown",
    )


async def admin_breakdown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update):
        return
    days = 7
    if context.args and context.args[0].isdigit():
        days = min(int(context.args[0]), 60)
    rows = get_daily_breakdown(days)
    if not rows:
        await update.message.reply_text("No transactions recorded yet.")
        return
    text = f"📊 *Last {days}-day breakdown*\n\n"
    for day, total, txns, buyers in rows:
        text += f"`{day}` → *{total}* ⭐ | {txns} txns | {buyers} buyers\n"
    await update.message.reply_text(text, parse_mode="Markdown")


async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: `/admin_broadcast <message>`", parse_mode="Markdown")
        return
    message = " ".join(context.args)
    await _send_broadcast(update, context, get_all_buyer_ids(), message)


async def admin_msg_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: `/admin_msg_today <message>`", parse_mode="Markdown")
        return
    message = " ".join(context.args)
    today = datetime.now(KARACHI_TZ).strftime("%Y-%m-%d")
    await _send_broadcast(update, context, get_buyers_since(today), message)


async def _send_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE, recipients: list[int], message: str):
    if not recipients:
        await update.message.reply_text("No recipients found.")
        return

    status = await update.message.reply_text(
        f"📤 Sending to *{len(recipients)}* users...", parse_mode="Markdown"
    )
    sent, failed = 0, 0
    for uid in recipients:
        try:
            await context.bot.send_message(chat_id=uid, text=message)
            sent += 1
            await asyncio.sleep(0.05)  # Rate limiting to follow Telegram API constraints
        except TelegramError:
            failed += 1

    await status.edit_text(
        f"✅ Broadcast complete.\n\nSent: *{sent}*\nFailed: *{failed}*",
        parse_mode="Markdown",
    )


# ---------------------------------------------------------
# Application Lifecycle
# ---------------------------------------------------------
def main():
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Public commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("peak", peak_time))
    app.add_handler(CommandHandler("calc", calc))
    app.add_handler(CommandHandler("ping", start_ping))

    # Admin commands
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CommandHandler("admin_daily", admin_daily))
    app.add_handler(CommandHandler("admin_weekly", admin_weekly))
    app.add_handler(CommandHandler("admin_breakdown", admin_breakdown))
    app.add_handler(CommandHandler("admin_broadcast", admin_broadcast))
    app.add_handler(CommandHandler("admin_msg_today", admin_msg_today))

    # Payment flow handlers
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))

    app.run_polling()


if __name__ == "__main__":
    main()
