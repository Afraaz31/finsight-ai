# FinSight AI on Hugging Face Spaces (Docker, free CPU tier).
# One container runs both parts: FastAPI on 127.0.0.1:8000 (internal) and Streamlit on :7860 (public).
# Built by scripts/deploy_space.py, which also copies in the ready-made data (search index, SEC figures,
# saved answers, the 4 fictional sample files). The Gemini key is a Space secret, never in the image.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/home/user \
    HF_HOME=/home/user/.cache/huggingface \
    PUBLIC_DEMO=true \
    OLLAMA_ENABLED=false \
    RATE_LIMIT_PER_MINUTE=20 \
    DAILY_LLM_CALL_LIMIT=150

RUN useradd -m -u 1000 user
WORKDIR /home/user/app

# CPU-only PyTorch first (the default wheel bundles ~2 GB of GPU libraries this Space can't use)
COPY --chown=user requirements.txt .
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch==2.15.0 \
 && pip install -r requirements.txt

USER user
# Download the embedding model at build time, so the first question doesn't wait for it
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY --chown=user . .
RUN sed -i 's/\r$//' start.sh && chmod +x start.sh

EXPOSE 7860
CMD ["./start.sh"]
