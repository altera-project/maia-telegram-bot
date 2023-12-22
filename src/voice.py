from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import chatgpt
import json
import whisper

whisper_model = None
def audio_to_text(audio_file):
    global whisper_model
    if whisper_model == None:
        whisper_model = whisper.load_model("small.en")
    result = whisper_model.transcribe(audio_file)
    return result['text']

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    voice_file = await context.bot.get_file(update.message.voice.file_id)
    path = '/tmp/'+voice_file.file_unique_id
    await voice_file.download_to_drive(path+'.oga')
    transcription = audio_to_text(path+'.oga')
    with open(path+'.txt', 'w') as file:
        file.write(transcription)
    await update.message.reply_text("I heard:")
    await update.message.reply_text(transcription)
    keyboard = [
            [InlineKeyboardButton("Yes", callback_data=json.dumps({"cmd": "voice", "path": path+'.txt'}))],
            [InlineKeyboardButton("No", callback_data=json.dumps({"cmd": "voice"}))],
            ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Is that right?", reply_markup=reply_markup)

async def command_voice(update, context, data):
    query = update.callback_query
    if 'path' in data:
        await query.edit_message_text(text="Selected: Yes")
        with open(data['path'], 'r') as file:
            transcription = file.read()
        await chatgpt.send_message_to_chatgpt(context, update.effective_chat.id, transcription, {})
    else:
        await query.edit_message_text(text="Selected: No")
        await update.message.reply_text("Please try again.")

callback_commands = {"voice": command_voice}
