# StructAI Copilot — Frontend Design System

**Version 1.0 · May 2026**

This document specifies the visual language, layout architecture, component contracts, and interaction patterns for the production-ready StructAI Copilot web application. It replaces the current dashboard-centric model with a single-surface workspace.

---

## 1. Design Philosophy

**Tool-first, not app-first.** Engineers open this to work, not to navigate. Every screen exists to reduce the distance between the user and their current project. Surfaces that exist purely as navigation intermediaries (the dashboard) are eliminated.

**Calm density.** The dark engineering palette already communicates precision. Components should use space economically without feeling cramped. Nothing decorative; everything intentional.

**Progressive disclosure.** The sidebar shows enough to orient; the workspace shows everything needed to act. Panels collapse to give space to what matters right now.

---

## 2. Information Architecture

### Current State (to be removed)
```
/login
/register
/verify-pending
/verify
/forgot-password
/reset-password
/auth/callback
/dashboard          ← ELIMINATE THIS ROUTE
/                   ← workspace (requires active project; redirects to /dashboard)
```

### Target State
```
/login
/register
/verify-pending
/verify
/forgot-password
/reset-password
/auth/callback
/                   ← workspace (always accessible; shows empty state if no project open)
/profile            ← NEW: professional profile + settings page
```

The `/dashboard` page and route are deleted. Project management lives inside the collapsible project sidebar within the workspace. The root route (`/`) becomes the permanent home once authenticated.

---

## 3. Layout System

### 3.1 Three-Panel Workspace

The workspace is a full-viewport layout with three horizontal regions:

```
┌──────────────────────────────────────────────────────────────┐
│ PROJECT SIDEBAR (collapsible, 240px ↔ 48px)                  │
│                         │ STAGE HEADER (48px, spans panels 2+3) │
│  [search]               ├──────────────────────────────────────│
│  ─ Projects ─           │                                      │
│    • Greenfield Blk A   │  CANVAS VIEWPORT                     │
│    • Harbour Tower      │  (flex-1, dot-grid)                  │
│    • ...                │                                      │
│                         │                    ┌────────────────│
│  ─────────────          │                    │ CHAT SIDEBAR   │
│  [profile avatar]       │                    │ (320px,        │
│  [sign out]             │                    │  collapsible)  │
└─────────────────────────┴────────────────────┴────────────────┘
```

| Panel | Expanded | Collapsed | Trigger |
|---|---|---|---|
| Project sidebar | 240px | 48px (icon rail) | Toggle button or project click |
| Chat sidebar | 320px | 0px (hidden) | Toggle button in stage header |
| Stage header | 48px | — | Always visible when project open |

### 3.2 Empty State (No Active Project)

When no project is selected, the canvas area and chat sidebar are replaced by a centered prompt surface:

```
┌──────────────────────────────────────────────────────────────┐
│ PROJECT SIDEBAR (240px, expanded by default)                 │
│                         │                                    │
│  [search]               │         StructAI Copilot           │
│  ─ Recent ─             │                                    │
│    • Project A          │   Start a new structural project   │
│    • Project B          │   or select one from the sidebar.  │
│                         │                                    │
│  [New Project]          │   ┌──────────────────────────┐    │
│                         │   │ Project name...          │    │
│  ─────────────          │   └──────────────────────────┘    │
│  [profile avatar]       │   [Create project →]               │
│                         │                                    │
└─────────────────────────┴────────────────────────────────────┘
```

The stage header is hidden when no project is open. The AppHeader is replaced by a minimal logo bar.

---

## 4. Component Specifications

### 4.1 ProjectSidebar (New Component)

**File:** `src/components/ProjectSidebar.tsx`

**States:**
- `expanded` (240px) — full content visible
- `collapsed` (48px) — icon rail only, tooltips on hover

**Expanded layout (top → bottom):**

```
┌────────────────────────┐
│ ⬡ StructAI   [←]      │  ← logo + collapse button
├────────────────────────┤
│ 🔍 Search projects...  │  ← controlled text input, filters list
├────────────────────────┤
│ RECENT                 │  ← section label (font-mono, xs, muted)
│   📁 Greenfield Blk A  │  ← project row (see 4.1.1)
│   📁 Harbour Tower     │
│   ...                  │
├────────────────────────┤
│ + New Project          │  ← ghost button, opens modal overlay
├────────────────────────┤
│ ──────────────         │  ← separator (mt-auto pushes this down)
│ [AY] Adeyemi Ade       │  ← avatar + name, links to /profile
│ ⤴ Sign out             │  ← muted text button
└────────────────────────┘
```

**Collapsed layout:**

```
┌────┐
│ ⬡  │  ← logo, click to expand
├────┤
│ 🔍 │  ← tooltip: "Search projects"
├────┤
│ 📁 │  ← each project as icon, tooltip: project name
│ 📁 │
│ ...│
├────┤
│ +  │  ← tooltip: "New Project"
├────┤
│────│
│ AY │  ← avatar only, tooltip: "Profile"
│ ⤴  │  ← tooltip: "Sign out"
└────┘
```

**Collapse behaviour:** When the user clicks a project row, the sidebar collapses to the icon rail (48px). The canvas viewport expands to fill the freed space. This happens via a CSS `width` transition (200ms ease-out).

**Search behaviour:** Input filters the project list client-side by `name` and `reference` fields (case-insensitive substring). Matches highlight the matching portion of the name. When the search query is non-empty and the sidebar is collapsed, expanding it focuses the search input automatically.

#### 4.1.1 Project Row

```
┌──────────────────────────────────────┐
│ 📁  Greenfield Blk A          active │
│     JOB-2026-001              ·· 2h  │
└──────────────────────────────────────┘
```

- **Icon:** `Folder` (lucide), `text-muted-foreground`, switches to `text-primary` when active or hovered.
- **Name:** `text-sm font-medium`, truncated with ellipsis.
- **Reference:** `text-xs font-mono text-muted-foreground`.
- **Status pill:** right-aligned, `text-xs font-mono` — colour follows existing `statusColor()` logic. Only shown in expanded state.
- **Active state:** `bg-primary/10 text-foreground border-l-2 border-primary`.
- **Hover state:** `hover:bg-muted` (non-active rows).

#### 4.1.2 New Project Modal

Triggered by "+ New Project" in the sidebar (or the `Cmd/Ctrl + N` shortcut). Opens as a centered modal overlay over the full screen — identical in behaviour to the current dashboard modal. The sidebar stays in its current state (expanded or collapsed) behind the overlay.

```
              ╔═══════════════════════════════════════╗
              ║  New Project                      [✕] ║
              ╠═══════════════════════════════════════╣
              ║  Project name *                       ║
              ║  [Greenfield Office Block — Block A]  ║
              ║  Job reference *                      ║
              ║  [JOB-2026-001]                       ║
              ║  Client                               ║
              ║  [Acme Property Developments Ltd]     ║
              ║  Design code                          ║
              ║  [BS8110]  [EC2]                      ║
              ║  ─────────────────────────────────    ║
              ║  [Cancel]           [Create project]  ║
              ╚═══════════════════════════════════════╝
```

- **Backdrop:** `bg-black/60 backdrop-blur-sm`, same as current dashboard modal.
- **Width:** `max-w-md w-full`, centered with `fixed inset-0 flex items-center justify-center`.
- **Fields and validation:** identical to the existing dashboard modal.
- **On successful create:** closes modal, calls `setActiveProject()`, collapses sidebar to icon rail.
- **On cancel / `Escape`:** closes modal, no side effects.

---

### 4.2 Workspace Header (Replaces AppHeader)

**File:** `src/components/WorkspaceHeader.tsx` (rename/replace `AppHeader.tsx`)

Only rendered when a project is active. Height: 48px.

```
┌──────────────────────────────────────────────────────────────┐
│ [Parsing] ──●── [Verification] ──○── [Analysis] ──○── [Draft]│ ← StageTracker (centered)
│                                                              │
│                                                 [💬 toggle] │ ← chat toggle button (right)
└──────────────────────────────────────────────────────────────┘
```

- The left logo area is owned by the ProjectSidebar (always visible in its top slot), so the WorkspaceHeader no longer needs a logo or project name — the sidebar provides that context.
- **Chat toggle button:** `MessageSquare` icon (lucide), with a subtle badge (unread indicator dot) if there are new agent messages while chat is hidden.
- **No project name in header** — the sidebar's active state makes it redundant.

---

### 4.3 ChatSidebar (Modified)

**File:** `src/components/ChatSidebar.tsx` (modify existing)

Existing logic is mostly correct; the changes are:
- Remove the internal header (the green status dot + "StructAI Agent" label). This label moves to a subtle chip inside the chat message area.
- Add a **close button** (`X` icon) at the top-right that calls back to the workspace to collapse the panel.
- The panel itself is controlled by `WorkspaceHeader`'s toggle; `ChatSidebar` is always mounted but conditionally shown via `width` transition (not `display: none`, to preserve WebSocket lifecycle).

```
┌──────────────────────────┐
│ ● Connected        [✕]   │  ← slim top bar (32px) with close
├──────────────────────────┤
│ [messages area]          │
├──────────────────────────┤
│ [input + send]           │
└──────────────────────────┘
```

---

### 4.4 Empty State / Project Prompt

**File:** `src/components/ProjectPrompt.tsx` (new)

Rendered in the main content area when `activeProject === null`.

```
┌───────────────────────────────────────────────────┐
│                                                   │
│              ⬡ StructAI Copilot                   │  ← logo + name, 24px
│                                                   │
│       Start a structural engineering project.     │  ← subtitle, sm, muted
│                                                   │
│           [+ New Project]                         │  ← primary button, opens modal
│                                                   │
│  ───────  or pick a recent project  ───────       │  ← divider (only if projects exist)
│  📁 Greenfield Blk A   📁 Harbour Tower           │  ← max 3 recent projects as chips
│                                                   │
└───────────────────────────────────────────────────┘
```

**Interaction detail:** The "New Project" button opens the same modal overlay described in §4.1.2. There is no inline form on this screen — clicking the button is the single entry point, keeping the empty state visually clean.

---

### 4.5 Profile Page (New)

**Route:** `/profile`
**File:** `src/app/profile/page.tsx`

A professional-grade profile and settings page. Accessed via the avatar/name link at the bottom of the ProjectSidebar.

#### Layout

```
┌────────────────────────────────────────────────────────────────┐
│  PROJECT SIDEBAR (48px collapsed, icon rail)                  │
│             │ PROFILE CONTENT AREA                            │
│             │                                                 │
│             │  ┌─────────────────────────────────────────┐  │
│             │  │  PROFILE HEADER                         │  │
│             │  │  [AY] Adeyemi Ade        engineer        │  │
│             │  │       adejumoadeyemi32@gmail.com         │  │
│             │  │       Acme Org · Verified ✓              │  │
│             │  └─────────────────────────────────────────┘  │
│             │                                                 │
│             │  [Account]  [Security]  [Preferences]          │  ← tab strip
│             │  ──────────────────────────────────────────── │
│             │  <tab content>                                 │
│             │                                                 │
└─────────────┴─────────────────────────────────────────────────┘
```

When on `/profile`, the project sidebar collapses to icon rail automatically, giving maximum reading width to the content area.

#### 4.5.1 Profile Header

```
┌─────────────────────────────────────────┐
│  ┌────┐                                 │
│  │ AY │  Adeyemi Ade          [Edit]   │  ← avatar (40px), name, edit button
│  └────┘  engineer                       │
│           adejumoadeyemi32@gmail.com    │
│           Acme Organisation  · ✓ Verified│
└─────────────────────────────────────────┘
```

- **Avatar:** Initials derived from `full_name`. Background: `bg-primary`, text: `text-primary-foreground`. Future: support uploaded photo.
- **Role badge:** `text-xs font-mono text-muted-foreground capitalize` — shows `engineer`, `admin`, or `viewer`.
- **Verified indicator:** `CheckCircle2` icon (`text-success`) shown when `is_verified === true`.
- **Organisation:** links to org name from `organisation.name`.

#### 4.5.2 Account Tab

| Field | Source | Editable |
|---|---|---|
| Full name | `user.full_name` | Yes |
| Email | `user.email` | No (shows "contact admin to change") |
| Organisation | `user.organisation.name` | No |
| Role | `user.role` | No (admin only) |

Save via `PATCH /users/me`.

#### 4.5.3 Security Tab

- **Change password:** current password + new password + confirm (only if not OAuth-only account; otherwise shows "Using Google SSO — password login disabled").
- **Two-factor authentication:** enable/disable 2FA toggle. When enabling, show QR code + backup codes flow.
- **Active sessions:** list of recent login sessions with browser/IP, with "Revoke" button per session.

#### 4.5.4 Preferences Tab

| Setting | Options | Default |
|---|---|---|
| Default design code | BS8110 / EC2 | BS8110 |
| Sidebar default state | Expanded / Collapsed | Expanded |
| Chat auto-open | On project open / Manual | On project open |
| Units display | Metric (kN, m) only (v1) | — |

Stored in `localStorage` under `structai-preferences` for now; move to `PATCH /users/me` preferences field when backend supports it.

---

## 5. Design Tokens

The existing token system in `globals.css` is well-structured. The following additions are needed:

### 5.1 New Tokens

```css
:root {
  /* Sidebar */
  --sidebar-width-expanded: 240px;
  --sidebar-width-collapsed: 48px;
  --sidebar-transition: 200ms ease-out;

  /* Chat panel */
  --chat-width: 320px;
  --chat-transition: 200ms ease-out;

  /* Profile avatar */
  --avatar-size-sm: 28px;
  --avatar-size-md: 40px;
  --avatar-size-lg: 80px;

  /* Surface elevation layers */
  --surface-0: hsl(var(--background));     /* page background */
  --surface-1: hsl(var(--card));           /* panels, sidebars */
  --surface-2: hsl(var(--muted));          /* inputs, inset areas */
  --surface-3: hsl(var(--secondary));      /* hover states, chips */
}
```

### 5.2 Existing Tokens (unchanged)

| Token | Value | Usage |
|---|---|---|
| `--primary` | `217 91% 60%` | Interactive elements, active states |
| `--muted` | `217 33% 14%` | Input backgrounds, subtle fills |
| `--border` | `217 33% 17%` | All dividers and borders |
| `--success` | `142 71% 45%` | Connected status, verified, parsing done |
| `--destructive` | `0 72% 51%` | Errors, delete actions |
| `--accent` | `24 95% 53%` | Warning states, gate banners |
| `--canvas-bg` | `222 47% 5%` | Canvas viewport background |

---

## 6. Typography System

| Scale | Class | Size | Weight | Font | Usage |
|---|---|---|---|---|---|
| Display | `.text-xl font-semibold` | 20px | 600 | Inter | Page titles (profile name) |
| Heading | `.text-base font-semibold` | 16px | 600 | Inter | Section headings |
| Body | `.text-sm` | 14px | 400 | Inter | Body copy, chat messages |
| Label | `.text-xs font-medium` | 12px | 500 | Inter | Form labels, status |
| Mono | `.text-xs font-mono` | 12px | 400 | JetBrains Mono | References, coords, codes |
| Micro | `.text-[10px] font-mono` | 10px | 400 | JetBrains Mono | Timestamps only |

**Rules:**
- Prose text is always Inter (`font-sans`).
- Any code, reference number, coordinate, pipeline status, design code, or timestamp uses JetBrains Mono (`font-mono`).
- Never use `font-bold` (`700`) — `font-semibold` (`600`) is the heaviest weight.
- Section labels in sidebars: `text-[10px] font-mono uppercase tracking-widest text-muted-foreground`.

---

## 7. Spacing System

All spacing uses Tailwind's default 4px base scale. Standard gaps:

| Context | Value | Tailwind |
|---|---|---|
| Within a compact row | 6px | `gap-1.5` |
| Between related elements | 8px | `gap-2` |
| Between form fields | 16px | `gap-4` / `space-y-4` |
| Section padding | 16px horizontal, 12px vertical | `px-4 py-3` |
| Page content inset | 24px | `px-6` |
| Sidebar section gap | 24px | `mt-6` |

Panel border widths: always `1px` (`border`), never `2px` except the active project indicator (`border-l-2 border-primary`).

---

## 8. Component States

All interactive components must implement these states consistently:

| State | Visual Treatment |
|---|---|
| Default | As specified per component |
| Hover | `hover:bg-muted` or `hover:border-primary/40` |
| Focus-visible | `focus-visible:ring-2 focus-visible:ring-ring` |
| Active / Selected | `bg-primary/10 border-l-2 border-primary text-foreground` |
| Loading | Replace label with `Loader2` (lucide) spinning at same size |
| Disabled | `opacity-50 cursor-not-allowed pointer-events-none` |
| Destructive | `text-destructive hover:bg-destructive/10` |

---

## 9. Interaction Design

### 9.1 Sidebar Collapse

**Trigger:** clicking the `ChevronLeft`/`ChevronRight` toggle button in the sidebar header, or clicking a project row.

**Animation:**
```css
width: var(--sidebar-width-expanded); /* or --sidebar-width-collapsed */
transition: width var(--sidebar-transition);
overflow: hidden;
```

Text labels in the sidebar use `opacity` transition so they fade out slightly before the width animation completes:
```css
.sidebar-label {
  opacity: 1;
  transition: opacity 100ms ease-out;
}
.sidebar--collapsed .sidebar-label {
  opacity: 0;
}
```

**Persistence:** Sidebar state (expanded/collapsed) is stored in `localStorage` under `structai-sidebar-state` and read on hydration.

### 9.2 Chat Panel Toggle

**Trigger:** the `MessageSquare` button in `WorkspaceHeader`.

**Animation:** `width` transition on the chat panel container (same pattern as sidebar). WebSocket connection is not torn down on collapse — the component stays mounted, only `width: 0; overflow: hidden`.

**Unread dot:** A 6px circle (`bg-primary`) appears on the chat toggle button when the chat is collapsed and a new agent message arrives. Cleared on re-open.

### 9.3 Project Selection Flow

1. User clicks a project row in sidebar.
2. Sidebar collapses to icon rail (200ms).
3. `setActiveProject()` called.
4. `WorkspaceHeader` and `CanvasViewport` render into the newly freed space.
5. Chat sidebar opens automatically (based on user preference).
6. WebSocket connects for the new project.

### 9.4 Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Cmd/Ctrl + B` | Toggle project sidebar |
| `Cmd/Ctrl + \` | Toggle chat sidebar |
| `Cmd/Ctrl + K` | Focus project search input |
| `Cmd/Ctrl + N` | Open new project form |
| `Enter` | Send chat message (existing) |
| `Escape` | Close inline new project form |

Shortcuts are registered in a `useKeyboardShortcuts()` hook at the workspace level.

---

## 10. Routing Changes

### Routes to Delete
- `/dashboard` — delete `src/app/dashboard/` directory entirely.

### Routes to Add
- `/profile` — create `src/app/profile/page.tsx`.

### Modified Route Behaviour

**`/` (workspace root):**
- No longer redirects to `/dashboard` when `activeProject === null`.
- Instead: renders `ProjectSidebar` (expanded) + `ProjectPrompt` (centered empty state).
- AuthGuard still redirects unauthenticated users to `/login`.

**`/profile`:**
- Protected by `AuthGuard`.
- Renders `ProjectSidebar` (collapsed to icon rail) + profile content.
- Back navigation: clicking the logo in the icon rail goes to `/`.

---

## 11. Page-Level File Map

```
src/
├── app/
│   ├── page.tsx                    ← MODIFY: remove dashboard redirect; render empty state
│   ├── profile/
│   │   └── page.tsx                ← NEW
│   ├── dashboard/                  ← DELETE entire directory
│   └── ...auth pages unchanged...
├── components/
│   ├── ProjectSidebar.tsx          ← NEW (replaces dashboard project list)
│   ├── ProjectPrompt.tsx           ← NEW (empty state for no active project)
│   ├── WorkspaceHeader.tsx         ← NEW (replaces AppHeader.tsx)
│   ├── ChatSidebar.tsx             ← MODIFY (add close button, remove internal header)
│   ├── CanvasViewport.tsx          ← unchanged
│   ├── StageTracker.tsx            ← unchanged
│   ├── AuthGuard.tsx               ← MODIFY (remove /dashboard redirect)
│   └── AppHeader.tsx               ← DELETE (replaced by WorkspaceHeader)
├── hooks/
│   └── useKeyboardShortcuts.ts     ← NEW
└── stores/
    └── uiStore.ts                  ← NEW (sidebar expanded, chat open, unread count)
```

---

## 12. New Zustand Store: `uiStore`

**File:** `src/stores/uiStore.ts`

```typescript
interface UIState {
  sidebarExpanded: boolean;
  chatOpen: boolean;
  chatUnread: number;
  toggleSidebar: () => void;
  setSidebarExpanded: (v: boolean) => void;
  toggleChat: () => void;
  setChatOpen: (v: boolean) => void;
  incrementUnread: () => void;
  clearUnread: () => void;
}
```

Persisted to `localStorage` under `structai-ui-state` (sidebar state only; unread count is session-only, not persisted).

---

## 13. Profile Page Data Requirements

The profile page reads from `useAuthStore` for user data already in memory, then optionally re-fetches from `GET /users/me` on mount to ensure freshness.

Edit form submits to `PATCH /users/me`. The API client already has JWT injection; no new auth plumbing needed.

The Security tab's "Change password" form posts to `POST /auth/reset-password` with the current token (confirm the correct endpoint with the backend — it may need a separate `PATCH /users/me/password` endpoint).

---

## 14. Accessibility

- All icon-only buttons have `aria-label` matching their tooltip text.
- Collapsed sidebar icons are wrapped in `<Tooltip>` (already available in `components/ui/tooltip.tsx`).
- The project search input has `role="searchbox"` and `aria-label="Search projects"`.
- Project list is a `<ul>` with each project as an `<li>` containing a `<button>`.
- Profile tabs use `role="tablist"` / `role="tab"` / `role="tabpanel"`.
- Focus is moved to the project search input when the sidebar expands via keyboard shortcut.
- Color is never the sole indicator of state (status labels always accompany status colors).

---

## 15. Empty State Variants

| Condition | What to Show |
|---|---|
| Authenticated, no projects exist | `ProjectPrompt` with "Create your first project" heading, no recent projects section |
| Authenticated, projects exist, none active | `ProjectPrompt` with recent projects section |
| Authenticated, project active | Full workspace (canvas + chat) |
| Unauthenticated | `AuthGuard` redirects to `/login` |

---

## 16. Implementation Order

The changes below are sequenced to avoid breaking the running app:

1. **Create `uiStore`** — no UI impact; just state.
2. **Create `ProjectSidebar`** — new component, not yet wired to layout.
3. **Create `ProjectPrompt`** — new component, not yet wired to layout.
4. **Modify `page.tsx`** — wire in `ProjectSidebar` + `ProjectPrompt`, remove dashboard redirect. Keep `AppHeader` temporarily.
5. **Create `WorkspaceHeader`** — replace `AppHeader` once sidebar is wired and tested.
6. **Delete `AppHeader.tsx`**.
7. **Modify `ChatSidebar`** — add close button, remove internal header.
8. **Add `useKeyboardShortcuts` hook** — wire to workspace.
9. **Create `/profile` page** — independent of workspace changes.
10. **Delete `/dashboard`** — last step, once all entry points are verified gone.
11. **Update `AuthGuard`** — remove `/dashboard` redirect references.

---

## 17. What Not to Build (Scope Boundaries)

- No light mode toggle. The dark engineering palette is intentional and production-defining.
- No mobile responsive layout. This is a desktop engineering tool. Minimum viewport: 1280px.
- No drag-and-drop project reordering in the sidebar.
- No project archiving UI (v1). The sidebar shows all projects.
- No in-sidebar project rename. Edit happens on the profile/settings page or a dedicated project settings route (future).
- No notification center beyond the chat unread dot.
- No organisation management UI (admin-only, future).
