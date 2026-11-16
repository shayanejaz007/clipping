"""How posts are worded: the title and text templates, filled in for each clip. Runs against the code directly;
nothing is posted anywhere."""
import os
import sys
import tempfile

os.environ["PEAKCUT_DATA"] = tempfile.mkdtemp(prefix="pc-templates-")
os.environ["DATABASE_URL"] = ""
for k in ("PEAKCUT_TITLE_TEMPLATE", "PEAKCUT_POST_TEMPLATE"):
    os.environ.pop(k, None)          # the built-in templates
sys.path.insert(0, ".")
from studio import config, creators, posting  # noqa: E402

fails = []


def check(name, got, want):
    ok = got == want
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"\n   got  {got!r}\n   want {want!r}"))
    ok or fails.append(name)


CLIP = {"title": "Police chase ends in the ocean", "description": "He drove straight off the pier to lose the cops.",
        "hashtags": ["gta6", "chase"], "hook": "NO WAY"}
plain = dict(creators.DEFAULTS, name="GTA clips")

check("with no templates set, the title is the clip's own, for any kind of stream", posting._title(CLIP, plain),
      "Police chase ends in the ocean")
check("...and the text is its description and its own hashtags", posting._caption(CLIP, plain),
      "He drove straight off the pier to lose the cops.\n\n#gta6 #chase")

config.TITLE_TEMPLATE = "{title} in GTA 6 😳 #shorts"            # a channel that is always about one game
config.POST_TEMPLATE = "{description}\nFollow for daily GTA 6 clips 🌴\n#GTA6 #GTAVI #Gaming #Shorts"
check("a title template from .env is used", posting._title(CLIP, plain), "Police chase ends in the ocean in GTA 6 😳 #shorts")
check("a text template from .env is used", posting._caption(CLIP, plain),
      "He drove straight off the pier to lose the cops.\nFollow for daily GTA 6 clips 🌴\n#GTA6 #GTAVI #Gaming #Shorts")

footer = dict(plain, post_footer="Clipped from the stream")
check("the creator's extra line still goes at the end", posting._caption(CLIP, footer).endswith("\n\nClipped from the stream"), True)

own = dict(plain, title_template="{hook}! {title}", post_template="{description}\n{hashtags}\n{footer}", post_footer="Credit: me")
check("a creator's own title template wins", posting._title(CLIP, own), "NO WAY! Police chase ends in the ocean")
check("a creator's own text template wins, with every blank", posting._caption(CLIP, own),
      "He drove straight off the pier to lose the cops.\n#gta6 #chase\nCredit: me")
check("an unknown blank is left as typed", posting._fill("{title} {nope}", CLIP, plain), "Police chase ends in the ocean {nope}")
check("braces in a template never break it", posting._fill("{ {title} }", CLIP, plain), "{ Police chase ends in the ocean }")
check("a missing description leaves no gap at the start", posting._caption({"title": "X"}, plain),
      "Follow for daily GTA 6 clips 🌴\n#GTA6 #GTAVI #Gaming #Shorts")
long = dict(CLIP, title="x" * 120)
check("the title never passes YouTube's 100 characters", len(posting._title(long, plain)), 100)

config.TITLE_TEMPLATE, config.POST_TEMPLATE = "", ""
check("with no templates at all, the title is the clip's own", posting._title(CLIP, plain), CLIP["title"])
check("...and the text is as before", posting._caption(CLIP, plain),
      "He drove straight off the pier to lose the cops.\n\n#gta6 #chase")

saved = creators._clean({"title_template": "  {title}\n in GTA 6  ", "post_template": "{description}\r\nFollow\r\n"})
check("a saved title template is one line", saved["title_template"], "{title} in GTA 6")
check("a saved text template keeps its lines", saved["post_template"], "{description}\nFollow")

print("ALL PASSED" if not fails else f"{len(fails)} failed")
sys.exit(1 if fails else 0)
