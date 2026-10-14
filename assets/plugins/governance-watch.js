/**
 * governance-watch.js — 治理可发现性：会话级半硬约束（opencode 宿主）
 *
 * 解决的问题：pre-commit 钩子只在提交时触发；「编辑治理目录后不提交就走人」
 * 会完全绕过钩子，且编辑期的确认偏误无人兜底。本插件在会话边界检测治理路径的
 * 未提交变更（脏区），在入口文件（AGENTS.md，框架保证常驻 Agent 上下文）写入
 * 一条强制可见的提醒行；干净时自动摘除。
 *
 * 定性：半硬约束——脏区是机械事实（提醒 fail-closed），如何处置是判断
 * （fail-open 不中断任务）。轻量边界：纯 git status + 标记行维护，
 * 不引入 embedding/LLM/常驻服务（知识库级质量治理见 init-kb-harness）。
 *
 * 安装：本文件复制到 ~/.config/opencode/plugins/（opencode 自动加载），
 *       按项目修改下方三个常量，然后按 SKILL 第 6.4 步实测双向。
 * 其他宿主：Claude Code 用 settings.json 的 SessionStart hook 回显同样提醒
 * （stdout 注入上下文）；无扩展点的宿主保持软约束，不伪造覆盖。
 *
 * 来源：WORKFLOW 治理实战下放（本机实测：脏→写入、净→摘除、中文路径防转义）。
 */

import { execFile } from "child_process";
import path from "path";
import fs from "fs";

// ── 按项目修改这三个常量 ─────────────────────────────────────
/** 受治理的 git 仓库根 */
const GOV_REPO = path.join(process.env.USERPROFILE || process.env.HOME || "", "WORKFLOW");
/** 仓库内受治理的路径（git pathspec） */
const GOV_PATHS = ["oa-ecology-cube", "githooks"];
/** 宿主保证常驻 Agent 上下文的入口文件（提醒行的载体） */
const ENTRY_FILE = path.join(process.env.USERPROFILE || process.env.HOME || "", "AGENTS.md");
// ─────────────────────────────────────────────────────────────

const MARKER_PREFIX = "> ⚠ GOV-DIRTY:";
const MARKER_NOTE =
  "本行由 governance-watch 插件自动维护（纯派生信息），禁止手改。";

let ran = false;

function runWatch() {
  if (ran) return;
  ran = true;
  try {
    if (!fs.existsSync(path.join(GOV_REPO, ".git"))) return;
    execFile(
      "git",
      [
        "-C", GOV_REPO,
        "-c", "core.quotepath=false", // 非 ASCII 路径保持字面输出（人工核对 status 友好）
        "status", "--porcelain", "--",
        ...GOV_PATHS,
      ],
      { windowsHide: true, timeout: 15000 },
      (err, stdout) => {
        if (err) return; // git 不可用时静默放弃，不影响会话
        const dirty = stdout.split("\n").filter((l) => l.trim()).length;
        updateMarker(dirty);
      }
    );
  } catch {
    // 静默: 不影响会话
  }
}

function updateMarker(dirtyCount) {
  try {
    if (!fs.existsSync(ENTRY_FILE)) return;
    const text = fs.readFileSync(ENTRY_FILE, "utf8");
    const cleaned = text
      .split("\n")
      .filter((l) => !l.startsWith(MARKER_PREFIX))
      .join("\n");
    if (!dirtyCount) {
      if (cleaned !== text) fs.writeFileSync(ENTRY_FILE, cleaned, "utf8");
      return;
    }
    const paths = GOV_PATHS.join(" / ");
    const line =
      `${MARKER_PREFIX} ${paths} 存在未提交变更（${dirtyCount} 处）——若本次任务涉及该目录：` +
      `先读其维护规范/治理文档；完成变更须 git 提交收尾（提交触发机械审计）。${MARKER_NOTE}`;
    let out = cleaned;
    const anchor = "<!-- workflow-index:auto:end -->"; // 有索引表的项目插在表后；否则追加文末
    const ai = out.indexOf(anchor);
    const eol = ai >= 0 ? out.indexOf("\n", ai) : -1;
    if (ai >= 0 && eol >= 0) {
      out = out.slice(0, eol + 1) + line + "\n" + out.slice(eol + 1);
    } else {
      out = out.replace(/\n*$/, "\n\n" + line + "\n");
    }
    if (out !== text) fs.writeFileSync(ENTRY_FILE, out, "utf8");
  } catch {
    // 静默: 标记失败不影响会话
  }
}

export default {
  id: "governance-watch",
  setup: async (ctx) => {
    runWatch();
    try {
      const events = ctx.event.subscribe();
      ;(async () => {
        for await (const event of events) {
          const t = event && event.type;
          if (
            t === "session.execution.started" ||
            t === "session.created" ||
            t === "session.started"
          ) {
            ran = false; // 会话边界重跑：中途产生的脏区在下一会话可见
            runWatch();
          }
        }
      })().catch(() => {}); // 事件流结束或异常时静默; 不影响会话
    } catch {
      // 静默: 事件总线不可用时不影响会话
    }
  },
};
