# UI Design Skill

## When to Activate
Activate when the request involves HTML, CSS, front-end layouts, templates, responsiveness, accessibility, colours, typography, forms, or browser-rendered interfaces.

**Trigger keywords:** css, html, frontend, ui, ux, template, layout, style, design, responsive, form, button, navbar, flex, grid, colour, font, modal, sidebar

---

## Best Practices

- Mobile-first: style the smallest viewport first, then override for larger screens.
- Use CSS custom properties (`--color-primary`) for a consistent design system.
- Prefer Flexbox for one-dimensional layouts; CSS Grid for two-dimensional layouts.
- Preserve Flask/Django/Jinja template syntax (`{{ }}`, `{% %}`) when editing templates.
- Never hard-code pixel widths on containers — use `%`, `rem`, `em`, or `fr`.
- Use semantic HTML: `<nav>`, `<main>`, `<section>`, `<article>`, `<header>`, `<footer>`.
- Add `alt` attributes to all `<img>` tags.
- Ensure form inputs have associated `<label>` elements.
- Use `rem` for font sizes (scales with user preferences).
- Test high-contrast and keyboard-navigability.

---

## Common Mistakes

- Breaking server-side template tags when editing HTML.
- Forgetting `<meta name="viewport">` for responsive layouts.
- Using inline styles (`style="..."`) instead of CSS classes.
- Hard-coding colours instead of using CSS variables.
- Missing `for`/`id` pairing on labels and inputs (breaks accessibility).
- Nesting block elements inside inline elements (`<span><div>...</div></span>`).
- Using `px` font sizes that don't respect user zoom.

---

## Checklist

- [ ] All template syntax (`{{ }}`, `{% %}`) preserved
- [ ] `<meta name="viewport">` present
- [ ] Semantic HTML tags used (`<nav>`, `<main>`, etc.)
- [ ] All images have `alt` attributes
- [ ] All form inputs have matching `<label>` elements
- [ ] No hard-coded pixel widths on containers
- [ ] Colours defined as CSS custom properties
- [ ] Responsive at mobile (320px), tablet (768px), desktop (1200px)

---

## Few-Shot Examples

### Example 1: Responsive nav with Flexbox
```html
<nav class="navbar">
  <a href="/" class="navbar__logo">App</a>
  <ul class="navbar__links">
    <li><a href="/about">About</a></li>
  </ul>
</nav>
```
```css
.navbar { display: flex; justify-content: space-between; align-items: center; padding: 0 1.5rem; }
.navbar__links { display: flex; gap: 1rem; list-style: none; }
@media (max-width: 600px) { .navbar__links { display: none; } }
```

### Example 2: CSS custom properties
```css
:root {
  --color-primary: #4f46e5;
  --color-text: #1f2937;
  --radius: 0.5rem;
}

.button {
  background: var(--color-primary);
  border-radius: var(--radius);
  color: #fff;
  padding: 0.5rem 1.25rem;
}
```

### Example 3: Accessible form field
```html
<div class="form-group">
  <label for="email">Email address</label>
  <input type="email" id="email" name="email" required
         placeholder="you@example.com" class="form-control">
</div>
```
