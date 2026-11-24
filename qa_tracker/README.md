# QA Tracker for Frappe

A self-hosted app for tracking software testing. Every issue keeps its screenshots, and each one moves through **Test → Retest → Confirmed → UAT**. Testers and developers can post updates from the web, **email, WhatsApp or Microsoft Teams**, and each message plus its screenshots becomes a ticket they can track.

- **Multi-project, multi-vendor (v2):** run many projects for many clients on one site. Each project has its own site tree, vendors and team. Vendors only ever see their own tickets and gaps.
- MIT licence. No paid components. WhatsApp uses Meta's Cloud API, which has its own per-message pricing; everything else (Raven, Telegram, email, Teams webhooks, Google Chat webhooks) is free.

### Supported Frappe versions

| Frappe | Python / Node | Status |
|---|---|---|
| v14 (tested 14.101) | 3.10 / 18+ | ✅ All features except Raven (Raven needs Frappe 15.111+) |
| v15 (tested 15.127) | 3.11 / 18+ | ✅ All features, including Raven |
| v16 (tested 16.60) — current Frappe Cloud stable | 3.14 / 24 | ✅ All features, including Raven |
| v17 (develop / nightly) | 3.14 / 24 | Declared supported (`frappe <18`); not released yet, so re-test when it ships |

Version differences are handled in `qa_tracker/compat.py`. The tester portal is plain JS/CSS with no build step, so it works the same everywhere, including Frappe Cloud.

---

## 1. What you get

| Area | What it does |
|---|---|
| **QA Issue** | Has a title, type (Bug / Configuration / Change Request / Query / Data Migration / Integration), severity, site, module, cycle and screenshots. Each issue gets an issue code like `PKL-BIL-0014`. The form is split into tabs: Details, Updates, Fix & Retest, UAT and More. A stage bar and a screenshot gallery sit at the top. |
| **Stages (workflow)** | New → Triaged → Assigned → In Progress → **Ready for Retest** → (Reopened ↺) → **Retest Passed** → **Confirmed** → **In UAT** → **UAT Accepted**. Queries go Answered → Closed. Issues can also be Deferred or Rejected. |
| **Updates** | Testers, developers, the QA lead and UAT users can post updates with screenshots in **any** status, from the web (the **Add Update** button) or from email / WhatsApp / Teams. The other side is notified. Every status change, fix, retest and UAT result is also written to the Updates log. |
| **One-click stage buttons** | Developer: **Mark Fixed** / **Answer Query** (resolution, root cause, build). Tester: **Record Retest** (Pass / Fail with notes, build and screenshots). UAT user: **Record UAT Result**. |
| **Test Cycles / Test Cases / Test Runs** | Plan a cycle (phase Test / Retest / UAT) and assign modules to testers. **Create Test Runs for Testers** gives each tester their own list. A failed run turns into an issue with one click, carrying its steps and screenshots. |
| **Dashboard** | QA Tracker workspace with number cards (Open, Blockers, Ready for Retest, In UAT, Done), charts, a Kanban board and the **QA Issue Summary** report (grouped by tester, developer, module, site, cycle or channel). |
| **Import** | **QA Import Batch** pulls in existing Word observation documents (text plus embedded screenshots) and Excel trackers (it maps status columns and flags likely duplicates). |
| **Notifications** | In-app alerts, emails threaded per ticket, WhatsApp replies, Teams channel cards, and a daily digest email for leads, developers and testers. |

Roles: **QA Lead**, **QA Tester**, **Vendor Developer**, **UAT User** and **QA Viewer**.

---

## 1a. Projects, site trees and vendors (multi-vendor)

```
Project  (e.g. "NWH MedX Go-Live", client: The Nairobi West Hospital)
 ├─ Site tree root ─ Nairobi West Group ─┬─ Parklands ─ Wards, Pharmacy…
 │                                       └─ Utawala
 ├─ Vendors ─ Trilo (MedX HMIS) · LabSys (Lab LIS) · …   each with a fix SLA
 └─ Team    ─ QA Leads, Testers, UAT users (client staff)
              Developers of each vendor (vendor staff)
```

**Who sees what**

| Person | Sees |
|---|---|
| System Manager | Everything, every project |
| Client staff: a project member **without** a vendor | The whole project, every vendor's tickets and gaps, plus the vendor scoreboard |
| Vendor staff: a project member **with** a vendor | Only that vendor's tickets and gaps in that project. Never other vendors, never other projects. |
| Anyone | Tickets they reported themselves |

The rule is the same everywhere: Desk lists, reports, dashboards, the `/qa` portal, the gap tracker, and chat commands (`status ISS-…`, replies on WhatsApp, Telegram, Raven and Teams).

**Setting up a project (QA Lead or System Manager)**
1. **QA Site → Tree view.** Build your tree, e.g. *Nairobi West Group* (group) → *Parklands*, *Utawala*. Existing sites are kept as top-level sites.
2. **QA Vendor → New.** Add one per vendor, with name, code, product and **fix SLA days** per severity.
3. **QA Project → New.** Fill in name, code (used as a `#CODE` message tag), client and **Site Tree Root**. Add the **Vendors** (optionally a *Default Assignee* per vendor) and the **Team**:
   - Client staff: role QA Lead / Tester / UAT User / Viewer / Gap Analyst / Gap Approver, with **Vendor left blank**.
   - Vendor staff: role Developer, with **Vendor set**.
   Saving gives each person the matching Frappe role automatically.
4. Optional, per project: a Raven channel (messages there become tickets of that project), and Teams / Google Chat webhooks for status cards.
5. Optional: set a **Vendor** on each QA Module (e.g. Laboratory → LabSys). Tickets in that area then go to that vendor automatically. Leave *Project* on a module blank to share it across projects.

**Sub-projects.** Any project can have sub-projects (phase, branch, workstream), e.g. *NWH MedX Go-Live* → *Phase 1 Parklands*, *Phase 2 Utawala*, *Lab Rollout*. In Desk use **QA Project → Tree view**; in the portal use **Team & coverage → New sub-project**.
- Members of a parent project automatically see every sub-project below it. People added only to a sub-project see only that sub-project.
- Sub-projects inherit the parent's **vendors** and **site tree**, unless the sub-project sets its own *Site Tree Root*.
- Lists, the vendor scoreboard and gap screens on a parent project roll up everything below it.
- QA Leads of a parent project manage its sub-projects. A sub-project's own lead can't change the parent.

**Allocations: limiting people to sites and areas.** On a project's **Allocations** table (or in the portal: **Team & coverage → Limit**), each row is *person + site (or a group of sites) + area*:
- No rows: the person sees the whole project.
- *Parklands · Pharmacy*: only Pharmacy at Parklands.
- *Nairobi West Group · Laboratory*: Laboratory at every site under that group.
- Several rows add up, e.g. Parklands · Pharmacy **plus** Utawala · Pharmacy.

People with limits still see records that don't have a site or area yet, and always see the tickets they reported. The report form only offers their sites and areas. Vendor staff can be limited too: the vendor rule and the limits both apply.

**Team & coverage (portal, for QA Leads).** Open it from the avatar menu or the link on the home screen. It shows:
- **Sub-projects**, with open tickets and member counts. You can open one or create a new one.
- **People**, with role, vendor and limits. You can add a person, add or remove limits, and deactivate someone.
- **Test coverage**: a site × area grid counting the client testers, UAT users and QA leads who cover each cell. Red means nobody covers it, amber means one person, green means two or more.

**How tickets get their project and vendor**
- Portal: the **project switcher** at the top (the choice is remembered), then *Which system / vendor?* on the report form. It is pre-selected from the area, and vendor staff are fixed to their own vendor.
- Chat and email: a `#CODE` tag (e.g. `#MEDX`), else the project's own Raven channel, else the sender's only project, else **QA Settings → Default Project**.
- Vendor: the vendor of the sender (vendor staff), else the module's vendor, else the project's only vendor.

**SLA.** When a ticket is assigned, its *Target Date* is set from the vendor's SLA for that severity. Every morning an **overdue digest** goes to the project's QA leads, the vendor's staff and the assignee.

**Portal for client staff.** The home screen shows a **vendor scoreboard** (open, blockers, overdue, waiting for retest, average age). Click a vendor to filter the list. *All my projects* in the switcher gives a combined view.

**Upgrading from v1.** `bench migrate` (Deploy on Frappe Cloud) creates **Main Project**, puts all existing tickets, cycles and gaps in it, and adds everyone who has a QA role as client staff. Nobody loses access. Then rename the project, add your vendors, and set the vendor on vendor developers' team rows. From that point they see only their vendor's work.

## 1c. Support tiers, management dashboard and role workspaces

**Support levels.** Every ticket has a **Support Level**: **L1** (hospital helpdesk / super users), **L2** (application support) or **L3** (vendor engineering). New tickets start at L1.

| Role (Frappe) | Project role | Can do |
|---|---|---|
| L1 Support | L1 Support | Triage, reject, defer, assign, answer how-to questions, **escalate to L2** |
| L2 Support | L2 Support | Start work, mark fixed, answer, **escalate to L3** or **send back to L1** |
| L3 Support | L3 Support | Start work, mark fixed, answer, **send back to L2** |
| QA Management | Management | Read-only: dashboards, reports and tickets of their projects |

On a ticket, the tier holding it (or a QA Lead) sees **Escalate to L2/L3** or **Send back**. A reason is required, and the ticket can be assigned to someone at the new level in the same step. The move is recorded on the timeline (*Last Escalated On / By / Note*), and the project's members at that level, plus the assignee, are notified. **Needs you** shows each tier its queue: L1 sees new and triaged L1 tickets, and L2 and L3 see unassigned tickets at their level and anything assigned to them. Add people to a project with the project role *L1 Support*, *L2 Support*, *L3 Support* or *Management*; vendor staff also get the vendor set.

**Management dashboard** (portal, **Dashboard** tab; it is the landing page for management users). It follows the project tree: start at *All my projects* or any project, then click a sub-project to drill in. Breadcrumbs take you back up. Filters for **vendor**, **site** (or a group of sites) and **support level** apply to the whole page. It shows:
- **Tiles:** open tickets, open blockers, past fix date, average age, last 7 days opened/closed, time to fix, fixed first time %, fixed within SLA %.
- **Sub-projects:** a RAG table. Red = open blockers or 5+ past fix date; amber = anything past fix date or an open High.
- **Weekly flow:** 12 weeks of opened, closed and open-at-week-end.
- **Breakdowns:** where tickets are by stage, support levels (L1/L2/L3), severity by level, age buckets, vendors (first-time fix and SLA %), sites (groups open their branches) and the busiest areas.
- **Lists and gaps:** the oldest blockers and High tickets, and a gap analysis summary (fit %, open must-haves, regulatory, awaiting approval, to deliver, to verify).

Every tile, bar and cell opens the matching ticket list. Figures follow each user's access, so vendor staff see only their vendor.

**Desk workspaces per role.** Each workspace is visible only to its roles:

| Workspace | For | Cards | Shortcuts |
|---|---|---|---|
| QA Management | QA Management, QA Lead, System Manager | Open, blockers, overdue, at L2, at L3, closed this week | Management Dashboard, Project Tree, Vendors, Issue Summary, Gap Tracker |
| QA Reporting | QA Tester, UAT User | My open tickets, waiting for my retest, in UAT | Report an issue, My tickets, My test runs, Gap Tracker |
| QA L1 Support | L1 Support, QA Lead | L1 triage queue, blockers, at L2, overdue | Triage queue, Portal, Issue board, Dashboard |
| QA Developer | Vendor Developer | Assigned to me, my reopened, my overdue | My work, Issue board |
| QA L2 L3 Support | L2 Support, L3 Support | At L2, at L3, assigned to me, overdue | L2 queue, L3 queue, Portal, Dashboard |

The original *QA Tracker* workspace remains for QA Leads, System Managers and viewers. Workspaces are rebuilt on every migrate, so copy one under a new name before customising it.

## 1b. Merging duplicate tickets and gaps

Several people often report the same problem. Merge the duplicates into one ticket (or gap) so they're fixed and retested once.

**Where**
- **Portal:** open a ticket or gap. If it looks like an existing one, an amber **Possible duplicates** bar appears. Click **Review & merge**, or use **Merge duplicates…** at the bottom. Then choose either:
  - *Merge others into this*: tick the duplicates in the list of similar items (ranked by % similarity) or search by number or words.
  - *This is a duplicate of…*: pick the one to keep.
- **Desk:** on the form, use **Merge → Merge duplicates into this** or **This is a duplicate of…**. In the list, tick several records and choose **Actions → Merge selected**, then pick the one to keep.

**What a merge does**
- Copies every screenshot, retest and UAT screenshot, recording and file, plus the whole timeline (marked `[ISS-…]`), into the ticket you keep. It also adds a note with the duplicate's text and reporter.
- Moves links: test runs, gap links, chat threads, and anything that was already merged into the duplicate.
- Keeps the **highest severity** (tickets) or **priority** (gaps).
- Marks each duplicate **Merged**, with a banner pointing to the kept ticket, and closes its to-dos.
- Tells the duplicate's reporter and developer. Replies like `ISS-00042 still happening` or `status ISS-00042` on WhatsApp, Telegram, Raven or email automatically go to the kept ticket.

**Who can merge:** the project's QA Leads (tickets) and Gap Analysts or QA Leads who aren't vendor staff (gaps). Only records of the same project tree can be merged. A merge can't be undone, so check the list before confirming.

## 2. The tester portal (`/qa`)

Testers, developers and UAT users don't need Desk. Send them to **https://your-site/qa**. On a phone, "Add to Home Screen" turns it into an app icon.

- **Tickets**: "Needs you" first (retests for testers, fixes for developers, accept or reject for UAT users, triage for leads), then Open and Done, with search by text or ISS number.
- **Report**: screenshots, one text box, tap-to-choose site, area and severity. The area is suggested as you type.
- **Ticket**: stage bar, big one-tap buttons (Pass / Fail, Accept / Reject, Mark fixed, Triage, Assign…), screenshot gallery, and a chat-style update thread showing which channel each update came from (Portal, Raven, WhatsApp, Telegram, Email…).
- **Test runs**: each tester's assigned test cases. Pass / Fail / Blocked; a failure raises a ticket automatically.
- QA leads can still open everything in Desk (avatar menu → Open Desk). Branding (title, logo, colour, help text) is in **QA Settings → Tester Portal**.

### Ways to add screenshots, recordings and files
Every report, update, retest and UAT screen has the same row of buttons: **Camera · Capture · Record · File**.

| Button / method | What it does | Works on |
|---|---|---|
| **Snipping Tool**: Win + Shift + S (or PrtScn), then **Ctrl + V** anywhere on the page | Pastes the snip straight in | Windows |
| Cmd + Ctrl + Shift + 4, then **Cmd + V** | Same on Mac | Mac |
| **Camera** | Phones: opens the phone camera. Desktops/laptops: opens the **webcam** inside the page (switch camera, Take photo) | All, HTTPS needed for webcam |
| **Capture** | One still screenshot of another tab, window or screen (live preview, *Capture now* / *Capture in 5 s*) | Chrome, Edge, Firefox on desktop |
| **Record** | A **screen video** of the steps, optionally **with your voice**. Floating bar with timer and Stop; preview before attaching | Chrome, Edge, Firefox on desktop |
| **File** or drag and drop | Images, videos (e.g. Snipping Tool video, Win + Shift + R), **PDF, Excel (xlsx/xls/csv), Word, PowerPoint, text/log, zip** | Everywhere |

Images open in the **markup editor** (pen, arrow, box, and a **blur tool to hide patient names or IDs**). Recordings and documents appear on the ticket under **Recordings & Files** and in the timeline as playable videos / file chips.

**Floating toolbox (Chrome / Edge): works like the Snipping Tool toolbar**
1. Click **Capture** or **Record** and choose what to share: the **MedX tab**, the **MedX window**, or your **entire screen**.
2. A small **always-on-top toolbox** pops out. Drag it anywhere, even onto another monitor. It stays visible while you work in MedX.
3. Toolbox buttons: **Snap** (screenshot now) · **3 s** (screenshot after 3 seconds, for open menus and pop-ups) · **Record / Stop** · 🎤 (voice on/off) · **Done**.
4. Take as many shots and recordings as you need, then press **Done**, or close the toolbox. Everything is added to the report; click a screenshot there to mark it up or blur patient details.
5. If Chrome doesn't pop the toolbox out by itself, click **Pop out toolbox** (Capture) or **Start in floating toolbox** (Record). Chrome only allows pop-ups straight after a click.
6. When sharing the *entire screen*, the toolbox itself appears in shots. Share the MedX window or tab instead, or blur it in the editor.

Firefox has no floating toolbox, so the in-page capture panel described below is used there.

**Capturing another screen (e.g. MedX) with the in-page panel**
1. Click **Capture** (or **Record**). Chrome asks what to share.
2. Easiest: choose the **Chrome Tab** that shows MedX (the QA Tracker tab isn't offered). For Capture press **Capture now**; you can stay on the QA Tracker tab.
3. If you share a **Window** or **Entire screen**, press **Capture in 5 s**, switch to MedX, and wait. The tab title counts down; sharing stops as soon as the shot is taken. When recording, the title shows **● REC m:ss**.
4. If you share the QA Tracker tab by mistake, the panel warns you. Use **Change source** in Chrome's sharing bar while on the MedX tab, or stop and pick again.
5. Click **Hide** on Chrome's "is sharing" bar if you don't want it in the shot.

**Recording length and file size.** Recordings are compressed (~0.7 Mbit/s) and stop automatically before they exceed the site's upload limit. With Frappe's default 10 MB limit that is about 1½ minutes; the bar shows the limit (e.g. `0:12 / 1:40`). For longer recordings raise the limit: `bench --site your.site set-config max_file_size 52428800` (50 MB; on Frappe Cloud: Site → Config → `max_file_size`). Recording is capped at 5 minutes regardless.

**HTTPS is required** for Capture, Record and the webcam (browsers block them on plain http). Frappe Cloud sites are HTTPS already.

## 3. Install

```bash
cd ~/frappe-bench
bench get-app https://your-git-server/qa_tracker.git     # or: bench get-app /path/to/qa_tracker
bench --site your.site install-app qa_tracker
bench setup requirements --python                          # installs python-docx (used by the Word import)
bench --site your.site migrate
bench restart
```

Installing creates the roles, the workflow, two sites (Parklands `PKL`, Utawala `UTW`), 14 modules with codes and keywords, the dashboard, the workspace and the Kanban board. You can edit any of these afterwards.

### First steps
1. **Users**: create a user for each tester, developer and UAT user and give them the matching role. **Put their mobile number on the user** (any format, e.g. `+254 7xx xxx xxx`). That's how WhatsApp messages are matched to a person.
2. **QA Module**: set a **Default Assignee** (developer) per module, so issues are auto-assigned when triaged.
3. **QA Settings**: default site / module / cycle for incoming messages, the grouping window (default 10 min), and **Public Base URL** (used in links sent to users).
4. **Email Account** (Setup → Email Account): set up an outgoing account so notifications can be sent.

---

## 4. How the stages work

```
 Tester logs it ──► QA Lead: Triage ──► Assign to Developer ──► Developer: Start Work / Mark Fixed
                                                                              │
          ┌──────────── Retest Failed (Reopened) ◄─── Tester: Record Retest ◄─┘
          ▼                                                 │ Pass
   Developer fixes again                                    ▼
                                    QA Lead: Confirm ──► Send to UAT ──► UAT User: Accept ──► UAT Accepted
                                                                         Reject ──► Reopened
```

- Only the **QA Lead** can triage, assign, confirm, send to UAT, defer, reject or reopen a closed issue.
- At **Triaged** the lead sees **Assign** (pick a developer), **Defer (later)** and **Reject**:
  - **Defer** = the issue is *valid* but parked for later (e.g. phase 2, change request, waiting on the vendor). It moves to **Deferred**, stays in reports, and a lead can **Reactivate** it any time. A note saying why / until when is required.
  - **Reject** = *not a real issue* (duplicate, works as designed, user error). It is closed. A reason is required.
- **Developers** record fixes. **Testers** record retests. **UAT users** record UAT results.
- Retest and UAT results each have their own screenshot tables. Retest count, reopen count and closed date are tracked automatically.
- A tester working through a test cycle opens **QA Test Execution → Set Result**. If it fails, **Raise Issue** creates the linked issue.

---

## 5. Sending tickets by chat and email

The same message rules apply on every channel:

| Message | Effect |
|---|---|
| Any text and/or screenshots | Creates a new ticket. Chat messages from the same person within the grouping window are added to the same ticket, so you can send the text first and the screenshots after. |
| `#PKL` `#UTW` · `#BIL` `#EMR` `#LAB` … · `#blocker` `#high` `#low` · `#query` · `#uat` | Sets site, module, severity, type or phase. `[PKL]` also works, e.g. in email subjects. If there's no module tag, the module is guessed from keywords. |
| `ISS-00012 your text` (+ screenshots) | Adds an update to that ticket. |
| `ISS-00012 fixed what was changed` | Developer: marks it fixed (moves to Ready for Retest). |
| `ISS-00012 pass notes` / `ISS-00012 fail notes` | Tester: records the retest result. Screenshots go into the retest screenshots. |
| `ISS-00012 accept` / `ISS-00012 reject notes` | UAT user: records the UAT result. |
| `status ISS-00012` · `my tickets` · `new` · `help` | Shows status, lists your open tickets, starts a fresh ticket, or shows help. |

Commands that change status only work if the sender is matched to a user who has the right role. Otherwise the message is saved as an update and the sender is told why.

Every incoming message is logged in **QA Channel Message**, including errors, and duplicates are ignored.

### 5.1 Email (no extra software)
1. Create a mailbox, e.g. `qa@yourhospital.co.ke`.
2. In Frappe go to **Email Account → New**. Set your IMAP or POP server, tick **Enable Incoming**, and set **Append To = QA Issue**. Tick **Enable Outgoing** too if you want acknowledgements sent from this mailbox.
3. A new email creates a ticket: the subject becomes the title, the body becomes the description and image attachments become screenshots. The sender gets an acknowledgement. **Replies** (including commands like `pass` / `fail`, and images) are added to the same ticket.
4. Notification emails are threaded, so users can reply to them directly.

### 5.2 WhatsApp (Meta WhatsApp Business Cloud API)
You need a Meta Business account, a WhatsApp Business phone number, and your site reachable on **HTTPS**.

1. Go to developers.facebook.com → your App → **WhatsApp → API Setup**. Copy the **Phone Number ID** and create a **permanent access token** (System User token with `whatsapp_business_messaging`).
2. In **QA Settings → WhatsApp**: tick Enabled, then fill in the Phone Number ID, Access Token, a **Verify Token** (any secret word you choose) and the **App Secret** (App → Settings → Basic).
3. Click **Show Webhook URLs** in QA Settings and copy the WhatsApp URL:
   `https://<site>/api/method/qa_tracker.channels.whatsapp.webhook`
4. In Meta, go to **WhatsApp → Configuration → Webhook → Edit**. Paste the URL and your Verify Token, then **subscribe to `messages`**.
5. Testers save the number and send messages and screenshots. They get a reply like:
   `✅ Ticket ISS-00042 created … reply 'ISS-00042 your update' • 'status ISS-00042' to track`.
   Swipe-replying to a bot message about a ticket adds the reply to that ticket.

Note: WhatsApp only allows free-form replies within 24 hours of the user's last message. For notifications after that, create an approved template with one body variable and put its name in **Template for notifications outside 24h window**.

### 5.3 Microsoft Teams
**Getting messages from Teams into tickets** (pick one or more):

| Option | Setup | Screenshots |
|---|---|---|
| **A. Share to Outlook** (recommended for screenshots) | None. On any Teams message choose **… → Share to Outlook** and send it to the QA mailbox. | ✅ via email intake |
| **B. Outgoing Webhook** `@QA Tracker your message` in a channel | Team → **Manage team → Apps → Create an outgoing webhook**. Name it *QA Tracker*, set the callback URL `https://<site>/api/method/qa_tracker.channels.teams.outgoing_webhook`, then paste the security token Teams shows into **QA Settings → Teams**. | Text, commands and an in-thread reply with the ticket number. Pasted images usually can't be downloaded without Microsoft Graph sign-in; the bot tells the user to use A when that happens. |
| **C. Power Automate flow** | Trigger "When a new channel message is added" → HTTP POST to the **Generic Intake API** (below), including images as base64. | ✅ (the HTTP action needs a Power Automate premium licence) |

**Status updates going to Teams:** in the channel open **… → Workflows → "Post to a channel when a webhook request is received"**, copy the URL into **QA Settings → Teams Workflow Webhook URL**, and tick **Post status changes to Teams channel**. Each new ticket and status change is posted as a card with an **Open ticket** button.

### 5.4 Raven (free, on your own Frappe site)
Raven is open-source team chat that runs on the same site, with the same users and a mobile app. It needs Frappe 15.111 or newer.
1. Install it: `bench get-app raven && bench --site your.site install-app raven` (on Frappe Cloud, add Raven from the Marketplace).
2. In Raven, create a channel such as **#qa-reports** and add your testers and developers.
3. In **QA Settings**, click **Chat → Pick Raven Channel**. This turns on Raven and creates the **QA Tracker** bot.
4. Anything posted in that channel (text, images, or both) becomes a ticket. The bot replies with a **ticket card** that shows the status and lets leads and UAT users run workflow actions from the chat.
5. **Reply** to a bot message to add an update to that ticket. The usual commands (`ISS-00012 pass`, `status ISS-00012`…) also work.
6. Status changes are posted to the channel, and people get **direct messages** from the bot ("Ready for retest", "Assigned to you"). Both can be turned off in settings.

Note: the Raven listener runs as a background job, so your bench needs its workers running (they always are on Frappe Cloud and in production setups).

### 5.5 Telegram (free)
1. In Telegram, message **@BotFather**, send `/newbot` and copy the token.
2. In **QA Settings → Telegram**: tick Enable, paste the token, type any random **Webhook Secret**, save, then click **Chat → Register Telegram Webhook**.
3. Testers open the bot and press **Start**, then tap **Share my phone number** once. That links them to their QA Tracker user by the mobile number on their profile. Linked accounts appear in **QA Channel Link**, where a lead can also link someone manually.
4. Photos (with or without captions), image files, text, replies to bot messages and all the commands work. Notifications are sent to linked users.

### 5.6 Google Chat
Google Chat apps and webhooks require a **Google Workspace** account; personal Gmail can't use them. If you have Workspace: in a Chat space open **Apps & integrations → Webhooks**, add one, and paste the URL into **QA Settings → Google Chat**. New tickets and status changes are then posted to that space as cards with an **Open ticket** button. Reporting *into* QA Tracker from Google Chat would need a full Chat app (Google Cloud project), so use email, the portal or Telegram for that.

### 5.7 Generic Intake API (any other tool)
Enable it in QA Settings and set a token.
```
POST https://<site>/api/method/qa_tracker.api.intake
Header: X-QA-Token: <token>
{
  "channel": "Teams", "sender_id": "aad-or-phone-or-email", "sender_name": "Jane",
  "sender_email": "jane@hospital.co.ke", "message_id": "unique-id",
  "text": "#PKL #BIL credit bills showing in cash counter",
  "images": [{"filename": "s1.png", "content": "<base64>"}]
}
→ {"message": {"issue": "ISS-00042", "reply": "...", "url": "..."}}
```

---

## 6. Gap analysis tracker (separate module)

A separate **Gap Analysis** module records what the hospital needs, whether the system covers it, and what happens to each gap until it's delivered and signed off. It has its own DocTypes (**Gap Assessment**, **Gap Item** and their child tables), workflow, roles, workspace, dashboard, report and print format. It shares only the Site and Module lists with QA Tracker.

**Records**
- **Gap Assessment**: one fit-gap workshop or review (e.g. "Parklands Pharmacy fit-gap"), with site, module, date, facilitator, business approver, scope and participants. It rolls up totals automatically (Fit / Partial / Gap, Fit %, open must-haves, effort, cost) and has **Sign Off** and a printable **Sign-off Sheet** with signature lines.
- **Gap Item**: one requirement. It records the business need, as-is process, what the system does today, fit status (Fit / Partial Fit / Gap / N/A), MoSCoW priority, impact, gap type, a regulatory flag (SHA, MOH, KRA, PPB…), source and reference, evidence files, resolution approach (Configuration, Customization, Workaround, Process change, Third-party, Training, Future release, Not required), proposed solution, workaround, owner, effort, cost, target release, the decision, delivery, verification with evidence, linked QA issues and test cases, and an update log.

**Stages**
```
Identified → Analysed → Awaiting Approval → Approved → In Progress → Delivered → Verified → Closed
                 │              ├─ Reject → Rejected        └─ Verification failed → In Progress
                 │              ├─ Defer  → Deferred
                 │              └─ Send back → Analysed
                 └─ Close as Fit (Fit / N/A items skip approval)
```
| Role | Does |
|---|---|
| **GA Analyst** (new) | Records and analyses gaps, submits them for approval, closes fits |
| **GA Approver** (new; business owner or steering committee) | Approves, rejects, defers or sends back; signs off assessments |
| Vendor Developer | Starts work and marks gaps delivered |
| QA Tester / UAT User | Verifies delivered gaps (Pass / Fail with evidence) |
| QA Lead | Everything |

**Fast capture and follow-up in the portal (`/qa` → Gaps)**

Analysts, approvers, developers and testers can do all of their gap work in the portal; Desk isn't needed.
- **Capture** (for workshops): pick or create the assessment, then type a requirement and press **Enter**. The text box clears and keeps focus, so the next item can be typed straight away.
  - Fit and priority are tap-to-choose and stay selected between items. On desktop, **Alt+1–4** sets the fit and **Alt+5–8** the priority.
  - Tags in the text also work: `#gap` `#partial` `#fit` `#na` · `#must` `#should` `#could` `#wont` · `#reg` (or `#sha` `#moh` `#ppb` `#kra`).
  - 🎤 **Dictate** with the microphone button (Chrome, Edge, Android; the site must be on HTTPS).
  - **Paste a list**: one requirement per line from Excel, Word or meeting notes. Bullets and numbers are removed, and each line can carry its own tags.
  - Optional details: process, how it's done today, what the system does, a regulatory flag, and screenshots or photos (paste, camera, snip).
  - **Captured now** lists this session's items. Tap the Fit or Priority badge to change it, or tap the bin twice to remove an item. Totals (Fit %, gaps, open must-haves) update live.
- **Follow-up**: each person's **Needs you** list: analysis for analysts, approval for business owners, delivery for developers, verification for testers and UAT users, closing for approvers. Each gap page has the stage bar, tap-to-change fit and priority, tap-to-choose resolution approach with owner, developer, effort and release, one-tap actions (Send for approval, Approve / Reject / Defer / Send back, Mark delivered, Works / Doesn't work, Close) and an update thread with screenshots.

**Linking to QA Tracker**
- On any QA ticket: **Create → Log as Gap** turns a change request or question found in testing into a gap. The description and screenshots are copied, the ticket is linked, and a note is added to the ticket.
- On a gap: **Create → Verification Test Case** creates a QA Test Case so the delivered gap is retested in a test cycle.

**Dashboard and reports**: **Gap Analysis** workspace (open gaps, open must-haves, awaiting approval, awaiting verification, closed), charts by fit status, module, priority, resolution approach and effort, a **Gap Board** Kanban, and the **Gap Register Summary** report. That report is a fit-gap matrix by module, site, assessment, approach, priority, party, owner or status, with Fit %, open must-haves, effort and cost. Fit % counts a partial fit as half.

**Notifications**: the business owner is told when a gap needs approval (and gets a to-do), the assignee when it's approved or verification fails, and the raiser when it's decided, delivered or closed. These go out in-app, by email, and by Raven DM if Raven is enabled.

**Bulk entry**: to load an existing gap register from Excel, use Frappe's standard **Data Import** on Gap Item (Desk → Data Import → New → Gap Item → download template).

## 7. Importing your existing Word and Excel files
**QA Import Batch → New**: attach a `.docx` or `.xlsx`, choose Site, Default Module, Test Cycle and Reported By, then click **Run Import**.

- **Word**: each observation becomes one issue. A numbered line (`3. …`) or a screenshot starts a new observation. Screenshots after the text are attached to it, and screenshots at the top of the document go to the first observation.
- **Excel**: the header row is found by a column named "Issue". Status columns are mapped: "Fixed / Completed" → Ready for Retest, "To be done / Pending" → Assigned, "…pushed" → In Progress, and a test result of "Completed / Pass" → Retest Passed. The blank column next to Issue is used as root cause. Titles that look like existing issues are flagged in **Possible Duplicate Of**.
- Imported issues need a quick review by the QA lead, because module guesses come from keywords.

You can import a whole folder from the command line:
```bash
bench --site your.site execute qa_tracker.importer.import_path \
  --kwargs "{'path': '/home/frappe/old_tests', 'site': 'Parklands', 'default_module': 'General'}"
```

---

## 8. Day-to-day use
- **Tester**: open `/qa` → **Report** (snip, paste, describe, send), or post in Raven / Telegram / WhatsApp / email → check **Needs you** and press **Pass** or **Fail** on fixes.
- **Developer**: `/qa` → **Needs you** shows your assigned issues → **Mark fixed** with the build number. Ask the tester questions in the update thread.
- **QA Lead**: triage New issues each day (set module, severity and developer), **Confirm** retested issues, **Send to UAT** (you can select several in the list and use **Actions**), and watch the dashboard and **QA Issue Summary**.
- **UAT User**: list filtered to *In UAT* → **Record UAT Result**.
- **Business analyst**: Gap Analysis workspace → create an Assessment → **Add Gap** for each requirement → set fit status, approach, owner, effort → **Submit for Approval**.
- **Business owner**: Gap Item list → *Quick Filters → Awaiting my approval* → **Decision → Approve / Reject / Defer** → finally **Sign Off** the assessment.
- A **daily digest** email goes out each morning, once an outgoing email account is set up.

---

## 9. Notes for administrators
- Everything set up at install is re-applied on `bench migrate`, and existing data is never overwritten. You can change roles and workflow transitions in the Workflow screen, but they reset on migrate. To customise them permanently, edit `qa_tracker/install.py`.
- Webhooks need **HTTPS** with a public hostname (WhatsApp and Teams both require it). Behind a firewall, open only `/api/method/qa_tracker.channels.*` and `/api/method/qa_tracker.api.intake`.
- Security: WhatsApp requests are checked against the App Secret (`X-Hub-Signature-256`), Teams requests are HMAC-signed, and the API uses a token. Screenshots are stored as **private** files.
- Backups: the usual `bench backup --with-files` includes all screenshots.
- Upgrading Frappe (for example v15 → v16): upgrade as usual, then run `bench --site your.site migrate`. QA Tracker needs no changes.
- Frappe Cloud: add the app from your Git repository to a bench group on v15 or v16, then install it on the site. Add Raven from the Marketplace if you want chat.
