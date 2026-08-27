# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
from zoneinfo import ZoneInfo

from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.genai import types


MODEL = "gemini-3.6-flash"


async def generate_memories_callback(callback_context: CallbackContext):
    await callback_context.add_session_to_memory()
    return None


def get_weather(query: str) -> str:
    """Simulates a web search. Use it get information on weather.

    Args:
        query: A string containing the location to get weather information for.

    Returns:
        A string with the simulated weather information for the queried location.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        return "It's 60 degrees and foggy."
    return "It's 90 degrees and sunny."


def get_current_time(query: str) -> str:
    """Simulates getting the current time for a city.

    Args:
        query: The name of the city to get the current time for.

    Returns:
        A string with the current time information.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        tz_identifier = "America/Los_Angeles"
    else:
        return f"Sorry, I don't have timezone information for query: {query}."

    tz = ZoneInfo(tz_identifier)
    now = datetime.datetime.now(tz)
    return f"The current time for query {query} is {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}"


FIRESTORE_PROJECT_ID = "qwiklabs-gcp-03-4e4c0736bba1"
GCS_BUCKET_NAME = "guitar-transcriber-assets-qwiklabs-gcp-03-4e4c0736bba1"


def _get_firestore_client():
    from google.cloud import firestore
    return firestore.Client(project=FIRESTORE_PROJECT_ID)


def search_songbook(query: str = "") -> str:
    """Search or list songs in the Firestore songbook database.

    Args:
        query: Optional string to filter songs by title or artist.

    Returns:
        JSON string or list of matching songs in the songbook.
    """
    import json
    db = _get_firestore_client()
    docs = db.collection("songs").stream()
    results = []
    q = query.lower()
    for doc in docs:
        data = doc.to_dict()
        if not q or q in data.get("title", "").lower() or q in data.get("artist", "").lower():
            results.append(data)
    if not results:
        return f"No songs found matching '{query}' in the songbook database."
    return json.dumps(results, indent=2)


def get_song_from_songbook(title_or_id: str) -> str:
    """Fetch details for a specific song from the Firestore songbook database.

    Args:
        title_or_id: The title or ID of the song to retrieve.

    Returns:
        JSON string with full song details (chords, key, tuning, lyrics).
    """
    import json
    db = _get_firestore_client()
    doc_ref = db.collection("songs").document(title_or_id.lower().replace(" ", "_"))
    doc = doc_ref.get()
    if doc.exists:
        return json.dumps(doc.to_dict(), indent=2)
    docs = db.collection("songs").stream()
    for d in docs:
        data = d.to_dict()
        if title_or_id.lower() in data.get("title", "").lower():
            return json.dumps(data, indent=2)
    return f"Song '{title_or_id}' not found in the songbook database."


def save_song_to_songbook(
    title: str,
    artist: str,
    key: str,
    chords: list[str],
    tuning: str = "Standard",
    lyrics_snippet: str = "",
    audio_file: str = "",
) -> str:
    """Save or update a transcribed song into the Firestore songbook database.

    Args:
        title: Title of the song.
        artist: Artist name.
        key: Musical key (e.g. 'E Major').
        chords: List of chord names (e.g. ['E5', 'A5', 'B5']).
        tuning: Guitar tuning (e.g. 'Standard', 'Drop D').
        lyrics_snippet: Short snippet of lyrics.
        audio_file: Path to audio file if applicable.

    Returns:
        Confirmation message.
    """
    db = _get_firestore_client()
    song_id = title.lower().replace(" ", "_").replace("'", "")
    doc_data = {
        "id": song_id,
        "title": title,
        "artist": artist,
        "key": key,
        "chords": chords,
        "tuning": tuning,
        "lyrics_snippet": lyrics_snippet,
        "audio_file": audio_file,
    }
    db.collection("songs").document(song_id).set(doc_data)
    return f"Successfully saved '{title}' by {artist} into Firestore songbook database!"


def transcribe_audio_file(audio_path: str) -> str:
    """Decodes an MP3 audio file to transcribe song details, lyrics, key, and guitar chords using Gemini.

    Args:
        audio_path: Path to the MP3 audio file on disk (e.g. '/config/Downloads/recordings/04_I_love_rock_and_roll.mp3').

    Returns:
        String containing transcribed lyrics, guitar chords, key, tempo, and song title.
    """
    import os
    from google import genai
    from google.genai import types

    if not os.path.exists(audio_path):
        return f"Error: Audio file not found at path '{audio_path}'."

    client = genai.Client(vertexai=True, project=FIRESTORE_PROJECT_ID, location="us-east1")
    with open(audio_path, "rb") as f:
        audio_bytes = f.read()

    prompt = (
        "Listen to this audio recording carefully and transcribe it for a guitarist:\n"
        "1. Song Title and Artist\n"
        "2. Musical Key\n"
        "3. Estimated Tempo (BPM)\n"
        "4. Guitar Chord Progression (list of chord names)\n"
        "5. Transcribed Lyrics with chord markers placed above lines where chords change."
    )

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            types.Part.from_bytes(
                data=audio_bytes,
                mime_type="audio/mp3",
            ),
            prompt,
        ],
    )
    return response.text


def generate_html_leadsheet(
    title: str,
    artist: str,
    key: str,
    chords: list[str],
    sections: list[dict],
    tuning: str = "Standard",
) -> str:
    """Generates a beautifully styled HTML lead sheet with chords placed directly above words, section indicators (Verse 1, Chorus, Bridge, Intro), and saves it to a local HTML file.

    Args:
        title: Title of the song.
        artist: Artist name.
        key: Musical key signature.
        chords: List of unique chords used in the song.
        sections: List of section dicts. Each section dict has:
                  - 'name': Section label (e.g., 'Verse 1', 'Chorus', 'Intro', 'Bridge')
                  - 'type': 'verse', 'chorus', 'intro', 'bridge', or 'outro'
                  - 'lines': List of lines. Each line is a list of dicts: [{'chord': 'E5', 'word': 'Hey '}, ...]
        tuning: Guitar tuning (e.g., 'Standard', 'Drop D').

    Returns:
        Confirmation message with path to the generated HTML file.
    """
    import os

    os.makedirs("leadsheets", exist_ok=True)
    file_slug = title.lower().replace(" ", "_").replace("'", "")
    output_filename = f"leadsheets/{file_slug}.html"

    chords_str = ", ".join(chords) if isinstance(chords, list) else str(chords)

    sections_html = ""
    for sec in (sections if isinstance(sections, list) else []):
        if not isinstance(sec, dict):
            continue
        sec_type = str(sec.get("type", "verse")).lower()
        sec_name = str(sec.get("name", sec_type.capitalize()))
        badge_class = f"badge-{sec_type}" if sec_type in ("intro", "verse", "chorus", "bridge", "outro") else "badge-verse"

        lines_html = ""
        lines_list = sec.get("lines", [])
        if isinstance(lines_list, list):
            for line in lines_list:
                pairs_html = ""
                if isinstance(line, str):
                    pairs_html += f'<div class="chord-word-pair"><span class="chord"></span><span class="word">{line}</span></div>'
                elif isinstance(line, list):
                    for pair in line:
                        if isinstance(pair, dict):
                            chord = pair.get("chord", "")
                            word = pair.get("word", "")
                        elif isinstance(pair, str):
                            chord = ""
                            word = pair
                        else:
                            chord = ""
                            word = str(pair)
                        pairs_html += f'<div class="chord-word-pair"><span class="chord">{chord}</span><span class="word">{word}</span></div>'
                lines_html += f'<div class="lyric-line">{pairs_html}</div>\n'

        sections_html += f'''
    <div class="section">
      <span class="badge {badge_class}">{sec_name}</span>
      {lines_html}
    </div>'''

    html_document = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} - Lead Sheet</title>
  <style>
    body {{ font-family: system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; padding: 2rem; margin: 0; }}
    .container {{ max-width: 850px; margin: 0 auto; background: #1e293b; border-radius: 16px; padding: 2.5rem; box-shadow: 0 20px 25px -5px rgba(0,0,0,0.5); border: 1px solid #334155; }}
    .header {{ border-bottom: 2px solid #334155; padding-bottom: 1.5rem; margin-bottom: 2rem; }}
    h1 {{ font-size: 2.25rem; font-weight: 800; color: #38bdf8; margin: 0 0 0.5rem 0; letter-spacing: -0.02em; }}
    .artist {{ font-size: 1.25rem; color: #cbd5e1; font-weight: 600; margin-bottom: 1rem; }}
    .meta-bar {{ display: flex; flex-wrap: wrap; gap: 0.75rem; font-size: 0.9rem; color: #94a3b8; }}
    .meta-item {{ background: #0f172a; padding: 0.4rem 0.85rem; border-radius: 8px; border: 1px solid #334155; }}
    .section {{ margin-bottom: 1.75rem; background: #0f172a; padding: 1.5rem; border-radius: 12px; border: 1px solid #334155; }}
    .badge {{ display: inline-block; padding: 0.35rem 0.85rem; border-radius: 9999px; font-size: 0.8rem; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase; margin-bottom: 1rem; }}
    .badge-intro {{ background: rgba(139, 92, 246, 0.2); color: #c084fc; border: 1px solid #8b5cf6; }}
    .badge-verse {{ background: rgba(59, 130, 246, 0.2); color: #60a5fa; border: 1px solid #3b82f6; }}
    .badge-chorus {{ background: rgba(236, 72, 153, 0.2); color: #f472b6; border: 1px solid #ec4899; }}
    .badge-bridge {{ background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid #f59e0b; }}
    .badge-outro {{ background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid #10b981; }}
    .lyric-line {{ display: flex; flex-wrap: wrap; margin-bottom: 0.85rem; line-height: 1.1; }}
    .chord-word-pair {{ display: inline-flex; flex-direction: column; margin-right: 0.4rem; align-items: flex-start; margin-bottom: 0.25rem; }}
    .chord {{ font-weight: 800; color: #f43f5e; font-size: 1rem; min-height: 1.25rem; font-family: monospace; }}
    .word {{ font-size: 1.15rem; color: #f1f5f9; white-space: pre; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>{title}</h1>
      <div class="artist">by {artist}</div>
      <div class="meta-bar">
        <div class="meta-item"><strong>Key:</strong> {key}</div>
        <div class="meta-item"><strong>Tuning:</strong> {tuning}</div>
        <div class="meta-item"><strong>Chords:</strong> {chords_str}</div>
      </div>
    </div>
    {sections_html}
  </div>
</body>
</html>'''

    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(html_document)

    gcs_url = ""
    try:
        from google.cloud import storage
        storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(f"leadsheets/{file_slug}.html")
        blob.upload_from_filename(output_filename, content_type="text/html")
        gcs_url = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/leadsheets/{file_slug}.html"
    except Exception as e:
        gcs_url = f"GCS Upload Note: {e}"

    abs_local = os.path.abspath(output_filename)
    return (
        f"Successfully generated HTML lead sheet!\n"
        f"- Public Chrome URL: {gcs_url}\n"
        f"- Local File URL: file://{abs_local}"
    )


def open_in_chrome(url_or_path: str) -> str:
    """Launches Google Chrome to view an HTML lead sheet or public URL.

    Args:
        url_or_path: HTTP URL or local file path to open in Google Chrome.

    Returns:
        Status message confirming browser launch.
    """
    import os
    import subprocess
    target = url_or_path if url_or_path.startswith("http") else f"file://{os.path.abspath(url_or_path)}"
    try:
        subprocess.Popen(["google-chrome", target])
        return f"Successfully opened {target} in Google Chrome!"
    except Exception:
        try:
            subprocess.Popen(["xdg-open", target])
            return f"Successfully opened {target} in default web browser!"
        except Exception as e:
            return f"Could not launch browser automatically: {e}. You can open {target} manually."


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=(
        "You are a helpful AI assistant designed to provide accurate and useful information. "
        "You remember stated user preferences, personal details, and facts across conversations. "
        "CRITICAL MEMORY REQUIREMENT: You MUST record and remember every song title, chord progression, "
        "tuning, key signature, capo position, and transcribed lyrics discussed or generated for the user. "
        "Use your transcription tool (transcribe_audio_file) to process local audio files. "
        "When transcribing or generating lead sheets, ALWAYS ALSO call generate_html_leadsheet to create an "
        "HTML lead sheet with chords placed directly over words and section indicators (Verse 1, Chorus, Intro, Bridge). "
        "Use open_in_chrome to automatically open lead sheets in Google Chrome for the user when requested. "
        "Use your songbook tools (search_songbook, get_song_from_songbook, save_song_to_songbook) to query "
        "and persist songs in the Firestore database."
    ),
    tools=[
        PreloadMemoryTool(),
        transcribe_audio_file,
        generate_html_leadsheet,
        open_in_chrome,
        search_songbook,
        get_song_from_songbook,
        save_song_to_songbook,
        get_weather,
        get_current_time,
    ],
    after_agent_callback=generate_memories_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)

