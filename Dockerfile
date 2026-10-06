# Image du backend (API FastAPI + scripts d'indexation).
# Ollama n'est pas dans l'image : il tourne sur l'hôte (accès GPU direct),
# joint via OLLAMA_BASE_URL (voir docker-compose.yml).
FROM python:3.11-slim
# progression affichée en direct (journaux Docker et Jenkins), pas seulement à la fin
ENV PYTHONUNBUFFERED=1

# Tesseract (OCR des textes scannés) : nécessaire pour scripts/indexer_tout.sh
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-fra tesseract-ocr-ara \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY rules/ rules/
COPY scripts/ scripts/
COPY data/raw_pdfs/ data/raw_pdfs/
RUN mkdir -p output

EXPOSE 8000
# Pas de --reload en production ; un seul processus (la file de génération
# vit dans le processus de l'API).
CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]
