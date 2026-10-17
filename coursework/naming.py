"""Naming conventions, in one place so every tool agrees.

  Course folder   short course name, no professor or term code:
                  "Product Management (Christopher LaSala) FA2026" -> "Product Management"
  Session prefix  "S02 Pitney Bowes.pdf": added only when a Canvas calendar event
                  for session 2 links that exact file. Never guessed.
  Transcripts     "Transcripts/S07 Transcript.txt"
  Assignments     "Canvas_Assignments.md" at the course root, rewritten each sync.
"""

import os
import re

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".wmv", ".webm"}


def sanitize(name):
    """Safe as a file or folder name on macOS, Windows and Google Drive."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return re.sub(r"\s{2,}", " ", name) or "untitled"


def course_folder_name(canvas_name):
    """Strip the term code, professor and any leading list number Canvas adds."""
    name = re.sub(r"\s+[A-Z]{2}\d{4}\s*$", "", canvas_name.strip())   # " FA2026"
    while re.search(r"\([^()]*\)\s*$", name):                          # " (Prof Name)"
        name = re.sub(r"\s*\([^()]*\)\s*$", "", name)
    name = re.sub(r"^\d+\s*-\s*", "", name)                            # "1 - Trade…"
    return sanitize(name)


def clean_file_name(display_name, real_filename=""):
    """Canvas display name -> local file name.

    - Strips the hex upload prefix some professors' tools add
      ("f883baa5113f__2.1 - Word2Vec.xlsb" -> "2.1 - Word2Vec.xlsb").
    - Restores a missing extension from the real filename
      ("Session01 MBA FA25" over "Session01+MBA+FA25.pdf" -> "Session01 MBA FA25.pdf"),
      otherwise the file will not open.
    """
    name = sanitize(re.sub(r"^[0-9a-f]{8,}__", "", display_name))
    if not os.path.splitext(name)[1]:
        ext = os.path.splitext(real_filename or "")[1]
        if re.fullmatch(r"\.[A-Za-z0-9]{1,5}", ext):
            name += ext
    return name


_SESSION_WORD = re.compile(r"\b(?:session|class|lecture|day)\s*#?\s*0*(\d{1,2})(?!\d)", re.I)
# "2. Topic", "S05 Topic", and course-coded ones like "USHS4: Topic"
_LEADING_NUM = re.compile(r"^\s*(?:[A-Z]{0,6}S\s*)?0*(\d{1,2})\s*[:.\-–)_ ]")


def session_number(title):
    """Session number stated in a calendar-event or lesson title, else None.

    Handles "Session 3: …", "Negotiations Session 1: …", "Class 4_ Topic",
    "S05 …", "USHS4: …" and "2. Topic". Returns None rather than guessing.
    """
    if not title:
        return None
    m = _SESSION_WORD.search(title) or _LEADING_NUM.match(title)
    return int(m.group(1)) if m else None


def has_session_prefix(name):
    return bool(re.match(r"^\s*(S\d{1,2}\b|session\s*\d)", name, re.I))


def with_session_prefix(name, n):
    if n is None or has_session_prefix(name) or re.search(r"syllabus", name, re.I):
        return name
    return f"S{n:02d} {name}"


def unique_path(path):
    """Never overwrite a different file that already sits at the destination."""
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    n = 2
    while os.path.exists(f"{stem} ({n}){ext}"):
        n += 1
    return f"{stem} ({n}){ext}"
