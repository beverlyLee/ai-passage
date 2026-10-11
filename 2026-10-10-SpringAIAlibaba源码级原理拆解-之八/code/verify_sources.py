#!/usr/bin/env python3
"""verify_sources.py — 之八（shell 沙箱）源码行号一手核对。

读取环境变量 SAA_SRC（默认 /tmp/saa），逐条核对 (相对路径, 行号, 期望片段)。
任一不匹配则打印差异并 exit(1)；全绿打印 PASS 与条数。

用法：
    SAA_SRC=/tmp/saa python3 code/verify_sources.py
"""
import os
import sys

SAA = os.environ.get("SAA_SRC", "/tmp/saa")

TOOLS = "spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/tools"
HOOK = "spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook"
EXT = "spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/extension"

# (相对源码根的路径, 行号, 期望该行包含的片段)
CHECKS = [
    # ---- ShellTool2.java（@Tool 入口与默认上限）----
    (f"{TOOLS}/ShellTool2.java", 76, '@Tool(name = "shell"'),
    (f"{TOOLS}/ShellTool2.java", 100, "sessionManager.executeCommand(command, config)"),
    (f"{TOOLS}/ShellTool2.java", 158, "private long commandTimeout = 60000"),
    (f"{TOOLS}/ShellTool2.java", 160, "private int maxOutputLines = 1000"),

    # ---- ShellSessionManager.java（会话隔离 / 输出治理 / 脱敏 / 超时 / 截断）----
    (f"{TOOLS}/ShellSessionManager.java", 34, "public class ShellSessionManager"),
    (f"{TOOLS}/ShellSessionManager.java", 56, "this.useTemporaryWorkspace = builder.workspaceRoot == null"),
    (f"{TOOLS}/ShellSessionManager.java", 80, 'Files.createTempDirectory("shell_tool_")'),
    (f"{TOOLS}/ShellSessionManager.java", 149, "public CommandResult executeCommand(String command, RunnableConfig config)"),
    (f"{TOOLS}/ShellSessionManager.java", 152, "Shell session not initialized. Call initialize() first"),
    (f"{TOOLS}/ShellSessionManager.java", 156, "CommandResult result = session.execute(command, commandTimeout, maxOutputLines, maxOutputBytes)"),
    (f"{TOOLS}/ShellSessionManager.java", 162, "for (RedactionRule rule : redactionRules) {"),
    (f"{TOOLS}/ShellSessionManager.java", 220, "private class ShellSession"),
    (f"{TOOLS}/ShellSessionManager.java", 323, "String marker = DONE_MARKER_PREFIX + UUID.randomUUID().toString().replace"),
    (f"{TOOLS}/ShellSessionManager.java", 357, "private CommandResult collectOutput(String marker, long deadline, int maxOutputLines, Long maxOutputBytes)"),
    (f"{TOOLS}/ShellSessionManager.java", 367, "long remaining = deadline - System.currentTimeMillis()"),
    (f"{TOOLS}/ShellSessionManager.java", 368, "if (remaining <= 0) {"),
    (f"{TOOLS}/ShellSessionManager.java", 369, "timedOut = true"),
    (f"{TOOLS}/ShellSessionManager.java", 370, 'log.warn("Command timed out, restarting session")'),
    (f"{TOOLS}/ShellSessionManager.java", 371, "restart()"),
    (f"{TOOLS}/ShellSessionManager.java", 413, "if (totalLines <= maxOutputLines) {"),
    (f"{TOOLS}/ShellSessionManager.java", 417, "truncatedByBytes = true"),
    (f"{TOOLS}/ShellSessionManager.java", 420, "truncatedByLines = true"),
    (f"{TOOLS}/ShellSessionManager.java", 514, "public interface RedactionRule"),
    (f"{TOOLS}/ShellSessionManager.java", 529, "class PatternRedactionRule implements RedactionRule"),
    (f"{TOOLS}/ShellSessionManager.java", 563, "private long commandTimeout = 30000"),
    (f"{TOOLS}/ShellSessionManager.java", 564, "private long startupTimeout = 10000"),
    (f"{TOOLS}/ShellSessionManager.java", 565, "private long terminationTimeout = 5000"),
    (f"{TOOLS}/ShellSessionManager.java", 566, "private int maxOutputLines = 1000"),
    (f"{TOOLS}/ShellSessionManager.java", 570, "redactionRules = new ArrayList<>()"),

    # ---- ShellToolAgentHook.java（生命周期钩子）----
    (f"{HOOK}/shelltool/ShellToolAgentHook.java", 45, "@HookPositions({HookPosition.BEFORE_AGENT, HookPosition.AFTER_AGENT})"),
    (f"{HOOK}/shelltool/ShellToolAgentHook.java", 88, "sessionManager.initialize(config)"),
    (f"{HOOK}/shelltool/ShellToolAgentHook.java", 109, "sessionManager.cleanup(config)"),

    # ---- LocalFilesystemBackend.java（文件隔离）----
    (f"{EXT}/file/LocalFilesystemBackend.java", 52, "MAX_LINE_LENGTH = 10000"),
    (f"{EXT}/file/LocalFilesystemBackend.java", 75, "public LocalFilesystemBackend(String rootDir)"),
    (f"{EXT}/file/LocalFilesystemBackend.java", 76, "this(rootDir, false, 10)"),
    (f"{EXT}/file/LocalFilesystemBackend.java", 90, 'vpath.contains("..") || vpath.startsWith("~")'),
    (f"{EXT}/file/LocalFilesystemBackend.java", 94, "if (!full.startsWith(cwd)) {"),
    (f"{EXT}/file/LocalFilesystemBackend.java", 124, "LinkOption.NOFOLLOW_LINKS"),
    (f"{EXT}/file/LocalFilesystemBackend.java", 217, "NOFOLLOW_LINKS"),

    # ---- PIIDetectionHook.java（PII 钩子默认只管输入）----
    (f"{HOOK}/pii/PIIDetectionHook.java", 49, "@HookPositions({HookPosition.BEFORE_MODEL, HookPosition.AFTER_MODEL})"),
    (f"{HOOK}/pii/PIIDetectionHook.java", 294, "private PIIDetector getDefaultDetector(PIIType type)"),
    (f"{HOOK}/pii/PIIDetectionHook.java", 337, "applyToInput = true"),
    (f"{HOOK}/pii/PIIDetectionHook.java", 338, "applyToOutput = false"),
    (f"{HOOK}/pii/PIIDetectionHook.java", 339, "applyToToolResults = false"),

    # ---- ReturnDirectModelHook.java（return_direct 优先跳 END）----
    (f"{HOOK}/returndirect/ReturnDirectModelHook.java", 42, "@HookPositions({HookPosition.BEFORE_MODEL})"),
    (f"{HOOK}/returndirect/ReturnDirectModelHook.java", 51, "public int getOrder()"),
    (f"{HOOK}/returndirect/ReturnDirectModelHook.java", 52, "HIGHEST_PRECEDENCE"),
    (f"{HOOK}/returndirect/ReturnDirectModelHook.java", 56, "public List<JumpTo> canJumpTo()"),
    (f"{HOOK}/returndirect/ReturnDirectModelHook.java", 77, "if (metadata.containsKey(FINISH_REASON_METADATA_KEY)) {"),

    # ---- ModelCallLimitHook.java（模型调用限额）----
    (f"{HOOK}/modelcalllimit/ModelCallLimitHook.java", 40, "@HookPositions({HookPosition.BEFORE_MODEL, HookPosition.AFTER_MODEL})"),
    (f"{HOOK}/modelcalllimit/ModelCallLimitHook.java", 74, "throw new ModelCallLimitExceededException("),

    # ---- ToolCallLimitHook.java（工具调用限额）----
    (f"{HOOK}/toolcalllimit/ToolCallLimitHook.java", 39, "@HookPositions({HookPosition.BEFORE_MODEL, HookPosition.AFTER_MODEL})"),
    (f"{HOOK}/toolcalllimit/ToolCallLimitHook.java", 61, "private String getThreadCountKey()"),
    (f"{HOOK}/toolcalllimit/ToolCallLimitHook.java", 66, "private String getRunCountKey()"),
]


def load_lines(rel_path):
    full = os.path.join(SAA, rel_path)
    if not os.path.exists(full):
        raise FileNotFoundError(full)
    with open(full, "r", encoding="utf-8", errors="replace") as f:
        return f.read().splitlines()


def main():
    if not os.path.isdir(SAA):
        print(f"[FAIL] SAA_SRC 目录不存在: {SAA}")
        sys.exit(1)
    cache = {}
    failed = 0
    for rel, lineno, snippet in CHECKS:
        if rel not in cache:
            cache[rel] = load_lines(rel)
        lines = cache[rel]
        if lineno < 1 or lineno > len(lines):
            print(f"[FAIL] {rel}:{lineno} 越界（文件共 {len(lines)} 行）")
            failed += 1
            continue
        actual = lines[lineno - 1]
        if snippet not in actual:
            print(f"[FAIL] {rel}:{lineno}")
            print(f"  期望包含: {snippet!r}")
            print(f"  实际行  : {actual!r}")
            failed += 1
    if failed:
        print(f"\n[RESULT] {failed} 条不匹配，共检查 {len(CHECKS)} 条")
        sys.exit(1)
    print(f"[PASS] 之八源码行号全部核对通过，共 {len(CHECKS)} 条（基准 7405a7d / v1.1.2.2）")
    sys.exit(0)


if __name__ == "__main__":
    main()
