# React Motion Rules

Animation patterns for React / Next.js using `motion/react` (formerly Framer Motion).

## Foundations

- Use motion tokens for all durations and easing — never hardcode values
- Use spring presets (`gentle`, `snappy`, `smooth`) over cubic-bezier for interactive animations
- Always check `useReducedMotion()` and disable or minimize motion when `true`
- Animations must be SSR-safe — avoid `window`/`document` in initial render

```ts
// Always check reduced motion
const prefersReduced = useReducedMotion();
const transition = prefersReduced ? { duration: 0 } : springs.gentle;
```

## Standard Transitions

- **Fade**: `initial={{ opacity: 0 }} animate={{ opacity: 1 }}`
- **Slide up**: `initial={{ y: 16, opacity: 0 }} animate={{ y: 0, opacity: 1 }}`
- **Scale in**: `initial={{ scale: 0.95, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}`

Use `AnimatePresence` for exit animations — wrap the conditional tree, use `mode="wait"` for sequential transitions.

## Common Patterns

### Stagger lists
Use `staggerChildren` in the parent `variants` to fan items out. Keep delay under 50ms per item for lists > 5 items.

### Modal / overlay
`AnimatePresence` + `motion.div` with scale + opacity. Use `layoutId` for shared-element transitions between list and detail views.

### Page transitions
Wrap `{children}` in `<AnimatePresence mode="wait">` at the layout level. Keep transitions under 300ms to avoid feeling sluggish.

## Performance

- Animate `transform` and `opacity` only — never animate `width`, `height`, or `top/left`
- Use `layout` prop for layout animations instead of animating position manually
- `will-change: transform` is applied automatically by motion — avoid adding it manually
- Disable animations during automated tests (`NEXT_PUBLIC_DISABLE_ANIMATIONS=true` pattern)

## Gestures

- Add `whileTap={{ scale: 0.97 }}` to interactive elements for tactile feedback
- Use `useMotionValue` + `useTransform` for scroll-linked animations
- `drag` with `dragConstraints` for bounded drag — always provide boundaries
- `useAnimate` for imperative sequences (multi-step timelines)

## Accessibility

- All animated elements must still be keyboard navigable
- Respect `prefers-reduced-motion` — `motion/react` does NOT do this automatically
- Provide static fallback for content inside `AnimatePresence` (content exists in DOM during exit)

## Anti-Patterns

- Do not animate on every re-render — use `key` or `layoutId` for controlled transitions
- Do not use `motion.div` where `<div>` suffices — only wrap elements that actually animate
- Do not chain `useEffect` → setState to trigger animations — use `variants` state machines instead
