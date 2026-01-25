# Semantic HTML Reference

## Why Semantic HTML Matters

Semantic HTML:
1. **Accessibility** - Screen readers understand content structure
2. **SEO** - Search engines parse content meaning
3. **Maintainability** - Developers understand intent
4. **Browser Features** - Native behaviors (outline, reader mode)

## Document Structure

### Required Structure

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Descriptive Page Title</title>
  <meta name="description" content="Page description for SEO">
</head>
<body>
  <!-- Content -->
</body>
</html>
```

### Landmark Elements

```html
<body>
  <header>         <!-- Site header (logo, nav) -->
    <nav>          <!-- Primary navigation -->
    </nav>
  </header>

  <main>           <!-- Main content (ONE per page) -->
    <article>      <!-- Self-contained content -->
      <header>     <!-- Article header -->
      </header>
      <section>    <!-- Thematic grouping -->
      </section>
      <footer>     <!-- Article footer -->
      </footer>
    </article>

    <aside>        <!-- Related content (sidebar) -->
    </aside>
  </main>

  <footer>         <!-- Site footer -->
  </footer>
</body>
```

## Sectioning Elements

### `<article>`
Self-contained, independently distributable content.

```html
<!-- Blog post -->
<article>
  <header>
    <h2>Article Title</h2>
    <time datetime="2026-01-05">January 5, 2026</time>
  </header>
  <p>Article content...</p>
</article>

<!-- Comment -->
<article>
  <header>
    <strong>Username</strong>
    <time datetime="2026-01-05T10:30">10:30 AM</time>
  </header>
  <p>Comment text...</p>
</article>

<!-- Widget -->
<article>
  <h3>Weather Widget</h3>
  <p>72°F Sunny</p>
</article>
```

### `<section>`
Thematic grouping of content, typically with a heading.

```html
<section>
  <h2>Features</h2>
  <ul>
    <li>Feature 1</li>
    <li>Feature 2</li>
  </ul>
</section>

<section>
  <h2>Pricing</h2>
  <div class="pricing-cards">...</div>
</section>
```

### `<nav>`
Navigation links (primary, secondary, breadcrumbs, pagination).

```html
<!-- Primary navigation -->
<nav aria-label="Main">
  <ul>
    <li><a href="/">Home</a></li>
    <li><a href="/products">Products</a></li>
    <li><a href="/about">About</a></li>
  </ul>
</nav>

<!-- Breadcrumbs -->
<nav aria-label="Breadcrumb">
  <ol>
    <li><a href="/">Home</a></li>
    <li><a href="/products">Products</a></li>
    <li aria-current="page">Widget</li>
  </ol>
</nav>

<!-- Pagination -->
<nav aria-label="Pagination">
  <a href="?page=1">Previous</a>
  <a href="?page=3">Next</a>
</nav>
```

### `<aside>`
Tangentially related content (sidebars, pull quotes, ads).

```html
<!-- Sidebar -->
<aside>
  <h3>Related Articles</h3>
  <ul>
    <li><a href="#">Article 1</a></li>
    <li><a href="#">Article 2</a></li>
  </ul>
</aside>

<!-- Pull quote -->
<aside>
  <blockquote>
    "Important quote from the article"
  </blockquote>
</aside>
```

### `<header>` and `<footer>`
Introductory or footer content for their parent.

```html
<!-- Page header -->
<header>
  <h1>Site Name</h1>
  <nav>...</nav>
</header>

<!-- Article header -->
<article>
  <header>
    <h2>Article Title</h2>
    <p>By <a href="/author">Author</a></p>
    <time datetime="2026-01-05">January 5, 2026</time>
  </header>
</article>

<!-- Page footer -->
<footer>
  <nav>Legal links</nav>
  <p>&copy; 2026 Company</p>
</footer>
```

## Headings

Headings create document outline. Use them hierarchically:

```html
<h1>Page Title</h1>           <!-- One per page -->
  <h2>Major Section</h2>
    <h3>Subsection</h3>
      <h4>Sub-subsection</h4>
    <h3>Another Subsection</h3>
  <h2>Another Major Section</h2>
```

**Rules:**
- One `<h1>` per page (usually page title)
- Don't skip levels (h1 → h3)
- Headings should describe content below them

## Text Content

### Paragraphs and Line Breaks

```html
<p>A paragraph of text. Multiple sentences belong in one paragraph.</p>

<p>Another paragraph with a<br>line break for poetry or addresses:</p>

<address>
  123 Main Street<br>
  City, State 12345
</address>
```

### Lists

```html
<!-- Unordered (no sequence) -->
<ul>
  <li>Item</li>
  <li>Item</li>
</ul>

<!-- Ordered (sequence matters) -->
<ol>
  <li>First step</li>
  <li>Second step</li>
</ol>

<!-- Description list (term/definition pairs) -->
<dl>
  <dt>Term</dt>
  <dd>Definition of the term</dd>

  <dt>Another term</dt>
  <dd>Its definition</dd>
</dl>
```

### Quotations

```html
<!-- Block quote (extended quotation) -->
<blockquote cite="https://source.com">
  <p>A longer quotation that deserves its own block.</p>
  <footer>— <cite>Author Name</cite></footer>
</blockquote>

<!-- Inline quote -->
<p>She said <q>this is a short quote</q> in passing.</p>

<!-- Citation (title of work) -->
<p>Read <cite>The Great Gatsby</cite> for reference.</p>
```

### Preformatted and Code

```html
<!-- Preformatted (whitespace preserved) -->
<pre>
  Exactly
    as
      written
</pre>

<!-- Code (inline) -->
<p>Use the <code>forEach()</code> method.</p>

<!-- Code block -->
<pre><code class="language-javascript">
function hello() {
  console.log("Hello");
}
</code></pre>

<!-- Keyboard input -->
<p>Press <kbd>Ctrl</kbd> + <kbd>S</kbd> to save.</p>

<!-- Sample output -->
<p>The program outputs: <samp>Hello, World!</samp></p>

<!-- Variable -->
<p>The variable <var>x</var> represents the count.</p>
```

## Inline Semantics

### Emphasis and Importance

```html
<!-- Emphasis (stress, typically italic) -->
<p>I <em>really</em> want this.</p>

<!-- Strong importance (typically bold) -->
<p><strong>Warning:</strong> This action is irreversible.</p>

<!-- Note: Use CSS for styling, semantics for meaning -->
<!-- AVOID: <b> and <i> for emphasis (use for stylistic offset only) -->
```

### Technical and Editorial

```html
<!-- Marked/highlighted text -->
<p>Search results: <mark>highlighted term</mark></p>

<!-- Deleted text -->
<p>Price: <del>$50</del> <ins>$40</ins></p>

<!-- Small print (legal, copyright) -->
<p><small>&copy; 2026 Company. All rights reserved.</small></p>

<!-- Subscript/Superscript -->
<p>H<sub>2</sub>O, E=mc<sup>2</sup></p>

<!-- Abbreviation -->
<p><abbr title="HyperText Markup Language">HTML</abbr></p>

<!-- Definition -->
<p><dfn>Hypermedia</dfn> is media with embedded links.</p>
```

### Links

```html
<!-- Standard link -->
<a href="/page">Link text</a>

<!-- External link -->
<a href="https://example.com" target="_blank" rel="noopener noreferrer">
  External Site
</a>

<!-- Download link -->
<a href="/file.pdf" download>Download PDF</a>

<!-- Email link -->
<a href="mailto:info@example.com">Email Us</a>

<!-- Phone link -->
<a href="tel:+15555555555">Call Us</a>

<!-- Anchor link -->
<a href="#section-id">Jump to Section</a>
```

## Forms

### Form Structure

```html
<form action="/submit" method="post">
  <fieldset>
    <legend>Personal Information</legend>

    <label for="name">Name</label>
    <input type="text" id="name" name="name" required>

    <label for="email">Email</label>
    <input type="email" id="email" name="email" required>
  </fieldset>

  <fieldset>
    <legend>Preferences</legend>

    <label>
      <input type="checkbox" name="newsletter">
      Subscribe to newsletter
    </label>
  </fieldset>

  <button type="submit">Submit</button>
</form>
```

### Input Types

```html
<!-- Text inputs -->
<input type="text">         <!-- Plain text -->
<input type="email">        <!-- Email validation -->
<input type="password">     <!-- Hidden characters -->
<input type="url">          <!-- URL validation -->
<input type="tel">          <!-- Phone number -->
<input type="search">       <!-- Search field -->

<!-- Numbers -->
<input type="number" min="0" max="100" step="1">
<input type="range" min="0" max="100">

<!-- Date/Time -->
<input type="date">         <!-- Date picker -->
<input type="time">         <!-- Time picker -->
<input type="datetime-local">  <!-- Date + time -->
<input type="month">        <!-- Month picker -->
<input type="week">         <!-- Week picker -->

<!-- Other -->
<input type="file">         <!-- File upload -->
<input type="color">        <!-- Color picker -->
<input type="hidden">       <!-- Hidden data -->
```

### Selection Inputs

```html
<!-- Single select -->
<select name="country">
  <option value="">Select country</option>
  <option value="us">United States</option>
  <option value="uk">United Kingdom</option>
</select>

<!-- Grouped options -->
<select name="car">
  <optgroup label="Swedish Cars">
    <option value="volvo">Volvo</option>
    <option value="saab">Saab</option>
  </optgroup>
  <optgroup label="German Cars">
    <option value="mercedes">Mercedes</option>
    <option value="audi">Audi</option>
  </optgroup>
</select>

<!-- Datalist (autocomplete) -->
<input list="browsers" name="browser">
<datalist id="browsers">
  <option value="Chrome">
  <option value="Firefox">
  <option value="Safari">
</datalist>

<!-- Radio buttons (single choice) -->
<fieldset>
  <legend>Payment Method</legend>
  <label><input type="radio" name="payment" value="card"> Credit Card</label>
  <label><input type="radio" name="payment" value="paypal"> PayPal</label>
</fieldset>

<!-- Checkboxes (multiple choice) -->
<fieldset>
  <legend>Interests</legend>
  <label><input type="checkbox" name="interests" value="tech"> Technology</label>
  <label><input type="checkbox" name="interests" value="sports"> Sports</label>
</fieldset>
```

### Form Validation

```html
<input type="text" required>                    <!-- Required field -->
<input type="text" minlength="3" maxlength="50"> <!-- Length limits -->
<input type="number" min="1" max="100">         <!-- Value limits -->
<input type="text" pattern="[A-Za-z]{3}">       <!-- Regex pattern -->
<input type="email">                            <!-- Built-in email validation -->
```

## Tables

```html
<table>
  <caption>Monthly Sales Report</caption>

  <thead>
    <tr>
      <th scope="col">Month</th>
      <th scope="col">Sales</th>
      <th scope="col">Revenue</th>
    </tr>
  </thead>

  <tbody>
    <tr>
      <th scope="row">January</th>
      <td>150</td>
      <td>$15,000</td>
    </tr>
    <tr>
      <th scope="row">February</th>
      <td>200</td>
      <td>$20,000</td>
    </tr>
  </tbody>

  <tfoot>
    <tr>
      <th scope="row">Total</th>
      <td>350</td>
      <td>$35,000</td>
    </tr>
  </tfoot>
</table>
```

## Media

### Images

```html
<!-- Basic image -->
<img src="image.jpg" alt="Description of image">

<!-- Responsive image -->
<img src="small.jpg"
     srcset="small.jpg 300w, medium.jpg 600w, large.jpg 1200w"
     sizes="(max-width: 600px) 300px, (max-width: 1200px) 600px, 1200px"
     alt="Description">

<!-- Figure with caption -->
<figure>
  <img src="chart.png" alt="Sales chart showing growth">
  <figcaption>Figure 1: Sales growth over 12 months</figcaption>
</figure>

<!-- Picture element (art direction) -->
<picture>
  <source media="(min-width: 800px)" srcset="wide.jpg">
  <source media="(min-width: 400px)" srcset="medium.jpg">
  <img src="narrow.jpg" alt="Description">
</picture>
```

### Video and Audio

```html
<!-- Video -->
<video controls width="640" height="360">
  <source src="video.mp4" type="video/mp4">
  <source src="video.webm" type="video/webm">
  <p>Your browser doesn't support video. <a href="video.mp4">Download</a></p>
</video>

<!-- Audio -->
<audio controls>
  <source src="audio.mp3" type="audio/mpeg">
  <source src="audio.ogg" type="audio/ogg">
  <p>Your browser doesn't support audio. <a href="audio.mp3">Download</a></p>
</audio>
```

### Embedded Content

```html
<!-- iframe -->
<iframe src="https://example.com"
        width="600"
        height="400"
        title="Embedded content description"
        loading="lazy">
</iframe>
```

## Interactive Elements

### Details/Summary (No JS Required)

```html
<details>
  <summary>Click to expand</summary>
  <p>Hidden content revealed when expanded.</p>
</details>

<details open>  <!-- Open by default -->
  <summary>FAQ: What is HTMX?</summary>
  <p>HTMX gives HTML access to the full HTTP protocol.</p>
</details>
```

### Dialog

```html
<dialog id="my-dialog">
  <h2>Dialog Title</h2>
  <p>Dialog content</p>
  <form method="dialog">
    <button>Close</button>
  </form>
</dialog>

<button onclick="document.getElementById('my-dialog').showModal()">
  Open Dialog
</button>
```

## ARIA Basics

Use ARIA to enhance accessibility when HTML semantics aren't sufficient:

```html
<!-- Landmark roles (prefer semantic elements) -->
<div role="navigation">...</div>  <!-- Prefer <nav> -->
<div role="main">...</div>        <!-- Prefer <main> -->

<!-- Live regions (announce changes) -->
<div aria-live="polite">Updates announced to screen readers</div>
<div aria-live="assertive">Urgent updates</div>

<!-- Labels -->
<button aria-label="Close dialog">✕</button>
<input aria-labelledby="label-id">

<!-- States -->
<button aria-pressed="true">Toggle On</button>
<button aria-expanded="false">Expand</button>
<div aria-hidden="true">Hidden from assistive tech</div>

<!-- Descriptions -->
<input aria-describedby="help-text">
<p id="help-text">Enter your email address</p>
```

## Common Patterns

### Card

```html
<article class="card">
  <header>
    <h3>Card Title</h3>
  </header>
  <p>Card content</p>
  <footer>
    <a href="/more">Learn more</a>
  </footer>
</article>
```

### Modal

```html
<dialog id="modal">
  <header>
    <h2>Modal Title</h2>
    <form method="dialog">
      <button aria-label="Close">✕</button>
    </form>
  </header>
  <main>
    <p>Modal content</p>
  </main>
  <footer>
    <form method="dialog">
      <button>Cancel</button>
      <button>Confirm</button>
    </form>
  </footer>
</dialog>
```

### Search

```html
<search>  <!-- HTML5.2 search element -->
  <form action="/search" method="get" role="search">
    <label for="search">Search</label>
    <input type="search" id="search" name="q">
    <button type="submit">Search</button>
  </form>
</search>
```
