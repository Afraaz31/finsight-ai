"""Level 0 check: confirm the Gemini key works and see which models it can use."""
from google import genai

from backend.config import GEMINI_API_KEY, GEMINI_MODEL, require

client = genai.Client(api_key=require("GEMINI_API_KEY", GEMINI_API_KEY))

print("Models this key can see:")
for model in client.models.list():
    print(" ", model.name)

reply = client.models.generate_content(
    model=GEMINI_MODEL, contents="Reply with exactly five words: the key works."
)
print("\nTest reply:", reply.text)
