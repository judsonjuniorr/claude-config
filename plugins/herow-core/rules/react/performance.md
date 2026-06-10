# React Performance Rules

Performance optimization patterns for React 18/19 and Next.js.

## Priority Order

1. CRITICAL — Waterfalls (sequential awaits)
2. CRITICAL — Bundle size
3. HIGH — Server-side performance
4. MEDIUM — Re-render optimization
5. MEDIUM — Rendering (long lists, hydration)

## Eliminating Waterfalls

- Check sync conditions before `await` — fail fast on cheap guards
- Use `Promise.all` for independent data fetches (never sequential `await` for parallel work)
- In Server Components, split siblings into separate async child components so React runs them in parallel
- Push `<Suspense>` close to data so the page streams progressively

```ts
// Wrong — sequential
const user = await getUser(id);
const posts = await getPosts(id);

// Correct — parallel
const [user, posts] = await Promise.all([getUser(id), getPosts(id)]);
```

## Bundle Size

- Direct imports over barrel `index.ts` (direct saves 200–800ms first-load JS)
- `next/dynamic` with `loading` skeleton for heavy components
- Defer third-party scripts with `next/script` `strategy="afterInteractive"`
- Conditional `import()` inside the branch that actually needs the module
- Use `optimizePackageImports` in `next.config` for large component libraries

## Server-Side Performance

- Authenticate Server Actions like public API routes — never trust the calling component
- `React.cache()` to deduplicate per-request data fetches across components
- Validate and coerce `process.env` at startup (never per-request)
- Keep `cookies()`, `headers()`, `searchParams` reads co-located with the component that needs them

## Re-render Optimization

- Move frequently-changing state down the tree — fewer children re-render
- Wrap stable props in `useCallback`/`useMemo` only when passed to `React.memo` children
- Avoid creating new objects/functions inline as props to memoized children
- Prefer `useReducer` over multiple `useState` when state transitions are coupled
- Split context: separate high-frequency value context from low-frequency config context

## Rendering Performance

- Virtualize lists of 50+ visible items (TanStack Virtual, react-window)
- Use `React.memo` only with profiling evidence — premature memo adds overhead
- Prefer CSS transitions/animations over JS-driven for anything non-interactive
- Prefer `useDeferredValue` over `debounce` for input filtering (respects React scheduler)

## Diagnostics

- Profile with React DevTools "Profiler" before optimizing
- Check Lighthouse Core Web Vitals (LCP, CLS, INP) for production regressions
- Analyze bundle with `@next/bundle-analyzer`
