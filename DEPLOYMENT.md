# Deploying the backend

Free stack: Render (API), Supabase (database and login), Cloudinary (media), Resend (email),
Cloudflare Turnstile (spam protection) and a Cloudflare Worker (timer).

## Before the first deploy

1. Apply `supabase/migrations/009_public_site.sql` to the database.
2. In Supabase, go to Authentication → Sign In / Providers and turn off new signups. Check you can still log in.

## Render

1. New → Blueprint, and connect this repo. It reads `render.yaml`.
2. Enter every value marked `sync: false`. Use the same values as your local `.env` where they exist.
3. Set `CORS_ALLOWED_ORIGINS` to the three site addresses, separated by spaces.
4. Check `https://<service>.onrender.com/healthz` returns `{"status":"ok","env":"production"}`.

Generate `BLOG_CRON_SECRET` yourself, for example with `openssl rand -hex 32`.

## Timer

From `infra/cron-worker`:

```
npx wrangler deploy
npx wrangler secret put API_BASE_URL       # https://<service>.onrender.com
npx wrangler secret put BLOG_CRON_SECRET   # same value as on Render
```

Check Render's current terms on keep-alive requests when you set this up.

## Email

In Resend, verify the domain you send from, then set `RESEND_API_KEY`, `EMAIL_FROM` and `CONTACT_NOTIFY_EMAIL`.
Until these are set, contact messages still save to the Inbox, but newsletter confirmation emails can't be sent.

## Backups

Supabase's free plan has no automatic backups. See `.github/workflows/backup.yml`.
