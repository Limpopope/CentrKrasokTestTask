import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import os
import logging
from collections import defaultdict
from openai import AsyncOpenAI  # Использовать AsyncOpenAI вместо OpenAI
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from company_knowledge import COMPANY_KNOWLEDGE

# ─── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─── OpenAI client ─────────────────────────────────────────────────────────────
# Инициализируем асинхронный клиент
client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])

# ─── System prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = f"""Ты — вежливый и компетентный AI-ассистент интернет-магазина «Центр Красок #1».
Твоя задача — отвечать на вопросы пользователей ТОЛЬКО на основе базы знаний ниже.

ПРАВИЛА:
1. Отвечай кратко, по делу, дружелюбно.
2. Если вопрос не связан с компанией — вежливо скажи, что можешь помочь только по теме магазина.
3. Не придумывай информацию, которой нет в базе знаний.
4. Если точного ответа нет — предложи связаться с менеджером: +7 (777) 292-84-01.
5. При необходимости давай ссылки из базы знаний.
6. Отвечай на языке пользователя (русский или казахский).

БАЗА ЗНАНИЙ:
{COMPANY_KNOWLEDGE}
"""

# ─── Conversation history (in-memory per user) ─────────────────────────────────
MAX_HISTORY = 10
user_histories: dict[int, list[dict]] = defaultdict(list)


# Делаем функцию асинхронной (добавили async)
async def get_ai_response(user_id: int, user_message: str) -> str:
    history = user_histories[user_id]

    history.append({"role": "user", "content": user_message})

    if len(history) > MAX_HISTORY * 2:
        history = history[-(MAX_HISTORY * 2):]
        user_histories[user_id] = history

    # Добавили await перед вызовом OpenAI
    response = await client.chat.completions.create(
        model="gpt-4o-mini",  # дешёвая и быстрая модель
        messages=[{"role": "system", "content": SYSTEM_PROMPT}] + history,
        max_tokens=1024,
        temperature=0.3,  # меньше галлюцинаций
    )

    assistant_reply = response.choices[0].message.content
    history.append({"role": "assistant", "content": assistant_reply})

    return assistant_reply


# ─── Telegram handlers ─────────────────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_text = update.message.text.strip()

    if not user_text:
        return

    logger.info(f"User {user_id}: {user_text[:80]}")

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )

    try:
        # Теперь здесь вызываем через await
        reply = await get_ai_response(user_id, user_text)
    except Exception as e:
        logger.error(f"AI error for user {user_id}: {e}")
        reply = "Извините, произошла ошибка. Пожалуйста, попробуйте позже или свяжитесь с нами: +7 (777) 292-84-01"

    await update.message.reply_text(reply)


async def handle_non_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Привет! Я отвечаю только на текстовые вопросы о магазине «Центр Красок #1». "
        "Напишите ваш вопрос — и я с удовольствием помогу! 🎨"
    )


# ─── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    # Проверяем наличие токена перед стартом, чтобы бот не падал глубоко в библиотеке
    if "TELEGRAM_BOT_TOKEN" not in os.environ:
        logger.error("TELEGRAM_BOT_TOKEN не задан в переменных окружения!")
        return
        
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = ApplicationBuilder().token(token).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(~filters.TEXT, handle_non_text))
    logger.info("Bot started. Polling...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
