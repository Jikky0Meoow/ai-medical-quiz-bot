import os
import logging
from telegram import Update, Poll, KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from utils import extract_text_from_file, generate_mcq
from storage import can_upload_file, register_file_upload, reset_user_score, add_user_answer, get_user_score

BOT_TOKEN = os.getenv("BOT_TOKEN")
logging.basicConfig(level=logging.INFO)
app = ApplicationBuilder().token(BOT_TOKEN).build()

active_users = {}

WELCOME = (
    "👋 Welcome to the AI Medical Quiz Bot !\n\n"
    "📄 Send me a PDF or PPT/PPTX file with medical content.\n"
    "📌 I will generate quiz questions for you using AI.\n"
    "📬 You can upload up to 2 files per hour or 5 files per 24 hours.\n"
    "✅ Let’s get started!\n"
    "This bot was created by : عبدالله الشرع"
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(WELCOME)

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not can_upload_file(user_id):
        await update.message.reply_text("🚫 Upload limit reached. Try again later.")
        return

    file = update.message.document
    msg = await update.message.reply_text("📥 Downloading file...")
    new_msg = await msg.edit_text("🔍 Extracting content...")
    file_obj = await file.get_file()
    path = await file_obj.download_to_drive()

    text = extract_text_from_file(path)
    if len(text.strip()) < 100:
        await new_msg.edit_text("❌ Not enough content found.")
        return

    register_file_upload(user_id)
    active_users[user_id] = {"text": text, "questions": [], "current": 0}
    max_q = min(max(len(text.split()) // 100, 5), 50)
    keyboard = [[KeyboardButton(str(n)) for n in [5, 10, 15, 20, 25, 30, 40, 50] if n <= max_q]]
    await new_msg.edit_text(
        f"✅ Extracted successfully.\nChoose number of questions:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )

async def handle_question_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in active_users:
        return
    try:
        num = int(update.message.text.strip())
        text = active_users[user_id]["text"]
        await update.message.reply_text("🧠 Generating questions...")
        questions = generate_mcq(text, num)
        active_users[user_id]["questions"] = questions
        active_users[user_id]["current"] = 0
        reset_user_score(user_id)
        await send_next_batch(update, context)
    except:
        await update.message.reply_text("⚠️ Invalid number.")

async def send_next_batch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    qlist = active_users[user_id]["questions"]
    index = active_users[user_id]["current"]

    if index >= len(qlist):
        score = get_user_score(user_id)
        await update.message.reply_text(f"🎉 Done! You got {score}/{len(qlist)} correct.")
        return

    for i in range(index, min(index + 5, len(qlist))):
        q = qlist[i]
        msg = await update.message.reply_poll(
            question=q["question"],
            options=q["options"],
            type=Poll.QUIZ,
            correct_option_id=q["correct"],
            is_anonymous=False
        )
        context.chat_data[msg.poll.id] = {"user_id": user_id, "correct": q["correct"]}

    active_users[user_id]["current"] += 5
    btn = InlineKeyboardMarkup([[InlineKeyboardButton("Next 5", callback_data="next_batch")]]) if active_users[user_id]["current"] < len(qlist) else InlineKeyboardMarkup([[InlineKeyboardButton("Finish Quiz", callback_data="finish_quiz")]])
    await update.message.reply_text("🧪 Ready for more?" if "next_batch" in btn.inline_keyboard[0][0].callback_data else "🏁 Final questions!", reply_markup=btn)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "next_batch":
        await send_next_batch(query, context)
    elif query.data == "finish_quiz":
        user_id = query.from_user.id
        score = get_user_score(user_id)
        total = len(active_users[user_id]["questions"])
        await query.edit_message_text(f"✅ You got {score}/{total} correct.")

async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    poll_answer = update.poll_answer
    data = context.chat_data.get(poll_answer.poll_id)
    if data:
        add_user_answer(data["user_id"], data["correct"] in poll_answer.option_ids)

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.Document.ALL, handle_file))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_question_count))
app.add_handler(CallbackQueryHandler(handle_callback))
app.add_handler(MessageHandler(filters.POLL_ANSWER, handle_poll_answer))

if __name__ == "__main__":
    app.run_polling()