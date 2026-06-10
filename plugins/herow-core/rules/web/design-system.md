# Design System Rules

Patterns for generating and auditing design systems.

## Design Token Hierarchy

- **Primitives**: raw values (color hex, px, ms) — never reference these directly in components
- **Semantic tokens**: purpose-named (`color.action`, `space.component-gap`) — use these in components
- **Component tokens**: component-scoped (`button.padding`, `card.border-radius`)

Prefer semantic tokens over primitives. A component that references a primitive is a smell.

## Audit Checklist

When reviewing code for visual consistency:

1. Are spacing values from the token scale (4px grid) or magic numbers?
2. Are colors from the palette or hardcoded hex?
3. Are font sizes from the type scale?
4. Are border radii consistent with the component library?
5. Are shadows using the defined elevation scale?

## Component Patterns

- Single source of truth for each component variant — no copy-pasted style blocks
- Document component API with JSDoc (props, variants, sizes, states)
- Variants should be a closed union type, not `string`
- Always include a `data-testid` or accessible role — never rely on class names in tests

## Visual Consistency Reviews

Flag when reviewing PRs that touch styling:

- New color not in the palette
- Spacing value not on the 4/8/16/24/32/48 scale
- Font size outside the type scale
- Component recreated inline instead of using the shared one
- Z-index magic numbers (use the z-index scale: 10/20/30/50/100)

## Theming

- CSS custom properties for tokens — enables dark mode without JS
- Avoid Tailwind `arbitrary values` (`[23px]`) in component code — define a token instead
- Light/dark toggle via `data-theme` attribute on `<html>`, not class toggling
