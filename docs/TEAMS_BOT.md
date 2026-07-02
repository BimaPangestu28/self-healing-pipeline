# Connecting to a real Microsoft Teams bot (Azure Bot)

This wires the Approve/Reject Adaptive Card actions to a real Teams **bot account**.
Button clicks arrive at `POST /api/teams/messages` as an `adaptiveCard/action`
invoke; the endpoint validates the Bot Framework JWT, executes approve/reject, and
returns a refreshed card that Teams renders in place.

The code side is ready. The steps below (Azure/M365 tenant) are done by your team.

## 1. Create an Azure Bot

1. Azure Portal → **Create a resource → Azure Bot**.
2. Type: **Multi Tenant** (or single-tenant if required). This creates a
   **Microsoft App ID** — copy it.
3. In the bot's **Configuration**, create a **client secret** (App password) and copy it.
4. Set **Messaging endpoint** to your public URL:
   `https://<your-host>/api/teams/messages`
5. Under **Channels**, add the **Microsoft Teams** channel.

## 2. Configure this service

```bash
export MICROSOFT_APP_ID=<the app id>
export MICROSOFT_APP_PASSWORD=<the client secret>   # for outbound/proactive
# LLM for the chat agent (optional)
export LLM_PROVIDER=deepseek
export DEEPSEEK_API_KEY=<key>
make demo
```

When `MICROSOFT_APP_ID` is set, `/api/teams/messages` **requires** a valid Bot
Framework JWT (unauthenticated requests get `401`).

## 3. Expose the endpoint publicly (local testing)

Teams calls your bot over the internet, so `localhost` needs a tunnel:

```bash
# Microsoft dev tunnels
devtunnel host -p 8080 --allow-anonymous
# or ngrok
ngrok http 8080
```

Set the Azure Bot **Messaging endpoint** to `https://<tunnel-domain>/api/teams/messages`.

## 4. Package + sideload the Teams app

1. Edit `deploy/teams/manifest.json`: replace both `REPLACE_WITH_MICROSOFT_APP_ID`
   occurrences (`id` and `bots[0].botId`) with your App ID.
2. Add two icons next to it: `color.png` (192×192) and `outline.png` (32×32).
3. Zip the three files (`manifest.json`, `color.png`, `outline.png`) into `app.zip`.
4. Teams → **Apps → Manage your apps → Upload a custom app** → upload `app.zip`
   (custom app upload must be allowed in your tenant).

## 5. Post the approval card into a channel

Two options to get the card in front of a human:

- **Incoming webhook** (simplest): set `TEAMS_WEBHOOK_URL` and post the card via
  `src/notifications` (already implemented). The Approve/Reject buttons then invoke
  the bot endpoint.
- **Proactive bot message**: send from the bot using the connector API with
  `MICROSOFT_APP_ID`/`MICROSOFT_APP_PASSWORD` and a stored conversation reference.
  (Not yet implemented here — the invoke round-trip and JWT auth are.)

## What is implemented vs. pending

| Piece | Status |
|-------|--------|
| `adaptiveCard/action` invoke handling (Approve/Reject) | ✅ |
| Bot Framework **JWT validation** (RS256 via JWKS, aud/iss/expiry) | ✅ |
| HMAC mode (outgoing webhook) | ✅ |
| Teams app manifest | ✅ (fill in App ID + icons) |
| Proactive/connector send of the initial card from the bot | ⛔ (use incoming webhook for now) |
| Azure Bot registration + tunnel + sideload | ⛔ your tenant (steps above) |
