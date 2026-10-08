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
    ("spring-ai-alibaba-graph-core/src/main/java/com/alibaba/cloud/ai/graph/StateGraph.java", 43, "public class StateGraph"),
    ("spring-ai-alibaba-graph-core/src/main/java/com/alibaba/cloud/ai/graph/StateGraph.java", 230, "public StateGraph addNode(String id, AsyncNodeAction action)"),
    ("spring-ai-alibaba-graph-core/src/main/java/com/alibaba/cloud/ai/graph/StateGraph.java", 242, "public StateGraph addNode(String id, AsyncNodeActionWithConfig actionWithConfig)"),
    ("spring-ai-alibaba-graph-core/src/main/java/com/alibaba/cloud/ai/graph/StateGraph.java", 255, "public StateGraph addNode(String id, Node node)"),
    ("spring-ai-alibaba-graph-core/src/main/java/com/alibaba/cloud/ai/graph/StateGraph.java", 279, "public StateGraph addNode(String id, AsyncCommandAction action, Map<String, String> mappings)"),
    ("spring-ai-alibaba-graph-core/src/main/java/com/alibaba/cloud/ai/graph/StateGraph.java", 295, "public StateGraph addNode(String id, AsyncMultiCommandAction action, Map<String, String> mappings)"),
    ("spring-ai-alibaba-graph-core/src/main/java/com/alibaba/cloud/ai/graph/StateGraph.java", 311, "public StateGraph addNode(String id, CompiledGraph subGraph)"),
    ("spring-ai-alibaba-graph-core/src/main/java/com/alibaba/cloud/ai/graph/StateGraph.java", 337, "public StateGraph addNode(String id, StateGraph subGraph)"),
    ("spring-ai-alibaba-graph-core/src/main/java/com/alibaba/cloud/ai/graph/StateGraph.java", 362, "public StateGraph addEdge(String sourceId, String targetId)"),
    ("spring-ai-alibaba-graph-core/src/main/java/com/alibaba/cloud/ai/graph/StateGraph.java", 382, "public StateGraph addEdge(List<String> sourceIds, String targetId)"),
    ("spring-ai-alibaba-graph-core/src/main/java/com/alibaba/cloud/ai/graph/StateGraph.java", 392, "public StateGraph addEdge(String sourceId, List<String> targetIds)"),
    ("spring-ai-alibaba-graph-core/src/main/java/com/alibaba/cloud/ai/graph/StateGraph.java", 411, "public StateGraph addConditionalEdges(String sourceId, AsyncCommandAction condition, Map<String, String> mappings)"),
    ("spring-ai-alibaba-graph-core/src/main/java/com/alibaba/cloud/ai/graph/StateGraph.java", 441, "public StateGraph addConditionalEdges(String sourceId, AsyncEdgeAction condition, Map<String, String> mappings)"),
    ("spring-ai-alibaba-graph-core/src/main/java/com/alibaba/cloud/ai/graph/StateGraph.java", 456, "public StateGraph addConditionalEdges(String sourceId, AsyncEdgeActionWithConfig asyncEdgeActionWithConfig, Map<String, String> mappings)"),
    ("spring-ai-alibaba-graph-core/src/main/java/com/alibaba/cloud/ai/graph/StateGraph.java", 517, "public CompiledGraph compile(CompileConfig config)"),
    ("spring-ai-alibaba-graph-core/src/main/java/com/alibaba/cloud/ai/graph/StateGraph.java", 531, "public CompiledGraph compile()"),

    ("spring-ai-alibaba-graph-core/src/main/java/com/alibaba/cloud/ai/graph/OverAllState.java", 77, "public final class OverAllState"),
    ("spring-ai-alibaba-graph-core/src/main/java/com/alibaba/cloud/ai/graph/OverAllState.java", 78, "MARK_FOR_REMOVAL = new Object()"),
    ("spring-ai-alibaba-graph-core/src/main/java/com/alibaba/cloud/ai/graph/OverAllState.java", 145, "registerKeyAndStrategy(OverAllState.DEFAULT_INPUT_KEY, new ReplaceStrategy())"),
    ("spring-ai-alibaba-graph-core/src/main/java/com/alibaba/cloud/ai/graph/OverAllState.java", 155, "registerKeyAndStrategy(OverAllState.DEFAULT_INPUT_KEY, new ReplaceStrategy())"),
    ("spring-ai-alibaba-graph-core/src/main/java/com/alibaba/cloud/ai/graph/OverAllState.java", 167, "registerKeyAndStrategy(OverAllState.DEFAULT_INPUT_KEY, new ReplaceStrategy())"),
    ("spring-ai-alibaba-graph-core/src/main/java/com/alibaba/cloud/ai/graph/OverAllState.java", 180, "registerKeyAndStrategy(OverAllState.DEFAULT_INPUT_KEY, new ReplaceStrategy())"),
    ("spring-ai-alibaba-graph-core/src/main/java/com/alibaba/cloud/ai/graph/OverAllState.java", 234, "public OverAllState registerKeyAndStrategy(String key, KeyStrategy strategy)"),
    ("spring-ai-alibaba-graph-core/src/main/java/com/alibaba/cloud/ai/graph/OverAllState.java", 263, "public Map<String, Object> updateState(Map<String, Object> partialState) {"),
    ("spring-ai-alibaba-graph-core/src/main/java/com/alibaba/cloud/ai/graph/OverAllState.java", 271, "if (partialState.get(key) == MARK_FOR_REMOVAL)"),

    ("spring-ai-alibaba-graph-core/src/main/java/com/alibaba/cloud/ai/graph/state/strategy/ReplaceStrategy.java", 20, "public class ReplaceStrategy"),
    ("spring-ai-alibaba-graph-core/src/main/java/com/alibaba/cloud/ai/graph/state/strategy/ReplaceStrategy.java", 23, "public Object apply(Object oldValue, Object newValue)"),
    ("spring-ai-alibaba-graph-core/src/main/java/com/alibaba/cloud/ai/graph/state/strategy/ReplaceStrategy.java", 24, "return newValue;"),

    ("spring-ai-alibaba-graph-core/src/main/java/com/alibaba/cloud/ai/graph/state/strategy/AppendStrategy.java", 31, "public class AppendStrategy"),
    ("spring-ai-alibaba-graph-core/src/main/java/com/alibaba/cloud/ai/graph/state/strategy/AppendStrategy.java", 43, "public Object apply(Object oldValue, Object newValue)"),
    ("spring-ai-alibaba-graph-core/src/main/java/com/alibaba/cloud/ai/graph/state/strategy/AppendStrategy.java", 44, "if (newValue == null)"),
    ("spring-ai-alibaba-graph-core/src/main/java/com/alibaba/cloud/ai/graph/state/strategy/AppendStrategy.java", 48, "newValue instanceof ReplaceAllWith"),
    ("spring-ai-alibaba-graph-core/src/main/java/com/alibaba/cloud/ai/graph/state/strategy/AppendStrategy.java", 58, "oldValueIsList && newValue instanceof AppenderChannel.RemoveIdentifier"),
    ("spring-ai-alibaba-graph-core/src/main/java/com/alibaba/cloud/ai/graph/state/strategy/AppendStrategy.java", 60, "removeFromList(result, (AppenderChannel.RemoveIdentifier) newValue);"),

    ("spring-ai-alibaba-graph-core/src/main/java/com/alibaba/cloud/ai/graph/CompiledGraph.java", 58, "public class CompiledGraph"),
    ("spring-ai-alibaba-graph-core/src/main/java/com/alibaba/cloud/ai/graph/CompiledGraph.java", 366, "private Command nextNodeId(EdgeValue route, Map<String, Object> state, String nodeId, RunnableConfig config)"),
    ("spring-ai-alibaba-graph-core/src/main/java/com/alibaba/cloud/ai/graph/CompiledGraph.java", 410, "private Command nextNodeId(String nodeId, Map<String, Object> state, RunnableConfig config)"),
    ("spring-ai-alibaba-graph-core/src/main/java/com/alibaba/cloud/ai/graph/CompiledGraph.java", 416, "var entryPoint = this.edges.get(START);"),
    ("spring-ai-alibaba-graph-core/src/main/java/com/alibaba/cloud/ai/graph/CompiledGraph.java", 491, "public AsyncNodeActionWithConfig getNodeAction(String nodeId)"),
    ("spring-ai-alibaba-graph-core/src/main/java/com/alibaba/cloud/ai/graph/CompiledGraph.java", 578, "public Flux<NodeOutput> streamFromInitialNode(OverAllState overAllState, RunnableConfig config)"),

    ("spring-ai-alibaba-graph-core/src/main/java/com/alibaba/cloud/ai/graph/GraphRunner.java", 30, "public class GraphRunner"),
    ("spring-ai-alibaba-graph-core/src/main/java/com/alibaba/cloud/ai/graph/GraphRunner.java", 53, "return mainGraphExecutor.execute(context, resultValue);"),
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
