"""Automation (every new clip posted for you, with captions written like a person) and the Claude account card.
Runs against the code directly; nothing is posted anywhere and no AI or Claude program is asked."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["PEAKCUT_DATA"] = tempfile.mkdtemp(prefix="pc-auto-")
os.environ["DATABASE_URL"] = ""
os.environ["PEAKCUT_ACCOUNTS"] = "0"
sys.path.insert(0, ".")
from studio import accounts, ai, automation, brain, config, ctx, export, posting  # noqa: E402

fails = []


def check(name, got, want):
    ok = got == want
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"\n   got  {got!r}\n   want {want!r}"))
    ok or fails.append(name)


def refused(fn):
    try:
        fn()
    except ValueError:
        return True
    return False


ctx.set_uid("owner_test")
check("automation starts off", automation.settings()["on"], False)
check("it can't be turned on with nowhere to post", refused(lambda: automation.save({"on": True})), True)

accounts._write("accounts.json", [{"id": "yt1", "platform": "youtube", "name": "My channel", "added": 0},
                                  {"id": "tt1", "platform": "tiktok", "name": "@me", "added": 0}])
s = automation.save({"on": True, "accounts": ["yt1", "tt1", "made-up"], "gap_min": "45", "daily_cap": 500,
                     "min_score": -3, "voice": "  chill  ", "always_tags": "#GTA6, Gaming", "nonsense": 1})
check("only accounts that are really connected are kept", s["accounts"], ["yt1", "tt1"])
check("numbers are kept within sense", (s["gap_min"], s["daily_cap"], s["min_score"]), (45, 100, 0))
check("text is tidied", s["voice"], "chill")
check("unknown settings are ignored", "nonsense" in s, False)
check("the always-added tags each get one #", automation.tags_line(s), "#GTA6 #Gaming")
check("settings are kept after a restart", automation.settings()["gap_min"], 45)

accounts._write("accounts.json", [{"id": "yt1", "platform": "youtube", "name": "My channel", "added": 0}])
check("a disconnected account drops out", automation.settings()["accounts"], ["yt1"])
accounts._write("accounts.json", [{"id": "yt1", "platform": "youtube", "name": "My channel", "added": 0},
                                  {"id": "tt1", "platform": "tiktok", "name": "@me", "added": 0}])
automation.save({"accounts": ["yt1", "tt1"], "min_score": 60})

folder = Path(tempfile.mkdtemp(prefix="pc-auto-out-")) / "clips"
check("a clip folder can be chosen", automation.save({"folder": str(folder)})["folder"], str(folder.resolve()))
check("...and clips without a creator go there", export.folder_for(None), str(folder.resolve()))
check("a creator's own folder still wins", export.folder_for({"export_folder": "D:\\Mine"}), "D:\\Mine")
check("a relative folder is refused", refused(lambda: automation.save({"folder": "clips"})), True)

# a new clip with no creator: automation queues it, spaced by its own rules
queued = []
posting.enqueue = lambda job, clip, ids, now=False, rules=None: queued.append((ids, rules["gap_min"], rules["daily_cap"])) or [1]
job = {"id": "j1", "creator": "", "title": "Stream", "clips": []}
posting.on_clip_ready(job, {"id": "c1", "score": 80})
check("a good clip is queued for the ticked accounts", queued, [(["yt1", "tt1"], 45, 100)])
queued.clear()
posting.on_clip_ready(job, {"id": "c2", "score": 40})
check("a clip under the score is not posted", queued, [])
automation.save({"on": False})
posting.on_clip_ready(job, {"id": "c3", "score": 95})
check("nothing is posted with automation off", queued, [])

# captions written like a person: the AI's answer is cleaned, cached on the clip, and the templates take over without it
calls = []
brain.human_caption = lambda clip, platform, *a: calls.append(platform) or {
    "title": "bro really drove into the ocean", "caption": "this is why i don't let him drive", "hashtags": ["gta6", "gaming"]}
posting.jobs.save = lambda j: None
clip = {"id": "c1", "title": "Police chase ends in the ocean", "description": "x", "hashtags": []}
automation.save({"human_captions": True, "always_tags": "GTA6 Shorts"})
t, cap = posting._human(job, clip, {"name": "me"}, "tiktok")
check("the AI's title is used", t, "bro really drove into the ocean")
check("the caption ends with its tags, plus yours without repeats", cap, "this is why i don't let him drive\n\n#gta6 #gaming #Shorts")
posting._human(job, clip, {"name": "me"}, "tiktok")
check("it is written once per clip and platform, so a retry posts the same words", calls, ["tiktok"])
automation.save({"human_captions": False})
check("with human captions off, the templates are used", posting._human(job, clip, {"name": "me"}, "youtube"), None)

real = sys.modules["studio.brain"]
import importlib  # noqa: E402
real = importlib.reload(real)
config.ai_ready = lambda: False
check("with no AI set up, no caption is invented", real.human_caption(clip, "youtube"), {})

# the Claude account card: what Claude Code reports is passed on, nothing else
ai.claude_cli = lambda: ""
got = ai.claude_account(fresh=True)
check("without Claude Code it says so", (got["installed"], got["signed_in"]), (False, False))
check("connecting without Claude Code explains what to do", refused(ai.claude_login), True)

print("ALL PASSED" if not fails else f"{len(fails)} failed")
sys.exit(1 if fails else 0)
