# Tailwind CSS Utilities Reference

## Layout

### Display
| Class | CSS |
|-------|-----|
| `block` | `display: block` |
| `inline-block` | `display: inline-block` |
| `inline` | `display: inline` |
| `flex` | `display: flex` |
| `inline-flex` | `display: inline-flex` |
| `grid` | `display: grid` |
| `inline-grid` | `display: inline-grid` |
| `hidden` | `display: none` |

### Flexbox

**Direction:**
- `flex-row` - Left to right (default)
- `flex-row-reverse` - Right to left
- `flex-col` - Top to bottom
- `flex-col-reverse` - Bottom to top

**Wrap:**
- `flex-wrap` - Allow wrapping
- `flex-nowrap` - No wrapping (default)
- `flex-wrap-reverse` - Wrap in reverse

**Justify Content (Main Axis):**
- `justify-start` - Pack at start
- `justify-center` - Pack at center
- `justify-end` - Pack at end
- `justify-between` - Space between items
- `justify-around` - Space around items
- `justify-evenly` - Even spacing

**Align Items (Cross Axis):**
- `items-start` - Align at start
- `items-center` - Align at center
- `items-end` - Align at end
- `items-baseline` - Align baselines
- `items-stretch` - Stretch to fill (default)

**Gap:**
- `gap-0` through `gap-12` (0-48px)
- `gap-x-*` - Horizontal gap only
- `gap-y-*` - Vertical gap only

**Flex Item:**
- `flex-1` - Grow and shrink, ignore initial size
- `flex-auto` - Grow and shrink, respect initial size
- `flex-initial` - Shrink but don't grow
- `flex-none` - Don't grow or shrink

### Grid

**Columns:**
- `grid-cols-1` through `grid-cols-12`
- `grid-cols-none` - No columns

**Rows:**
- `grid-rows-1` through `grid-rows-6`
- `grid-rows-none` - No rows

**Span:**
- `col-span-1` through `col-span-12`
- `col-span-full` - Span all columns
- `row-span-1` through `row-span-6`
- `row-span-full` - Span all rows

### Position
| Class | CSS |
|-------|-----|
| `static` | `position: static` |
| `fixed` | `position: fixed` |
| `absolute` | `position: absolute` |
| `relative` | `position: relative` |
| `sticky` | `position: sticky` |

**Inset (top/right/bottom/left):**
- `inset-0` - All sides 0
- `top-0`, `right-0`, `bottom-0`, `left-0` - Individual sides
- `inset-x-0` - Left and right 0
- `inset-y-0` - Top and bottom 0

## Sizing

### Width
| Class | Value |
|-------|-------|
| `w-0` | 0px |
| `w-px` | 1px |
| `w-1` | 4px |
| `w-4` | 16px |
| `w-8` | 32px |
| `w-16` | 64px |
| `w-32` | 128px |
| `w-64` | 256px |
| `w-full` | 100% |
| `w-screen` | 100vw |
| `w-1/2` | 50% |
| `w-1/3` | 33.333% |
| `w-2/3` | 66.667% |
| `w-1/4` | 25% |
| `w-3/4` | 75% |

**Max Width:**
- `max-w-xs` - 320px
- `max-w-sm` - 384px
- `max-w-md` - 448px
- `max-w-lg` - 512px
- `max-w-xl` - 576px
- `max-w-2xl` - 672px
- `max-w-4xl` - 896px
- `max-w-6xl` - 1152px
- `max-w-7xl` - 1280px
- `max-w-full` - 100%
- `max-w-prose` - 65ch (readable line length)

### Height
- Same scale as width: `h-0`, `h-4`, `h-8`, `h-16`, etc.
- `h-full` - 100%
- `h-screen` - 100vh
- `min-h-screen` - min-height: 100vh
- `min-h-full` - min-height: 100%

## Spacing

### Padding
| Pattern | Example | Meaning |
|---------|---------|---------|
| `p-*` | `p-4` | All sides |
| `px-*` | `px-4` | Left and right |
| `py-*` | `py-4` | Top and bottom |
| `pt-*` | `pt-4` | Top only |
| `pr-*` | `pr-4` | Right only |
| `pb-*` | `pb-4` | Bottom only |
| `pl-*` | `pl-4` | Left only |

### Margin
Same pattern as padding: `m-*`, `mx-*`, `my-*`, `mt-*`, etc.

Special values:
- `mx-auto` - Auto horizontal margins (centers block elements)
- Negative margins: `-m-4`, `-mt-2`, etc.

### Spacing Scale
| Value | Pixels | Rem |
|-------|--------|-----|
| 0 | 0px | 0 |
| 0.5 | 2px | 0.125rem |
| 1 | 4px | 0.25rem |
| 2 | 8px | 0.5rem |
| 3 | 12px | 0.75rem |
| 4 | 16px | 1rem |
| 5 | 20px | 1.25rem |
| 6 | 24px | 1.5rem |
| 8 | 32px | 2rem |
| 10 | 40px | 2.5rem |
| 12 | 48px | 3rem |
| 16 | 64px | 4rem |
| 20 | 80px | 5rem |
| 24 | 96px | 6rem |

## Typography

### Font Size
| Class | Size | Line Height |
|-------|------|-------------|
| `text-xs` | 12px | 16px |
| `text-sm` | 14px | 20px |
| `text-base` | 16px | 24px |
| `text-lg` | 18px | 28px |
| `text-xl` | 20px | 28px |
| `text-2xl` | 24px | 32px |
| `text-3xl` | 30px | 36px |
| `text-4xl` | 36px | 40px |
| `text-5xl` | 48px | 1 |
| `text-6xl` | 60px | 1 |

### Font Weight
| Class | Weight |
|-------|--------|
| `font-thin` | 100 |
| `font-extralight` | 200 |
| `font-light` | 300 |
| `font-normal` | 400 |
| `font-medium` | 500 |
| `font-semibold` | 600 |
| `font-bold` | 700 |
| `font-extrabold` | 800 |
| `font-black` | 900 |

### Text Alignment
- `text-left`, `text-center`, `text-right`, `text-justify`

### Line Height
- `leading-none` - 1
- `leading-tight` - 1.25
- `leading-snug` - 1.375
- `leading-normal` - 1.5
- `leading-relaxed` - 1.625
- `leading-loose` - 2

### Letter Spacing
- `tracking-tighter` - -0.05em
- `tracking-tight` - -0.025em
- `tracking-normal` - 0
- `tracking-wide` - 0.025em
- `tracking-wider` - 0.05em
- `tracking-widest` - 0.1em

## Colors

### Text Colors
`text-{color}-{shade}`

Examples:
- `text-black`, `text-white`
- `text-gray-50` through `text-gray-900`
- `text-blue-500`, `text-red-600`, `text-green-400`

### Background Colors
`bg-{color}-{shade}`

Examples:
- `bg-white`, `bg-black`, `bg-transparent`
- `bg-gray-100`, `bg-blue-600`

### Border Colors
`border-{color}-{shade}`

### Color Palette (50-900 shades)
- `slate` - Blue-gray
- `gray` - Pure gray
- `zinc` - Warm gray
- `neutral` - True neutral
- `stone` - Warm neutral
- `red`, `orange`, `amber`, `yellow`, `lime`, `green`, `emerald`, `teal`, `cyan`, `sky`, `blue`, `indigo`, `violet`, `purple`, `fuchsia`, `pink`, `rose`

## Borders

### Border Width
- `border` - 1px all sides
- `border-0` - No border
- `border-2` - 2px
- `border-4` - 4px
- `border-t`, `border-r`, `border-b`, `border-l` - Single side

### Border Radius
| Class | Radius |
|-------|--------|
| `rounded-none` | 0 |
| `rounded-sm` | 2px |
| `rounded` | 4px |
| `rounded-md` | 6px |
| `rounded-lg` | 8px |
| `rounded-xl` | 12px |
| `rounded-2xl` | 16px |
| `rounded-3xl` | 24px |
| `rounded-full` | 9999px (pill) |

### Border Style
- `border-solid`, `border-dashed`, `border-dotted`, `border-double`, `border-none`

## Effects

### Box Shadow
| Class | Description |
|-------|-------------|
| `shadow-sm` | Small shadow |
| `shadow` | Default shadow |
| `shadow-md` | Medium shadow |
| `shadow-lg` | Large shadow |
| `shadow-xl` | Extra large |
| `shadow-2xl` | 2x extra large |
| `shadow-inner` | Inner shadow |
| `shadow-none` | No shadow |

### Opacity
- `opacity-0` through `opacity-100` (0%, 25%, 50%, 75%, 100%)

## Transitions & Animations

### Transition Property
- `transition-none` - No transition
- `transition-all` - All properties
- `transition` - Common properties (color, bg, border, shadow, transform)
- `transition-colors` - Colors only
- `transition-opacity` - Opacity only
- `transition-shadow` - Shadow only
- `transition-transform` - Transform only

### Duration
- `duration-75` through `duration-1000` (75ms, 100ms, 150ms, 200ms, 300ms, 500ms, 700ms, 1000ms)

### Timing Function
- `ease-linear`, `ease-in`, `ease-out`, `ease-in-out`

### Animations
- `animate-none` - No animation
- `animate-spin` - Continuous rotation
- `animate-ping` - Ping/pulse outward
- `animate-pulse` - Fade in/out
- `animate-bounce` - Bounce up/down

## Transforms

### Scale
- `scale-0` through `scale-150` (0, 50, 75, 90, 95, 100, 105, 110, 125, 150)
- `scale-x-*`, `scale-y-*` - Individual axes

### Rotate
- `rotate-0`, `rotate-1`, `rotate-2`, `rotate-3`, `rotate-6`, `rotate-12`, `rotate-45`, `rotate-90`, `rotate-180`
- Negative: `-rotate-45`, etc.

### Translate
- `translate-x-*`, `translate-y-*`
- Uses spacing scale

## Interactivity

### Cursor
- `cursor-auto`, `cursor-default`, `cursor-pointer`, `cursor-wait`, `cursor-text`, `cursor-move`, `cursor-not-allowed`

### User Select
- `select-none`, `select-text`, `select-all`, `select-auto`

### Pointer Events
- `pointer-events-none`, `pointer-events-auto`

## Responsive Prefixes

Apply any utility at specific breakpoints:

| Prefix | Min Width |
|--------|-----------|
| (none) | 0px (mobile first) |
| `sm:` | 640px |
| `md:` | 768px |
| `lg:` | 1024px |
| `xl:` | 1280px |
| `2xl:` | 1536px |

Example: `md:flex lg:grid xl:grid-cols-4`

## State Modifiers

Apply styles on specific states:

- `hover:` - On mouse hover
- `focus:` - On focus
- `focus-within:` - When child has focus
- `focus-visible:` - Only on keyboard focus (not mouse click)
- `active:` - On click/tap
- `disabled:` - Disabled state
- `first:` - First child
- `last:` - Last child
- `odd:` - Odd children
- `even:` - Even children
- `group-hover:` - When parent with `group` class is hovered
- `dark:` - Dark mode

---

## Modern Features (Tailwind v3+)

### Arbitrary Values

Use `[value]` syntax for one-off values not in the default scale:

| Pattern | Example | Use Case |
|---------|---------|----------|
| `w-[200px]` | Exact width | Custom dimensions |
| `h-[calc(100vh-64px)]` | CSS calc | Dynamic sizing |
| `bg-[#1da1f2]` | Hex color | Brand colors |
| `bg-[url('/img.png')]` | Background image | Custom backgrounds |
| `grid-cols-[1fr_2fr_1fr]` | Custom grid | Asymmetric layouts |
| `text-[length:16px]` | With type hint | Ambiguous values |
| `p-[clamp(1rem,5vw,3rem)]` | CSS clamp | Fluid spacing |

```html
<!-- Custom width -->
<div class="w-[calc(100%-2rem)]">...</div>

<!-- Brand color -->
<div class="bg-[#1da1f2] text-white">Twitter blue</div>

<!-- Custom grid -->
<div class="grid grid-cols-[200px_1fr_200px] gap-4">...</div>
```

**In FastHTML:**
```python
Div(content, cls="w-[calc(100%-2rem)] p-[clamp(1rem,5vw,3rem)]")
```

### Container Queries (v3.2+)

Style based on container size instead of viewport:

| Class | Purpose |
|-------|---------|
| `@container` | Mark element as container |
| `@container/name` | Named container |
| `@xs:`, `@sm:`, `@md:`, `@lg:`, `@xl:` | Container breakpoints |

```html
<!-- Container query -->
<div class="@container">
  <div class="@md:flex @md:gap-4">
    Flexes when container > 28rem
  </div>
</div>

<!-- Named container -->
<div class="@container/sidebar">
  <nav class="@lg/sidebar:flex-col">
    Changes based on sidebar width
  </nav>
</div>
```

**Container Breakpoints:**
| Prefix | Min Width |
|--------|-----------|
| `@xs:` | 20rem (320px) |
| `@sm:` | 24rem (384px) |
| `@md:` | 28rem (448px) |
| `@lg:` | 32rem (512px) |
| `@xl:` | 36rem (576px) |
| `@2xl:` | 42rem (672px) |

### Peer & Has Modifiers

Style elements based on sibling or child state:

**Peer (sibling-based):**
```html
<!-- Style label based on input state -->
<input type="email" class="peer" placeholder="Email">
<p class="invisible peer-invalid:visible text-red-500">
  Invalid email
</p>

<!-- Peer focus -->
<input class="peer">
<label class="peer-focus:text-blue-500">Focuses with input</label>
```

| Modifier | Description |
|----------|-------------|
| `peer-hover:` | When sibling with `peer` is hovered |
| `peer-focus:` | When sibling with `peer` is focused |
| `peer-invalid:` | When sibling with `peer` is invalid |
| `peer-checked:` | When sibling checkbox/radio is checked |
| `peer-disabled:` | When sibling with `peer` is disabled |

**Has (child-based):**
```html
<!-- Style parent based on child -->
<div class="has-[:checked]:bg-blue-100">
  <input type="checkbox">
  <label>Check me to change parent</label>
</div>

<!-- Has focus-within alternative -->
<div class="has-[:focus]:ring-2 has-[:focus]:ring-blue-500">
  <input type="text">
</div>
```

| Modifier | Description |
|----------|-------------|
| `has-[:checked]:` | When contains checked element |
| `has-[:focus]:` | When contains focused element |
| `has-[:disabled]:` | When contains disabled element |
| `group-has-[:checked]:` | Group + has combined |

### Direct Children Selector

Style only direct children:

```html
<ul class="*:p-4 *:border-b">
  <li>Direct child gets padding + border</li>
  <li>Direct child gets padding + border</li>
</ul>
```

### Accessibility Utilities

| Class | Purpose | CSS |
|-------|---------|-----|
| `sr-only` | Visually hidden, screen reader visible | Position off-screen |
| `not-sr-only` | Undo sr-only | Restore visibility |
| `focus-visible:*` | Style only on keyboard focus | `:focus-visible` |
| `motion-reduce:*` | Respect prefers-reduced-motion | `@media (prefers-reduced-motion: reduce)` |
| `motion-safe:*` | Only when motion is OK | `@media (prefers-reduced-motion: no-preference)` |
| `forced-colors:*` | High contrast mode | `@media (forced-colors: active)` |

```html
<!-- Screen reader only label -->
<button>
  <span class="sr-only">Close menu</span>
  <svg><!-- X icon --></svg>
</button>

<!-- Skip link (visible on focus) -->
<a href="#main" class="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-50 focus:p-4 focus:bg-white">
  Skip to main content
</a>

<!-- Keyboard-only focus ring -->
<button class="focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2">
  Accessible button
</button>

<!-- Respect reduced motion -->
<div class="motion-safe:animate-bounce motion-reduce:animate-none">
  Bounces only if user allows motion
</div>
```

**In FastHTML:**
```python
# Screen reader text
Button(
    Span("Close menu", cls="sr-only"),
    UkIcon("x", height=20),
    cls="btn btn-ghost"
)

# Skip link
A(
    "Skip to main content",
    href="#main",
    cls="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-50 focus:p-4 focus:bg-white focus:rounded-lg"
)
```

### Text Overflow & Line Clamp

| Class | Effect |
|-------|--------|
| `truncate` | Single line with ellipsis |
| `text-ellipsis` | Ellipsis overflow |
| `text-clip` | Clip overflow |
| `line-clamp-1` through `line-clamp-6` | Clamp to N lines |
| `line-clamp-none` | Remove clamping |

```html
<!-- Single line truncate -->
<p class="truncate">Very long text that will be truncated...</p>

<!-- Multi-line clamp -->
<p class="line-clamp-3">
  Long paragraph that will be clamped to three lines
  with an ellipsis at the end of the third line...
</p>
```

### Aspect Ratio

| Class | Ratio |
|-------|-------|
| `aspect-auto` | Natural aspect ratio |
| `aspect-square` | 1:1 |
| `aspect-video` | 16:9 |
| `aspect-[4/3]` | Custom ratio |

```html
<!-- Video container -->
<div class="aspect-video bg-gray-200">
  <iframe src="..." class="w-full h-full"></iframe>
</div>

<!-- Square thumbnail -->
<img src="..." class="aspect-square object-cover w-20">

<!-- Custom ratio -->
<div class="aspect-[4/3] bg-gray-100">
  4:3 container
</div>
```

### Scroll Utilities

**Scroll Behavior:**
- `scroll-auto` - Default scroll
- `scroll-smooth` - Smooth scrolling

**Scroll Snap:**
| Class | Effect |
|-------|--------|
| `snap-x` | Horizontal snap container |
| `snap-y` | Vertical snap container |
| `snap-mandatory` | Always snap |
| `snap-proximity` | Snap when close |
| `snap-start` | Snap to start |
| `snap-center` | Snap to center |
| `snap-end` | Snap to end |

```html
<!-- Horizontal scroll snap carousel -->
<div class="flex overflow-x-auto snap-x snap-mandatory">
  <div class="snap-center shrink-0 w-80">Card 1</div>
  <div class="snap-center shrink-0 w-80">Card 2</div>
  <div class="snap-center shrink-0 w-80">Card 3</div>
</div>
```

**Scroll Margin/Padding:**
- `scroll-m-*` - Scroll margin (offset from edge)
- `scroll-p-*` - Scroll padding (snap offset)

### Touch & Pointer

| Class | Effect |
|-------|--------|
| `touch-auto` | Default touch behavior |
| `touch-none` | Disable touch |
| `touch-pan-x` | Allow horizontal pan only |
| `touch-pan-y` | Allow vertical pan only |
| `touch-manipulation` | Allow pan/zoom, disable double-tap |

```html
<!-- Draggable element -->
<div class="touch-none cursor-move">
  Drag me
</div>

<!-- Scrollable in one direction -->
<div class="touch-pan-y overflow-y-auto">
  Vertical scroll only
</div>
```

### Accent & Caret Colors

| Class | Effect |
|-------|--------|
| `accent-*` | Form element accent (checkbox, radio, range) |
| `caret-*` | Text input cursor color |

```html
<!-- Colored checkbox -->
<input type="checkbox" class="accent-blue-500">

<!-- Colored text cursor -->
<input type="text" class="caret-pink-500">
```
