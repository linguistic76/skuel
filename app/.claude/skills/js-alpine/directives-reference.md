# Alpine.js Directives Reference

Complete reference for all 15 Alpine.js directives and 9 magic properties.

## State & Initialization

### x-data

Initialize reactive data for a component. The element becomes the component root.

```html
<!-- Object literal -->
<div x-data="{ count: 0, name: 'Alpine' }">
    <span x-text="count"></span>
    <span x-text="name"></span>
</div>

<!-- With methods -->
<div x-data="{
    count: 0,
    increment() { this.count++ },
    decrement() { this.count-- }
}">
    <button x-on:click="decrement()">-</button>
    <span x-text="count"></span>
    <button x-on:click="increment()">+</button>
</div>

<!-- Reusable component (defined with Alpine.data()) -->
<div x-data="counter">
    <button x-on:click="increment()">+</button>
    <span x-text="count"></span>
</div>

<!-- Empty for accessing magic properties only -->
<div x-data>
    <button x-on:click="$dispatch('notify')">Notify</button>
</div>
```

**Scoping:** Child elements can access parent `x-data`, but nested `x-data` creates a new scope.

### x-init

Execute code when the component initializes.

```html
<!-- Inline expression -->
<div x-data="{ loaded: false }" x-init="loaded = true">

<!-- Call a method -->
<div x-data="{ items: [] }" x-init="items = await fetchItems()">

<!-- With $nextTick for DOM access -->
<div x-data x-init="$nextTick(() => $refs.input.focus())">
    <input x-ref="input">
</div>

<!-- Async initialization -->
<div x-data="{ user: null }"
     x-init="user = await (await fetch('/api/user')).json()">
    <span x-text="user?.name ?? 'Loading...'"></span>
</div>
```

**Timing:** Runs after Alpine processes the element but before `x-effect`.

### x-effect

Run code reactively when dependencies change.

```html
<!-- Log whenever count changes -->
<div x-data="{ count: 0 }" x-effect="console.log('Count is:', count)">
    <button x-on:click="count++">Increment</button>
</div>

<!-- Sync with external API -->
<div x-data="{ query: '' }"
     x-effect="if (query.length > 2) search(query)">
    <input x-model="query" placeholder="Search...">
</div>

<!-- Update document title -->
<div x-data="{ page: 'Home' }"
     x-effect="document.title = page + ' - My App'">
```

**Dependencies:** Alpine automatically tracks which reactive data is accessed and re-runs when it changes.

---

## Rendering

### x-show

Toggle element visibility using CSS `display` property.

```html
<!-- Basic toggle -->
<div x-data="{ visible: true }">
    <button x-on:click="visible = !visible">Toggle</button>
    <p x-show="visible">I'm visible!</p>
</div>

<!-- With transition -->
<div x-show="open" x-transition>Content with animation</div>

<!-- Expression -->
<div x-show="items.length > 0">Items exist</div>
<div x-show="user && user.isAdmin">Admin only</div>
```

**Key Point:** Element stays in DOM, only CSS display changes. Use for frequently toggled content.

### x-if

Conditionally add/remove element from DOM. Must use `<template>` wrapper.

```html
<!-- Basic conditional -->
<template x-if="showPanel">
    <div class="panel">Panel Content</div>
</template>

<!-- Conditional with single root -->
<template x-if="user">
    <div>
        <h2 x-text="user.name"></h2>
        <p x-text="user.email"></p>
    </div>
</template>
```

**Key Point:** Element is completely removed from DOM when false. Use for rarely shown content or heavy components.

**Comparison:**

| Feature | x-show | x-if |
|---------|--------|------|
| DOM presence | Always in DOM | Added/removed |
| Performance | Fast toggle | Slower toggle |
| Initial load | Always rendered | Only if true |
| Use case | Frequent toggles | Rare conditions |

### x-for

Loop over an array to render elements. Must use `<template>` wrapper.

```html
<!-- Basic loop -->
<ul>
    <template x-for="item in items">
        <li x-text="item"></li>
    </template>
</ul>

<!-- With index -->
<ul>
    <template x-for="(item, index) in items">
        <li>
            <span x-text="index + 1"></span>:
            <span x-text="item.name"></span>
        </li>
    </template>
</ul>

<!-- With key for optimal updates -->
<template x-for="user in users" :key="user.id">
    <div x-text="user.name"></div>
</template>

<!-- Nested loops -->
<template x-for="category in categories">
    <div>
        <h3 x-text="category.name"></h3>
        <template x-for="item in category.items">
            <span x-text="item"></span>
        </template>
    </div>
</template>

<!-- Range (1 to n) -->
<template x-for="i in 5">
    <span x-text="i"></span> <!-- 1, 2, 3, 4, 5 -->
</template>
```

**Key Attribute:** Always use `:key` when items have unique identifiers for optimal DOM updates.

### x-text

Set element's `textContent`.

```html
<!-- Variable -->
<span x-text="message"></span>

<!-- Expression -->
<span x-text="firstName + ' ' + lastName"></span>

<!-- Formatted -->
<span x-text="count.toLocaleString()"></span>
<span x-text="date.toLocaleDateString()"></span>

<!-- With fallback -->
<span x-text="user?.name ?? 'Anonymous'"></span>
```

**Security:** Content is escaped. Use for displaying user input safely.

### x-html

Set element's `innerHTML`. Use with caution.

```html
<!-- Render HTML -->
<div x-html="richContent"></div>

<!-- From API response -->
<div x-data="{ content: '' }"
     x-init="content = await fetch('/api/content').then(r => r.text())"
     x-html="content">
</div>
```

**Warning:** Only use with trusted content. Never use with user input - XSS risk!

---

## Events & Input

### x-on / @

Listen for DOM events and run JavaScript.

```html
<!-- Click -->
<button x-on:click="count++">Increment</button>
<button @click="count++">Shorthand</button>

<!-- With method -->
<button @click="handleClick($event)">Click</button>

<!-- Keyboard -->
<input @keydown.enter="submit()">
<input @keydown.escape="cancel()">
<input @keydown.arrow-up="previous()">

<!-- Form -->
<form @submit.prevent="save()">
<input @input="search($event.target.value)">
<input @change="update()">
<input @focus="highlight()" @blur="unhighlight()">

<!-- Mouse -->
<div @mouseenter="show()" @mouseleave="hide()">
<div @mouseover="hover = true" @mouseout="hover = false">

<!-- Touch -->
<div @touchstart="startDrag($event)"
     @touchmove="drag($event)"
     @touchend="endDrag($event)">
```

#### Event Modifiers

```html
@click.prevent      <!-- event.preventDefault() -->
@click.stop         <!-- event.stopPropagation() -->
@click.outside      <!-- Click outside element -->
@click.self         <!-- Only if target is this element -->
@click.once         <!-- Only fire once -->
@click.window       <!-- Listen on window -->
@click.document     <!-- Listen on document -->
@click.passive      <!-- Passive event listener -->
@click.capture      <!-- Capture phase -->

<!-- Combinations -->
@click.prevent.stop
@submit.prevent
```

#### Key Modifiers

```html
@keydown.enter
@keydown.escape
@keydown.space
@keydown.tab
@keydown.delete     <!-- Delete or Backspace -->
@keydown.arrow-up
@keydown.arrow-down
@keydown.arrow-left
@keydown.arrow-right

<!-- With meta keys -->
@keydown.ctrl.s
@keydown.cmd.s      <!-- Mac Command -->
@keydown.shift.enter
@keydown.alt.a
@keydown.meta.k     <!-- Cmd on Mac, Ctrl on Windows -->
```

#### Debounce & Throttle

```html
<!-- Debounce: Wait for pause in events -->
<input @input.debounce="search()">           <!-- Default 250ms -->
<input @input.debounce.500ms="search()">     <!-- Custom delay -->

<!-- Throttle: Limit frequency -->
<div @scroll.throttle="handleScroll()">      <!-- Default 250ms -->
<div @scroll.throttle.100ms="handleScroll()">
```

### x-model

Two-way data binding for form inputs.

```html
<!-- Text input -->
<input type="text" x-model="name">

<!-- Textarea -->
<textarea x-model="message"></textarea>

<!-- Checkbox (boolean) -->
<input type="checkbox" x-model="agreed">

<!-- Checkbox (array) -->
<input type="checkbox" value="red" x-model="colors">
<input type="checkbox" value="blue" x-model="colors">
<!-- colors = ['red', 'blue'] when both checked -->

<!-- Radio -->
<input type="radio" value="small" x-model="size">
<input type="radio" value="large" x-model="size">

<!-- Select -->
<select x-model="country">
    <option value="us">United States</option>
    <option value="uk">United Kingdom</option>
</select>

<!-- Select multiple (array) -->
<select x-model="selectedCountries" multiple>
    <option value="us">US</option>
    <option value="uk">UK</option>
</select>
```

#### x-model Modifiers

```html
<!-- Lazy: Update on change, not input -->
<input x-model.lazy="name">

<!-- Number: Parse as number -->
<input type="number" x-model.number="age">

<!-- Debounce: Delay updates -->
<input x-model.debounce="search">
<input x-model.debounce.500ms="search">

<!-- Throttle: Limit update frequency -->
<input x-model.throttle="liveValue">

<!-- Fill: Pre-fill with value attribute -->
<input x-model.fill="name" value="Default">
```

### x-bind / :

Dynamically bind HTML attributes.

```html
<!-- Class binding -->
<div x-bind:class="{ 'active': isActive }"></div>
<div :class="{ 'active': isActive, 'disabled': isDisabled }"></div>
<div :class="isActive ? 'bg-green' : 'bg-gray'"></div>

<!-- Style binding -->
<div :style="{ color: textColor, fontSize: size + 'px' }"></div>
<div :style="`background: ${bgColor}`"></div>

<!-- Other attributes -->
<input :disabled="isLoading">
<input :readonly="!canEdit">
<button :aria-pressed="isPressed">
<a :href="url">
<img :src="imageUrl" :alt="imageAlt">

<!-- Multiple attributes with object -->
<input x-bind="{ type: 'text', placeholder: 'Enter name', required: true }">
```

#### Class Object Syntax

```html
<!-- Object: key = class name, value = boolean condition -->
<div :class="{
    'text-red-500': hasError,
    'text-green-500': isSuccess,
    'opacity-50': isLoading
}">

<!-- Array: combine static and dynamic -->
<div :class="['base-class', { 'active': isActive }]">

<!-- Ternary for exclusive classes -->
<div :class="status === 'success' ? 'bg-green' : 'bg-red'">
```

---

## Animation & Transitions

### x-transition

Apply enter/leave transitions when element is shown/hidden.

```html
<!-- Default transition -->
<div x-show="open" x-transition>Fades in/out</div>

<!-- Custom durations -->
<div x-show="open" x-transition.duration.500ms>

<!-- Scale origin -->
<div x-show="open" x-transition.origin.top>
<div x-show="open" x-transition.origin.top.right>

<!-- Scale amount -->
<div x-show="open" x-transition.scale.90>

<!-- Opacity only (no scale) -->
<div x-show="open" x-transition.opacity>
```

#### Full Control

```html
<div x-show="open"
     x-transition:enter="transition ease-out duration-300"
     x-transition:enter-start="opacity-0 transform scale-95"
     x-transition:enter-end="opacity-100 transform scale-100"
     x-transition:leave="transition ease-in duration-200"
     x-transition:leave-start="opacity-100 transform scale-100"
     x-transition:leave-end="opacity-0 transform scale-95">
```

| Stage | When |
|-------|------|
| `enter` | Classes applied during entire enter phase |
| `enter-start` | Initial state, removed after first frame |
| `enter-end` | Final state, applied after first frame |
| `leave` | Classes applied during entire leave phase |
| `leave-start` | Initial leave state |
| `leave-end` | Final leave state |

---

## Utilities

### x-ref

Create a named reference to an element, accessible via `$refs`.

```html
<div x-data>
    <input x-ref="input" type="text">
    <button @click="$refs.input.focus()">Focus Input</button>
</div>

<!-- Multiple refs -->
<div x-data>
    <input x-ref="username" placeholder="Username">
    <input x-ref="password" type="password">
    <button @click="console.log($refs.username.value, $refs.password.value)">
        Log Values
    </button>
</div>
```

### x-cloak

Hide element until Alpine initializes. Prevents flash of unprocessed template.

```css
/* Required CSS */
[x-cloak] { display: none !important; }
```

```html
<div x-data="{ ready: false }" x-cloak x-init="ready = true">
    <span x-show="ready">Ready!</span>
</div>
```

### x-ignore

Prevent Alpine from processing element and children.

```html
<div x-data="{ count: 0 }">
    <span x-text="count"></span> <!-- Processed -->

    <div x-ignore>
        <span x-text="count"></span> <!-- NOT processed, shows literal "count" -->
    </div>
</div>
```

**Use case:** Third-party widgets, iframes, or content managed by other libraries.

---

## Magic Properties

### $el

Reference to the current DOM element.

```html
<button @click="$el.textContent = 'Clicked!'">Click me</button>
<input @focus="$el.select()">
<div x-init="console.log($el.offsetWidth)">
```

### $refs

Object containing all elements with `x-ref` attributes.

```html
<div x-data>
    <input x-ref="name" placeholder="Name">
    <input x-ref="email" placeholder="Email">
    <button @click="console.log($refs.name.value, $refs.email.value)">
        Submit
    </button>
</div>
```

### $store

Access global Alpine stores.

```javascript
// Define store
Alpine.store('user', {
    name: 'John',
    loggedIn: true,
    logout() { this.loggedIn = false }
})
```

```html
<!-- Access store -->
<span x-text="$store.user.name"></span>
<button x-show="$store.user.loggedIn" @click="$store.user.logout()">
    Logout
</button>
```

### $watch

Watch a reactive property for changes.

```html
<div x-data="{ count: 0 }"
     x-init="$watch('count', (value, oldValue) => {
         console.log('Changed from', oldValue, 'to', value)
     })">
    <button @click="count++">Increment</button>
</div>
```

### $dispatch

Dispatch a custom DOM event.

```html
<!-- Dispatch -->
<button @click="$dispatch('notify', { message: 'Hello!' })">
    Notify
</button>

<!-- Listen (bubbles up) -->
<div @notify.window="alert($event.detail.message)">
    <button @click="$dispatch('notify', { message: 'Hello!' })">
        Notify
    </button>
</div>
```

### $nextTick

Execute callback after Alpine finishes updating the DOM.

```html
<div x-data="{ items: [] }">
    <button @click="
        items.push('New Item');
        $nextTick(() => $refs.list.lastChild.scrollIntoView())
    ">
        Add Item
    </button>
    <ul x-ref="list">
        <template x-for="item in items">
            <li x-text="item"></li>
        </template>
    </ul>
</div>
```

### $root

Reference to the root element of the component (the element with `x-data`).

```html
<div x-data="{ id: 123 }" data-section="main">
    <div>
        <button @click="console.log($root.dataset.section)">
            Log Section <!-- "main" -->
        </button>
    </div>
</div>
```

### $data

Access the component's reactive data object.

```html
<div x-data="{ count: 0, name: 'Alpine' }">
    <button @click="console.log($data)">
        Log Data <!-- { count: 0, name: 'Alpine' } -->
    </button>
</div>
```

### $id

Generate unique IDs for accessibility.

```html
<div x-data>
    <label :for="$id('input')">Name</label>
    <input :id="$id('input')">

    <label :for="$id('input')">Email</label>
    <input :id="$id('input')">
    <!-- Each $id('input') generates a unique ID -->
</div>
```

---

## Alpine.data() - Reusable Components

Define reusable component logic.

```javascript
// Register component
document.addEventListener('alpine:init', () => {
    Alpine.data('dropdown', () => ({
        open: false,

        toggle() {
            this.open = !this.open
        },

        close() {
            this.open = false
        },

        // Lifecycle: init runs on component initialization
        init() {
            console.log('Dropdown initialized')
        },

        // Lifecycle: destroy runs on component removal
        destroy() {
            console.log('Dropdown destroyed')
        }
    }))
})
```

```html
<!-- Usage -->
<div x-data="dropdown" @click.outside="close()">
    <button @click="toggle()">Menu</button>
    <ul x-show="open" x-transition>
        <li>Option 1</li>
        <li>Option 2</li>
    </ul>
</div>
```

### With Parameters

```javascript
Alpine.data('counter', (initialCount = 0) => ({
    count: initialCount,
    increment() { this.count++ },
    decrement() { this.count-- }
}))
```

```html
<div x-data="counter(10)">
    <button @click="decrement()">-</button>
    <span x-text="count"></span>
    <button @click="increment()">+</button>
</div>
```

---

## Alpine.store() - Global State

Define global reactive state accessible anywhere.

```javascript
Alpine.store('notifications', {
    items: [],

    add(message) {
        this.items.push({ id: Date.now(), message })
    },

    remove(id) {
        this.items = this.items.filter(n => n.id !== id)
    }
})
```

```html
<!-- Add notification from anywhere -->
<button @click="$store.notifications.add('Hello!')">
    Add Notification
</button>

<!-- Display notifications -->
<div x-data>
    <template x-for="notification in $store.notifications.items" :key="notification.id">
        <div>
            <span x-text="notification.message"></span>
            <button @click="$store.notifications.remove(notification.id)">
                Dismiss
            </button>
        </div>
    </template>
</div>
```
