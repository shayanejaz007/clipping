"""Copying finished clips into a folder of your choice, each with a text file holding its title and description.

    PEAKCUT_EXPORT_DIR   a folder every creator's clips are copied into (a creator's own folder, set on their page
                         under Posting, wins)

For each clip two files land side by side, named after the clip:

    Police chase ends in the ocean (clip03-1a2b3c).mp4
    Police chase ends in the ocean (clip03-1a2b3c).txt      Title: ... then the post text

The title and text are worded with the same templates as posting (studio/posting.py), so what is in the folder is
exactly what would be posted. When a clip is re-made, its two files are replaced; if its title changed, the old
pair is removed so the folder never holds two copies of one clip. A folder of your own is only offered when PeakCut
runs on your own computer (accounts off): on a shared site, nobody may write into the server's folders."""
import os
import re
import shutil
from pathlib import Path

from . import config, creators

_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f#]+')       # characters Windows, macOS or Linux won't take in a name


def folder_for(creator) -> str:
    """The folder this creator's clips go to, or "" for none."""
    own = (creator or {}).get("export_folder") or ""
    if own and not config.ACCOUNTS:
        return own
    return config.EXPORT_DIR


def check_folder(raw: str) -> str:
    """A folder typed on a creator's page, made whole and checked; "" turns the folder off."""
    raw = str(raw or "").strip().strip('"').strip("'")
    if not raw:
        return ""
    if config.ACCOUNTS:
        raise ValueError("A clip folder can only be chosen when PeakCut runs on your own computer.")
    p = Path(os.path.expanduser(raw))
    if not p.is_absolute():
        raise ValueError("Give the whole path of the folder, for example D:\\Clips or /Users/you/Clips.")
    try:
        p.mkdir(parents=True, exist_ok=True)
        probe = p / ".peakcut-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as e:
        raise ValueError(f"PeakCut can't write into that folder ({e.strerror or e}). Choose another one.") from None
    return str(p.resolve())[:500]


def _stem(job, clip) -> str:
    name = _BAD.sub(" ", clip.get("title") or clip.get("hook") or "Clip")
    name = re.sub(r"\s+", " ", name).strip(" .")[:80] or "Clip"
    return f"{name} ({clip['id']}-{str(job['id'])[:6]})"


def text_for(clip, creator) -> str:
    """What goes in the clip's text file: the post title, then the post text, as the posting templates word them."""
    from . import posting
    return f"Title: {posting._title(clip, creator)}\n\n{posting._caption(clip, creator)}\n"


def _replace(src: Path, dest: Path, data: str = None):
    """Write next to the final name, then swap it in, so a half-copied clip never sits in the folder."""
    tmp = dest.with_name(dest.name + ".part")
    if data is None:
        shutil.copyfile(src, tmp)
    else:
        tmp.write_text(data, encoding="utf-8")
    os.replace(tmp, dest)


def on_clip_made(job, clip):
    """Called every time a clip finishes rendering (the first time and after each re-make)."""
    creator = creators.get(job["creator"]) or dict(creators.DEFAULTS, name="clips")
    where = folder_for(creator)
    if not where or not clip.get("file"):
        return
    src = Path(job["dir"]) / "clips" / clip["file"]
    try:
        out = Path(where)
        out.mkdir(parents=True, exist_ok=True)
        stem = _stem(job, clip)
        old = clip.get("exported") or {}
        if old.get("folder") == str(out) and old.get("stem") and old["stem"] != stem:
            for ext in (".mp4", ".txt"):             # the title changed: the old pair goes
                (out / (old["stem"] + ext)).unlink(missing_ok=True)
        _replace(src, out / (stem + ".mp4"))
        _replace(src, out / (stem + ".txt"), text_for(clip, creator))
        clip["exported"] = {"folder": str(out), "stem": stem}
        creators.log(job["creator"], f"Copied to your clip folder: {stem}.mp4")
    except OSError as e:
        creators.log(job["creator"], f"Couldn't copy the clip to {where}: {e.strerror or e}. Check the folder under Posting.")
