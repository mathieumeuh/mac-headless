FROM spotdl/spotify-downloader:latest

USER root

# Deno
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl unzip \
    && curl -fsSL https://deno.land/install.sh | sh \
    && ln -s /root/.deno/bin/deno /usr/local/bin/deno \
    && rm -rf /var/lib/apt/lists/*

# Environnement SpotDL + Deno
ENV PATH="/root/.deno/bin:/app/.venv/bin:${PATH}"

# yt-dlp nightly
RUN /app/.venv/bin/python -m ensurepip --upgrade \
    && /app/.venv/bin/python -m pip install --upgrade --pre yt-dlp
