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

  // Vis.js Timeline
  [
    "node_modules/vis-timeline/standalone/umd/vis-timeline-graph2d.min.js",
    "vis-timeline/vis-timeline-graph2d.min.js",
  ],
  [
    "node_modules/vis-timeline/styles/vis-timeline-graph2d.min.css",
    "vis-timeline/vis-timeline-graph2d.min.css",
  ],

  // Frappe Gantt
  [
    "node_modules/frappe-gantt/dist/frappe-gantt.min.js",
    "frappe-gantt/frappe-gantt.min.js",
  ],
  [
    "node_modules/frappe-gantt/dist/frappe-gantt.min.css",
    "frappe-gantt/frappe-gantt.min.css",
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
