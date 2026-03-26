# Golf Agent Form - Ready for Codex

## What's Included

### `form/index.html`
A standalone HTML + vanilla JS form that matches the architecture spec. It includes:
- Yes/No attendance question
- Course selection (populated dynamically from session data)
- Time slot selection: 9-10 AM, 10-11 AM, 11 AM-12 PM, 12-1 PM, 1-2 PM, 2-3 PM
- New player profile section: name, phone, general availability, favorite courses
- Success state with agent contact info

### How It Works
1. **URL Parameters**: Form reads `session_id` and `player_id` from query string
2. **Data Loading**: Fetches session data from Supabase (lead name, date, courses)
3. **Form Submission**: Writes to `session_players` and `players` tables

---

## Integration Checklist for Codex

### 1. Supabase Setup
```javascript
// Update these constants in form/index.html
const SUPABASE_URL = 'https://your-project.supabase.co';
const SUPABASE_ANON_KEY = 'your-anon-key';
```

### 2. Row Level Security (RLS) Policies
```sql
-- Allow players to update their own session_player row
CREATE POLICY "Players can update own session response"
ON session_players FOR UPDATE
USING (player_id = auth.uid())
WITH CHECK (player_id = auth.uid());

-- Allow players to read their session
CREATE POLICY "Players can read own session"
ON sessions FOR SELECT
USING (id IN (
  SELECT session_id FROM session_players WHERE player_id = auth.uid()
));
```

### 3. Uncomment Supabase Code
Search for `// TODO:` comments in `form/index.html` to find:
- `loadSessionData()` - fetch session and player data
- `submit handler` - write form responses to Supabase

### 4. Generate Form URLs
When creating a session, generate URLs like:
```
https://your-domain.com/form/?session_id=abc123&player_id=player456
```

### 5. Host the Form
Options:
- Supabase Storage (static hosting)
- Vercel/Netlify (free static hosting)
- GitHub Pages

---

## Database Schema Reference

```sql
-- session_players table (form writes here)
session_id UUID
player_id UUID
status TEXT -- 'confirmed' | 'declined'
available_time_blocks JSONB -- ['9_10am', '10_11am', ...]
approved_courses JSONB -- ['Bethpage Black', 'Marine Park', ...]
responded_at TIMESTAMPTZ

-- players table (profile updates go here)
name TEXT
phone TEXT
general_availability JSONB
course_preferences JSONB
```

---

## Testing the Form

Open `form/index.html` directly in a browser - it loads mock data when no URL params are present.

To test with params:
```
file:///path/to/form/index.html?session_id=test123&player_id=player456
```

---

## Key Files for Codex

| File | Purpose |
|------|---------|
| `form/index.html` | The player-facing form (this file) |
| `schema.sql` | Database schema (from your spec) |
| `main.py` | FastAPI webhook endpoint (create this) |
| `tools.py` | Tool implementations for LLM (create this) |
| `policy_engine.py` | Intersection logic (create this) |

---

## Next Steps for Codex

1. **Create Supabase project** and run schema.sql
2. **Update form** with your Supabase credentials
3. **Build FastAPI webhook** for Twilio SMS
4. **Implement session creation** when lead texts "Set up a round..."
5. **Wire up form URL generation** and SMS sending
