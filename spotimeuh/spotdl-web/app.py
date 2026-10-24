from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse
import subprocess
import threading
import uuid
import re
from queue import Queue
from html import escape
from urllib.parse import urlparse
import os
import json
import urllib.parse
import urllib.request
from pathlib import Path

import acoustid
import musicbrainzngs
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TDRC, APIC, TCON

ACOUSTID_API_KEY = os.environ.get("ACOUSTID_API_KEY", "")

musicbrainzngs.set_useragent(
    "spotdl",
    "1.0",
    "https://acoustid.org/"
)


def enrich_mp3(filepath: str) -> str:
    """Identifie le morceau et complète ses métadonnées si possible."""
    path = Path(filepath)

    if not path.is_file() or path.suffix.lower() != ".mp3":
        return "Fichier MP3 introuvable pour l'enrichissement."

    try:
        tags = ID3(str(path))
    except Exception:
        tags = ID3()

    # Valeur de repli pour les téléchargements YouTube.
    if not tags.getall("TALB"):
        tags.add(TALB(encoding=3, text="Singles YouTube"))

    if not ACOUSTID_API_KEY:
        tags.save(str(path))
        return "Album par défaut ajouté ; clé AcoustID absente."

    try:
        results = acoustid.match(
            ACOUSTID_API_KEY,
            str(path),
            parse=True
        )

        best_recording_id = None
        best_score = 0.0

        for score, recording_id, title, artist in results:
            if score > best_score:
                best_score = score
                best_recording_id = recording_id

        # Seuil volontairement prudent pour limiter les erreurs.
        if not best_recording_id or best_score < 0.80:
            tags.save(str(path))
            return f"Pas de correspondance fiable (score : {best_score:.2f})."

        recording = musicbrainzngs.get_recording_by_id(
            best_recording_id,
            includes=["artists", "releases"]
        )["recording"]

        title = recording.get("title")
        artists = recording.get("artist-credit", [])
        artist_names = []

        for item in artists:
            if isinstance(item, dict):
                if "artist" in item:
                    artist_names.append(item["artist"].get("name", ""))
                elif "name" in item:
                    artist_names.append(item["name"])

        artist_name = ", ".join(name for name in artist_names if name)

        if title:
            tags.delall("TIT2")
            tags.add(TIT2(encoding=3, text=title))

        if artist_name:
            tags.delall("TPE1")
            tags.add(TPE1(encoding=3, text=artist_name))

        releases = recording.get("release-list", [])
        if releases:
            release = releases[0]
            album = release.get("title")
            date = release.get("date", "")[:4]

            if album:
                tags.delall("TALB")
                tags.add(TALB(encoding=3, text=album))

            if date:
                tags.delall("TDRC")
                tags.add(TDRC(encoding=3, text=date))

            # Récupération de la pochette depuis Cover Art Archive.
            release_id = release.get("id")
            if release_id:
                cover_url = (
                    "https://coverartarchive.org/release/"
                    + release_id
                    + "/front-500"
                )
                try:
                    request = urllib.request.Request(
                        cover_url,
                        headers={"User-Agent": "spotdl/1.0"}
                    )
                    with urllib.request.urlopen(request, timeout=10) as response:
                        image_data = response.read()

                    tags.delall("APIC")
                    tags.add(APIC(
                        encoding=3,
                        mime="image/jpeg",
                        type=3,
                        desc="Cover",
                        data=image_data
                    ))
                except Exception:
                    pass

        tags.save(str(path))
        return f"Métadonnées enrichies (score AcoustID : {best_score:.2f})."

    except Exception as exc:
        try:
            tags.save(str(path))
        except Exception:
            pass
        return f"Enrichissement indisponible : {exc}"

app = FastAPI()

SPOTDL = "/app/.venv/bin/spotdl"
YT_DLP = "/app/.venv/bin/yt-dlp"

jobs = {}
queue = Queue()


def is_youtube_url(url: str) -> bool:
    """Détermine si l'URL provient de YouTube."""
    try:
        hostname = (urlparse(url).hostname or "").lower()
        return (
            hostname == "youtu.be"
            or hostname == "youtube.com"
            or hostname.endswith(".youtube.com")
            or hostname == "youtube-nocookie.com"
            or hostname.endswith(".youtube-nocookie.com")
        )
    except Exception:
        return False


def download_job(job_id: str, url: str):
    jobs[job_id]["status"] = "Téléchargement"

    try:
        if is_youtube_url(url):
            # Téléchargement direct de l'audio de la vidéo YouTube.
            command = [
                YT_DLP,
                "--no-playlist",
                "--no-progress",
                "--newline",
                "--print",
                "after_move:filepath",
                "--extract-audio",
                "--audio-format", "mp3",
                "--audio-quality", "0",
                "--embed-thumbnail",
                "--embed-metadata",
                "--parse-metadata", 
                "%(uploader|)s:%(meta_artist)s",
                "--output", "/music/%(title)s.%(ext)s",
                url,
            ]
        else:
            # Conserver le comportement historique pour Spotify.
            command = [
                SPOTDL,
                "--threads", "1",
                "--output", "/music/{artists} - {title}.{output-ext}",
                "download",
                url,
            ]

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        result_file = None
        error_lines = []

        for line in process.stdout:
            line = line.strip()
            if line.lower().endswith(".mp3") and line.startswith("/music/"):
               result_file = line  
            # Ne conserver que le nom du fichier produit
            if "Destination:" in line:
                result_file = line.split("Destination:", 1)[1].strip()

            # Conserver les erreurs, sans afficher tous les logs techniques
            if "ERROR:" in line or "Error:" in line:
                error_lines.append(line)

        process.wait()

        if process.returncode == 0:
           if is_youtube_url(url) and result_file:
              jobs[job_id]["status"] = "Identification musicale"
              enrichment_result = enrich_mp3(result_file)
              jobs[job_id]["log"] = (
                 f"✅ Fichier : {result_file}\n"
                 f"🎵 {enrichment_result}"
              )
           elif result_file:
              jobs[job_id]["log"] = f"✅ Fichier : {result_file}"
           else:
              jobs[job_id]["log"] = "✅ Téléchargement terminé."
        
           jobs[job_id]["status"] = "Terminé"

        else:
            jobs[job_id]["status"] = "Erreur"
            jobs[job_id]["log"] = (
                "❌ Échec du téléchargement.\n"
                + "\n".join(error_lines[-5:])
                if error_lines
                else "Consulte les logs Docker pour plus de détails."
            )
    except Exception as e:
        jobs[job_id]["status"] = "Erreur"
        jobs[job_id]["log"] = f"❌ Erreur : {e}"

def worker():
    while True:
        job_id = queue.get()

        try:
            if job_id is None:
                break

            job = jobs.get(job_id)

            if job:
                download_job(job_id, job["url"])

        finally:
            queue.task_done()


threading.Thread(target=worker, daemon=True).start()


def render_jobs():
    rows = ""

    for job_id, job in reversed(list(jobs.items())):
        status_class = job["status"].lower().replace(" ", "-")

        rows += f"""
        <div class="job">
            <div class="job-header">
                <div class="url">{escape(job["url"])}</div>
                <span class="status {status_class}">
                    {escape(job["status"])}
                </span>
            </div>
            <pre>{escape(job["log"])}</pre>
        </div>
        """

    return rows


@app.get("/", response_class=HTMLResponse)
def index():
    return f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>SpotDL</title>
        <style>
            * {{ box-sizing: border-box; }}
            body {{
                font-family: system-ui, -apple-system, BlinkMacSystemFont,
                    "Segoe UI", sans-serif;
                margin: 0;
                padding: 32px 20px;
                background: #111;
                color: #eee;
            }}
            .container {{
                width: 100%;
                max-width: 1000px;
                margin: 0 auto;
            }}
            h1 {{ margin: 0 0 24px; font-size: 28px; }}
            h2 {{ margin: 32px 0 16px; font-size: 20px; }}
            textarea {{
                display: block;
                width: 100%;
                min-height: 120px;
                padding: 14px;
                background: #222;
                color: #fff;
                border: 1px solid #444;
                border-radius: 8px;
                resize: vertical;
                font-family: inherit;
                font-size: 16px;
                line-height: 1.5;
                outline: none;
            }}
            textarea:focus {{ border-color: #777; }}
            button {{
                width: 100%;
                margin-top: 10px;
                padding: 13px 20px;
                border: 0;
                border-radius: 8px;
                background: #eee;
                color: #111;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
            }}
            .job {{
                margin-top: 12px;
                padding: 16px;
                background: #1b1b1b;
                border-radius: 8px;
                overflow: hidden;
            }}
            .job-header {{
                display: flex;
                align-items: flex-start;
                justify-content: space-between;
                gap: 16px;
            }}
            .url {{
                min-width: 0;
                overflow-wrap: anywhere;
                word-break: break-word;
            }}
            .status {{
                flex-shrink: 0;
                font-weight: 600;
                white-space: nowrap;
            }}
            .téléchargement {{ color: #ffd166; }}
            .terminé {{ color: #06d6a0; }}
            .erreur {{ color: #ef476f; }}
            .en-attente {{ color: #aaa; }}
            pre {{
                margin: 14px 0 0;
                white-space: pre-wrap;
                overflow-wrap: anywhere;
                color: #999;
                font-size: 13px;
                line-height: 1.4;
            }}
            @media (max-width: 600px) {{
                body {{ padding: 20px 12px; }}
                h1 {{ font-size: 24px; margin-bottom: 20px; }}
                h2 {{ margin-top: 28px; font-size: 18px; }}
                textarea {{ min-height: 110px; padding: 12px; }}
                .job {{ padding: 14px; }}
                .job-header {{ flex-direction: column; gap: 8px; }}
                .status {{ white-space: normal; }}
                pre {{ font-size: 12px; }}
            }}
        </style>
    </head>
    <body>
        <main class="container">
            <h1>🎵 SpotDL</h1>
            <form method="post" action="/download">
                <textarea
                    name="urls"
                    placeholder="Colle une ou plusieurs URLs Spotify / YouTube, une par ligne..."
                    required
                    autocomplete="off"
                    autocorrect="off"
                    autocapitalize="off"
                    spellcheck="false"
                ></textarea>
                <button type="submit">Ajouter à la file</button>
            </form>
            <h2>File d'attente</h2>
            <div id="jobs">{render_jobs()}</div>
            <script>
                async function refreshJobs() {{
                    try {{
                        const response = await fetch("/jobs", {{
                            cache: "no-store"
                        }});
                        if (!response.ok) return;
                        document.getElementById("jobs").innerHTML =
                            await response.text();
                    }} catch (error) {{
                        console.error("Erreur lors de la mise à jour :", error);
                    }}
                }}
                setInterval(refreshJobs, 2000);
            </script>
        </main>
    </body>
    </html>
    """


@app.get("/jobs", response_class=HTMLResponse)
def get_jobs():
    return render_jobs()


@app.post("/download")
def download(urls: str = Form(...)):
    for url in urls.splitlines():
        url = url.strip()

        if not url:
            continue

        job_id = str(uuid.uuid4())

        jobs[job_id] = {
            "url": url,
            "status": "En attente",
            "log": "",
        }

        queue.put(job_id)

    return RedirectResponse("/", status_code=303)
