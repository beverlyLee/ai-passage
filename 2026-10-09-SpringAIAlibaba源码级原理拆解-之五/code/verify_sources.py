#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""逐行号核对本篇引用的 Spring AI Alibaba 源码。

数据源：alibaba/spring-ai-alibaba，tag v1.1.2.2，提交 7405a7dc0d66d582ec79430af6e24d259d5ca6ea。
本地 clone 默认 /tmp/saa，可用环境变量 SAA_SRC 覆盖。

运行：python3 code/verify_sources.py
预期：末尾打印 self-test PASS，FAIL 数为 0。
"""

import os
import sys

SAA_SRC = os.environ.get("SAA_SRC", "/tmp/saa")

# (相对 /tmp/saa 根的路径, 行号, 该行应包含的片段)
EXPECTED = [
    # a2a / A2aRemoteAgent.java
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/a2a/A2aRemoteAgent.java", 34, "public class A2aRemoteAgent extends BaseAgent"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/a2a/A2aRemoteAgent.java", 60, "protected StateGraph initGraph()"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/a2a/A2aRemoteAgent.java", 80, 'throw new UnsupportedOperationException("A2aRemoteAgent has not support schedule.");'),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/a2a/A2aRemoteAgent.java", 141, "private boolean shareState = true;"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/a2a/A2aRemoteAgent.java", 174, "this.agentCard = new AgentCardWrapper(agentCard);"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/a2a/A2aRemoteAgent.java", 228, "this.streaming = agentCard.capabilities().streaming();"),
    # a2a / A2aNodeActionWithConfig.java
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/a2a/A2aNodeActionWithConfig.java", 60, "public class A2aNodeActionWithConfig implements NodeActionWithConfig"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/a2a/A2aNodeActionWithConfig.java", 81, "public A2aNodeActionWithConfig(AgentCardWrapper agentCard, String agentName, boolean includeContents, String outputKeyToParent, String instruction, boolean streaming) {"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/a2a/A2aNodeActionWithConfig.java", 88, "this.shareState = false;"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/a2a/A2aNodeActionWithConfig.java", 98, "public Map<String, Object> apply(OverAllState state, RunnableConfig config)"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/a2a/A2aNodeActionWithConfig.java", 116, "private RunnableConfig getSubGraphRunnableConfig(RunnableConfig config)"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/a2a/A2aNodeActionWithConfig.java", 129, "public String subGraphId() {"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/a2a/A2aNodeActionWithConfig.java", 644, "private String buildSendMessageRequest(OverAllState state, RunnableConfig config)"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/a2a/A2aNodeActionWithConfig.java", 671, 'root.put("method", "message/send");'),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/a2a/A2aNodeActionWithConfig.java", 687, "private String buildSendStreamingMessageRequest(OverAllState state, RunnableConfig config)"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/a2a/A2aNodeActionWithConfig.java", 714, 'root.put("method", "message/stream");'),
    # flow / FlowGraphBuilder.java
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/flow/builder/FlowGraphBuilder.java", 37, "public class FlowGraphBuilder {"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/flow/builder/FlowGraphBuilder.java", 46, "public static StateGraph buildGraph(String strategyType, FlowGraphConfig config) throws GraphStateException {"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/flow/builder/FlowGraphBuilder.java", 47, "FlowGraphBuildingStrategy strategy = FlowGraphBuildingStrategyRegistry.getInstance().createStrategy(strategyType);"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/flow/builder/FlowGraphBuilder.java", 55, "public static class FlowGraphConfig {"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/flow/builder/FlowGraphBuilder.java", 73, "private List<Hook> hooks;"),
    # flow / FlowGraphBuildingStrategyRegistry.java
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/flow/strategy/FlowGraphBuildingStrategyRegistry.java", 34, "public class FlowGraphBuildingStrategyRegistry {"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/flow/strategy/FlowGraphBuildingStrategyRegistry.java", 49, "public static FlowGraphBuildingStrategyRegistry getInstance() {"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/flow/strategy/FlowGraphBuildingStrategyRegistry.java", 110, 'throw new IllegalArgumentException("No strategy registered for type: " + type);'),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/flow/strategy/FlowGraphBuildingStrategyRegistry.java", 139, "public Set<String> getRegisteredTypes() {"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/flow/strategy/FlowGraphBuildingStrategyRegistry.java", 164, "registerStrategy(FlowAgentEnum.SEQUENTIAL.getType(), SequentialGraphBuildingStrategy::new);"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/flow/strategy/FlowGraphBuildingStrategyRegistry.java", 165, "registerStrategy(FlowAgentEnum.ROUTING.getType(), RoutingGraphBuildingStrategy::new);"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/flow/strategy/FlowGraphBuildingStrategyRegistry.java", 166, "registerStrategy(FlowAgentEnum.PARALLEL.getType(), ParallelGraphBuildingStrategy::new);"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/flow/strategy/FlowGraphBuildingStrategyRegistry.java", 167, "registerStrategy(FlowAgentEnum.CONDITIONAL.getType(), ConditionalGraphBuildingStrategy::new);"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/flow/strategy/FlowGraphBuildingStrategyRegistry.java", 168, "registerStrategy(FlowAgentEnum.LOOP.getType(), LoopGraphBuildingStrategy::new);"),
    # flow / FlowAgentEnum.java
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/flow/enums/FlowAgentEnum.java", 20, 'CONDITIONAL("CONDITIONAL"), SEQUENTIAL("SEQUENTIAL"), ROUTING("ROUTING"), PARALLEL("PARALLEL"), LOOP("LOOP"), SUPERVISOR("SUPERVISOR");'),
    # flow / AbstractFlowGraphBuildingStrategy.java
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/flow/strategy/AbstractFlowGraphBuildingStrategy.java", 53, "public abstract class AbstractFlowGraphBuildingStrategy implements FlowGraphBuildingStrategy {"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/flow/strategy/AbstractFlowGraphBuildingStrategy.java", 104, "public final StateGraph buildGraph(FlowGraphBuilder.FlowGraphConfig config) throws GraphStateException {"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/flow/strategy/AbstractFlowGraphBuildingStrategy.java", 169, "this.graph.addNode(getRootAgent().name(), node_async(new TransparentNode()));"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/flow/strategy/AbstractFlowGraphBuildingStrategy.java", 184, "protected void connectBeforeModelHooks() throws GraphStateException {"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/flow/strategy/AbstractFlowGraphBuildingStrategy.java", 202, "protected void connectAfterModelHooks() throws GraphStateException {"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/flow/strategy/AbstractFlowGraphBuildingStrategy.java", 219, "protected void connectBeforeAgentHooks() throws GraphStateException {"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/flow/strategy/AbstractFlowGraphBuildingStrategy.java", 239, "protected void connectAfterAgentHooks() throws GraphStateException {"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/flow/strategy/AbstractFlowGraphBuildingStrategy.java", 255, "protected static List<Hook> filterHooksByPosition(List<? extends Hook> hooks, HookPosition position) {"),
    # flow / LoopGraphBuildingStrategy.java
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/flow/strategy/LoopGraphBuildingStrategy.java", 47, "public class LoopGraphBuildingStrategy extends AbstractFlowGraphBuildingStrategy {"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/flow/strategy/LoopGraphBuildingStrategy.java", 50, "protected void buildCoreGraph(FlowGraphBuilder.FlowGraphConfig config) throws GraphStateException {"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/flow/strategy/LoopGraphBuildingStrategy.java", 52, "LoopStrategy loopStrategy = (LoopStrategy) config.getCustomProperty(LoopAgent.LOOP_STRATEGY);"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/flow/strategy/LoopGraphBuildingStrategy.java", 53, "Agent subAgent = config.getSubAgents().get(0);"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/flow/strategy/LoopGraphBuildingStrategy.java", 56, "this.graph.addNode(rootAgent.name(), node_async(new TransparentNode()));"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/flow/strategy/LoopGraphBuildingStrategy.java", 59, "this.graph.addNode(loopStrategy.loopInitNodeName(), node_async(loopStrategy::loopInit));"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/flow/strategy/LoopGraphBuildingStrategy.java", 62, "this.graph.addNode(loopStrategy.loopDispatchNodeName(), node_async(loopStrategy::loopDispatch));"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/flow/strategy/LoopGraphBuildingStrategy.java", 66, "this.graph.addNode(subAgent.name(), subAgent.getGraph());"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/flow/strategy/LoopGraphBuildingStrategy.java", 90, "this.graph.addConditionalEdges(loopStrategy.loopDispatchNodeName(), edge_async(state -> {"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/flow/strategy/LoopGraphBuildingStrategy.java", 102, "protected void connectBeforeAgentHooks() throws GraphStateException {"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/flow/strategy/LoopGraphBuildingStrategy.java", 113, "protected void connectBeforeModelHooks() throws GraphStateException {"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/flow/strategy/LoopGraphBuildingStrategy.java", 122, "protected void connectAfterModelHooks() throws GraphStateException {"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/flow/strategy/LoopGraphBuildingStrategy.java", 127, "public String getStrategyType() {"),
]


def verify():
    src_root = os.path.abspath(SAA_SRC)
    if not os.path.isdir(src_root):
        print("SAA_SRC 不存在：%s" % src_root)
        sys.exit(1)

    passed = 0
    failed = 0
    for rel, line_no, snippet in EXPECTED:
        fpath = os.path.join(src_root, rel)
        if not os.path.isfile(fpath):
            print("[FAIL] 文件缺失 %s" % rel)
            failed += 1
            continue
        with open(fpath, "r", encoding="utf-8", errors="replace") as f:
            lines = f.read().split("\n")
        if line_no < 1 or line_no > len(lines):
            print("[FAIL] 行号越界 %s:%d (文件共 %d 行)" % (rel, line_no, len(lines)))
            failed += 1
            continue
        actual = lines[line_no - 1]
        if snippet in actual:
            passed += 1
        else:
            print("[FAIL] %s:%d" % (rel, line_no))
            print("       期望包含: %s" % snippet)
            print("       实际行  : %s" % actual)
            failed += 1

    print("")
    print("核对 %d 条，通过 %d，失败 %d" % (len(EXPECTED), passed, failed))
    if failed == 0:
        print("self-test PASS")
        return 0
    print("self-test FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(verify())
