# Reimflow mobile release plan (payments excluded)

## Current position

- Persistent account, moderation, licensed Beats, rhyme AI, Flow Challenge and Rap Flow live in the website code base.
- Android and iOS native builds are **not submitted**. Native project generation and device QA remain necessary.
- \`capacitor.config.json\` currently loads the live HTTPS site in a Capacitor WebView for early **internal QA only**. Do not submit a remote-only wrapper to Apple.
- Bundled UI snapshot is produced by \`npm run mobile:prepare\`.

## Native build setup

1. Install Node.js 22+, Android Studio, recent Android SDK, and Xcode on a Mac for iOS.
2. Run \`npm install\`, \`npm run mobile:prepare\`, \`npx cap add android\`, \`npx cap add ios\`.
3. Configure iOS microphone usage text and Android microphone permission plus WebView media capture permissions.
4. Replace the remote-only WebView with bundled native app functionality and an explicit secured API client, including cookie/session architecture for an app origin.
5. Configure universal/app links, share, file picker, native recording, offline saved results, proper splash/icon assets.
6. Test register, sign-in, session recovery, account deletion, uploads, reports, block, moderator workflow, audio range seeking and loss of connectivity on physical Android and iPhone.
7. Generate signed AAB and archived iOS build through the connected Publisher only after signing and store assets are ready.

## App Store/Google Play blockers

- Verified email ownership, self-service account recovery and abuse-resistant registration.
- Privacy Policy, Terms, Impressum, account/data deletion policy, copyright takedown and **published support contact** supplied by the operating legal entity.
- App Store age rating, UGC moderation response process and user blocking (code exists; operational staffing/SLA still required).
- Final app ownership, app ID/package name, signing certificates, push setup if needed, test account, store metadata/screenshots.
- Live voice recording tests and declared microphone/data-processing usage, including OpenAI transcription.
- A reviewable native feature set beyond merely showing a website (Apple guideline 4.2).
- End-to-end privacy, security, performance, accessibility, iOS and Android release QA.

## Reimflow production deployment

The STRATO deployment is controlled by the Publisher repo. It must include
\`platform_api.py\`, \`platform.js\`, \`role_admin.py\` and persist the media directory;
allow 14 MiB+ uploads in Nginx and Caddy; mount the admin role tool.
**Do not run the old Publisher deployment recipe against the upgraded source**:
the old recipe would omit these files.

After account registration, an operator with STRATO shell access must promote
the initial community administrator:
\`docker compose exec api python /app/role_admin.py existing_username admin\`.
Never derive administrator rights from an unverified email address.

## Payments

No payments or recurring subscriptions are enabled. Any Premium UI is
informational and must not promise entitlement until billing is implemented.
