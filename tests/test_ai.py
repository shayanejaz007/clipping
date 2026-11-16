"""The AI layer, with the network replaced: every kind of service is asked correctly and its answer is read
correctly. Nothing leaves this machine and no key is needed."""
import json
import os
import sys
import tempfile

os.environ["PEAKCUT_DATA"] = tempfile.mkdtemp(prefix="pc-ai-")
os.environ["DATABASE_URL"] = ""
os.environ.update(PEAKCUT_AI_PROVIDER="gemini", PEAKCUT_AI_MODELS="model-a, model-b", PEAKCUT_AI_KEY="test-key-123456", PEAKCUT_AI_BASE_URL="")
sys.path.insert(0, ".")
from studio import ai, auth, brain, config, ctx, db, usage  # noqa: E402

db.init()
fails = []


def check(name, ok, extra=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  {extra}" if extra and not ok else ""))
    ok or fails.append(name)


class Reply:
    def __init__(self, status, data):
        self.status_code, self._data, self.text = status, data, json.dumps(data)

    def json(self):
        return self._data


CLIP = {"start": 1, "end": 20, "score": 80, "hook": "WOW", "title": "t", "description": "d", "hashtags": ["a"], "reason": "r"}
seen = []


def fake_post(url, json=None, headers=None, timeout=None, **_k):  # noqa: A002
    seen.append((url, json, headers or {}))
    if url.endswith(":generateContent"):
        return Reply(200, {"candidates": [{"content": {"parts": [{"text": globals()["json_text"]([CLIP])}]}}],
                           "usageMetadata": {"promptTokenCount": 100, "totalTokenCount": 130}})
    if url.endswith("/chat/completions"):
        if "temperature" in json:                      # a model that refuses an extra setting: asked again without it
            return Reply(400, {"error": {"message": "temperature is not supported"}})
        return Reply(200, {"choices": [{"message": {"content": "```json\n" + globals()["json_text"]({"items": [CLIP]}) + "\n```"}}],
                           "usage": {"prompt_tokens": 90, "completion_tokens": 20}})
    if url.endswith("/messages"):
        return Reply(200, {"content": [{"type": "text", "text": "Here you go: " + globals()["json_text"]({"items": [CLIP]})}],
                           "usage": {"input_tokens": 70, "output_tokens": 10}})
    return Reply(404, {})


def json_text(x):
    return json.dumps(x)


ai.httpx.post = fake_post


def use(provider, base=""):
    config.AI_PROVIDER, config.AI_BASE_URL = provider, base
    seen.clear()


use("gemini")
out, sent, wrote = ai.call("model-a", "hello", brain.SCHEMA)
check("gemini: answer and tokens", out == [CLIP] and (sent, wrote) == (100, 30), str((out, sent, wrote)))
check("gemini: key in the header, schema passed as is", seen[0][2].get("x-goog-api-key") == "test-key-123456"
      and seen[0][1]["generationConfig"]["responseSchema"] is brain.SCHEMA and seen[0][0].endswith("/model-a:generateContent"))

for name, host in (("openai", "api.openai.com"), ("xai", "api.x.ai"), ("grok", "api.x.ai"), ("groq", "api.groq.com"), ("openrouter", "openrouter.ai")):
    use(name)
    out, sent, wrote = ai.call("model-a", "hello", brain.SCHEMA)
    check(f"{name}: answer unwrapped from a code fence, tokens read", out == [CLIP] and (sent, wrote) == (90, 20), str((out, sent, wrote)))
    check(f"{name}: right address, key as a bearer token", host in seen[0][0] and seen[0][2].get("Authorization") == "Bearer test-key-123456")
check("a refused extra setting is dropped and asked again", len(seen) == 2 and "temperature" not in seen[1][1])
check("the schema is told in the prompt for chat models", '"type": "array"' in seen[1][1]["messages"][0]["content"])

use("anthropic")
out, sent, wrote = ai.call("model-a", "hello", brain.SCHEMA)
check("anthropic: answer found inside a sentence, tokens read", out == [CLIP] and (sent, wrote) == (70, 10), str((out, sent, wrote)))
check("anthropic: key and version headers", seen[0][2].get("x-api-key") == "test-key-123456" and "anthropic-version" in seen[0][2])

use("custom", "http://127.0.0.1:1234/v1")
out, _s, _w = ai.call("model-a", "hello", brain.SCHEMA)
check("custom: uses the address from settings", seen[0][0] == "http://127.0.0.1:1234/v1/chat/completions" and out == [CLIP])

use("custom")
check("custom without an address is not ready", not ai.ready())
use("nonsense")
check("an unknown provider is not ready", not ai.ready())
use("ollama")
os.environ["PEAKCUT_AI_KEY"] = ""
config._kept.clear()
check("ollama needs no key", ai.ready() and ai.label().startswith("Ollama"))
out, _s, _w = ai.call("model-a", "hello", brain.SCHEMA)
check("ollama: no key header is sent", "Authorization" not in seen[0][2] and out == [CLIP])
use("gemini")
check("gemini without a key is not ready", not ai.ready())

# ---- Claude through the owner's own plan: a stand-in for the claude program records how it was asked
fake_dir = tempfile.mkdtemp(prefix="pc-fake-claude-")
fake_log = os.path.join(fake_dir, "asked.json")
fake = os.path.join(fake_dir, "claude.py")
with open(fake, "w", encoding="utf-8") as f:
    f.write(f"""import json, os, sys
prompt = sys.stdin.read()
json.dump({{"args": sys.argv[1:], "prompt": prompt, "cwd": os.getcwd(), "api_key": os.environ.get("ANTHROPIC_API_KEY"),
           "token": os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")}}, open({fake_log!r}, "w"))
mode = os.environ.get("FAKE_CLAUDE", "ok")
if mode == "login":
    print(json.dumps({{"type": "result", "subtype": "success", "is_error": True, "result": "Not logged in · Please run /login"}}))
elif mode == "limit":
    print(json.dumps({{"type": "result", "subtype": "success", "is_error": True, "result": "Claude usage limit reached. Your limit will reset at 5pm"}}))
else:
    print(json.dumps({{"type": "result", "subtype": "success", "is_error": False, "result": "```json\\n" + json.dumps({{"items": [{json.dumps(CLIP)}]}}) + "\\n```",
                      "usage": {{"input_tokens": 50, "cache_read_input_tokens": 10, "cache_creation_input_tokens": 5, "output_tokens": 12}}}}))
""")
if os.name == "nt":
    runner = os.path.join(fake_dir, "claude.cmd")
    open(runner, "w").write(f'@"{sys.executable}" "{fake}" %*\n')
else:
    runner = os.path.join(fake_dir, "claude")
    open(runner, "w").write(f'#!/bin/sh\nexec "{sys.executable}" "{fake}" "$@"\n')
    os.chmod(runner, 0o755)

os.environ["PEAKCUT_AI_KEY"] = ""
config._kept.clear()
os.environ["ANTHROPIC_API_KEY"] = "sk-should-not-be-used"
config.CLAUDE_CLI = runner
was_accounts, config.ACCOUNTS = config.ACCOUNTS, False   # your own computer: no sign-in
use("claude-code")
check("claude-code needs no key and no address", ai.ready() and "plan" in ai.label())
check("claude-code: the model list needs no network", ai.list_models("claude-code") == ["sonnet", "haiku", "opus"])
out, sent, wrote = ai.call("sonnet", "hello", brain.SCHEMA)
asked = json.load(open(fake_log))
check("claude-code: answer read, tokens added up", out == [CLIP] and (sent, wrote) == (65, 12), str((out, sent, wrote)))
a = asked["args"]
check("claude-code: asked once, as JSON, with the chosen model", a[:3] == ["-p", "--output-format", "json"] and a[a.index("--model") + 1] == "sonnet")
check("claude-code: every tool is switched off", a[a.index("--tools") + 1] == "" and "--strict-mcp-config" in a)
check("claude-code: the prompt goes in on stdin with the schema", asked["prompt"].startswith("hello") and '"type": "array"' in asked["prompt"])
check("claude-code: an API key in the environment is not passed on, so the plan is used", asked["api_key"] is None and asked["token"] is None)
check("claude-code: runs in an empty folder of its own", "peakcut-claude-" in asked["cwd"] and not os.path.exists(asked["cwd"]))
os.environ["PEAKCUT_AI_KEY"] = "a-key-meant-for-another-service"
config._kept.clear()
ai.call("haiku", "hello", brain.SCHEMA)
check("claude-code: no key of ClipForge's is ever handed to Claude Code", json.load(open(fake_log))["token"] is None and ai.key() == "")
saved = ai.save("claude-code", "sonnet, haiku", "", "pasted-by-mistake-123456")
stored = json.load(open(os.path.join(os.environ["PEAKCUT_DATA"], "ai.json")))
check("claude-code: saving keeps no key at all", stored["key"] == "" and not saved["has_key"] and saved["ready"], str(stored))
config.ACCOUNTS = True
try:
    ai.save("claude-code", "sonnet")
    check("claude-code: refused on a shared site", False)
except ValueError as e:
    check("claude-code: refused on a shared site", "own use" in str(e))
check("claude-code: not offered and not ready on a shared site", not ai.ready()
      and all(x["id"] != "claude-code" for x in ai.public()["providers"]))
config.ACCOUNTS = False
os.remove(os.path.join(os.environ["PEAKCUT_DATA"], "ai.json"))
for mode, word in (("login", "/login"), ("limit", "refills by itself")):
    os.environ["FAKE_CLAUDE"] = mode
    try:
        ai.call("sonnet", "hello", brain.SCHEMA)
        check(f"claude-code: {mode} is an error", False)
    except ai.AIError as e:
        check(f"claude-code: {mode} explained in plain words", word in ai.explain(e), ai.explain(e))
os.environ.pop("FAKE_CLAUDE")
config.CLAUDE_CLI = os.path.join(fake_dir, "missing")
try:
    ai.call("sonnet", "hello", brain.SCHEMA)
    check("claude-code: missing program is an error", False)
except ai.AIError as e:
    check("claude-code: a missing program says to install it", "isn't installed" in ai.explain(e), ai.explain(e))
config.CLAUDE_CLI, config.ACCOUNTS = "", was_accounts
os.environ.pop("ANTHROPIC_API_KEY")

os.environ["PEAKCUT_AI_KEY"] = "test-key-123456"
config._kept.clear()
use("gemini")

# ---- the whole path: a call is made for a user and shows up in their usage, and only theirs
u1, _ = auth._create("ai-one@example.com", "One", password_hash="x")
u2, _ = auth._create("ai-two@example.com", "Two", password_hash="x")
words = [{"w": f"word{i}", "s": i * 0.5, "e": i * 0.5 + 0.4} for i in range(120)]
with ctx.as_user(u1.id):
    usage.set_context(None, "A test video")
    import numpy as np
    clips, info = brain.find_clips(words, np.zeros(60), 60.0, title="T", uploader="U")
    check("clips come back through the whole path", len(clips) == 1 and clips[0]["hook"] == "WOW" and info["model"] == "model-a", str((clips, info)))
    s = usage.summary({})
    check("the call is in this user's usage", s["calls_total"] == 1 and s["tokens_total"] == 130 and s["recent"][0]["where"] == "A test video", str(s))
    check("usage says which AI is set", s["ready"] and s["provider"] == "Gemini" and s["model"] == "model-a")
with ctx.as_user(u2.id):
    check("another user sees none of it", usage.summary({})["calls_total"] == 0)

print("ALL PASSED" if not fails else f"{len(fails)} failed")
import shutil  # noqa: E402
db.engine.dispose()
shutil.rmtree(os.environ["PEAKCUT_DATA"], ignore_errors=True)
sys.exit(1 if fails else 0)
