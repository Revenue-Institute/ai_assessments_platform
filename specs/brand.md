Overview
This document outlines the core brand identity, typography, color palette, and UI components used in the Revenue Institute application.
Typography
The brand utilizes a modern, clean typography stack:
Headings
Font Family: Plus Jakarta Sans, sans-serif
Styling: Tightly tracked (letter-spacing: -0.02em) for a professional, consolidated look.
Usage: Used for all main page headings (h1-h6).
Body Text
Font Family: Satoshi, sans-serif
Usage: Used for all paragraph text, standard UI elements, buttons, and general content.
Monospace
Font Family: Menlo, monospace
Usage: Used for code snippets or technical specifications.
Specialty: Section/Eyebrow Labels
Font: Satoshi, sans-serif
Size: 13px
Weight: 500 (Medium)
Transform: UPPERCASE
Tracking: Widely spaced (letter-spacing: 0.1em to 0.12em)
Color: #64748B (Slate)

Color Palette
Core Brand Colors
Forest Green (Primary Base): #0A8F5D - Used for primary buttons and solid brand backgrounds.
Neon Green (Primary Accent): #12d68e - Used for hover states, accents, and high-visibility borders.
Neutral & Dark Tones
Deep Navy (Backgrounds): #020617 - Used for dark section backgrounds.
Slate Navy (Text/Accents): #0F172A - Used for primary dark text and outlines.
Light Section Base: #F8FAFC - Used for soft background sections in light mode.
System Variables (Tailwind)
The system uses HSL variables for dynamic theming:
Primary: hsl(158, 83%, 46%)
Secondary / Muted / Accent: Slate-based neutral tones (hsl(210, 17%, 96%) etc.)
Destructive: hsl(0, 72%, 51%)
UI Components
Buttons
Primary Button (.btn-primary)
Background: Forest Green (#0A8F5D)
Text: White, bold (700), 16px Satoshi
Padding: 14px 28px, 4px border radius
Hover State: Neon Green (#12d68e), dark text (#020617), soft green shadow.
Outline Button (.btn-outline)
Border: #CBD5E1 (1px solid)
Text: Slate Navy (#0F172A)
Background: Transparent
Hover State: Grey border (#94A3B8), Light Section Base background (#F8FAFC).
White Outline Button (.btn-outline-white)
For use on dark backgrounds (like Deep Navy).
Border: 2px solid White
Hover State: 10% white opacity fill.
Cards (.card-base)
Background: White
Border: Light Gray (#E2E8F0), 4px radius
Padding: 24px
Hover State: Darker border (#CBD5E1) with subtle shadow (0 4px 12px rgba(15,31,46,0.05)).
Assets & Logos
Logo Dark Mode: logo-dark.png (Used for light backgrounds)
Logo Light Mode: logo-white.png (Used for dark backgrounds like Navy sections)
Animation & Motion
Reveal: Elements fade in and slide up 16px (transform: translateY(16px)) over 0.6s.
Slide In: Quick right-to-left entry (0.25s ease-out).
Marquee: Infinite linear translations (80-85s) for horizontal scrolling elements.
