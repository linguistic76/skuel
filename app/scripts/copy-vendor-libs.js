/**
 * Copy vendor libraries from node_modules to static/vendor
 *
 * Run with: npm run vendor:copy
 *
 * This script copies the minified distribution files from npm packages
 * to the static/vendor directory for serving directly to browsers.
 */

const fs = require("fs");
const path = require("path");

const VENDOR_DIR = path.join(__dirname, "..", "static", "vendor");

// Libraries to copy: [source_path, dest_filename]
const LIBRARIES = [
  // Chart.js
  ["node_modules/chart.js/dist/chart.umd.js", "chart.js/chart.umd.js"],

  // Frappe Gantt. 1.x ships no minified build: dist/ is .es.js / .umd.js / .css,
  // where 0.6.1 had .min.js / .min.css. The UMD build is the one a <script> tag
  // can load without a bundler. Note ensureDir() below creates the destination
  // BEFORE the source is checked, so a stale path here fails into an empty
  // directory that looks like a successful copy.
  [
    "node_modules/frappe-gantt/dist/frappe-gantt.umd.js",
    "frappe-gantt/frappe-gantt.umd.js",
  ],
  [
    "node_modules/frappe-gantt/dist/frappe-gantt.css",
    "frappe-gantt/frappe-gantt.css",
  ],
];

function ensureDir(dirPath) {
  if (!fs.existsSync(dirPath)) {
    fs.mkdirSync(dirPath, { recursive: true });
    console.log(`Created directory: ${dirPath}`);
  }
}

function copyFile(src, dest) {
  const srcPath = path.join(__dirname, "..", src);
  const destPath = path.join(VENDOR_DIR, dest);

  // Ensure destination directory exists
  ensureDir(path.dirname(destPath));

  if (!fs.existsSync(srcPath)) {
    console.error(`Source not found: ${srcPath}`);
    return false;
  }

  fs.copyFileSync(srcPath, destPath);
  console.log(`Copied: ${src} -> static/vendor/${dest}`);
  return true;
}

function main() {
  console.log("Copying vendor libraries to static/vendor/...\n");

  // Ensure vendor directory exists
  ensureDir(VENDOR_DIR);

  let success = 0;
  let failed = 0;

  for (const [src, dest] of LIBRARIES) {
    if (copyFile(src, dest)) {
      success++;
    } else {
      failed++;
    }
  }

  console.log(`\nDone: ${success} copied, ${failed} failed`);

  if (failed > 0) {
    console.log("\nRun 'npm install' first if files are missing.");
    process.exit(1);
  }
}

main();
