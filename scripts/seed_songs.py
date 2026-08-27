# Copyright 2026 Google LLC
# Seed script for populating the Firestore 'songs' collection for Guitar Chord & Lyrics Transcriber.

from google.cloud import firestore

PROJECT_ID = "qwiklabs-gcp-03-4e4c0736bba1"
COLLECTION_NAME = "songs"

SEED_SONGS = [
    {
        "id": "i_love_rock_and_roll",
        "title": "I Love Rock 'N' Roll",
        "artist": "Joan Jett & the Blackhearts",
        "key": "E Major",
        "tempo_bpm": 94,
        "tuning": "Standard",
        "chords": ["E5", "A5", "B5"],
        "audio_file": "/config/Downloads/recordings/04_I_love_rock_and_roll.mp3",
        "lyrics_snippet": "I saw him dancin' there by the record machine, I knew he must a been about seventeen...",
        "difficulty": "Beginner",
    },
    {
        "id": "the_middle",
        "title": "The Middle",
        "artist": "Jimmy Eat World",
        "key": "D Major",
        "tempo_bpm": 126,
        "tuning": "Drop D",
        "chords": ["D5", "A5", "G5"],
        "audio_file": "/config/Downloads/recordings/05_the_middle.mp3",
        "lyrics_snippet": "Hey, don't write yourself off yet, it's only in your head you feel left out...",
        "difficulty": "Beginner",
    },
    {
        "id": "gold_on_the_ceiling",
        "title": "Gold on the Ceiling",
        "artist": "The Black Keys",
        "key": "G Major",
        "tempo_bpm": 130,
        "tuning": "Standard",
        "chords": ["G5", "Bb5", "C5", "F5"],
        "audio_file": "/config/Downloads/recordings/00 Gold_On_The_Ceiling.mp3",
        "lyrics_snippet": "They wanna get my, gold on the ceiling, un-ey-eye, eye...",
        "difficulty": "Intermediate",
    },
    {
        "id": "superstition",
        "title": "Superstition",
        "artist": "Stevie Wonder",
        "key": "Eb Minor",
        "tempo_bpm": 100,
        "tuning": "Eb Standard",
        "chords": ["Ebm7", "Ab7", "Bb7", "B7"],
        "audio_file": "/config/Downloads/recordings/13_superstition.mp3",
        "lyrics_snippet": "Very superstitious, writings on the wall, very superstitious, ladders bout to fall...",
        "difficulty": "Intermediate",
    },
]


def seed_database():
    print(f"Connecting to Firestore with project '{PROJECT_ID}'...")
    db = firestore.Client(project=PROJECT_ID)
    collection_ref = db.collection(COLLECTION_NAME)

    for song in SEED_SONGS:
        doc_id = song["id"]
        doc_ref = collection_ref.document(doc_id)
        doc_ref.set(song)
        print(f"✅ Seeded song '{song['title']}' ({doc_id}) into Firestore.")

    print("\n🎉 Seeding complete!")


if __name__ == "__main__":
    seed_database()
