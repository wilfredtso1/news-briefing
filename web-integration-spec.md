# Web Integration Spec — Alloy UI → FastAPI Backend

> This doc specifies exactly what needs to change in the React app and what new endpoints
> need to be added to the FastAPI backend to wire the two together.
>
> The UI is at: `/Users/wilfredtso/Downloads/Alloy Form Design for News Agent`
> The backend is at: `/Users/wilfredtso/news-briefing-agent`

---

## Overview

The React app is a complete, static SPA built with Vite + React Router. Every page and
interaction point exists but uses hardcoded mock data and simulated delays. The work is:

1. Add 7 API endpoints to `main.py`
2. Replace 5 stubs in the React app with real `fetch()` calls
3. Add session handling to both sides
4. Add one new env var group (`GOOGLE_OAUTH_*`)

No page redesigns. No routing changes. No new React pages.

---

## Architecture

```
React SPA (Vite, served as static files)
    ↕ HTTPS + session cookie
FastAPI backend (existing, on Railway)
    ↕
Supabase (users table + existing tables)
    ↕
Gmail API (per-user credentials)
```

**Hosting options:**
- Serve the built React app as static files from FastAPI (`app.mount("/", StaticFiles(...))`)
- Or deploy the React app separately (Vercel/Netlify) with CORS configured on the FastAPI backend

Serving from FastAPI is simpler for now — one Railway service, no CORS to manage.

---

## New Environment Variables

Add to `.env` and `.env.example`:

```
# Google OAuth — for user sign-in flow (separate from service account GMAIL_* vars)
GOOGLE_OAUTH_CLIENT_ID=...       # from Google Cloud Console, OAuth 2.0 client
GOOGLE_OAUTH_CLIENT_SECRET=...
GOOGLE_OAUTH_REDIRECT_URI=https://[your-domain]/auth/google/callback

# Session security
SESSION_SECRET_KEY=...           # random 32-byte hex string, for signing session cookies

# Unsubscribe link signing
UNSUBSCRIBE_SECRET_KEY=...       # random 32-byte hex string, for signing unsubscribe tokens
```

**Note**: `GOOGLE_OAUTH_CLIENT_ID` is different from `GMAIL_CLIENT_ID`. The existing
`GMAIL_*` vars are for the service-level Gmail API access (sending, archiving). The new
`GOOGLE_OAUTH_*` vars are specifically for the user sign-in OAuth consent flow.

---

## Backend: New Endpoints

Add all of the following to `main.py`. Each maps to one interaction in the React app.

---

### 1. `GET /auth/google` — Initiate OAuth

Redirects the browser to Google's OAuth consent screen requesting Gmail scopes.

```python
@app.get("/auth/google")
async def auth_google():
    params = {
        "client_id": settings.google_oauth_client_id,
        "redirect_uri": settings.google_oauth_redirect_uri,
        "response_type": "code",
        "scope": " ".join([
            "openid",
            "email",
            "profile",
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.send",
            "https://www.googleapis.com/auth/gmail.modify",
        ]),
        "access_type": "offline",   # required to get refresh_token
        "prompt": "consent",        # required to always get refresh_token on re-auth
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    return RedirectResponse(url)
```

---

### 2. `GET /auth/google/callback` — OAuth Callback

Exchanges the auth code for tokens, creates or updates the user record, sets session cookie,
redirects to `/setup` (new users) or `/account` (returning users).

```python
@app.get("/auth/google/callback")
async def auth_google_callback(code: str, response: Response):
    # 1. Exchange code for tokens
    token_response = httpx.post("https://oauth2.googleapis.com/token", data={
        "code": code,
        "client_id": settings.google_oauth_client_id,
        "client_secret": settings.google_oauth_client_secret,
        "redirect_uri": settings.google_oauth_redirect_uri,
        "grant_type": "authorization_code",
    })
    tokens = token_response.json()
    # tokens contains: access_token, refresh_token, id_token

    # 2. Decode id_token to get user info (google_sub, email, name)
    # Use google-auth library: google.oauth2.id_token.verify_oauth2_token(...)

    # 3. Upsert user in DB
    user = upsert_user(
        google_sub=claims["sub"],
        email=claims["email"],
        display_name=claims.get("name"),
        refresh_token=encrypt(tokens["refresh_token"]),  # encrypt before storing
    )

    # 4. Set session cookie
    session_token = sign_session(user.id)  # HMAC-signed user_id
    response.set_cookie("session", session_token, httponly=True, secure=True, samesite="lax")

    # 5. Redirect
    if user.onboarding_complete:
        return RedirectResponse("/account")
    return RedirectResponse("/setup")
```

**DB helper needed**: `upsert_user(google_sub, email, display_name, refresh_token)` in `tools/db.py`
— INSERT ... ON CONFLICT (google_sub) DO UPDATE SET refresh_token, display_name.

---

### 3. `GET /api/me` — Current User Data

Called by `SetupPage` (to pre-fill email) and `AccountPage` (to show status/last brief).
Returns 401 if no valid session cookie.

```python
@app.get("/api/me")
async def get_me(request: Request):
    user = require_session(request)  # raises 401 if no valid cookie
    return {
        "id": str(user.id),
        "email": user.email,
        "delivery_email": user.delivery_email,
        "display_name": user.display_name,
        "first_name": user.display_name.split()[0] if user.display_name else user.email,
        "timezone": user.timezone,
        "status": user.status,             # "active" | "waiting" | "paused"
        "onboarding_complete": user.onboarding_complete,
        "last_brief_at": user.last_brief_at.isoformat() if user.last_brief_at else None,
    }
```

**`status` mapping:**
- `"waiting"` — `onboarding_complete = false` (still waiting for setup email reply)
- `"active"` — `onboarding_complete = true` and `status = 'active'`
- `"paused"` — `status = 'paused'`

---

### 4. `POST /api/setup` — Submit Setup Form

Called when user submits the `/setup` form. Writes delivery email + timezone to the user
record, then triggers onboarding (inbox scan + setup email) as a background task.

```python
@app.post("/api/setup")
async def setup(request: Request, background_tasks: BackgroundTasks, body: SetupRequest):
    user = require_session(request)
    update_user_setup(user.id, delivery_email=body.delivery_email, timezone=body.timezone)
    background_tasks.add_task(_run_onboard, user_id=user.id)
    return {"ok": True}

class SetupRequest(BaseModel):
    delivery_email: str
    timezone: str
```

`_run_onboard(user_id)` already exists — just needs a `user_id` parameter added.

---

### 5. `POST /api/pause` — Pause Briefings

```python
@app.post("/api/pause")
async def pause(request: Request):
    user = require_session(request)
    set_user_status(user.id, "paused")
    return {"ok": True}
```

---

### 6. `DELETE /api/account` — Delete Account

Marks user as deleted, revokes Gmail token with Google, returns 200. The React app then
navigates to `/unsubscribe` client-side.

```python
@app.delete("/api/account")
async def delete_account(request: Request, response: Response):
    user = require_session(request)
    # Revoke token with Google
    httpx.post("https://oauth2.googleapis.com/revoke",
               params={"token": decrypt(user.refresh_token)})
    set_user_status(user.id, "deleted")
    response.delete_cookie("session")
    return {"ok": True}
```

---

### 7. `GET /unsubscribe` — One-Click Unsubscribe from Email Link

This endpoint is hit from the unsubscribe link in every brief footer. Validates a signed
token, marks user deleted, then serves the unsubscribe confirmation page (or redirects to
`/unsubscribe` which the React SPA renders).

```python
@app.get("/unsubscribe")
async def unsubscribe(token: str):
    user_id = verify_unsubscribe_token(token)  # raises 400 if invalid/expired
    set_user_status(user_id, "deleted")
    return RedirectResponse("/unsubscribe")    # React SPA renders the confirmation page
```

**Token generation** (add to digest formatter): every brief footer gets a signed token:
```python
import hmac, hashlib, base64

def make_unsubscribe_token(user_id: str) -> str:
    sig = hmac.new(UNSUBSCRIBE_SECRET_KEY.encode(), user_id.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(f"{user_id}:{base64.b64encode(sig).decode()}".encode()).decode()
```

---

## Session Handling

Use `itsdangerous` (already a common FastAPI dependency) to sign session cookies:

```python
from itsdangerous import URLSafeSerializer

_signer = URLSafeSerializer(settings.session_secret_key)

def sign_session(user_id: str) -> str:
    return _signer.dumps(str(user_id))

def require_session(request: Request) -> User:
    token = request.cookies.get("session")
    if not token:
        raise HTTPException(status_code=401)
    try:
        user_id = _signer.loads(token)
    except Exception:
        raise HTTPException(status_code=401)
    user = get_user_by_id(user_id)
    if not user or user.status == "deleted":
        raise HTTPException(status_code=401)
    return user
```

---

## Frontend: Changes Required

Five stubs to replace with real API calls. No other changes.

---

### 1. `LandingPage.tsx` — `handleSignIn`

**Current:**
```tsx
const handleSignIn = () => {
    navigate('/setup');  // simulate sign-in
};
```

**Replace with:**
```tsx
const handleSignIn = () => {
    window.location.href = '/auth/google';  // redirect to OAuth flow
};
```

No `fetch()` needed — the backend redirects to Google and back.

---

### 2. `SetupPage.tsx` — pre-fill email from session

**Current:**
```tsx
const [email, setEmail] = useState('alex@example.com');
```

**Replace with:**
```tsx
const [email, setEmail] = useState('');

useEffect(() => {
    fetch('/api/me')
        .then(r => r.json())
        .then(user => setEmail(user.delivery_email || user.email));
}, []);
```

---

### 3. `SetupPage.tsx` — `handleSubmit`

**Current:**
```tsx
await new Promise(resolve => setTimeout(resolve, 1000));  // simulate API
navigate('/confirm');
```

**Replace with:**
```tsx
const res = await fetch('/api/setup', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ delivery_email: email, timezone }),
});
if (!res.ok) throw new Error('Setup failed');
navigate('/confirm');
```

---

### 4. `AccountPage.tsx` — load real user data

**Current:**
```tsx
const user = {
    firstName: 'Alex',
    email: 'alex@example.com',
    lastBriefSent: '2026-03-25',
    lastBriefTime: '7:42 AM',
    status: 'active' as 'active' | 'waiting' | 'paused',
};
```

**Replace with:**
```tsx
const [user, setUser] = useState<User | null>(null);

useEffect(() => {
    fetch('/api/me')
        .then(r => { if (!r.ok) throw new Error(); return r.json(); })
        .then(setUser)
        .catch(() => navigate('/'));  // redirect to landing if unauthenticated
}, []);
```

Where `User` type mirrors the `/api/me` response shape.

---

### 5. `AccountPage.tsx` — `handlePause` and `handleDelete`

**Current:**
```tsx
const handlePause = async () => {
    await new Promise(resolve => setTimeout(resolve, 1000));
};

const handleDelete = () => {
    setShowDeleteModal(false);
    navigate('/unsubscribe');
};
```

**Replace with:**
```tsx
const handlePause = async () => {
    setIsPausing(true);
    await fetch('/api/pause', { method: 'POST' });
    setUser(u => u ? { ...u, status: 'paused' } : u);
    setIsPausing(false);
};

const handleDelete = async () => {
    setShowDeleteModal(false);
    await fetch('/api/account', { method: 'DELETE' });
    navigate('/unsubscribe');
};
```

---

## New DB Helpers (add to `tools/db.py`)

```python
def upsert_user(google_sub, email, display_name, refresh_token) -> User: ...
def get_user_by_id(user_id) -> User | None: ...
def update_user_setup(user_id, delivery_email, timezone) -> None: ...
def set_user_status(user_id, status) -> None: ...
```

---

## New Tables (migration required)

```sql
-- migrations/005_users.sql

CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    google_sub      TEXT NOT NULL UNIQUE,
    email           TEXT NOT NULL UNIQUE,
    display_name    TEXT,
    refresh_token   TEXT NOT NULL,
    delivery_email  TEXT NOT NULL,
    timezone        TEXT NOT NULL DEFAULT 'America/New_York',
    status          TEXT NOT NULL DEFAULT 'active',
    onboarding_complete BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_brief_at   TIMESTAMPTZ
);

-- Rollback: DROP TABLE users;
```

Adding `user_id` to existing tables is a separate, larger migration (see multi-user-spec.md).
This migration just adds the `users` table so sign-up works end-to-end for new users.
Existing single-user behavior is unchanged until the larger multi-tenancy migration runs.

---

## Deployment

1. Build the React app: `bun run build` in the Alloy project folder
2. Copy `dist/` into the news-briefing-agent project (e.g. `static/`)
3. Add to `main.py`:
   ```python
   from fastapi.staticfiles import StaticFiles
   app.mount("/", StaticFiles(directory="static", html=True), name="static")
   ```
   **Important**: mount static files LAST, after all API routes, so `/auth/*` and `/api/*`
   routes are matched before the SPA catch-all.
4. Add `static/` to `.gitignore`; build step in Railway's build command:
   ```
   cd /path/to/alloy-app && bun install && bun run build && cp -r dist/ /app/static/
   ```

---

## What This Does NOT Cover

- Multi-tenancy (`user_id` on all pipeline tables) — that's the larger migration in multi-user-spec.md
- Encrypting `refresh_token` at rest — use `cryptography` library (`Fernet`), key in env var
- Google OAuth app verification for production launch (required for >100 users)
- Rate limiting sign-up endpoint
- Privacy policy page (`/privacy` is linked in the footer)
