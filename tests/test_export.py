"""Copying finished clips into a folder of your choice, with a text file holding the title and post text. Runs
against the code directly, with its own temporary folders; nothing is posted anywhere."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["PEAKCUT_DATA"] = tempfile.mkdtemp(prefix="pc-export-")
os.environ["DATABASE_URL"] = ""
for k in ("PEAKCUT_TITLE_TEMPLATE", "PEAKCUT_POST_TEMPLATE", "PEAKCUT_EXPORT_DIR"):
    os.environ.pop(k, None)
sys.path.insert(0, ".")
from studio import config, creators, export  # noqa: E402

fails = []


def check(name, got, want=True):
    ok = got == want
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"\n   got  {got!r}\n   want {want!r}"))
    ok or fails.append(name)


config.ACCOUNTS = False
work = Path(tempfile.mkdtemp(prefix="pc-export-job-"))
(work / "clips").mkdir()
(work / "clips" / "clip03.mp4").write_bytes(b"fake video one")
out = Path(tempfile.mkdtemp(prefix="pc-export-out-")) / "GTA 6"

creator = dict(creators.DEFAULTS, id="c1", name="GTA clips", export_folder=str(out))
logged = []
creators.get = lambda cid: creator
creators.log = lambda cid, text: logged.append(text)

job = {"id": "1a2b3c4d5e", "creator": "c1", "dir": str(work)}
clip = {"id": "clip03", "file": "clip03.mp4", "title": "Police chase: ends in the ocean?",
        "description": "He drove straight off the pier to lose the cops.", "hashtags": ["gta6"], "hook": "NO WAY"}

export.on_clip_made(job, clip)
stem = "Police chase ends in the ocean (clip03-1a2b3c)"
check("the clip is copied into the folder, which is made if missing", (out / f"{stem}.mp4").read_bytes(), b"fake video one")
check("a text file beside it holds the title and post text, worded by the templates", (out / f"{stem}.txt").read_text(encoding="utf-8"),
      "Title: Police chase: ends in the ocean? in GTA 6 😳 #shorts\n\n"
      "He drove straight off the pier to lose the cops.\nFollow for daily GTA 6 clips 🌴\n#GTA6 #GTAVI #Gaming #Shorts\n")
check("no half-written files are left behind", sorted(p.suffix for p in out.iterdir()), [".mp4", ".txt"])

(work / "clips" / "clip03.mp4").write_bytes(b"fake video two")
clip["title"] = "Biggest crash of the night"
export.on_clip_made(job, clip)
new = "Biggest crash of the night (clip03-1a2b3c)"
check("a re-made clip with a new title replaces the old pair", sorted(p.name for p in out.iterdir()), [f"{new}.mp4", f"{new}.txt"])
check("...with the new video", (out / f"{new}.mp4").read_bytes(), b"fake video two")

export.on_clip_made(job, clip)
check("making it again just overwrites", len(list(out.iterdir())), 2)

creator["export_folder"] = ""
config.EXPORT_DIR = str(out / "standard")
check("with no folder of its own, a creator uses the standard folder", export.folder_for(creator), str(out / "standard"))
config.EXPORT_DIR = ""
check("with neither, nothing is copied", export.folder_for(creator), "")

for bad, why in (("clips/gta", "whole path"),):
    try:
        export.check_folder(bad)
        check(f"a folder like {bad!r} is refused", False)
    except ValueError as e:
        check(f"a folder like {bad!r} is refused: {why}", why in str(e))
check("an empty folder turns copying off", export.check_folder("  "), "")
check("a good folder is made and kept whole", export.check_folder(str(out / "new one")), str((out / "new one").resolve()))
check("it is saved with the creator's settings", creators._clean({"export_folder": str(out)})["export_folder"], str(out.resolve()))

config.ACCOUNTS = True
creator["export_folder"] = str(out)
check("on a shared site a creator's own folder is ignored", export.folder_for(creator), "")
try:
    export.check_folder(str(out))
    check("on a shared site no folder may be chosen", False)
except ValueError:
    check("on a shared site no folder may be chosen", True)
config.ACCOUNTS = False

blocked = Path(tempfile.mkdtemp(prefix="pc-export-file-")) / "a file"
blocked.write_text("not a folder")
creator["export_folder"] = str(blocked)
logged.clear()
export.on_clip_made(job, clip)
check("a folder that can't be written is noted in the log, and the clip is not harmed", any("Couldn't copy" in t for t in logged))

print("ALL PASSED" if not fails else f"{len(fails)} failed")
sys.exit(1 if fails else 0)
