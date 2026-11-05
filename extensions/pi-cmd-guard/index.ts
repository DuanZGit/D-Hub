/**
 * pi-cmd-guard — 命令级硬拦截
 *
 * 目的：把「会打印明文密钥的命令」变成发不出去，而不是执行完再遮蔽。
 * 触发点：tool_call（bash），返回 { block: true } 后命令根本不执行。
 *
 * 覆盖场景：2026-11-05 事故（sudo systemctl cat caddy 把 Environment=ALI_ACCESS_KEY_SECRET 打进上下文）。
 *
 * 逃生门：PI_CMD_GUARD=off 关闭；或用户自己敲 `!` 命令（user_bash 不经过这里）。
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

type Rule = {
  name: string;
  re: RegExp;
  why: string;
  alt: string;
};

export const RULES: Rule[] = [
  {
    name: "直接重启 pi-web",
    re: /\bsystemctl\s+(?:--user\s+)?(?:restart|stop|kill)\s+[^|;&\n]*\bpi-web\b/,
    why: "会直接掐断其他正在跑的会话（in-flight 轮次全部丢失）",
    alt: "用 d_restart 工具，或终端跑 d-restart（旧名 safe_restart / piweb-safe-restart）；自动快照忙碌会话并在就绪后唤醒接力",
  },
  {
    name: "systemctl cat",
    re: /\bsystemctl\s+cat\b/,
    why: "会把 unit 里的 Environment= 整行打出来，里面常有明文密钥",
    alt: "systemctl show <unit> -p EnvironmentFiles,ExecStart,WorkingDirectory,User",
  },
  {
    name: "systemctl show Environment",
    re: /\bsystemctl\s+show\b[^|;&\n]*(?:-p|--property)[= ]*[^|;&\n]*\bEnvironment\b(?!Files)/,
    why: "直接 dump 环境变量的值",
    alt: "systemctl show <unit> -p EnvironmentFiles（只给文件路径）",
  },
  {
    name: "裸 env / printenv",
    re: /(?:^|[;&|(]\s*|\bsudo\s+)(?:env|printenv)\s*(?:$|[;&|)])/,
    why: "会 dump 当前进程全部环境变量",
    alt: "printenv | cut -d= -f1（只看变量名）",
  },
  {
    name: "printenv 指定敏感变量",
    re: /\bprintenv\s+[A-Za-z0-9_]*(?:SECRET|TOKEN|KEY|PASSWORD|PASSWD|CREDENTIAL)/i,
    why: "直接打印该变量的明文值",
    alt: "safe_inspect action=env + unit 名（只出变量名）",
  },
  {
    name: "cat 密钥文件",
    re: /\bcat\s+[^|;&\n]*?(?:\.env(?:\.[a-z]+)?\b|secrets?\.json|credentials?|\.netrc|id_rsa\b|id_ed25519\b|\.pem\b|\.key\b)/,
    why: "文件内容就是明文密钥",
    alt: "safe_inspect action=secret + 路径（只出 存在/长度/sha8）",
  },
  {
    name: "读 /proc/*/environ",
    re: /\/proc\/[^/\s]+\/environ/,
    why: "进程环境块的原始字节，全是明文",
    alt: "tr '\\0' '\\n' < /proc/PID/environ | cut -d= -f1（只看变量名）",
  },
  {
    name: "grep 全环境",
    re: /\bgrep\b[^|;&\n]*\s(?:\/proc\/self\/environ|-z\s*\/proc)/,
    why: "在环境块里全文搜索会把命中的值一起打出来",
    alt: "先用 cut -d= -f1 只取变量名，再筛",
  },
];

/** 把引号内的内容抹成空格再匹配：避免「文档里提到某命令」被当成「要执行它」。
 *  代价：`bash -c "..."` 这类引号内真实执行的命令会漏拦，可接受。 */
export function stripQuoted(s: string): string {
  let out = "";
  let q: string | null = null;
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (q) {
      if (c === "\\" && q === '"') {
        out += "  ";
        i++;
        continue;
      }
      if (c === q) {
        q = null;
        out += c;
        continue;
      }
      out += " ";
      continue;
    }
    if (c === "'" || c === '"') {
      q = c;
      out += c;
      continue;
    }
    out += c;
  }
  return out;
}

/** 返回命中的规则；null = 放行。扩展与测试共用同一份判定。 */
export function checkCommand(cmd: string): Rule | null {
  const probe = stripQuoted(cmd);
  for (const rule of RULES) {
    if (!rule.re.test(probe)) continue;
    // 裸 env/printenv 管道给 cut/head/wc 之类加工时不拦（只出变量名或截断，不 dump 值）
    if (rule.name === "裸 env / printenv" && /\|\s*(?:cut|head|wc|sort|uniq|awk)\b/.test(probe)) continue;
    return rule;
  }
  return null;
}

export default function (pi: ExtensionAPI) {
  pi.on("tool_call", async (event) => {
    if (process.env.PI_CMD_GUARD === "off") return;
    if (event.toolName !== "bash") return;

    const cmd = String((event.input as any)?.command ?? "");
    if (!cmd) return;

    const rule = checkCommand(cmd);
    if (!rule) return;
    return {
      block: true,
      reason:
        `[cmd-guard] 已拦下「${rule.name}」：${rule.why}。\n` +
        `改用：${rule.alt}\n` +
        `（这条拦截不依赖模型是否记得规则，命令根本没执行。确需放行时让用户自己敲 ! 命令。）`,
    };
  });
}
