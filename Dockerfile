FROM python:3.11-slim

# Installa ffmpeg, chromaprint (per AcoustID) e libsndfile (per librosa)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg libchromaprint-tools libsndfile1 wget && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Installa le dipendenze Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia il codice sorgente e i template
COPY src/ /app/src/
COPY templates/ /app/templates/

# Configurazione default porte
EXPOSE 8020

# Comando di avvio FastAPI
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8020"]
