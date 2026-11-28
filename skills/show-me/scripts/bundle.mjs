#!/usr/bin/env node
/**
 * bundle.mjs — 把模板里的外链 Three.js 内联回单文件
 *
 * 模板在 templates/ 下用 <script src="assets/three.min.js"></script> 保持可读（20–38KB），
 * 产出页面必须单文件自包含，所以交付前跑一次本脚本把它内联成 603KB 的 <script>…</script>。
 *
 * 用法：
 *   node scripts/bundle.mjs <输入.html> [输出.html]
 *   node scripts/bundle.mjs explain/my-page.html            # 原地内联
 *   node scripts/bundle.mjs templates/skeleton-tech.html /tmp/out.html
 *
 * 幂等：已经内联过的文件再跑一次不会变化。
 * 找不到外链、也找不到内联库时退出码 2，并说明缺什么。
 */
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { dirname, resolve, join, relative, isAbsolute } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const SKILL_ROOT = resolve(HERE, "..");
const DEFAULT_LIB = join(SKILL_ROOT, "templates", "assets", "three.min.js");

const LINK_RE = /<script\s+src=["']([^"']*assets\/three\.min\.js)["']\s*><\/script>/;
const INLINED_RE = /<script>\/\*\*\n \* @license\n \* Copyright 2010-2021 Three\.js Authors/;

function die(msg, code = 1) {
  console.error(`bundle: ${msg}`);
  process.exit(code);
}

const [input, output] = process.argv.slice(2);
if (!input) die("用法: node scripts/bundle.mjs <输入.html> [输出.html]");
if (!existsSync(input)) die(`找不到输入文件: ${input}`);

const html = readFileSync(input, "utf8");
const outPath = output || input;

if (INLINED_RE.test(html)) {
  console.log(`bundle: ${input} 已经内联过，跳过`);
  process.exit(0);
}

const m = html.match(LINK_RE);
if (!m) {
  die(`${input} 里没有 <script src="...assets/three.min.js">，也不是已内联版本。`, 2);
}

// 外链路径优先按 HTML 所在目录解析；找不到就用技能自带的库
let libPath = resolve(dirname(input), m[1]);
if (!existsSync(libPath)) libPath = DEFAULT_LIB;
if (!existsSync(libPath)) die(`找不到 Three.js 库: ${m[1]}（也没找到 ${DEFAULT_LIB}）`);

const lib = readFileSync(libPath, "utf8").replace(/\s+$/, "");
const bundled = html.replace(LINK_RE, () => `<script>${lib}</script>`);

writeFileSync(outPath, bundled, "utf8");
const show = (f) => { const r = relative(process.cwd(), f); return r.startsWith("..") ? f : r; };
const before = Buffer.byteLength(html);
const after = Buffer.byteLength(bundled);
console.log(
  `bundle: ${show(input)} → ${show(outPath)}  ` +
  `${(before / 1024).toFixed(0)}KB → ${(after / 1024).toFixed(0)}KB（已内联，单文件自包含）`
);
