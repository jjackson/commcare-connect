# Streamlined View - Recent Updates

## Changes Made

### 1. ✅ Action Buttons Streamlined

**Before:** 3 columns with vertical layout
**After:** Single compact row with horizontal layout

- **Contact Worker** moved to first position (left)
- **Assign to NM** in middle position
- **Assign to PM** in right position
- Buttons flex-wrap on smaller screens
- Minimum width of 200px per button

### 2. ✅ Role Tags (Badges)

All role identifiers now use consistent badge styling:

```html
<span
  class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800"
>
  Program Manager
</span>
```

**Colors:**

- **Program Manager**: Blue (`bg-blue-100 text-blue-800`)
- **Network Manager**: Purple (`bg-purple-100 text-purple-800`)
- **AI Assistant**: Green (`bg-green-100 text-green-800`)

**Format:** `[Role Badge] [User Name]`

- Example: `Program Manager PM - Michael Chen`
- Example: `Network Manager Jane Smith`

### 3. ✅ Consistent Icons

- **All comments**: `fa-comment` (gray circle background)
- **AI conversations**: `fa-robot` (green circle background)
- No more color-coded icons based on event type

### 4. ✅ Button Text Updated

- Changed from "Post Comment" to "Add comment"

### 5. ✅ AI Conversation Component

New expandable AI conversation element showing:

**Collapsed State:**

- Green left border (4px)
- Green background tint
- Robot icon
- AI Assistant badge
- Brief description: "SMS conversation with worker about quality concerns"
- Chevron (up/down) to indicate expandability

**Expanded State:**

- Full conversation thread with messages alternating between:
  - **AI messages**: Green robot avatar, green border
  - **Worker replies**: Gray user avatar, gray border
- Each message shows timestamp and sender
- Footer showing: "Conversation completed • Issue documented • Network Manager notified"

**Example Conversation Flow:**

1. AI: Asks about quality concerns
2. Worker: Explains camera issue on phone
3. AI: Suggests app update
4. Worker: Accepts help
5. AI: Sends instructions and notifies NM

## Visual Design

### Action Buttons Row

```
┌─────────────────┬─────────────────┬─────────────────┐
│ [Contact Worker]│ [Assign to NM]  │ [Assign to PM]  │
│ 🟢 Send message │ 🟣 Route review │ 🔵 Escalate     │
└─────────────────┴─────────────────┴─────────────────┘
```

### Comment Timeline Entry

```
┌──────────────────────────────────────────────┐
│ 💬  [Program Manager] PM - Michael Chen      │
│     3 weeks ago                              │
│                                              │
│     Commented                                │
│     Thanks for the context. Let's...         │
└──────────────────────────────────────────────┘
```

### AI Conversation Entry

```
┌──────────────────────────────────────────────┐ Green border
│ 🤖  [AI Assistant] contacted Sarah Johnson   │
│     2 days ago                               │
│                                              │
│     SMS conversation with worker... ⌄        │
│                                              │
│     [Expanded: 5 messages back-and-forth]    │
│     ✓ Conversation completed                 │
└──────────────────────────────────────────────┘
```

## Technical Details

### Alpine.js State

Added new property:

```javascript
showAIConversation: false; // Controls expand/collapse
```

### Role Detection Logic

```django
{% if "Program Manager" in item.actor or item.actor == action.created_by %}
  <span class="...bg-blue-100 text-blue-800">Program Manager</span>
{% elif "Network Manager" in item.actor or item.actor == action.assigned_to %}
  <span class="...bg-purple-100 text-purple-800">Network Manager</span>
{% endif %}
```

### Button Layout

```html
<div class="flex flex-wrap gap-3">
  <button class="flex-1 min-w-[200px]">...</button>
  <button class="flex-1 min-w-[200px]">...</button>
  <button class="flex-1 min-w-[200px]">...</button>
</div>
```

## Screenshots

1. **`streamlined-view-updated.png`**

   - Shows compact action buttons row
   - Displays role badges in comments
   - Shows collapsed AI conversation

2. **`streamlined-view-ai-conversation-expanded.png`**
   - Full view with AI conversation expanded
   - Shows back-and-forth message flow
   - Demonstrates AI/Worker message styling differences

## Next Steps (If Needed)

Potential future enhancements:

1. Add more AI conversation examples for different scenarios
2. Make role badge colors themeable/configurable
3. Add "Start AI Conversation" button to Contact Worker modal
4. Track AI conversation success metrics
5. Allow manual override of role badges for edge cases

## Files Modified

- `commcare_connect/templates/actions/action_detail_streamlined.html`
  - Action buttons section (lines 105-143)
  - Comment timeline section (lines 181-308)
  - Alpine.js state (line 456)
  - Button text (line 176)

Total changes: ~150 lines modified/added
