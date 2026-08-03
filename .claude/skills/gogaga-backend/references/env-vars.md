# Real Environment Variables (core/config.py names) + GoGaga additions

Existing (Settings class): APP_NAME, APP_VERSION, DEBUG, ENVIRONMENT, FRONTEND_URL, ALLOWED_ORIGINS,
SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY,
JWT_SECRET (HS256 access), JWT_REFRESH_SECRET (separate!), JWT_ACCESS_TTL_MIN=15, JWT_REFRESH_TTL_DAYS=7,
FERNET_KEY (optional; dev-derives from JWT_SECRET), SENDGRID_API_KEY, NOTIFICATION_EMAIL, FROM_EMAIL,
plus provider stubs (Twilio/Wapi) — check config.py for exact names before use.

Add per phase (extend Settings, fail-fast on missing):
P1: REDIS_URL (logout blacklist — also add redis service to docker-compose)
P2: PLIVO_AUTH_ID, PLIVO_AUTH_TOKEN, PLIVO_PHONE_NUMBER, SARVAM_API_KEY, DEEPGRAM_API_KEY, ELEVENLABS_API_KEY, ANTHROPIC_API_KEY, PUBLIC_BASE_URL (ngrok in dev)
P4: RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, RAZORPAY_WEBHOOK_SECRET, GEMINI_API_KEY, WHATSAPP creds (check wapi provider's existing names first)

Rules: config only via pydantic Settings; never os.environ inline; secrets never logged; update this file + config.py together.
