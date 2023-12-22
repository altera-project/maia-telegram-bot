#!/usr/bin/env python3
# pylint: disable=unused-argument

from job_store import PTBSQLAlchemyJobStore
from telegram import Update
from telegram.ext import filters, ApplicationHandlerStop, Application, CallbackQueryHandler, CommandHandler, MessageHandler, ContextTypes, TypeHandler
from urllib.parse import quote
import alarms
import chatgpt
import gcal
import json
import logging
import re
import voice

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

class HTTPRequestFilter(logging.Filter):
    def filter(self, record):
        return not bool(re.match(r"HTTP Request: POST https://api.telegram.org/bot.+:.+/getUpdates", record.getMessage()))

logging.getLogger('httpx').addFilter(HTTPRequestFilter())

try:
    with open('allowed_users.json', 'r') as file:
        allowed_users = json.load(file)
except FileNotFoundError:
    with open('allowed_users.json', 'w') as file:
        file.write('[]')

chatbot_functions = [
        {"type": "function",
         "function": {"name": "generate_image",
                      "description": "Generates an image with the given prompt, returns the url to the image.",
                      "parameters": {
                          "type": "object",
                          "properties": {
                              "prompt": {
                                  "type": "string",
                                  "description": "The prompt describing the image",
                                  }
                              },
                          "required": ["prompt"],
                          }
                      }
         }
] + alarms.chatbot_functions + gcal.chatbot_functions

async def handle_view_calendar(update, context):
    await update.message.reply_text(gcal.get_google_calendar_events_for_today())

async def validate_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user.id in allowed_users:
        await update.message.reply_text("You are not authorized to talk to this bot!")
        raise ApplicationHandlerStop

async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
    """
    Hi! The following commands are available:

    Use /start or /help to see this message
    Use /timer <minutes> <name> [...description] to set a timer
    Use /alarm [--silent] <name> <24-time> [...description] to set an alarm
    Use /cancel <name> to stop and remove an alarm or timer
    Use /jobs to view all alarms and timers
    Use /calendar to view your calendar events for today

    Use `/dev forget` to reset the chatgpt history
    """)

async def handle_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Sorry, I didn't understand that command.")

callback_commands = {} | alarms.callback_commands | voice.callback_commands

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    # CallbackQueries need to always be answered See https://core.telegram.org/bots/api#callbackquery
    await query.answer()
    data = json.loads(query.data)
    await callback_commands[data['cmd']](update, context, data)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await chatgpt.send_message_to_chatgpt(context, update.effective_chat.id, update.effective_message.text, {})

async def handle_dev(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args[0] == "forget":
        await chatgpt.handle_forget(update, context)
    else:
        await update.message.reply_text("Unknown dev command")

async def generate_image(context, chat_id, send_fn, function_args):
    response = chatgpt.chatgpt.images.generate(
            model="dall-e-3",
            prompt=function_args["prompt"],
            size="1024x1024",
            quality="standard",
            n=1)
    url = response.data[0].url
    encoded_url = quote(url, safe='')
    return encoded_url

function_callbacks = {"generate_image": generate_image} | alarms.function_callbacks | gcal.function_callbacks

def main() -> None:
    chatgpt.init(chatbot_functions, function_callbacks)
    with open('telegram.token', 'r') as file:
        token = file.read().strip()
    application = Application.builder().token(token).build()
    application.job_queue.scheduler.add_jobstore(
            PTBSQLAlchemyJobStore(application, url='sqlite:///jobs.sqlite'))
    application.add_handler(TypeHandler(Update, validate_user), -1)
    application.add_handler(CommandHandler(["start", "help"], handle_start))
    application.add_handler(CommandHandler("timer", alarms.handle_set_timer))
    application.add_handler(CommandHandler("alarm", alarms.handle_set_alarm))
    application.add_handler(CommandHandler("cancel", alarms.handle_cancel_job))
    application.add_handler(CommandHandler("jobs", alarms.handle_view_jobs))
    application.add_handler(CommandHandler("calendar", handle_view_calendar))
    application.add_handler(CommandHandler("dev", handle_dev))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.COMMAND, handle_unknown))
    application.add_handler(MessageHandler(filters.VOICE, voice.handle_voice))
    application.add_handler(MessageHandler(filters.TEXT, handle_text))
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
