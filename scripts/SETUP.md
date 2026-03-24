# Flight Email Scanner — Setup Guide

## What you need
- Python 3.10+
- A Google account (Gmail + Google Calendar)
- An Anthropic API key

---

## Step 1 — Get your Anthropic API key
1. Go to https://console.anthropic.com
2. Sign up or log in
3. Go to **API Keys** and create a new key
4. Save it somewhere safe — you'll need it in Step 4

---

## Step 2 — Create a Google Cloud project
1. Go to https://console.cloud.google.com
2. Click **Select a project** → **New Project** → give it any name → **Create**
3. Make sure your new project is selected in the top bar

---

## Step 3 — Enable Gmail and Calendar APIs
1. Go to **APIs & Services → Library**
2. Search for **Gmail API** → click it → click **Enable**
3. Go back to Library, search for **Google Calendar API** → **Enable**

---

## Step 4 — Create OAuth credentials
1. Go to **APIs & Services → Credentials**
2. Click **+ Create Credentials → OAuth client ID**
3. If prompted to configure the consent screen first:
   - Click **Configure Consent Screen**
   - Choose **External** → **Create**
   - Fill in App name (anything), your email for support and developer contact
   - Click **Save and Continue** through the rest (no need to add scopes manually)
   - On the **Test Users** screen, click **+ Add Users** and add your Gmail address
   - Click **Save and Continue** → **Back to Dashboard**
4. Back in Credentials, click **+ Create Credentials → OAuth client ID** again
   - Application type: **Desktop app**
   - Name: anything
   - Click **Create**
5. Click **Download JSON** on the popup
6. Rename the downloaded file to `credentials.json`
7. Move it into the `scripts/` folder

---

## Step 5 — Create your .env file
1. In the `scripts/` folder, copy the example file:
   ```bash
   cp .env.example .env
   ```
2. Open `.env` and replace `your_anthropic_api_key_here` with the key from Step 1

---

## Step 6 — Install dependencies
```bash
cd scripts
pip install -r requirements.txt
```

---

## Step 7 — Run it
```bash
python3 email_flight_scanner.py
```

On first run a browser window will open — log in with your Google account and click **Allow**.
Your login is saved to `token.json` locally so you only do this once.

---

## Notes
- `credentials.json`, `token.json`, and `.env` are all gitignored — never commit them
- The script only searches emails from the last 5 days by default
- It only has read access to Gmail — it cannot send, delete, or modify emails
