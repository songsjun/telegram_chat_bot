import os
import json
import html
import openai
from telegram import Update
from telegram.ext import Updater, MessageHandler, Filters, CommandHandler
from langdetect import detect
from google.cloud import translate_v2 as translate

# Global variable to store the configuration data
data = {}

CONFIG_FILE = '.forward.json'

# Load Configuration
def load_config():
    with open(CONFIG_FILE, 'r') as file:
        global data
        data = json.load(file)

# Detect if text is Chinese
def is_chinese(text):
    try:
        return detect(text) == 'zh-cn'
    except:
        return False

# Translate text to Chinese using ChatGPT
def translate_to_chinese(text):
    response = openai.Completion.create(
      model="gpt-4-0613",
      prompt=f"You are a translator familiar with Internet technology and crypto technology. Please translate the following English text to Chinese: \"{text}\"",
      max_tokens=1500
    )
    return response.choices[0].text.strip()

def translate_to_chineseViaGoogle(text):
    client = translate.Client()
    result = client.translate(text, target_language="zh-CN")
    return result.get('translatedText')

# Command to set the current chat as the destination chat
def sethost(update: Update, context):
    chat_id = update.message.chat_id
    data['DESTINATION_CHAT_ID'] = chat_id
    with open(CONFIG_FILE, 'w') as file:
        json.dump(data, file)
    update.message.reply_text("This chat has been set as the destination chat.")

# Command to list all source chats
def list_chats(update: Update, context):
    message = "Source chats:\n"
    for chat_id, chat_name in data.get('SOURCE_CHATS', {}).items():
        message += f"{chat_id}: {chat_name}\n"
    update.message.reply_text(message)

# Command to pause forwarding from a specific chat
def pause(update: Update, context):
    chat_id = int(context.args[0])
    if 'PAUSED_CHATS' not in data:
        data['PAUSED_CHATS'] = []
    data['PAUSED_CHATS'].append(chat_id)
    data['PAUSED_CHATS'] = list(set(data['PAUSED_CHATS']))  # Ensure uniqueness
    with open(CONFIG_FILE, 'w') as file:
        json.dump(data, file)
    update.message.reply_text(f"Paused forwarding messages from chat {chat_id}.")

# Command to resume forwarding from a specific chat
def resume(update: Update, context):
    chat_id = int(context.args[0])
    if 'PAUSED_CHATS' in data and chat_id in data['PAUSED_CHATS']:
        data['PAUSED_CHATS'].remove(chat_id)
        with open(CONFIG_FILE, 'w') as file:
            json.dump(data, file)
        update.message.reply_text(f"Resumed forwarding messages from chat {chat_id}.")
    else:
        update.message.reply_text(f"Chat {chat_id} was not paused.")

# Command to pause forwarding from all chats
def pauseall(update: Update, context):
    data['PAUSED_CHATS'] = list(data.get('SOURCE_CHATS', {}).keys())
    with open(CONFIG_FILE, 'w') as file:
        json.dump(data, file)
    update.message.reply_text("Paused forwarding messages from all chats.")

# Command to resume forwarding from all chats
def resumeall(update: Update, context):
    data['PAUSED_CHATS'] = []
    with open(CONFIG_FILE, 'w') as file:
        json.dump(data, file)
    update.message.reply_text("Resumed forwarding messages from all chats.")


def forward_message(update: Update, context):
    message = update.message
    chat_id = message.chat_id
    chat_name = html.escape(message.chat.title)
    user_name = html.escape(message.from_user.first_name or message.from_user.username)
    message_text = html.escape(message.text)

    
    # If the message is not in Chinese, translate it
    if not is_chinese(message_text):
        translated_text = translate_to_chineseViaGoogle(message_text)
        message_text = f"{message_text}\n\n翻译: {translated_text}"
    
    formatted_message = f"<b>{chat_name}</b> - <i>{user_name}</i>:\n\n{message_text}"
    # Check if the chat is paused
    if chat_id in data.get('PAUSED_CHATS', []):
        return

    # Forward the message
    context.bot.send_message(chat_id=data['DESTINATION_CHAT_ID'], text=formatted_message, parse_mode="HTML")

    # Save the source chat ID and name to the config
    if 'SOURCE_CHATS' not in data:
        data['SOURCE_CHATS'] = {}
    data['SOURCE_CHATS'][str(chat_id)] = chat_name
    with open(CONFIG_FILE, 'w') as file:
        json.dump(data, file)


def forward_message_v1(update: Update, context):
    message = update.message
    chat_id = message.chat_id
    chat_name = message.chat.title
    user_name = message.from_user.first_name
    message_text = message.text

    # If the message is not in Chinese, translate it
    if not is_chinese(message_text):
        translated_text = translate_to_chineseViaGoogle(message_text)
        message_text = f"{message_text}\n\n翻译: {translated_text}"

    # Check if the chat is paused
    if chat_id in data.get('PAUSED_CHATS', []):
        return

    # Forward the message
    context.bot.send_message(chat_id=data['DESTINATION_CHAT_ID'], text=message_text)

    # Save the source chat ID and name to the config
    if 'SOURCE_CHATS' not in data:
        data['SOURCE_CHATS'] = {}
    data['SOURCE_CHATS'][str(chat_id)] = chat_name
    with open(CONFIG_FILE, 'w') as file:
        json.dump(data, file)

def main():
    load_config()

    updater = Updater(token=data['TELEGRAM_BOT_TOKEN'])
    dp = updater.dispatcher

    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = data['GOOGLE_CLOUD_KEY_FILE']
    openai.api_key = data['OPENAI_API_KEY']

    # Register the command handlers
    dp.add_handler(CommandHandler("sethost", sethost))
    dp.add_handler(CommandHandler("list", list_chats))
    dp.add_handler(CommandHandler("pause", pause, pass_args=True))
    dp.add_handler(CommandHandler("resume", resume, pass_args=True))
    dp.add_handler(CommandHandler("pauseall", pauseall))
    dp.add_handler(CommandHandler("resumeall", resumeall))

    # Handle incoming messages
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, forward_message))
    
    # Start the Bot
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
