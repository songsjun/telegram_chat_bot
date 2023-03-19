import openai
import os
import json
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app, origins=["http://localhost:8000"])

with open(".secret.json") as f:
    config = json.load(f)
    api_key = config['OPENAI_KEY']
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = config['GOOGLE_CLOUD_KEY_FILE']

def generate_ai_response(user_messages):
    openai.api_key = api_key

    response = openai.ChatCompletion.create(
      model="gpt-3.5-turbo",
      messages=user_messages)
    usage = response['usage']['total_tokens']
    utilization = float(usage*100/4096)
    reply_text = response['choices'][0]['message']['content'].strip()

    return reply_text, utilization

@app.route("/ask", methods=["POST"])
def ask():
    data = request.get_json()
    messages = data["input"]

    response, utilization = generate_ai_response(messages)

    return jsonify({"answer": response, "utilization": utilization})

if __name__ == "__main__":
    app.run(port=5000, debug=True)
