#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对照 alibaba/spring-ai-alibaba 提交 7405a7d 复核本篇引用的源码行号。

用法：
    python3 verify_sources.py

本脚本不依赖任何第三方库。它读取 SAA 源码目录（默认 /tmp/saa，
可用环境变量 SAA_SRC 覆盖），逐条检查本篇 README.md 引用的
(文件, 行号, 关键片段) 是否对得上。任一条对不上就报 FAIL 并退出码 1。
"""
import os
import sys

SAA_SRC = os.environ.get(
    "SAA_SRC", "/tmp/saa"
)

# (相对仓库根的路径, 行号, 该行应包含的关键片段)
EXPECTED = [
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/ReactAgent.java", 96, "public class ReactAgent extends BaseAgent"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/ReactAgent.java", 101, "private final AgentLlmNode llmNode;"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/ReactAgent.java", 103, "private final AgentToolNode toolNode;"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/ReactAgent.java", 117, "public ReactAgent(AgentLlmNode llmNode, AgentToolNode toolNode, CompileConfig compileConfig, Builder builder)"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/ReactAgent.java", 154, "hasTools = toolNode.getToolCallbacks() != null && !toolNode.getToolCallbacks().isEmpty();"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/ReactAgent.java", 328, "StateGraph graph = new StateGraph(name, buildMessagesKeyStrategyFactory(effectiveHooks), stateSerializer);"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/ReactAgent.java", 330, "graph.addNode(AGENT_MODEL_NAME, node_async(this.llmNode));"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/ReactAgent.java", 332, "graph.addNode(AGENT_TOOL_NAME, node_async(this.toolNode));"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/ReactAgent.java", 389, "String entryNode = determineEntryNode(beforeAgentHooks, beforeModelHooks);"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/ReactAgent.java", 392, "String exitNode = determineExitNode(afterAgentHooks);"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/ReactAgent.java", 540, "private static String determineExitNode("),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/ReactAgent.java", 550, "private static void setupHookEdges("),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/ReactAgent.java", 666, "private static void addHookEdge("),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/ReactAgent.java", 676, "Object jumpToValue = state.value(\"jump_to\").orElse(null);"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/ReactAgent.java", 676, "state.value(\"jump_to\")"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/ReactAgent.java", 715, "graph.addConditionalEdges(loopExitNode, edge_async(agentInstance.makeModelToTools(loopEntryNode, exitNode)), Map.of(AGENT_TOOL_NAME, AGENT_TOOL_NAME, exitNode, exitNode, loopEntryNode, loopEntryNode));"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/ReactAgent.java", 718, "graph.addConditionalEdges(AGENT_TOOL_NAME, edge_async(agentInstance.makeToolsToModelEdge(loopEntryNode, exitNode)), Map.of(loopEntryNode, loopEntryNode, exitNode, exitNode));"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/ReactAgent.java", 721, "private static String resolveJump(JumpTo jumpTo, String modelDestination, String endDestination, String defaultDestination)"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/ReactAgent.java", 733, "private KeyStrategyFactory buildMessagesKeyStrategyFactory(List<? extends Hook> hooks)"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/ReactAgent.java", 755, "private EdgeAction makeModelToTools(String modelDestination, String endDestination)"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/ReactAgent.java", 759, "Object jumpToValue = state.value(\"jump_to\").orElse(null);"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/ReactAgent.java", 771, "case model -> modelDestination;"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/ReactAgent.java", 779, "List<Message> messages = (List<Message>) state.value(\"messages\").orElse(List.of());"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/ReactAgent.java", 789, "if (assistantMessage.hasToolCalls())"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/ReactAgent.java", 790, "return AGENT_TOOL_NAME;"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/ReactAgent.java", 828, "private EdgeAction makeToolsToModelEdge(String modelDestination, String endDestination)"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/ReactAgent.java", 831, "ToolResponseMessage toolResponseMessage = fetchLastToolResponseMessage(state);"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/ReactAgent.java", 836, "return false; // FIXME"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/ReactAgent.java", 846, "return modelDestination;"),

    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/node/AgentLlmNode.java", 64, "public class AgentLlmNode implements NodeActionWithConfig"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/node/AgentToolNode.java", 98, "public class AgentToolNode implements NodeActionWithConfig"),
]


def main():
    if not os.path.isdir(SAA_SRC):
        print(f"FAIL: 源码目录不存在 {SAA_SRC}")
        print("请先执行：")
        print("  git clone https://github.com/alibaba/spring-ai-alibaba /tmp/saa")
        print("  cd /tmp/saa && git checkout 7405a7d")
        sys.exit(1)

    passed = 0
    failed = 0
    for rel, line_no, snippet in EXPECTED:
        path = os.path.join(SAA_SRC, rel)
        if not os.path.isfile(path):
            print(f"FAIL  {rel}:{line_no}  文件不存在")
            failed += 1
            continue
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
        if line_no < 1 or line_no > len(lines):
            print(f"FAIL  {rel}:{line_no}  行号越界(共 {len(lines)} 行)")
            failed += 1
            continue
        content = lines[line_no - 1]
        if snippet in content:
            passed += 1
        else:
            print(f"FAIL  {rel}:{line_no}  期望包含 {snippet!r}")
            print(f"       实际: {content.rstrip()!r}")
            failed += 1

    print(f"\n复核结果：通过 {passed} / 共 {len(EXPECTED)}，失败 {failed}")
    if failed == 0:
        print("self-test PASS")
        sys.exit(0)
    else:
        print("self-test FAIL")
        sys.exit(1)


if __name__ == "__main__":
    main()
