# ⚠️ READ FIRST — this file describes an app that is NOT in this repo

**There is no `frontend/` directory here.** Everything below this banner is the
design system for a PLANNED marketing site that was never built in this
repository (verified 2026-08-09: repo contains `agency-dashboard/`, `agents/`,
`api/`, `customer-app/`, `database/`, `supabase/` — see RISK-2 in
PLATFORM_STATUS.md). Building it is new scope needing Gowtham's requirements
(BLK-9); do not create it speculatively, and do not go looking for these
components — they do not exist.

**The real applications, and where their conventions live:**

| App | Directory | Conventions |
|---|---|---|
| Agency dashboard | `agency-dashboard/` | `.claude/skills/gogaga-frontend/` |
| Klara customer app | `customer-app/` | `.claude/skills/gogaga-frontend/` |
| FastAPI backend | `api/` | `.claude/skills/gogaga-backend/` |
| Migrations | `supabase/migrations/` | `.claude/skills/gogaga-migrations/` |

The design tokens below (blue #3D75F3, salmon #F5A086, Inter, `.wrap`, …) apply
to the FUTURE marketing site only. The real apps use their own token files
(`customer-app/src/styles/tokens.ts`, `agency-dashboard/src` CSS variables) —
do not import these values into them.

**Scoreboard rule:** `GOGAGA_ANALYSIS_REPORT.md` at the repo root is the
combined completeness scoreboard for both apps. Any change that moves an
area's completeness — up or down — must update `GOGAGA_ANALYSIS_REPORT.md`
in the same commit.

---

# TechScape AI — Design System Rules (Figma ↔ Code)

## 1. Project Structure

```
techscapeai/
├── frontend/                  # React SPA
│   ├── src/
│   │   ├── components/        # All UI components (one file per section)
│   │   ├── pages/             # Route-level pages (HomePage, ContactPage, LoginPage, NotFoundPage)
│   │   ├── layouts/           # MainLayout wraps pages (Navbar + Footer)
│   │   ├── hooks/             # useScrollAnimation (IntersectionObserver)
│   │   ├── services/          # api.js (native fetch to FastAPI backend)
│   │   ├── assets/            # Static images (hero.png)
│   │   ├── index.css          # All design tokens + global utilities (Tailwind v4)
│   │   └── App.jsx            # BrowserRouter + Routes
│   ├── public/                # favicon.svg, icons.svg
│   ├── vite.config.js         # Vite + @vitejs/plugin-react + @tailwindcss/vite
│   └── package.json
├── backend/                   # FastAPI (Python)
└── database/                  # schema.sql (Supabase)
```

## 2. Frameworks & Libraries

| Concern        | Tool                        | Version  |
|----------------|-----------------------------|----------|
| UI Framework   | React                       | 19       |
| Language       | JavaScript (JSX)            | ES2022   |
| Styling        | Tailwind CSS v4             | 4.2.x    |
| Bundler        | Vite                        | 8.x      |
| Routing        | react-router-dom            | 7.x      |
| Icons          | Inline SVGs only            | —        |
| HTTP           | Native fetch                | —        |

## 3. Design Tokens (defined in `frontend/src/index.css`)

All tokens are Tailwind v4 `@layer utilities` custom classes — **not** CSS variables or a token JSON file.

### Brand Colors
```
Blue   → #3D75F3   (primary accent)
Salmon → #F5A086   (secondary accent)
Black  → #000000   (page background)
Dark   → #0D0D0D   (card background)
Border → #1C1C1C   (card border)
Grays  → #1a1a1a, #2a2a2a, #333, #444 (subtle UI elements)
```

### Gradients
```css
.grad        /* blue→salmon bg: linear-gradient(97.97deg, #3D75F3 0%, #F5A086 100%) */
.grad-text   /* same gradient as text fill (background-clip: text) */
.blue-text   /* blue-only gradient text: #3D75F3 → #60A5FA */
.gradient-text /* alias for .grad-text */
.gradient-bg   /* alias for .grad */
```

### Typography Scale (Figma → Tailwind)
| Role            | Size (px)  | Class / Style                                              |
|-----------------|------------|------------------------------------------------------------|
| Hero H1         | 36–52      | `text-[36px] sm:text-[46px] lg:text-[52px] font-extrabold` |
| Section H2      | 32–50      | `text-[32px] sm:text-[42px] lg:text-[50px] font-extrabold` |
| Card H3         | 18–20      | `text-[18px] font-bold`                                    |
| Body            | 14–15      | `text-[14px] lg:text-[15px] text-white/50`                 |
| Small / Tag     | 11–13      | `text-[11px]–text-[13px]`                                  |
| Label / Eyebrow | 13         | `.label` (salmon, uppercase, tracking-wide)                |

### Font
```css
font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
```

### Spacing
- Section vertical padding: `py-20 lg:py-28`
- Container: `.wrap` → `max-width: 1440px`, `padding: 7.9%` desktop / `5%` mobile

## 4. Component Architecture

- **One component = one file**, located in `frontend/src/components/`
- Components are **function components** with no prop drilling (data defined inline as constants)
- Scroll animations via `useScrollAnimation` hook — add `ref` to wrapper, apply `transition-all duration-700` + `opacity/translate-y` classes based on `isVisible`

### Component List
| File             | Section ID       | Notes                                                      |
|------------------|------------------|------------------------------------------------------------|
| TopBanner.jsx    | —                | Dismissible gradient banner                                |
| Navbar.jsx       | —                | Sticky 48px, blur-on-scroll, logo mark, hamburger lg:hidden |
| Hero.jsx         | —                | 474px grid, SVG sphere, floating tags, stats row           |
| About.jsx        | #about           | Fan card layout (3 rotated cards)                          |
| Services.jsx     | #services        | 3-card showcase (422×477, ±55px bleed) + 4th strip         |
| Problem.jsx      | —                | Problem statement section                                  |
| AIAgents.jsx     | #ai-agents       | 2×2 grid                                                  |
| HowItWorks.jsx   | #how-it-works    | 3-col with connector line                                  |
| Team.jsx         | #team            | 3-col: text / SVG char / accordion                        |
| Partners.jsx     | #partners        | 5-logo marquee ticker (28s loop, hover pause)              |
| CTA.jsx          | #get-started     | Two-panel: left gradient 592px + right dark checklist      |
| Footer.jsx       | —                | 6-col grid + ghost wordmark, min-h-610px, bg #020101      |

### Pages
| File             | Route      | Layout      | Notes                                     |
|------------------|------------|-------------|--------------------------------------------|
| HomePage.jsx     | `/`        | MainLayout  | Composes all section components            |
| ContactPage.jsx  | `/contact` | MainLayout  | Contact form                               |
| LoginPage.jsx    | `/login`   | Standalone  | Split layout: dark left + white right 720px |
| NotFoundPage.jsx | `*`        | MainLayout  | 404 page                                  |

## 5. Styling Approach

- **Tailwind v4** utility classes inline on JSX elements
- **No CSS Modules, no Styled Components, no tailwind.config.js** (v4 doesn't require it)
- Custom reusable classes defined in `@layer utilities` in `index.css`:

| Class           | Purpose                                        |
|-----------------|-------------------------------------------------|
| `.btn`          | Gradient pill button (999px radius, hover lift) |
| `.btn-nav`      | Navbar gradient button (6px radius)             |
| `.card`         | Dark card (#0D0D0D bg, #1C1C1C border, hover lift) |
| `.card-hover`   | Alias for `.card`                               |
| `.tag`          | Salmon pill badge (12% alpha bg, 999px radius)  |
| `.input-line`   | Underline form input (focus: blue border)       |
| `.select-line`  | Underline select input                          |
| `.label`        | Salmon eyebrow text (13px, uppercase, 0.1em)    |
| `.section-label`| Alias for `.label`                              |
| `.wrap`         | Section container (max-w 1440px, responsive pad)|
| `.float`        | CSS float animation (5s ease-in-out)            |
| `.nav-blur`     | Backdrop-filter blur(20px) for navbar           |
| `.grid-bg`      | Subtle grid pattern (60px, blue 4% opacity)     |
| `.grad-border`  | Gradient border via ::before pseudo-element     |
| `.shimmer`      | Shimmer animation (3s linear)                   |
| `.marquee-track`| Marquee scroll animation (28s, pause on hover)  |

## 6. Icon System

- **No external icon library** — all icons are inline SVG in JSX
- Service icons: 32×32 viewBox, stroked paths, accent colors
- Social icons: 15×15, filled paths
- Action icons: 14×14, stroked arrows/checks
- Icon colors match component accent (`#3D75F3` or `#F5A086`)
- Icons live in the component that uses them

## 7. Asset Management

- Images in `frontend/src/assets/` — imported directly in JSX
- SVG illustrations inline in JSX (Sphere in Hero, social icons in Login/Footer)
- `public/favicon.svg` and `public/icons.svg` referenced via root path
- No CDN, no external image URLs in production

## 8. Responsive Design

Breakpoints (Tailwind defaults):
| Name | Width  | Usage                              |
|------|--------|------------------------------------|
| sm   | 640px  | Show floating tags, 2-col grids    |
| md   | 768px  | Login split layout                 |
| lg   | 1024px | Desktop nav, larger text, 3-col    |

Mobile-first approach: hamburger visible below `lg`, desktop nav at `lg:flex`.

## 9. Scroll Animation Pattern

```jsx
import { useScrollAnimation } from '../hooks/useScrollAnimation'

const { ref, isVisible } = useScrollAnimation({ threshold: 0.15 })

<section ref={ref} className={`transition-all duration-700 ${
  isVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-10'
}`}>
```

Stagger cards with `style={{ transitionDelay: '${i * 90}ms' }}`.

## 10. Figma → Code Mapping Rules

When implementing a Figma design into this codebase:

1. **Colors** → map to `#3D75F3` (blue), `#F5A086` (salmon), or white/opacity variants. Do not introduce new hex values.
2. **Gradients** → use `.grad`, `.grad-text`, `.blue-text` classes.
3. **Buttons** → use `.btn` (pill) or `.btn-nav` (navbar). Do not create new button styles.
4. **Cards** → use `.card` or `.card-hover` base, add inline `background` and `border` style overrides for accent variants.
5. **Typography** → match sizes using `text-[Npx]` with responsive variants; use `font-extrabold` for headings, `font-semibold` for subheadings, `text-white/50` for body.
6. **Sections** → each Figma frame = one component file in `components/`. Always include `id=""` for anchor navigation.
7. **Animations** → use `useScrollAnimation` hook + Tailwind `transition-all duration-700` + `opacity/translate-y`. Stagger cards with `transitionDelay`.
8. **Spacing** → use `.wrap` for the container. Section padding is always `py-20 lg:py-28`.
9. **SVG illustrations** → inline in JSX with `defs` for gradients. Max width via Tailwind (`max-w-[480px]`).
10. **Mobile-first** — build for xs, enhance at sm/lg. Hide decorative elements on xs with `hidden sm:block`.
11. **Figma frame dimensions** → map directly to CSS: `width` → `w-[Npx]`, `height` → `h-[Npx]`, `leading` → `pl-[N]` or `.wrap` padding.
12. **Light-theme panels** (like Login right) → use inline `style={{ background: '#FFFFFF', color: '#1A1A1A' }}`, input bg `#F2F2F2`, border `#E5E5E5`.
