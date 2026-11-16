"""Automation: what happens to every new clip without you pressing anything.

Set on the Automation page. For each finished clip ClipForge can
  - copy it into your clip folder (an .mp4 with a .txt beside it), and
  - post it to the YouTube, Instagram and TikTok accounts you tick, spaced out so it looks like a person posting,
    with a title and caption the AI writes fresh for each platform in a natural voice.

A creator who has their own posting set up (on their page, under Posting) keeps their own rules; this covers every
other clip, including videos you paste in without a creator. Saved per person in their accounts folder."""
import threading

from . import accounts, export

_lock = threading.Lock()
DEFAULTS = {"on": False, "accounts": [], "human_captions": True, "gap_min": 30, "daily_cap": 6, "min_score": 60,
            "folder": "", "voice": "", "always_tags": ""}


def settings() -> dict:
    saved = accounts._read("automation.json", {})
    s = {**DEFAULTS, **(saved if isinstance(saved, dict) else {})}
    have = {a["id"] for a in accounts.list_accounts()}
    s["accounts"] = [a for a in s.get("accounts") or [] if a in have]     # a disconnected account drops out
    return s


def save(patch: dict) -> dict:
    with _lock:
        s = settings()
        for k, v in (patch or {}).items():
            if k not in DEFAULTS:
                continue
            if k in ("on", "human_captions"):
                v = bool(v)
            elif k == "accounts":
                have = {a["id"] for a in accounts.list_accounts()}
                v = [str(a) for a in (v if isinstance(v, list) else []) if str(a) in have]
            elif k == "gap_min":
                v = max(0, min(24 * 60, int(v)))
            elif k == "daily_cap":
                v = max(1, min(100, int(v)))
            elif k == "min_score":
                v = max(0, min(100, int(v)))
            elif k == "folder":
                v = export.check_folder(v)
            else:
                v = str(v or "").strip()[:300]
            s[k] = v
        if s["on"] and not s["accounts"] and not s["folder"]:
            raise ValueError("Tick at least one account to post to, or choose a clip folder, before turning automation on.")
        accounts._write("automation.json", s)
        return s


def tags_line(s: dict) -> str:
    """The tags you always want added, each with one # in front."""
    words = [w.lstrip("#") for w in str(s.get("always_tags") or "").replace(",", " ").split() if w.strip("#")]
    return " ".join("#" + w for w in words)
