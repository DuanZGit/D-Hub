import { readFileSync, writeFileSync, existsSync } from "node:fs";

const REPO = {
  type: "git",
  url: "git+https://github.com/DuanZGit/D-Hub.git",
};
const RAW = "https://raw.githubusercontent.com/DuanZGit/D-Hub/master/docs/covers";
const bump = process.argv.includes("--bump");

/** 读现有 version；--bump 时 patch +1，否则沿用（缺省 1.0.0） */
function nextVersion(dir) {
  const path = `${dir}/package.json`;
  let current = "1.0.0";
  if (existsSync(path)) {
    try {
      current = JSON.parse(readFileSync(path, "utf8")).version ?? current;
    } catch {
      // 坏文件就当没写过
    }
  }
  if (!bump) return current;
  const m = /^(\d+)\.(\d+)\.(\d+)$/.exec(current);
  if (!m) return current;
  return `${m[1]}.${m[2]}.${Number(m[3]) + 1}`;
}

function image(slug) {
  return `${RAW}/${slug}.png`;
}

// name -> [description, dir, entry, extra]
const exts = {
  "auto-name": ["会话消息涨到阈值就自动重新生成标题，完成通知一眼看出是哪个会话", "extensions/auto-name", "./index.ts"],
  "d-live": ["把模型思考与工具调用实时改写成内心独白，推到 pi-web 界面顶部浮层", "extensions/d-live", "./index.ts"],
  "d-split": ["会话聊偏了按切点拆成两个独立会话，原会话不动", "extensions/d-split", "./index.ts", { typebox: true }],
  "goal-guard": ["用 /goal 把本次目标钉进系统提示，防止聊着聊着跑题", "extensions/goal-guard", "./index.ts"],
  "pi-cmd-guard": ["拦住会毁东西的命令：cat .env、裸 env、systemctl restart pi-web", "extensions/pi-cmd-guard", "./index.ts"],
  "pi-web-patch-keeper": ["pi-web 升级会覆盖本地补丁，这个扩展在启动时把它们重新打上", "extensions/pi-web-patch-keeper", "./index.ts"],
  "skill-search": ["按需检索本机全部技能，返回该用哪个和 SKILL.md 路径", "extensions/skill-search", "./index.ts", { typebox: true }],
  "skill-trigger": ["按任务内容自动匹配技能，省掉手动挑的一步", "extensions/skill-trigger", "./index.ts"],
  "sol-pi-stats": ["状态栏常驻 token / 上下文用量，另有 /sol 明细", "extensions/sol-pi-stats", "./index.ts"],
};

let n = 0;
for (const [name, [desc, dir, entry, extra]] of Object.entries(exts)) {
  const pkg = {
    name: `@duanz/pi-${name}`,
    version: nextVersion(dir),
    description: desc,
    type: "module",
    keywords: ["pi-package", "pi-extension", "pi-web"],
    license: "MIT",
    author: "DuanZ",
    homepage: `https://github.com/DuanZGit/D-Hub/tree/master/${dir}`,
    repository: { ...REPO, directory: dir },
    files: ["index.ts", "README.md", "README.en.md"],
    pi: { extensions: [entry], image: image(name) },
    engines: { node: ">=20" },
  };
  if (extra?.typebox) {
    pkg.peerDependencies = { "@earendil-works/pi-coding-agent": "*", typebox: "*" };
    pkg.peerDependenciesMeta = {
      "@earendil-works/pi-coding-agent": { optional: true },
      typebox: { optional: true },
    };
  }
  writeFileSync(`${dir}/package.json`, JSON.stringify(pkg, null, 2) + "\n");
  n++;
}

// d-restart：保留原有 files/scripts/peerDependencies，只同步 name / repository / version / pi.image
const drPath = "plugins/d-restart/package.json";
const dr = JSON.parse(readFileSync(drPath, "utf8"));
dr.name = "@duanz/pi-d-restart";
dr.version = nextVersion("plugins/d-restart");
dr.author = "DuanZ";
dr.homepage = "https://github.com/DuanZGit/D-Hub/tree/master/plugins/d-restart";
dr.repository = { ...REPO, directory: "plugins/d-restart" };
dr.pi = { ...(dr.pi ?? {}), image: image("d-restart") };
dr.files = ["extensions", "scripts", "README.md", "README.en.md", "LICENSE"];
writeFileSync(drPath, JSON.stringify(dr, null, 2) + "\n");
n++;

// skills 不打包：自建技能只在 GitHub 仓库里做备份，不发 npm

console.log(`wrote ${n} package.json files${bump ? " (bumped patch)" : ""}`);
