# Reimflow

## 2026-10 platform upgrade (payments excluded)

Reimflow now includes a persistent community service in `platform_api.py` with
SQLite accounts, secure session cookies, personal profiles, contributor points,
favorites, Flow Challenge personal scores, licensed audio uploads, account
deletion and data export, human approval queues, reports, per-user blocking,
and server-restricted administrator/tester roles. Browser UI integration is in
`platform.js` / `platform.css`. No fake rankings or beats are seeded.

Audio posts start **pending**, and community posts are not published to others
until approved. Users can see their own pending posts. The beat/audio storage
directory is persistent under the same mounted STRATO data volume.

Email verification and password reset are implemented but require SMTP settings
`REIMFLOW_SMTP_HOST`, `REIMFLOW_SMTP_PORT`, `REIMFLOW_SMTP_USER`,
`REIMFLOW_SMTP_PASSWORD` and `REIMFLOW_SMTP_FROM`. Without those settings,
account registration works in internal beta mode without verified email, so
do not open public production registration until email is configured.

The initial administrator is assigned via the server-only `role_admin.py`
operator command, never via username/email assumptions. No subscriptions,
checkout or payments are active; Premium is only planned.

Native mobile package scaffolding (Capacitor 8.5.1, stable) is present.
See `docs/MOBILE_RELEASE.md`. iOS/Android binaries are not shipped until
native microphone permissions, legal documents, store assets and real-device QA
are complete.

**Deployment dependency:** Merge the matching Publisher deploy workflow
update (Publisher PR #111) after this application PR. The old Publisher
deployment cannot serve the new backend module or audio files.



German-language rap rhyme and producer-community prototype. Live testing URL: **https://reimflow.smarbiz.sbs/**.

## Current functionality

- Phonetic AI rhyme search (requires server-side `OPENAI_API_KEY`)
- Rhyme validation / tester AI check (same API key)
- Syllable and part-of-speech filters, pronunciation hints and browser speech synthesis
- Persistent community submissions, human tester approval and verified point badges (server-backed)
- Moderated Beats and Samples archive with persistent, license-attested uploads
- Real rapper/producer accounts and profiles; Premium billing still disabled
- **Flow Challenge mini-game:** a 4-beat count-in followed by 16 timing targets over 4 bars, four selectable BPM presets (80/92/110/140), local Web Audio kick/snare/hi-hat, finger/spacebar rhythm tapping, optional microphone-onset mode (Beta), PERFECT/GOOD/OKAY/MISS timing, combo, score out of 100, local best-score record, and shareable result text. Open via the **Flow Game** navigation tab or homepage CTA.
- **Privacy:** microphone stream is analyzed transiently with Web Audio and never recorded, uploaded or saved. Mic onset analysis is experimental and can be distorted by background sound or metronome playback; headphones recommended. The score measures beat placement accuracy only, **not** musicality or rap skill. Game requires a browser with Web Audio; Mic Beta additionally needs microphone permission on HTTPS.
- **Rap Flow Analyse (Beta):** a separate tab in Flow Spiel. Select 4 or 8 bars, count in, record rap over a browser-generated beat, listen locally, and explicitly press "Mit KI auswerten" to upload the clip. The server uses OpenAI whisper-1 word timestamps and reports approximate word-onset alignment, longest pauses, estimated syllable density by bar, and density changes. No fabricated scores or verdict on artistic talent.
- **Audio privacy:** the microphone requires consent. Recordings remain local until explicit upload; Reimflow stores neither audio files nor transcripts on disk/in database. Uploaded audio is transmitted to OpenAI for transcription (their data processing terms apply). Server rate limits and a 4 MiB cap apply. Headphones recommended. Word and syllable timestamps are estimates, not precise phonetic analysis.
- Nine switchable designs: four fully functional comic editions (**Pop Comic**, **Street Graffiti**, **Graphic Novel**, **Clean Comic**) plus the five earlier themes.
- The four comic editions share the original `sonic-art` page mechanics and differ through `data-comic-style` in `comic-variants.css`. Pop uses `comic-flow.css`. Select editions from the theme menu or the quick switch on the home page.
- Selected design persists via `localStorage` (`reimflow_theme_v3`); no app API, search logic, account functionality or data persistence changed.

**Release caveat:** User accounts, community content, favorites and uploaded audio are persisted on the server. Email delivery remains conditional on SMTP configuration, and real-money payments are deliberately absent. Store publication additionally requires verified legal information, live moderation operations and physical-device QA.

## Hosting / deployment (STRATO)

- Host: `82.165.187.14` (shared STRATO host, also running A+ Publisher)
- Isolated source deployment under `/opt/reimflow` with separate Docker Compose services `web` (Nginx) and `api` (Python), constrained resources and persistent cache directory `/opt/reimflow/data`.
- HTTPS termination is provided by the **existing** Publisher Caddy service; no additional host listener on ports 80 or 443.
- The canonical Caddy route and the safe production deployment workflow are maintained in [hsdarestani/publisher](https://github.com/hsdarestani/publisher):
  - [Caddyfile](https://github.com/hsdarestani/publisher/blob/main/Caddyfile)
  - [Deploy Reimflow on STRATO](https://github.com/hsdarestani/publisher/blob/main/.github/workflows/reimflow-strato-deploy.yml)
- To publish future changes, run **Deploy Reimflow on STRATO (isolated)** from the Publisher repo Actions tab. The workflow reads current Reimflow `main` and verifies the live HTTPS website and `/api/health`.
- The GitHub Actions workflow in **this** repository validates source only. The former password-based Hetzner deployment was retired.

## Enable AI

Set the **Publisher** production GitHub Actions secret `OPENAI_API_KEY` (do not put the key in code, logs or chat), then rerun the Publisher **Deploy Reimflow on STRATO (isolated)** workflow.

Check `https://reimflow.smarbiz.sbs/api/health`. The JSON field `ai` must be `true` before live AI endpoints `/api/rhymes` and `/api/validate` can function. If the field is `false`, the browser still shows an offline demo/fallback but genuine AI search is unavailable.
