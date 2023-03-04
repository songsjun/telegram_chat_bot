import json
import logging
import os
import openai
import requests
from typing import Dict, Any

import telegram
from telegram import Update, ChatAction
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from google.cloud import texttospeech
from google.cloud import speech_v1p1beta1 as speech
from google.cloud import language_v1

# This dictionary will store the chat history for each user
user_chat_history = {}

# Load the Telegram bot token from a secret JSON file
with open(".secret.json") as f:
    config = json.load(f)
    TELEGRAM_BOT_TOKEN = config['TELEGRAM_BOT_TOKEN']
    OPENAI_KEY = config['OPENAI_KEY']
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = config['GOOGLE_CLOUD_KEY_FILE']

def load_chat_history(user_id):
    # Load the chat history from a file
    if user_id not in user_chat_history:
        file_path = f"{user_id}.json"
        if os.path.exists(file_path):
            with open(file_path, "r") as f:
                user_chat_history[user_id] = json.load(f)
        else:
            with open(file_path, "w") as f:
                json.dump([], f)
                user_chat_history[user_id] = []

    return user_chat_history[user_id]

def save_chat_history(user_id):
    # Save the chat history to a file in JSON format
    with open(f"{user_id}.json", "w") as f:
        json.dump(user_chat_history[user_id], f)

def process_reply_message(reply):
    # Extract the AI's reply from the OpenAI-generated text
    if reply is None:
        return ""

    for prefix in ["AI:", "Bot:", "Robot:", "Computer:", "Chatbot:"]:
        pos = reply.find(prefix)
        if pos >= 0:
            reply = reply[pos+len(prefix):]
            break
    reply = reply.strip()
    return reply

def detect_language(text):
    from google.cloud import translate_v2 as translate

    client = translate.Client()
    response = client.detect_language(text)

    return response['language']



def generate_ai_response(user_id):
    openai.api_key = OPENAI_KEY
    if user_id not in user_chat_history:
        user_chat_history[user_id] = []

    response = openai.ChatCompletion.create(
      model="gpt-3.5-turbo",
      messages=user_chat_history[user_id])
    usage = response['usage']['total_tokens']
    utilization = float(usage*100/4096)
    reply_text = response['choices'][0]['message']['content'].strip()
    reply_text = process_reply_message(reply_text)

    return reply_text, utilization

def transcribe_audio(audio_file):
    # Instantiates a client
    client = speech.SpeechClient()

    # Loads the audio into memory
    with open(audio_file, 'rb') as f:
        content = f.read()

    # Specifies the audio file format
    audio = speech.types.RecognitionAudio(content=content)
    
    config = speech.types.RecognitionConfig(
        encoding=speech.types.RecognitionConfig.AudioEncoding.OGG_OPUS,
        sample_rate_hertz=48000,
        audio_channel_count=2,
        language_code='en-US',
        alternative_language_codes='cmn-hans-cn',
        enable_automatic_punctuation=True,
        profanity_filter=True
    )

    # Performs speech recognition on the audio file
    response = client.recognize(config=config, audio=audio)

    # Extracts the transcript from the response
    transcript = ''
    for result in response.results:
        transcript += result.alternatives[0].transcript + ' '

    return transcript

def synthesize_text(language_code, text):
    """Synthesizes speech from the input string of text."""
    from google.cloud import texttospeech

    client = texttospeech.TextToSpeechClient()

    input_text = texttospeech.SynthesisInput(text=text)

    # Note: the voice can also be specified by name.
    # Names of voices can be retrieved with client.list_voices().
    voice = texttospeech.VoiceSelectionParams(
        language_code=language_code,
        ssml_gender=texttospeech.SsmlVoiceGender.FEMALE,
    )

    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3
    )

    response = client.synthesize_speech(
        request={"input": input_text, "voice": voice, "audio_config": audio_config}
    )

    return response.audio_content

def handle_voice(update: Update, context: CallbackContext):
    # Handle an audio message from the user
    user_id = str(update.message.chat_id)
    audio_file_id = update.message.voice.file_id
    load_chat_history(user_id)

    # Send a "typing" indicator while processing the audio file
    context.bot.send_chat_action(chat_id=update.message.chat_id, action=ChatAction.TYPING)

    audio_file = context.bot.get_file(audio_file_id)
    audio_file.download(f"{user_id}.ogg")

    # Transcribe the audio file
    message_text = transcribe_audio(f"{user_id}.ogg")
    # openai.api_key = OPENAI_KEY
    # message_text = openai.Audio.transcribe("whisper-1", open(f"{user_id}.mp3", "rb"))
    print("Human:", message_text)

    # Add the message to the chat history
    user_chat_history[user_id].append({"role": "user", "content": message_text})

    # Generate a response from OpenAI
    reply_text, utilization = generate_ai_response(user_id)
    print("AI:", reply_text)
    tips = "\n[ Chat used:%.2f%% ]" % utilization  

    if 100 - utilization <= 0.01:
        user_chat_history[user_id] = []
        tips = tips + "\nThe chat has been reset"
    else:
        user_chat_history[user_id].append({"role": "assistant", "content": reply_text})

    # Save the chat history to a file
    save_chat_history(user_id)

    # Send the audio response to the user
    language_code = detect_language(reply_text)
    response_audio = synthesize_text(language_code, reply_text)
    context.bot.send_audio(chat_id=update.message.chat_id, audio=response_audio, performer="assistant", title="assistant")
    update.message.reply_text(reply_text+tips)

def handle_text(update: Update, context: CallbackContext):
    # Handle a text message from the user
    user_id = str(update.message.chat_id)
    message_text = update.message.text
    print("Human:", message_text)
    load_chat_history(user_id)

    # Add the message to the chat history
    user_chat_history[user_id].append({"role": "user", "content": message_text})

    # Generate a response from OpenAI
    reply_text, utilization = generate_ai_response(user_id)
    print("AI:", reply_text)
    tips = "\n[ Chat used:%.2f%% ]" % utilization  

    if 100 - utilization <= 0.01:
        user_chat_history[user_id] = []
        tips = tips + "\nThe chat has been reset"
    else:
        user_chat_history[user_id].append({"role": "assistant", "content": reply_text})

    # Save the chat history to a file
    save_chat_history(user_id)

    # Send the audio response to the user
    language_code = detect_language(reply_text)
    response_audio = synthesize_text(language_code, reply_text)
    context.bot.send_audio(chat_id=update.message.chat_id, audio=response_audio, performer="assistant", title="assistant")
    
    # Reply to the user with the AI's response
    update.message.reply_text(reply_text+tips)

def start(update: Update, context: CallbackContext):
    # Start a new chat session with the user
    user_id = str(update.message.chat_id)
    user_chat_history[user_id] = []
    save_chat_history(user_id)
    update.message.reply_text("Hi, I'm your assistant! Let's start a new chat.")

def error_handler(update: Update, context: CallbackContext):
    # Log the error message
    logging.error(f"Update {update} caused error {context.error}")
    # Reply to the user with a generic error message
    try:
        update.message.reply_text("Sorry, something went wrong. Please try again later.")
    except Exception as e:
        logging.error(f"Error sending message: {e}")

def main():
    # Set up the bot and register the audio message handler
    bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
    updater = Updater(token=TELEGRAM_BOT_TOKEN, use_context=True)
    dispatcher = updater.dispatcher
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(MessageHandler(Filters.text, handle_text))
    dispatcher.add_handler(MessageHandler(Filters.voice, handle_voice))
    # dispatcher.add_handler(MessageHandler(Filters.audio, handle_audio))

    # Start the bot
    updater.start_polling()


if __name__ == '__main__':
    main()





