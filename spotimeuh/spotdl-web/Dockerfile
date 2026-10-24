FROM spotimeuh-spotdl:latest

USER root

RUN apt-get update && apt-get install -y --no-install-recommends \
    libchromaprint-tools \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/spotdl-web

COPY app.py .

RUN /app/.venv/bin/python -m pip install --no-cache-dir \
    fastapi \
    uvicorn \
    python-multipart \
    musicbrainzngs \
    pyacoustid \
    mutagen

EXPOSE 8800

ENTRYPOINT []

CMD ["/app/.venv/bin/uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8800"]
