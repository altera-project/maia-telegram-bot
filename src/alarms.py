from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from zoneinfo import ZoneInfo
import argparse
import chatgpt
import json

def parse_time_string(time_str):
    time_str = time_str.replace(':', '')
    if len(time_str) == 4:
        time_format = "%H%M"
    else:
        raise ValueError("Invalid time format. Time should be in 4 digit 24-hour format.")
    dt = datetime.strptime(time_str, time_format)
    dt = dt.replace(tzinfo=ZoneInfo("America/Los_Angeles"))
    return dt

async def job_timer(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    await context.bot.send_message(job.chat_id, text=f"[SYSTEM]: Ding! {job.data} is over!")
    text = f"A timer named {job.data['name']} for {job.data['time']} minutes is over, respond by informing the user of this fact without referencing this message."
    if job.data['description'] != '':
        text += f"\nThe user wrote the following DESCRIPTION:\n{job.data['description']}"
        text += f"\nIf the user requested external information or actions in the DESCRIPTION, use function calling to do so."
    await chatgpt.send_message_to_chatgpt(context, job.chat_id, text, {})

async def job_alarm(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    text = f"An alarm named {job.data['name']} for today at {job.data['time'].strftime('%H:%m')} is going off, respond by informing the user of this fact without referencing this message."
    if job.data['description'] != '':
        text += f"\nThe user wrote the following description:\n{job.data['description']}"
    opts = {}
    if job.data['silent'] == True:
        opts['disable_notification'] = True
    else:
        await context.bot.send_message(job.chat_id, text=f"[SYSTEM]: Ding! Alarm {job.data} is going off!")
    await chatgpt.send_message_to_chatgpt(context, job.chat_id, text, opts)

def remove_job_if_exists(name: str, context: ContextTypes.DEFAULT_TYPE) -> bool:
    current_jobs = context.job_queue.get_jobs_by_name(name)
    if not current_jobs:
        return False
    for job in current_jobs:
        job.schedule_removal()
    return True

async def set_timer(chat_id, context, send_fn, minutes, name, description):
    try:
        job_name = f"timer:{name}"
        job_data = {"time": minutes, "name": name, "description": description}
        removed = remove_job_if_exists(job_name, context)
        context.job_queue.run_once(job_timer, 60 * minutes, chat_id=chat_id, name=job_name, data=job_data)
        if removed:
            await send_fn("Cleared previous timer with the same name.")
        keyboard = [
                [InlineKeyboardButton("cancel "+job_name, callback_data=json.dumps({"cmd": "cancel", "job_name": job_name}))],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_fn("Timer successfully set! To cancel the timer use the following command:", reply_markup=reply_markup)
    except (IndexError, ValueError):
        await send_fn("Usage: /timer <minutes> <name> <description>")

async def handle_set_timer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Add a job to the queue."""
    chat_id = update.effective_message.chat_id
    minutes = float(context.args[0])
    if minutes < 0:
        await update.effective_message.reply_text("Sorry we can not go back to future!")
        return
    name = context.args[1]
    description = " ".join(context.args[2:])
    await set_timer(chat_id, context, update.effective_message.reply_text, minutes, name, description)


async def set_alarm(chat_id, context, send_fn, time24, name, description, silent):
    try:
        job_name = f"alarm:{name}"
        job_data = {"time": time24, "name": name, "description": description, "silent": silent}
        removed = remove_job_if_exists(job_name, context)
        context.job_queue.run_daily(job_alarm, time24, chat_id=chat_id, name=job_name, data=job_data)
        if removed:
            await send_fn("Cleared previous timer with the same name.")
        keyboard = [
                [InlineKeyboardButton("cancel "+job_name, callback_data=json.dumps({"cmd": "cancel", "job_name": job_name}))],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_fn("Alarm successfully set! To cancel the alarm use the following command:", reply_markup=reply_markup)
    except (IndexError, ValueError, argparse.ArgumentError):
        await send_fn("Usage: /alarm [--silent] <name> <24h-time> <description> ")

async def handle_set_alarm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_message.chat_id
    parser = argparse.ArgumentParser(exit_on_error=False)
    parser.add_argument('--silent', action='store_true', help='Silent, no notification noise if the user is asleep.')
    parser.add_argument('name', help='name of the alarm, used to refer to the alarm in other commands')
    parser.add_argument('time', help='24h time of the alarm')
    parser.add_argument('description', metavar='description', type=str, nargs='+', help='description for the alarm')
    args = parser.parse_args(context.args)
    alarm_time = parse_time_string(args.time)
    description = " ".join(args.description)
    await set_alarm(chat_id, context, update.effective_message.reply_text, alarm_time, args.name, description, args.silent)

async def command_cancel(update, context, data):
    job_name = data['job_name']
    job_removed = remove_job_if_exists(job_name, context)
    text = "Job successfully cancelled!" if job_removed else "Failed to find a job with that name."
    await context.bot.send_message(chat_id=update.effective_message.chat_id, text=text)

callback_commands = {"cancel": command_cancel}

async def handle_cancel_job(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args[0]:
        await update.message.reply_text("Please specify a job name!")
        return
    job_name = context.args[0]
    job_removed = remove_job_if_exists(job_name, context)
    text = "Job successfully cancelled!" if job_removed else "Failed to find a job with that name."
    await update.message.reply_text(text)

async def handle_view_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = str(context.job_queue.jobs())
    await update.message.reply_text(text)

chatbot_functions = [
        {"type": "function",
         "function": {"name": "set_alarm",
                      "description": "Sets an alarm that is triggered daily at a certain time.",
                      "parameters": {
                          "type": "object",
                          "properties": {
                              "name": {
                                  "type": "string",
                                  "description": "The name of the alarm, if not generated by the user come up with one based on the description",
                                  },
                              "time": {
                                  "type": "string",
                                  "description": "24 hour time, for example 0300 or 2345",
                                  },
                              "description": {
                                  "type": "string",
                                  "description": "The user specified description or text for the alarm",
                                  },
                              "silent": {
                                  "type": "boolean",
                                  "description": "If the notification should be silent or quiet so as to not disturb the user"
                                  },
                              },
                          "required": ["name", "time", "description"],
                          }
                      }
         },
        {"type": "function",
         "function": {"name": "set_timer",
                      "description": "Sets a timer that is triggered only once in the specified number of minutes.",
                      "parameters": {
                          "type": "object",
                          "properties": {
                              "name": {
                                  "type": "string",
                                  "description": "The name of the alarm, if not generated by the user come up with one based on the description",
                                  },
                              "time": {
                                  "type": "integer",
                                  "description": "number of minutes in which to trigger the timer, cannot be negative",
                                  },
                              "description": {
                                  "type": "string",
                                  "description": "The user specified description or text for the timer",
                                  }
                              },
                          "required": ["name", "time", "description"],
                          }
                      }
         }
]

async def fcb_set_alarm(context, chat_id, send_fn, function_args):
    time24 = parse_time_string(function_args['time'])
    name = function_args['name']
    description = function_args['description']
    silent = function_args['silent'] or False
    await set_alarm(chat_id, context, send_fn, time24, name, description, silent)
    return 'Alarm set successfully! Do not execute the alarm, just inform the user of this fact.'

async def fcb_set_timer(context, chat_id, send_fn, function_args):
    minutes = function_args['time']
    name = function_args['name']
    description = function_args['description']
    await set_timer(chat_id, context, send_fn, minutes, name, description)
    return 'Timer set successfully! Do not execute the timer, just inform the user of this fact.'

function_callbacks = {
    "set_alarm": fcb_set_alarm,
    "set_timer": fcb_set_timer
}
