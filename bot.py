
    import os
import time
import requests
from google import genai

TOKEN = os.environ.get("BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

client = genai.Client(api_key=GEMINI_API_KEY)
URL = f"https://api.telegram.org/bot{TOKEN}"


def send_message(chat_id, text):
  requests.post(f"{URL}/sendMessage", json={"chat_id": chat_id, "text": text})


def main():
  offset = 0
  print("Бот запущено...")
  while True:
    try:
      response = requests.get(f"{URL}/getUpdates", params={"offset": offset, "timeout": 30})
      data = response.json()
      for result in data.get("result", []):
        offset = result["update_id"] + 1
        message = result.get("message")
        if message and "text" in message:
          chat_id = message["chat"]["id"]
          text = message["text"]

          # Відповідь через Gemini
          try:
            chat_response = client.models.generate_content(
                model="gemini-2.5-flash", contents=text
            )
            reply = chat_response.text
          except Exception as e:
            reply = "Помилка обробки запиту."

          send_message(chat_id, reply)
    except Exception as e:
      print("Помилка:", e)
      time.sleep(5)


if __name__ == "__main__":
  main()
