# Cursor Prompt: Commit/Stream → Story Pipeline

You are auditing and extending an open-source "commit/stream → story" pipeline.

## Primary Goals (local-first, Python-first)

1) **Generate a STORY for each merged PR using local Python:**
   - Build a story packet (JSON) from GitHub events and Twitch clips.
   - Optionally auto-record a short OBS explainer (9:16 scene) without touching stream state.
   - Render a ≤60s vertical video (intro → clip/b-roll → outro) using ffmpeg/moviepy.
   - Draft a daily blog (Markdown) and a weekly recap from all stories.

2) **Control notifications and approvals via Discord:**
   - Use **webhooks** for notifications (merge cards, prompts) - fire-and-forget
   - Use **slash commands** for control (`/record start|extend|stop <pr>`, `/clip now`, `/why <pr>`, `/post daily|weekly`, `/status`)
   - Keep everything idempotent and safe (don't close OBS; don't toggle streaming).

3) **Use Cloudflare APIs only when required:**
   - Cloudflare R2 for clip/transcript storage (already present).
   - Cloudflare Worker endpoints we own (already present).
   - Cloudflare AI for optional text cleanup and title suggestions (bounded inputs, deterministic prompts).

## Architecture Principles

- **Local Python** handles deterministic, reproducible work (schemas, rendering, ffmpeg, OBS)
- **Cloudflare AI** is a nice-to-have assist (title cleanup, summaries) - keep optional with `CF_AI_ENABLED` flag
- **Strict boundary**: Cloudflare AI only takes small bounded inputs (8-word titles, short summaries)
- **Async rendering**: Don't block blog generation waiting for video completion
- **Immediate packet creation** on PR merge, **batched publishing** for heavy lifting

## Guardrails

- Never quit or start OBS streaming; only start/stop local recording.
- Add `OBS_DRY_RUN=true` mode for testing without touching OBS.
- Do not spam Discord; coalesce multiple merges within 5 minutes.
- Treat Twitch clips as optional; if missing, fall back to b-roll (code diffs/screenshots).
- All times internal = UTC; render as Asia/Bangkok for user-facing content.
- Story packets generated immediately, rendering/publishing batched.

## Deliverables

- `story_schema.py` (pydantic models)
- `packet_builder.py` (daily JSON → story packets)
- `obs_helper.py` (safe start/stop record + scene restore)
- `discord_bot.py` (slash commands + webhook notifications)
- `webhook_server.py` (FastAPI; GitHub PR merged → story packet)
- `renderer.py` (moviepy+ffmpeg; async queue; burns captions; 1080x1920)
- `blog_writer.py` (Markdown from packets)
- `config/.env.example` (document all env vars)
- `scripts/dev: run_local.sh`, `smoke_tests.py`
- `docs/OPERATIONS.md` and `docs/DECISIONS.md`
