"""Quick test for Gemini API credentials."""
import os
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    print("GEMINI_API_KEY not found in .env")
    exit(1)

genai.configure(api_key=api_key)
model = genai.GenerativeModel("gemini-2.0-flash-lite")

response = model.generate_content("Say 'Hello from Gemini!' in exactly 5 words.")
print(f"Gemini API: {response.text.strip()}")
