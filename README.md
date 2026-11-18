# EnergyX Social

**Multi-channel social media publishing for ERPNext / Frappe v16.**

EnergyX Social (module name: *Social Posting*) lets a team draft, approve, schedule and publish posts to **Instagram, Facebook Pages, YouTube and TikTok** directly from ERPNext, using each platform's official API. There is no third-party SaaS in between: tokens stay in your own database, encrypted.

---

## Table of contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Roles and approval workflow](#roles-and-approval-workflow)
- [Connecting your social accounts](#connecting-your-social-accounts)
  - [Instagram](#instagram)
  - [Facebook Page](#facebook-page)
  - [YouTube](#youtube)
  - [TikTok](#tiktok)
- [Media rules](#media-rules)
- [Scheduling and background jobs](#scheduling-and-background-jobs)
- [Security](#security)
- [Platform limits to know about](#platform-limits-to-know-about)
- [Troubleshooting](#troubleshooting)
- [Project structure](#project-structure)
- [License](#license)

---

## Features

- **One post, many channels.** Write a title, caption and media once, then pick any number of accounts. Override the caption, media, thumbnail, first comment or schedule per channel.
- **Approval workflow.** Draft → Pending Approval → Approved, with Hold, Cancel and Reopen. Installed automatically.
- **Scheduling.** Per-post or per-channel schedule. A cron job picks up due posts every 5 minutes.
- **Publish now.** Managers can publish selected channels immediately.
- **Automatic retries.** Rate limits and transient errors are rescheduled (up to 5 attempts). Failed channels can be retried with one click.
- **Remove from platform** for Facebook and YouTube.
- **Analytics.** Daily pull of impressions, reach, likes, comments, shares and engagement rate into the post.
- **Token renewal.** Tokens close to expiry are renewed daily. System Managers are notified if renewal fails.
- **Permission aware.** Editors never see credentials. Only System Managers can open the settings.

| Channel | Formats |
|---|---|
| Instagram | Post, Reel, Story |
| Facebook Page | Photo, Video, Text |
| YouTube | Short, Video (with thumbnail and playlist support) |
| TikTok | Video, Photo |

## Requirements

- Frappe Framework and ERPNext **v16** (`>=16.0.0-dev, <17.0.0`)
- A running **long** queue worker (included in `bench start`; in production make sure the worker handles the `long` queue)
- Bench scheduler enabled
- A **public HTTPS URL** for your site if you publish to Instagram, Facebook (photo/video) or TikTok in URL mode. These platforms download your media from that URL.

## Installation

From your bench directory:

```bash
cd ~/frappe-bench
bench get-app https://github.com/Royalless05/energyx_social --branch main
bench --site your-site.local install-app energyx_social
bench --site your-site.local migrate
bench restart
```

On install and on every migrate the app idempotently creates:

- the roles **Social Editor** and **Social Manager**
- the workflow **Social Post Approval** and its states and actions (existing ones are never overwritten)

An **EnergyX Social** icon then appears on the Desk Apps screen, with shortcuts to *Social Post* and *Social Posting Settings*.

If the icon does not appear after install, run:

```bash
bench --site your-site.local clear-cache
bench restart
```

### Updating

```bash
cd ~/frappe-bench/apps/energyx_social
git pull upstream main        # the remote created by bench is named "upstream"
cd ~/frappe-bench
bench --site your-site.local migrate
bench build --app energyx_social
bench restart
```

## Quick start

1. **Add accounts.** Open *Social Posting Settings* (System Manager only), add one row per account (see [Connecting your social accounts](#connecting-your-social-accounts)), **save**, then click **Test Connection** on each row. An account becomes `Enabled` only after Test Connection succeeds.
2. **Set the Public Base URL** in the same settings page. It must start with `https://` and be reachable from the internet without login.
3. **Create a post.** Open *Social Post → New*, fill in title, media and caption, add one row per channel in the *Channels* table, and click **Submit for Approval**.
4. **Approve.** A Social Manager clicks **Approve**. Channels with a schedule become `Scheduled`; channels without one become `Queued`.
5. **Publish.** Scheduled channels publish automatically. For queued channels use **Actions → Publish Now**.

## Roles and approval workflow

| Role | Can do |
|---|---|
| **System Manager** | Edit Social Posting Settings, run Test Connection, everything below |
| **Social Manager** | Approve / reject, hold / resume, cancel / reopen, Publish Now, Retry Failed, Remove from Platform |
| **Social Editor** | Create and edit drafts, submit for approval |

Give managers **both** the Social Editor and Social Manager roles so they can draft and approve.

```
Draft ──Submit for Approval──▶ Pending Approval ──Approve──▶ Approved ──▶ Publishing ──▶ Published / Partial
  ▲                                   │                         │
  └──────────── Reject ───────────────┘                    Hold ⇄ Resume
```

Content (title, media, caption) is locked after approval. To change it, send the post back to Draft.

Each channel row has its own status: `Queued`, `Scheduled`, `Publishing`, `Published`, `Failed`, `On Hold`, `Deleted`. The parent post shows `Partial` when only some channels succeeded.

## Connecting your social accounts

All credentials are entered in **Social Posting Settings → Accounts**. Use the field mapping at the start of each section below.

> **Tip:** start with a test account. Save the row first, then click **Test Connection**. Changing an account ID or any credential disables the account again until you re-test it.

### Instagram

This app uses **Instagram API with Facebook Login** (`graph.facebook.com`). The Instagram account must be linked to a Facebook Page. Tokens from the "Instagram Login" flow (`graph.instagram.com`) will not work.

**Prerequisites**

1. An Instagram **Professional** account (Business or Creator; Stories require Business).
2. A **Facebook Page** linked to that Instagram account, and you are an admin of the Page.
3. If the Page requires *Page Publishing Authorization* (PPA), complete it first, otherwise Meta rejects publishing.

**Steps**

1. Go to [developers.facebook.com](https://developers.facebook.com), create an app (type *Business*) and add the **Instagram** product. Note the **App ID** and **App Secret** under *Settings → Basic*.
2. Open the **Graph API Explorer**, select your app and generate a user token with these permissions:
   `instagram_basic`, `instagram_content_publish`, `pages_read_engagement`, `pages_show_list`.
3. Exchange the short-lived token for a long-lived one (about 60 days):
   ```
   https://graph.facebook.com/v21.0/oauth/access_token
     ?grant_type=fb_exchange_token
     &client_id=APP_ID
     &client_secret=APP_SECRET
     &fb_exchange_token=SHORT_LIVED_TOKEN
   ```
   Keep this URL private; it contains your app secret.
4. Find the **Instagram Business Account ID**:
   - `GET me/accounts` → note the Page `id`
   - `GET {page-id}?fields=instagram_business_account` → the `id` inside is your IG Business Account ID
5. In Social Posting Settings add a row:

| Field | Value |
|---|---|
| Channel | `Instagram` |
| Account Name | any label |
| Account / Page / Channel ID | IG Business Account ID |
| App ID / Client ID | your Meta App ID |
| App Secret | your Meta App Secret |
| Access Token | the long-lived token |
| Api Version | optional. Default is `graph.facebook.com/v21.0`; set a newer value such as `graph.facebook.com/v26.0` if Meta rejects the default |

6. Save, then **Test Connection**. Expected: `Instagram @your_username`.

With App ID and Secret filled in, the token is renewed automatically when it is within 10 days of expiry.

**Notes**

- While the Meta app is in *Development mode* you can only publish to accounts owned by app admins, developers or testers. Publishing to other people's accounts needs **Advanced Access** (App Review and Business Verification).
- Images must be **JPEG**. Media is fetched by Meta from your Public Base URL.
- Meta limits API-published posts per account per 24 hours (documentation states 50 to 100).

### Facebook Page

**Steps**

1. Use the same Meta app as above, or create a new one.
2. In the Graph API Explorer generate a user token with: `pages_manage_posts`, `pages_manage_engagement`, `pages_read_engagement`, `pages_show_list`.
3. Exchange it for a long-lived user token (same URL as in the Instagram section).
4. Call `GET me/accounts` with the long-lived user token. The response lists each Page with its `id` and its own `access_token`. A Page token obtained this way from a long-lived user token does not expire.
5. Add a row:

| Field | Value |
|---|---|
| Channel | `Facebook Page` |
| Account Name | any label |
| Account / Page / Channel ID | the Page `id` |
| App ID / App Secret | Meta app credentials (optional, enables renewal) |
| Access Token | the **Page** access token |

6. Save, then **Test Connection**. Expected: `Facebook Page <name>`.

### YouTube

Uploads use the YouTube Data API v3 (resumable upload). Videos are uploaded from your server, so no public URL is needed.

**Steps**

1. In the [Google Cloud Console](https://console.cloud.google.com), create a project and enable **YouTube Data API v3**.
2. Configure the **OAuth consent screen**. Add the Google account that owns the channel as a test user.
   - **Important:** while the consent screen is in *Testing* status, refresh tokens expire after 7 days. Move the app to *In production* for a long-lived refresh token.
3. Create an **OAuth client ID** (type *Web application*). Add `https://developers.google.com/oauthplayground` as an authorized redirect URI. Note the **Client ID** and **Client Secret**.
4. Get a refresh token with the [OAuth 2.0 Playground](https://developers.google.com/oauthplayground):
   - Click the gear icon, tick *Use your own OAuth credentials* and paste your Client ID and Secret.
   - Authorize these scopes: `https://www.googleapis.com/auth/youtube.upload` and `https://www.googleapis.com/auth/youtube`.
   - Sign in with the channel owner account, then click **Exchange authorization code for tokens** and copy the **Refresh token**.
5. Find your **Channel ID** (starts with `UC`) in YouTube Studio → *Settings → Channel → Advanced settings*.
6. Add a row:

| Field | Value |
|---|---|
| Channel | `YouTube` |
| Account Name | any label |
| Account / Page / Channel ID | Channel ID (`UC...`) |
| App ID / Client ID | OAuth Client ID |
| App Secret | OAuth Client Secret |
| Refresh Token | the refresh token |
| Target Playlist ID | optional |

7. Save, then **Test Connection**. Expected: `YouTube <channel title>`. The app verifies that the token belongs to the Channel ID you entered. Access tokens are refreshed automatically.

**Notes**

- One `videos.insert` costs **1,600 quota units**. The default daily quota is 10,000, so roughly 6 uploads per day. When quota runs out, the channel is rescheduled in 6 hours.
- API projects that have not passed Google's audit upload videos as **private**.

### TikTok

**Steps**

1. Register at [developers.tiktok.com](https://developers.tiktok.com) and create an app.
2. Add the products **Login Kit** and **Content Posting API** (enable *Direct Post*). Add the scopes `user.info.basic`, `video.publish`, `video.upload` and `video.list`.
3. Register a **redirect URI** (HTTPS only) and provide public Terms of Service and Privacy Policy URLs.
4. If you use `PULL_FROM_URL` mode, or publish photos, **verify ownership** of your media domain or URL prefix in the TikTok developer portal.
5. Note the **Client Key** and **Client Secret**.
6. Obtain the `open_id` and a refresh token with the standard authorization-code flow:
   - Open in a browser (while logged in to the TikTok account you will post to):
     ```
     https://www.tiktok.com/v2/auth/authorize/
       ?client_key=CLIENT_KEY
       &scope=user.info.basic,video.publish,video.upload,video.list
       &response_type=code
       &redirect_uri=YOUR_REDIRECT_URI
       &state=anything
     ```
   - After approval TikTok redirects to your URI with `?code=...`. URL-decode the code (for example `%2A` becomes `*`).
   - Exchange the code:
     ```bash
     curl -X POST https://open.tiktokapis.com/v2/oauth/token/ \
       -H "Content-Type: application/x-www-form-urlencoded" \
       -d "client_key=CLIENT_KEY" \
       -d "client_secret=CLIENT_SECRET" \
       -d "code=THE_CODE" \
       -d "grant_type=authorization_code" \
       -d "redirect_uri=YOUR_REDIRECT_URI"
     ```
   - The response contains `open_id`, `access_token` and `refresh_token`.
7. Add a row:

| Field | Value |
|---|---|
| Channel | `TikTok` |
| Account Name | any label |
| Account / Page / Channel ID | `open_id` |
| App ID / Client ID | Client Key |
| App Secret | Client Secret |
| Access Token | the access token |
| Refresh Token | the refresh token |

8. In the **TikTok** section of Social Posting Settings, choose:
   - **Tiktok Upload Mode**: `FILE_UPLOAD` (chunked upload from your server) or `PULL_FROM_URL` (TikTok downloads from your verified domain; always used for photos)
   - **Tiktok Default Privacy**: `PUBLIC_TO_EVERYONE`, `MUTUAL_FOLLOW_FRIENDS`, `FOLLOWER_OF_CREATOR` or `SELF_ONLY`
9. Save, then **Test Connection**. Expected: `TikTok <display name>`.

Access tokens are refreshed automatically, and the rotated refresh token is saved.

**Notes**

- **Unaudited TikTok apps can only post privately** (`SELF_ONLY`) and only to private accounts. Submit your app for TikTok's audit to lift this.
- Content Posting API calls are limited to 6 requests per minute per user token, plus a daily post cap.

## Media rules

Media is validated before publishing. Local files are exposed to platforms through the **Public Base URL**. Private files are copied temporarily to `/files/` under a random name and deleted after publishing. External media URLs must be HTTPS and are checked against private/internal addresses.

| Channel / format | Types | Max size |
|---|---|---|
| Instagram Post | JPEG | 8 MB |
| Instagram Story | JPEG, MP4, MOV | 100 MB |
| Instagram Reel | MP4, MOV | 300 MB |
| Facebook Photo | JPEG, PNG, GIF | 10 MB |
| Facebook Video | MP4, MOV | 1 GB |
| Facebook Text | none | - |
| YouTube Short | MP4, MOV, WebM | 4 GB |
| YouTube Video | MP4, MOV, WebM | 8 GB |
| YouTube Thumbnail | JPEG, PNG | 2 MB |
| TikTok Video | MP4, MOV, WebM | 4 GB |
| TikTok Photo | JPEG, WebP | 20 MB |

These are conservative defaults defined in `services/media.py` (`RULES`). Platforms change limits often, so verify against their current documentation and adjust if needed.

Caption limits: Instagram and TikTok 2,200 characters, YouTube 5,000, Facebook 63,206. YouTube titles are limited to 100 characters.

## Scheduling and background jobs

| Job | Schedule | What it does |
|---|---|---|
| `dispatch_due_posts` | every 5 minutes | Claims up to 10 due channels and enqueues them on the `long` queue (timeout 1,200 s). Recovers jobs stuck in `Publishing` for over 30 minutes. |
| `renew_tokens` | daily | Renews tokens that expire within 10 days. Notifies System Managers on failure. |
| `pull_metrics` | daily | Pulls metrics for posts published in the last 30 days into the *Metrics* table. |

The scheduler and a worker for the `long` queue must be running, otherwise nothing publishes automatically. Enable the scheduler with:

```bash
bench --site your-site.local enable-scheduler
```

Errors are written to the **Error Log** doctype and to the `Error Log` field of the channel row. Secrets are redacted before logging.

## Security

- Secrets (`App Secret`, `Access Token`, `Refresh Token`) are stored in encrypted `Password` fields.
- Tokens are sent in request headers, never in URLs.
- All error text passes through a redaction step before it is stored or shown.
- System fields on channel rows (status, remote ID, attempts, errors) are restored by the server, so they cannot be forged from the client.
- Only System Managers can open Social Posting Settings and run Test Connection. Editors choose from a credential-free account list.

## Platform limits to know about

- **Instagram:** Development mode apps only publish to accounts connected to the app. Stories need a Business account. Instagram has no delete API, so remove posts manually.
- **TikTok:** unaudited apps are limited to private posting; there is no delete API.
- **YouTube:** daily quota of about 6 uploads by default; unaudited API projects upload as private.
- **Facebook / YouTube:** *Remove from Platform* is supported.

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| Test Connection says to save first | Save the document so tokens are stored encrypted, then retry |
| Account stays disabled | Run Test Connection; changing credentials disables the account again |
| Meta error 190, 10 or 200 | Token expired or missing permissions. Regenerate the token with all required scopes |
| Instagram media cannot be fetched | Public Base URL is not public, or the image is not JPEG |
| `instagram_business_account` missing | The Instagram account is not linked to the Page, or is not a professional account |
| YouTube `invalid_grant` | Refresh token expired (consent screen still in *Testing*) or revoked. Create a new one |
| TikTok `url_ownership_unverified` | Verify the media domain in the TikTok developer portal, or use `FILE_UPLOAD` mode |
| TikTok "Unaudited clients can only post to a private account" | App is not audited. Use a private account and `SELF_ONLY`, or pass the audit |
| Scheduled posts never publish | Scheduler disabled or no `long` worker running |
| App icon missing on Desk | `bench migrate`, `bench --site <site> clear-cache`, hard refresh the browser |

## Project structure

```
energyx_social/
  hooks.py  jobs.py  api.py
  setup/install.py                 # roles + workflow
  public/images/logo.svg           # app icon
  services/
    client.py  media.py  credentials.py  errors.py  publisher.py
    providers/{meta,youtube,tiktok}.py
  social_posting/
    workspace/energyx_social/      # Desk workspace
    doctype/
      social_posting_settings/     # single doctype: accounts, base URL, TikTok options
      social_account/              # child table: credentials per account
      social_post/                 # the post, with workflow
      social_post_channel/         # child table: one row per target channel
      social_post_metric/          # child table: analytics
```

## License

MIT. See the license declared in `hooks.py`.

---

Built by **EnergyX 369**.
