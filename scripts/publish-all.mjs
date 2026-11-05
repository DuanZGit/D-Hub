#!/usr/bin/env node
// 发布 D-Hub 里每个子包到 npm。已存在同版本的自动跳过。
// 用法：npm run publish:all   （或在任意目录 node scripts/publish-all.mjs）
import { readdirSync, readFileSync, existsSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const REGISTRY = "https://registry.npmjs.org";

function collectDirs() {
  const dirs = [];
  const pushChildren = (base) => {
    const abs = join(ROOT, base);
    if (!existsSync(abs)) return;
    for (const name of readdirSync(abs)) {
      const dir = join(base, name);
      if (existsSync(join(ROOT, dir, "package.json"))) dirs.push(dir);
    }
  };
  pushChildren("extensions");
  pushChildren("plugins");
  // skills 不发 npm，只在仓库里备份
  return dirs;
}

function publishedVersion(name) {
  try {
    return execFileSync("npm", ["view", name, "version", "--registry", REGISTRY], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();
  } catch {
    return null;
  }
}

const only = process.argv.slice(2);
const targets = collectDirs().filter((d) => only.length === 0 || only.some((o) => d.includes(o)));

let ok = 0;
let skipped = 0;
const failed = [];

for (const dir of targets) {
  const pkg = JSON.parse(readFileSync(join(ROOT, dir, "package.json"), "utf8"));
  const current = publishedVersion(pkg.name);
  if (current === pkg.version) {
    console.log(`skip  ${pkg.name}@${pkg.version}（已是这个版本）`);
    skipped++;
    continue;
  }
  console.log(`publish ${pkg.name}@${pkg.version}  ${current ? `(npm 上现有 ${current})` : "(新包)"}`);
  try {
    execFileSync("npm", ["publish", "--access", "public", "--registry", REGISTRY], {
      cwd: join(ROOT, dir),
      stdio: "inherit",
    });
    ok++;
  } catch {
    failed.push(pkg.name);
  }
}

console.log(`\n完成：发布 ${ok} 个，跳过 ${skipped} 个${failed.length ? `，失败 ${failed.join(", ")}` : ""}`);
if (failed.length) process.exit(1);
