from openai import OpenAI
from telegram import Update
from telegram.ext import ContextTypes
from tts import tts_wav
import alarms
import gcal
import json

state = {"history": []}
chatgpt = OpenAI()

def init(functions, callbacks):
    state["functions"] = functions
    state["callbacks"] = callbacks
    with open('system_prompt.ai.txt', 'r') as file:
        state['system_prompt'] = file.read()
    try:
        with open('history/history.ai.json', 'r') as file:
            state["history"] += json.load(file)
    except FileNotFoundError:
        with open('history/history.ai.json', 'w') as file:
            file.write('[]')

def log_history():
    with open('history/history.ai.json', 'w') as file:
        file.write(json.dumps(state["history"], sort_keys=True, indent=4))

async def handle_forget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state["history"] = []
    with open("history/history.ai.json", "w") as file:
        file.write("[]")
    await bot_send_message(context, update.effective_chat.id, "Hard Reset Successful!", {})

async def function_call(context, chat_id, function_name, function_args):
    print("function_call", function_name, function_args)
    send_fn = lambda text, **opts: context.bot.send_message(chat_id=chat_id, text=text, **opts)
    function_callbacks = state["callbacks"]
    callback = function_callbacks[function_name]
    return await callback(context, chat_id, send_fn, function_args)

def chatgpt_send(raw_messages, functions=None):
    messages = [{"role": "system", "content": state["system_prompt"]}] + raw_messages
    kwargs = {'model': "gpt-4-1106-preview",
              'messages': messages}
    if functions: kwargs['tools'] = functions
    return chatgpt.chat.completions.create(**kwargs)

def bot_send_message(context, chat_id, text, opts):
    if 'parse_mode' not in opts:
        opts['parse_mode'] = "Markdown"
    return context.bot.send_message(chat_id=chat_id, text=text, **opts)

async def send_message_to_chatgpt(context: ContextTypes.DEFAULT_TYPE, chat_id, message: str, opts) -> None:
    state["history"].append({"role": "user", "content": message})
    log_history()
    response = chatgpt_send(state["history"], functions = state["functions"])
    print("RESPONSE", response)
    ensure_history_within_limits(response.usage.total_tokens)
    response_message = response.choices[0].message
    if response_message.tool_calls:
        tcs = [{"id": tc.id, "function": {"name": tc.function.name, "arguments": tc.function.arguments}, "type": tc.type}
               for tc in response_message.tool_calls]
        state['history'].append({"role": "assistant", "tool_calls": tcs})
        log_history()
        for tool_call in response_message.tool_calls:
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)
            function_call_result = await function_call(context, chat_id, function_name, function_args)
            state['history'].append({"tool_call_id": tool_call.id,
                                     "role": "tool",
                                     "name": function_name,
                                     "content": function_call_result})
            log_history()
        function_response = chatgpt_send(state['history'])
        content = function_response.choices[0].message.content
        state["history"].append({"role": "assistant", "content": content})
        log_history()
        await bot_send_message(context, chat_id, content, opts)
    elif response_message.content:
        state['history'].append({"role": "assistant", "content": response_message.content})
        log_history()
        await bot_send_message(context, chat_id, response_message.content, opts)
        await context.bot.send_voice(chat_id=chat_id, voice=tts_wav(response_message.content))
    else:
        print("TODO unknown response:", response_message)

def ensure_history_within_limits(tokens_used):
    print('[tokens used]:', tokens_used)
    MAX_TOKENS_THRESHOLD = 8000
    PERCENTAGE_TO_CLEAR = 0.25
    if tokens_used > MAX_TOKENS_THRESHOLD:
        num_elements_to_remove = int(len(state["history"]) * PERCENTAGE_TO_CLEAR)
        state["history"] = state["history"][num_elements_to_remove:]
        log_history()
