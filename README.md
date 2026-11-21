# SocialX

**Multi-channel social media publishing for EnergyX 369 ERP.**

SocialX (module name: *Social Posting*, package name: `energyx_social`) lets a team draft, approve, schedule and publish posts to **Instagram, Facebook Pages, YouTube, TikTok and LinkedIn** directly from EnergyX 369 ERP, using each platform's official API. There is no third-party SaaS in between: tokens stay in your own database, encrypted.

---

## Table of contents

- [Features](#features)
- [What's new in this release](#whats-new-in-this-release)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Roles and approval workflow](#roles-and-approval-workflow)
- [Connecting your social accounts](#connecting-your-social-accounts)
  - [Instagram](#instagram)
  - [Facebook Page](#facebook-page)
  - [YouTube](#youtube)
  - [TikTok](#tiktok)
  - [LinkedIn](#linkedin)
- [Media rules](#media-rules)
- [Wave 2 and 3 features in detail](#wave-2-and-3-features-in-detail)
- [Scheduling and background jobs](#scheduling-and-background-jobs)
- [Security](#security)
- [Platform limits to know about](#platform-limits-to-know-about)
- [Troubleshooting](#troubleshooting)
- [Roadmap](#roadmap)
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
- **Notifications.** Editors and managers are told when a post needs approval, is approved or rejected, publishes, or fails.
- **Content calendar.** See the scheduled queue on a calendar.
- **Hashtag templates.** Reusable hashtag sets per account or channel, inserted into the caption in one click.
- **Post preview.** An approximate per-platform mock-up on the post form before you approve.
- **Metrics history.** A wider daily pull plus weekly roll-ups that keep history over time.
- **Carousel and albums.** Instagram carousels and Facebook multi-photo albums (2-10 items).
- **Analytics report.** Engagement per post, account, channel, week, hour and weekday, with charts.
- **Media library.** Shared, tagged assets reusable across posts.
- **Multi-level approval and revision notes.** Optional second approval level and structured notes on every rejection.
- **Comment inbox.** Pull and answer comments from Facebook, Instagram and YouTube.
- **LinkedIn.** Text, image and video posts to a profile or an organization page.
- **Bulk scheduling and recurring posts.** CSV/XLSX import and evergreen templates that always go through approval.
- **UTM builder and short links.** Automatic UTM tags per channel and click-counting short links.

| Channel | Formats |
|---|---|
| Instagram | Post, Reel, Story, Carousel |
| Facebook Page | Photo, Video, Text, Album |
| YouTube | Short, Video (with thumbnail and playlist support) |
| TikTok | Video, Photo |
| LinkedIn | Text, Photo, Video |

## Requirements

- **EnergyX 369 ERP v16** (`>=16.0.0-dev, <17.0.0`), installed with `bench`
- A running **long** queue worker (included in `bench start`; in production make sure the worker handles the `long` queue)
- Bench scheduler enabled
- A **public HTTPS URL** for your site if you publish to Instagram, Facebook (photo/video) or TikTok in URL mode. These platforms download your media from that URL.

## Installation

From your bench directory (the folder that contains `apps/` and `sites/`):

```bash
cd <your-bench>
bench get-app https://github.com/Royalless05/energyx_social --branch main
bench --site your-site.local install-app energyx_social
bench --site your-site.local migrate
bench restart
```

On install and on every migrate the app idempotently creates:

- the roles **Social Editor** and **Social Manager**
- the workflow **Social Post Approval** and its states and actions (existing ones are never overwritten)

A **SocialX** icon then appears on the Desk Apps screen, with shortcuts to *Social Post*, *Content Calendar*, *Hashtag Templates* and *Social Posting Settings*.

If the icon does not appear after install, run:

```bash
bench --site your-site.local clear-cache
bench restart
```

### Updating

```bash
cd <your-bench>/apps/energyx_social
git pull upstream main        # the remote created by bench is named "upstream"
cd <your-bench>
bench --site your-site.local migrate
bench build --app energyx_social
bench restart
```

## What's new in this release

This release delivers the **whole roadmap**: Wave 1 (items 1-5), Wave 2 (items 6-9) and Wave 3 (items 10-13). Waves 2 and 3 are described in [Wave 2 and 3 features in detail](#wave-2-and-3-features-in-detail). Existing behaviour (publishing, workflow, retries, token renewal) keeps working; the only change to an existing flow is the optional second approval level, which is **off** by default.

### 1. Notifications

In-app notifications (Notification Log). Email is sent according to each user's own Notification Settings.

| Event | Who is notified |
|---|---|
| Post submitted for approval | All users with the **Social Manager** role |
| Approved, rejected (returned to Draft), put on hold, cancelled | The user who requested the post |
| Published on all channels, or only some (Partial) | The user who requested the post |
| A channel fails permanently (retries exhausted or a non-retryable error) | The requester and all Social Managers |
| Level-1 approval with *Require Final Approval* on | All Social Final Approvers (and the requester is told it passed level 1) |
| Final approval, or a rejection with revision notes | The requester (the rejection lists the open notes) |

You are never notified about your own actions. Notifications never block saving or publishing.

### 2. Content calendar

Open **SocialX → Content Calendar** (or the *Calendar* view of the Social Post list). Posts appear on their **Default Scheduled At** date and are coloured by status. Posts that only use per-channel schedule overrides and have no default schedule are not shown on the calendar.

### 3. Hashtag templates

- Create templates under **SocialX → Hashtag Templates**: a name, optionally a channel and an account, and the hashtags (separated by spaces, commas or new lines). The `#` is added automatically and duplicates are removed.
- Mark one template as **Default** for an account (or a channel) and it is picked automatically when you choose that account on a Social Post channel row.
- On a channel row, choose a **Hashtag Template**. Its hashtags are appended to the *Caption Override* (starting from the base caption if the override is empty). You can edit the result afterwards; the same hashtags are never added twice.

Templates are standalone records rather than a table inside the account, because the account list is itself a child table of the settings page.

### 4. Wider metrics retention

- **Social Posting Settings → Metrics** now has *Metrics Window (days)* (default 90, was a fixed 30) and *Metrics Max Posts per Run* (default 1,000, was a fixed 500).
- Each daily run also writes **Social Metric Weekly**: one row per channel per week (weeks start on Monday) holding the latest numbers of that week. Platform metrics are cumulative, so the last snapshot of a week is that week's final value.
- Nothing is deleted. Daily rows stay in the post's Metrics table; weekly rows stay in *Social Metric Weekly* (read-only for editors and managers).

### 5. Post preview

The **Preview** section on the Social Post form shows one tab per active channel with an approximate mock-up of Instagram (post, reel, story), Facebook, YouTube (video, short) and TikTok. It uses the effective caption and media (override first, then base), applies each platform's approximate "…more" cut-off, shows the first comment and the character count against the platform limit, and highlights hashtags. It is rendered in the browser and updates as you type. Real platforms render slightly differently, so treat it as a guide.

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
| **Social Final Approver** | Second approval level (only when *Require Final Approval* is on): Final Approve or Request Revision |
| **Social Editor** | Create and edit drafts, submit for approval, resolve revision notes, reply in the comment inbox |

Give managers **both** the Social Editor and Social Manager roles so they can draft and approve.

```
Draft ──Submit for Approval──▶ Pending Approval ──Approve──▶ Approved ──▶ Publishing ──▶ Published / Partial
  ▲                                   │                         │
  └──────────── Reject ───────────────┘                    Hold ⇄ Resume
```

With **Social Posting Settings → Require Final Approval** switched on, the flow gets a second level (see [Multi-level approval](#9-multi-level-approval-and-revision-notes)):

```
Pending Approval ──Approve──▶ Pending Final Approval ──Final Approve──▶ Approved
                                        └──Request Revision──▶ Draft
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
4. Call `GET me/accounts?fields=id,name,access_token` with the long-lived user token. The response lists each Page with its `id` and its own `access_token`. A Page token obtained this way from a long-lived user token does not expire.

   > **Use the Page token, not the user token.** Posting to a Page with a user token fails with `(#200) The permission(s) publish_actions are not available`. Test Connection can still pass with a user token because reading the Page name is allowed, so check the token in the [Access Token Debugger](https://developers.facebook.com/tools/debug/accesstoken): *Type* must be `Page` and *Scopes* must include `pages_manage_posts`.
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

### LinkedIn

**Fields in Social Account:** *Account ID* = the full author URN (`urn:li:organization:<id>` for a company page, `urn:li:person:<id>` for a profile), *Access Token*, optionally *Client ID / Client Secret / Refresh Token*, and *API Version* (format `YYYYMM`, default `202610`).

1. Create an app at [linkedin.com/developers](https://www.linkedin.com/developers/apps) and associate it with your company page.
2. Request the products you need. To post as an **organization** you need *Community Management API* (scope `w_organization_social`, plus `r_organization_social` for metrics). To post as a **member** you need *Share on LinkedIn* (`w_member_social`) and *Sign In with LinkedIn using OpenID Connect* (`openid profile`).
3. Run the OAuth 2.0 authorization-code flow to get an access token.
4. The organization or member URN goes into *Account ID*. Click **Test Connection**.

Limits and notes:
- LinkedIn access tokens live about **60 days**. Refresh tokens are only issued to approved partner apps. Without one, SocialX cannot renew the token: the daily renewal job notifies System Managers and you create a new token by hand. Set *Token Expires On* so the warning appears in time.
- LinkedIn versions its API monthly and retires old versions after about a year. If requests fail with a version error, set a current `YYYYMM` in *API Version*.
- LinkedIn's text format treats `\ | { } @ [ ] ( ) < > * _ ~` as special characters. SocialX escapes them automatically and leaves `#` alone so hashtags stay active.
- Not supported for LinkedIn in this release: first comment, comment inbox, multi-image posts.

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
| Instagram Carousel (2-10 items) | JPEG (8 MB) or MP4/MOV (100 MB) per item | per item |
| Facebook Album (2-10 photos) | JPEG, PNG, GIF | 10 MB per photo |
| LinkedIn Photo | JPEG, PNG, GIF | 10 MB |
| LinkedIn Video | MP4 | 200 MB |

These are conservative defaults defined in `services/media.py` (`RULES`). Platforms change limits often, so verify against their current documentation and adjust if needed.

Caption limits: Instagram and TikTok 2,200 characters, YouTube 5,000, LinkedIn 3,000, Facebook 63,206. YouTube titles are limited to 100 characters.

## Wave 2 and 3 features in detail

### 6. Carousel and albums

- On a channel row choose format **Carousel** (Instagram) or **Album** (Facebook Page).
- Fill the **Carousel / Album Media** table on the post with 2-10 images (Instagram also accepts videos). The order of the rows is the order of the slides. Each row can be uploaded or picked from the [media library](#8-media-library).
- The table is shared by all carousel/album channels of the post. Captions, schedule and first comment work as for other formats.
- Instagram creates one container per slide, waits until all are ready, then publishes the carousel. Facebook uploads each photo unpublished and then makes one post that attaches them all. Progress is checkpointed after every item, so a retry resumes instead of uploading again.
- The preview shows the first slide and the slide count.

### 7. Analytics report

Open **SocialX → Social Analytics** (a script report). Filters: date range (by publish date), channel, account, and **View**:

| View | Shows |
|---|---|
| Post | Every published channel row with its latest numbers, best engagement first |
| Account / Channel | Totals and engagement rate per account or channel |
| Week | Trend by publishing week (line chart) |
| Hour of Day / Weekday | When posts perform best; the summary names the best slot and how many posts it is based on |

The numbers are the latest daily snapshot of each post (platform metrics are cumulative). Engagement rate = (likes + comments + shares) / reach, falling back to impressions when reach is unavailable. Treat the "best hour" with care when a slot has only a few posts. Hours are in the server's time zone.

### 8. Media library

**SocialX → Media Library** stores *Social Media Asset* records: file, name, tags, campaign and description. Type, MIME and size are filled automatically; only images and videos are accepted. The asset form shows a preview and which posts use the file.

On a post, the base media, a channel's media override and each carousel slide have a **Media Library Asset** field: picking an asset copies its file into the matching attachment field. Changing the asset later does not overwrite a file you uploaded manually. The roadmap also mentioned alt text and a compatible-channels field; these are **not** included (the description field can hold alt text). Compatibility is checked when the post is published, using the media rules above.

### 9. Multi-level approval and revision notes

**Second approval level** (off by default): switch on *Social Posting Settings → Require Final Approval*, then give the final reviewers the **Social Final Approver** role. A Social Manager's *Approve* then moves the post to **Pending Final Approval**; a Final Approver completes it with **Final Approve** or sends it back with **Request Revision**. The setting is read when the post is submitted, so posts already in review keep the rules they started with. Approver names and times are stored for both levels. The server enforces the rules, not just the buttons.

**Revision notes** (always on): the *Revision Notes* table on the post. Reviewers add one note per issue (type, applies-to channel, text). Rules:
- Rejecting, or *Request Revision*, needs at least one **Open** note.
- The editor sees the notes, answers in *Resolution* and sets them to **Resolved**. Editors cannot add, edit or delete notes.
- *Submit for Approval* is blocked while any note is Open, and approving is blocked while a note is Open.
- Each note records who raised it, at which level and when, and who resolved it and when. The notification to the editor lists the open notes.

Existing installs: on `bench migrate` the existing *Social Post Approval* workflow is **extended in place** (new state, new transitions and the two conditions). Nothing you customized is overwritten; transitions that already exist are left alone.

### 10. Comment inbox

**SocialX → Comment Inbox** lists comments as *Social Comment* records (New / Replied / Ignored). An hourly job pulls comments for recently published posts; **Actions → Pull Comments** on a post does it on demand. Open a comment and click **Reply** to answer through the platform's API, or **Ignore**.

| Channel | Read | Reply | Notes |
|---|---|---|---|
| Facebook Page | yes | yes | needs `pages_read_engagement`, `pages_manage_engagement` |
| Instagram | yes | yes | needs `instagram_manage_comments` |
| YouTube | yes | yes | needs scope `https://www.googleapis.com/auth/youtube.force-ssl` in addition to the upload scope. A reply costs 50 quota units |
| TikTok, LinkedIn | no | no | no suitable API in this app |

Replies always go to the top-level comment (the platforms only nest one level). Comments written by your own account are skipped. Only the latest 50 comments per post are read per run. Direct messages are not included.

### 11. LinkedIn

See [LinkedIn](#linkedin) for setup. Formats: Text, Photo, Video. Posting, deleting and basic metrics (likes, comments) are supported.

### 12. Bulk scheduling and recurring posts

**Bulk import.** On the Social Post list click **Bulk Schedule (CSV)**, download the template, fill it and upload a `.csv` (UTF-8, `,` or `;`) or `.xlsx` file (up to 200 rows). **Validate** checks everything without saving; **Create Drafts** creates one Draft per valid row and reports the rows with errors. Drafts then go through normal approval (use the list view's bulk *Apply Workflow* to submit many at once).

| Column | Meaning |
|---|---|
| `title` | required |
| `caption`, `hashtags` | caption text; hashtags are normalized and appended |
| `media` | an `https://` URL or a `/files/...` path |
| `channels` | required; separated by `;`, each `Channel` or `Channel:Account Name` (the account name is needed when a channel has several enabled accounts) |
| `formats` | optional, `Channel=Format` separated by `;` (default: the channel's first format, or Text when there is no media) |
| `scheduled_at` | optional `YYYY-MM-DD HH:MM`, must be in the future |
| `campaign` | optional existing Campaign |

**Recurring posts.** **SocialX → Recurring Posts**: a template (title, caption, media, channels) plus a schedule (daily, weekly on a weekday, or monthly on day 1-28, at a time, optional start/end date). An hourly job creates the post *Create Days Before* days ahead (default 3) with **Pending Approval** (or Draft), so a human always approves before anything is published. The next publish time is shown on the template; missed occurrences (for example scheduler downtime) are skipped, never back-posted. Titles get the date appended. Carousel/Album formats are not supported in recurring templates.

**Throughput.** *Social Posting Settings → Dispatch Batch Limit* (default 25, was 10, max 200) controls how many due channels are enqueued every 5 minutes. Make sure enough `long` workers run for the volume you schedule.

### 13. UTM builder and short links

Each post has a **Link Tracking** section: *Default*, *None*, *UTM only* or *UTM + Short link* (the default comes from *Social Posting Settings → Default Link Tracking*, initially *None*, so existing behaviour does not change).

- The rewrite happens **when publishing**; your draft stays readable. It applies to the caption and the first comment.
- UTM parameters added when missing: `utm_source` (the channel, e.g. `instagram`), `utm_medium=social`, `utm_campaign` (the post's *UTM Campaign*, else its Campaign, else the title) and `utm_content` (the format). UTM parameters you typed yourself are never overwritten.
- With *UTM + Short link*, each URL becomes `<Public Base URL>/s/<code>`. Opening it records a click and redirects (HTTP 302) to the tagged URL. Retries reuse the same code. You can also create links by hand in **SocialX → Short Links** (custom code, expiry date, enable/disable). Disabled or expired codes return 404.
- **Actions → Link Clicks** on a post shows its links and click counts. Clicks include bots and link-preview fetchers, so treat the counts as an upper bound.
- Short links are public by design; the target URL is visible to anyone who follows the link.

## Scheduling and background jobs

| Job | Schedule | What it does |
|---|---|---|
| `dispatch_due_posts` | every 5 minutes | Claims up to *Dispatch Batch Limit* due channels (default 25, max 200; was a fixed 10) and enqueues them on the `long` queue (timeout 1,200 s). Recovers jobs stuck in `Publishing` for over 30 minutes. |
| `renew_tokens` | daily | Renews tokens that expire within 10 days. Notifies System Managers on failure. |
| `create_recurring_posts` | hourly | Creates posts for [recurring templates](#12-bulk-scheduling-and-recurring-posts) that enter their lead-time window. |
| `pull_comments` | hourly | Pulls new comments for posts published within the last *Comments Window* days (default 14). Switch off with *Pull Comments Hourly*. |
| `pull_metrics` | daily | Pulls metrics for posts published within the configured window (default 90 days, up to 1,000 channel rows) into the post's *Metrics* table, and writes a weekly roll-up to *Social Metric Weekly*. |

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
- **Facebook / YouTube / LinkedIn:** *Remove from Platform* is supported.
- **Comments:** TikTok and LinkedIn comments are not available through the APIs this app uses. YouTube replies need the `youtube.force-ssl` scope (see below) and cost 50 quota units each.

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| Test Connection says to save first | Save the document so tokens are stored encrypted, then retry |
| Account stays disabled | Run Test Connection; changing credentials disables the account again |
| Meta error 190, 10 or 200 | Token expired or missing permissions. Regenerate the token with all required scopes |
| Facebook `(#200) publish_actions are not available` | A user token was entered instead of the **Page** access token. Get the Page token from `me/accounts` |
| Instagram media cannot be fetched | Public Base URL is not public, or the image is not JPEG |
| `instagram_business_account` missing | The Instagram account is not linked to the Page, or is not a professional account |
| YouTube `invalid_grant` | Refresh token expired (consent screen still in *Testing*) or revoked. Create a new one |
| TikTok `url_ownership_unverified` | Verify the media domain in the TikTok developer portal, or use `FILE_UPLOAD` mode |
| TikTok "Unaudited clients can only post to a private account" | App is not audited. Use a private account and `SELF_ONLY`, or pass the audit |
| Scheduled posts never publish | Scheduler disabled or no `long` worker running |
| App icon missing on Desk | `bench migrate`, `bench --site <site> clear-cache`, hard refresh the browser |
| Desk still shows the old name "EnergyX Social" after updating | Run `bench migrate` and clear the cache. The old workspace is removed on migrate and the new **SocialX** workspace is created. If a sidebar or desktop icon label is cached, edit it in Desk or re-run the desktop-icon command for your version |
| No notification emails | Notifications are always created in-app. Email also needs outgoing email configured and email notifications enabled in the user's Notification Settings |
| Post missing from the calendar | The calendar uses *Default Scheduled At*; set it on the post |
| LinkedIn `426` / version error | The `LinkedIn-Version` is too old. Put a current `YYYYMM` in the account's *API Version* |
| YouTube comments fail with 403 | The refresh token was created without `https://www.googleapis.com/auth/youtube.force-ssl`. Re-authorize with that scope added |
| Instagram/Facebook comments fail with permission errors | Add `instagram_manage_comments` / `pages_read_engagement` + `pages_manage_engagement`, then get a new token |
| Approve does nothing / wrong next state | Check *Workflow → Social Post Approval*: the two *Approve* transitions out of *Pending Approval* use the conditions `not doc.needs_final_approval` and `doc.needs_final_approval` |
| Short link returns 404 | The code is disabled or expired, or the site was not restarted/migrated after the update (the `/s/<code>` route is registered in `hooks.py`) |
| Bulk import says "tidak ada akun ... yang aktif" | The account must be *Enabled* (Test Connection passed). With several accounts on one channel write `Channel:Account Name` |
| Preview shows "No media" | Attach a file in *Base Media* or *Media Override* on the channel row

## Roadmap

Source: *Roadmap Prioritas SocialX*, 20 November 2026. Effort and impact are the planning estimates from that document. All 13 items are implemented. The three platform audits are not code and still need to be submitted by you.

> **Start now, in parallel with development: the platform audits.** Reviews on the platform side take weeks, and until they pass every feature stays in testing mode: (1) TikTok audit so posts can be public; (2) YouTube API audit/verification so uploads are not private and the quota can be raised; (3) Meta App Review / Advanced Access so you can post for client accounts and not only your own.

### Wave 1 — Quick wins (1-2 weeks) · **delivered**

| # | Feature | Effort | Impact | Status |
|---|---|---|---|---|
| 1 | Editor notifications | Small | High | ✅ Done |
| 2 | Calendar view of the schedule | Small | High | ✅ Done |
| 3 | Hashtag templates per account | Small | Medium | ✅ Done |
| 4 | Wider metrics retention + weekly roll-ups | Small | Medium | ✅ Done |
| 5 | Post preview per platform | Medium | High | ✅ Done |

### Wave 2 — Content and insight boosters (1-2 months) · **delivered in this release**

| # | Feature | Detail | Effort | Impact | Status |
|---|---|---|---|---|---|
| 6 | Carousel / multi-media album | Media becomes a child table (several files per channel row). Instagram supports up to 10 items; Facebook supports multi-photo albums. Carousel is the best-performing Instagram format. | Medium | High | ✅ Done |
| 7 | Analytics dashboard | Report and charts from Social Post Metric: engagement trend per account/channel, post comparison, best posting hours. The data is already collected; this adds the presentation layer. | Medium | High | ✅ Done |
| 8 | Media library | A shared *Social Media Asset* record reusable across posts and teams, with alt text, size and compatible channels. | Medium | Medium | ✅ Done |
| 9 | Multi-level approval | Several approval levels plus structured revision notes (today a rejection just returns the post to Draft without context). | Medium | Medium | ✅ Done |

### Wave 3 — Scale and interaction (next quarter) · **delivered in this release**

| # | Feature | Detail | Effort | Impact | Status |
|---|---|---|---|---|---|
| 10 | Comment inbox | Read and reply to comments: Facebook, Instagram and YouTube through the official APIs; TikTok read-only. Direct messages in a later phase. (Implemented for Facebook, Instagram and YouTube; TikTok comments are not available through the APIs used here.) New channels are the heaviest work, so start with Facebook and Instagram because their APIs are the most complete. | Large | High | ✅ Done |
| 11 | New platform: LinkedIn first | The most relevant audience for B2B. The provider pattern already exists, so only the implementation is needed. X and Threads follow. | Large | Medium | ✅ Done |
| 12 | Bulk scheduling + recurring posts | CSV import of many posts at once and evergreen templates that republish automatically. The dispatch limit is now configurable (default 25 per 5 minutes) for this reason. | Medium | Medium | ✅ Done |
| 13 | Link shortener + UTM builder | Automatic UTM parameters per channel and short links to track content performance from clicks. | Medium | Medium | ✅ Done |

### Out of the roadmap (API limitations, not technical choices)

- **Remove from Platform for Instagram and TikTok.** Neither platform offers an API to delete posts. This is documented as an official limitation; delete these posts manually in the app.
- **Instagram Stories via API** are already supported (Business accounts), so no extra work is needed.

### Suggested focus

| Question | Short answer |
|---|---|
| What to do now? | Submit the 3 platform audits (TikTok, YouTube, Meta) — they are the only roadmap items that are not code, and every platform feature stays in testing mode until they pass. |
| What raises the product's selling value fastest? | Carousel (item 6) and the analytics dashboard (item 7): the two features prospects will look at in a demo. |
| What can wait? | X and Threads, and direct messages in the inbox. |
| Biggest risk | The platform audit path is slow and outside our control, so submit it at the start, not after development is finished. |

## Project structure

```
energyx_social/
  hooks.py  jobs.py  api.py  notifications.py
  www/s.py                         # public short-link redirect (/s/<code>)
  setup/install.py                 # roles + workflow
  public/images/logo.svg           # app icon
  services/
    client.py  media.py  credentials.py  errors.py  publisher.py  hashtags.py
    comments.py  links.py  bulk.py  recurring.py  library.py
    providers/{meta,youtube,tiktok,linkedin}.py
  social_posting/
    workspace/socialx/             # Desk workspace (SocialX)
    doctype/
      social_posting_settings/     # single doctype: accounts, base URL, TikTok options
      social_account/              # child table: credentials per account
      social_post/                 # the post, with workflow, preview and calendar view
      social_post_channel/         # child table: one row per target channel
      social_post_metric/          # child table: daily analytics
      social_metric_weekly/        # weekly metric roll-ups
      social_hashtag_template/     # reusable hashtag sets
      social_post_media/           # child table: carousel / album slides
      social_revision_note/        # child table: structured revision notes
      social_media_asset/          # media library
      social_comment/              # comment inbox
      social_recurring_post/  social_recurring_channel/   # recurring templates
      social_short_link/           # short links + click counter
    report/social_analytics/       # analytics script report
```

## License

MIT. See the license declared in `hooks.py`.

---

SocialX is built by **EnergyX 369**.
