import test from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, extname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");

function collectHtml(directory) {
  const files = [];
  for (const entry of readdirSync(directory)) {
    if (entry === ".git" || entry === "node_modules" || entry === ".venv") continue;
    const path = join(directory, entry);
    if (statSync(path).isDirectory()) files.push(...collectHtml(path));
    else if (extname(path) === ".html") files.push(path);
  }
  return files;
}

test("HTML の相対 href / src は存在するファイルへ解決できる", () => {
  const missing = [];
  const attributePattern = /\b(?:href|src)=["']([^"']+)["']/g;

  for (const htmlPath of collectHtml(repositoryRoot)) {
    const html = readFileSync(htmlPath, "utf8");
    for (const match of html.matchAll(attributePattern)) {
      const reference = match[1];
      if (/^(?:[a-z]+:|\/\/|#)/i.test(reference)) continue;
      const clean = reference.split(/[?#]/, 1)[0];
      if (!clean) continue;
      const target = resolve(dirname(htmlPath), clean);
      const resolvedTarget = clean.endsWith("/") ? join(target, "index.html") : target;
      if (!existsSync(resolvedTarget)) {
        missing.push(`${htmlPath.slice(repositoryRoot.length + 1)} -> ${reference}`);
      }
    }
  }

  assert.deepEqual(missing, []);
});

test("統合デモの app が参照する DOM id は HTML に存在する", () => {
  const demoRoot = join(repositoryRoot, "demos", "relational-ecology-lab");
  const app = readFileSync(join(demoRoot, "app.mjs"), "utf8");
  const html = readFileSync(join(demoRoot, "index.html"), "utf8");
  const referencedIds = [...app.matchAll(/querySelector\(["']#([^"']+)["']\)/g)]
    .map((match) => match[1]);
  const missing = referencedIds.filter(
    (id) => !new RegExp(`\\bid=["']${id}["']`).test(html),
  );

  assert.ok(referencedIds.length > 20);
  assert.deepEqual(missing, []);
});
