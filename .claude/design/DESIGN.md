# DESIGN.md — Nock Technologies (Dev Tools)

## Theme: Dark
## Neighborhood: Developer Tools

### Colors
- Background: #0A0A0F (pitch black)
- Surface: #0F1117
- Surface hover: #161B22
- Border: #1B1F27
- Primary accent: #10B981 (emerald)
- Primary dark: #059669
- Primary light: #34D399
- Success: #34D399
- Warning: #FBBF24
- Danger: #F87171
- Text primary: #E2E8F0
- Text secondary: #94A3B8
- Text muted: #64748B

### Typography
- Body: Geist, system-ui, sans-serif
- Code: JetBrains Mono, monospace
- Base size: 14px

### CSS Variables (from nockcc.css)

```css
:root {
    --bg-primary: #0A0A0F;
    --bg-surface: #0F1117;
    --bg-surface-hover: #161B22;
    --border-primary: #1B1F27;
    --accent-emerald: #10B981;
    --accent-emerald-dark: #059669;
    --accent-emerald-light: #34D399;
    --color-success: #34D399;
    --color-warning: #FBBF24;
    --color-danger: #F87171;
    --text-primary: #E2E8F0;
    --text-secondary: #94A3B8;
    --text-muted: #64748B;
}
```

### Component Conventions
- All custom classes use `ncc-` prefix (e.g., `ncc-card`, `ncc-badge`, `ncc-btn`)
- Cards: `ncc-card` with `--bg-surface` background, `--border-primary` border
- Badges: `ncc-badge-success`, `ncc-badge-warning`, `ncc-badge-danger`
- Buttons: `ncc-btn-primary` (emerald), `ncc-btn-danger`, `ncc-btn-outline`
- KPI row: `ncc-kpi-row` with `ncc-kpi-card` children
- Tabs: `ncc-tab` with `ncc-tab-active` state
- Modals: `ncc-modal` with backdrop blur

### Layout
- Sidebar navigation (collapsible)
- Content area with max-width container
- Mobile: bottom nav replaces sidebar
- All pages follow KPI → content → action pattern

### Charts (Chart.js)
- Grid color: rgba(255, 255, 255, 0.06)
- Tick color: #64748B
- Font: Geist
- Primary dataset: #10B981
- Secondary dataset: #3B82F6
- Tertiary dataset: #8B5CF6
- Fill: 10% opacity of line color

### Anti-Patterns (DO NOT)
- No blue-purple gradients
- No Inter or Arial fonts
- No cards nested inside cards
- No gray text on colored backgrounds
- No bounce easing on animations
- No generic AI-generated aesthetics
- No light mode (this is a command center)
- No rounded-full on content cards (reserved for avatars/badges)
- No opacity hover states below 0.6
