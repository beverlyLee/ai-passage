#!/usr/bin/env python3
"""verify_sources.py — 之九（Agent 运行时与多轮记忆）源码行号一手核对。

读取环境变量 SAA_SRC（默认 /tmp/saa），逐条核对 (相对路径, 行号, 期望片段)。
任一不匹配则打印差异并 exit(1)；全绿打印 PASS 与条数。

用法：
    SAA_SRC=/tmp/saa python3 code/verify_sources.py
"""
import os
import sys

SAA = os.environ.get("SAA_SRC", "/tmp/saa")

AGENT = "spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent"
NODE = f"{AGENT}/node"


# (相对源码根的路径, 行号, 期望该行包含的片段)
CHECKS = [
    # ---- Agent.java（运行时入口：graph 编译 + 流式 + 状态交还）----
    (f"{AGENT}/Agent.java", 25, "import com.alibaba.cloud.ai.graph.CompiledGraph"),
    (f"{AGENT}/Agent.java", 27, "import com.alibaba.cloud.ai.graph.OverAllState"),
    (f"{AGENT}/Agent.java", 29, "import com.alibaba.cloud.ai.graph.StateGraph"),
    (f"{AGENT}/Agent.java", 36, "import com.alibaba.cloud.ai.graph.streaming.OutputType"),
    (f"{AGENT}/Agent.java", 104, "public StateGraph getGraph()"),
    (f"{AGENT}/Agent.java", 116, "public synchronized CompiledGraph getAndCompileGraph()"),
    (f"{AGENT}/Agent.java", 124, "this.compiledGraph = graph.compile()"),
    (f"{AGENT}/Agent.java", 157, "public StateSnapshot getCurrentState(RunnableConfig config)"),
    (f"{AGENT}/Agent.java", 163, "public Optional<OverAllState> invoke(String message)"),
    (f"{AGENT}/Agent.java", 404, "public Flux<Message> streamMessages(Map<String, Object> inputs)"),
    (f"{AGENT}/Agent.java", 405, "return stream(inputs).transform(this::extractMessages)"),
    (f"{AGENT}/Agent.java", 430, "public Flux<NodeOutput> stream(String message)"),
    (f"{AGENT}/Agent.java", 497, "protected Optional<OverAllState> doInvoke(Map<String, Object> input, RunnableConfig runnableConfig)"),
    (f"{AGENT}/Agent.java", 507, "protected Flux<NodeOutput> doStream(Map<String, Object> input, RunnableConfig runnableConfig)"),
    (f"{AGENT}/Agent.java", 587, "private Flux<Message> extractMessages(Flux<NodeOutput> stream)"),

    # ---- ReactAgent.java（ReAct 运行时：钩子链 + 工具路由 + 状态序列化）----
    (f"{AGENT}/ReactAgent.java", 96, "public class ReactAgent extends BaseAgent"),
    (f"{AGENT}/ReactAgent.java", 117, "public ReactAgent(AgentLlmNode llmNode, AgentToolNode toolNode, CompileConfig compileConfig, Builder builder)"),
    (f"{AGENT}/ReactAgent.java", 136, "this.stateSerializer = Objects.requireNonNullElseGet(builder.stateSerializer, () -> new SpringAIJacksonStateSerializer(OverAllState::new))"),
    (f"{AGENT}/ReactAgent.java", 157, "public static Builder builder()"),
    (f"{AGENT}/ReactAgent.java", 165, "public AssistantMessage call(String message) throws GraphRunnerException"),
    (f"{AGENT}/ReactAgent.java", 260, "private AssistantMessage doMessageInvoke(Object message, RunnableConfig config)"),
    (f"{AGENT}/ReactAgent.java", 269, "private AssistantMessage extractAssistantMessage(Optional<OverAllState> state)"),
    (f"{AGENT}/ReactAgent.java", 287, "public StateGraph getStateGraph()"),
    (f"{AGENT}/ReactAgent.java", 345, "for (Hook hook : beforeAgentHooks)"),
    (f"{AGENT}/ReactAgent.java", 354, "for (Hook hook : afterAgentHooks)"),
    (f"{AGENT}/ReactAgent.java", 363, "for (Hook hook : beforeModelHooks)"),
    (f"{AGENT}/ReactAgent.java", 376, "for (Hook hook : afterModelHooks)"),
    (f"{AGENT}/ReactAgent.java", 390, "String loopEntryNode = determineLoopEntryNode(beforeModelHooks)"),
    (f"{AGENT}/ReactAgent.java", 391, "String loopExitNode = determineLoopExitNode(afterModelHooks)"),
    (f"{AGENT}/ReactAgent.java", 580, "setupToolRouting(graph, loopExitNode, loopEntryNode, exitNode, agentInstance)"),

    # ---- DefaultBuilder.java（装配：可观测注册表 + ChatClient 构建 + 节点装配）----
    (f"{AGENT}/DefaultBuilder.java", 24, "import io.micrometer.observation.ObservationRegistry"),
    (f"{AGENT}/DefaultBuilder.java", 48, "public class DefaultBuilder extends Builder"),
    (f"{AGENT}/DefaultBuilder.java", 56, "public ReactAgent build()"),
    (f"{AGENT}/DefaultBuilder.java", 76, "this.observationRegistry == null ? ObservationRegistry.NOOP : this.observationRegistry"),
    (f"{AGENT}/DefaultBuilder.java", 81, "chatClient = clientBuilder.build()"),
    (f"{AGENT}/DefaultBuilder.java", 83, "chatClient = chatClient.mutate().defaultOptions(effectiveOptions).build()"),
    (f"{AGENT}/DefaultBuilder.java", 132, "AgentLlmNode llmNode = llmNodeBuilder.build()"),
    (f"{AGENT}/DefaultBuilder.java", 165, "toolNode = toolBuilder.build()"),

    # ---- AgentLlmNode.java（模型节点：流式产出 + 写回 messages）----
    (f"{NODE}/AgentLlmNode.java", 64, "public class AgentLlmNode implements NodeActionWithConfig"),
    (f"{NODE}/AgentLlmNode.java", 135, "public Map<String, Object> apply(OverAllState state, RunnableConfig config) throws Exception"),
    (f"{NODE}/AgentLlmNode.java", 161, "messages = (List<Message>) state.value(\"messages\").get()"),
    (f"{NODE}/AgentLlmNode.java", 213, "Flux<ChatResponse> chatResponseFlux = buildChatClientRequestSpec(request, config).stream().chatResponse()"),
    (f"{NODE}/AgentLlmNode.java", 242, "return Map.of(StringUtils.hasLength(this.outputKey) ? this.outputKey : \"messages\", modelResponse.getMessage())"),
    (f"{NODE}/AgentLlmNode.java", 285, "updatedState.put(\"messages\", modelResponse.getMessage())"),

    # ---- AgentToolNode.java（工具节点：结果回流 + 并行执行 + 部分结果续跑 + 状态快照）----
    (f"{NODE}/AgentToolNode.java", 98, "public class AgentToolNode implements NodeActionWithConfig"),
    (f"{NODE}/AgentToolNode.java", 154, "public Map<String, Object> apply(OverAllState state, RunnableConfig config) throws Exception"),
    (f"{NODE}/AgentToolNode.java", 155, "List<Message> messages = (List<Message>) state.value(\"messages\").orElseThrow()"),
    (f"{NODE}/AgentToolNode.java", 174, "else if (lastMessage instanceof ToolResponseMessage toolResponseMessage)"),
    (f"{NODE}/AgentToolNode.java", 218, "private Map<String, Object> executeToolCallsSequential(List<AssistantMessage.ToolCall> toolCalls"),
    (f"{NODE}/AgentToolNode.java", 250, "updatedState.put(\"messages\", toolResponseMessage)"),
    (f"{NODE}/AgentToolNode.java", 306, "OverAllState stateSnapshot = state.snapShot().orElse(state)"),
    (f"{NODE}/AgentToolNode.java", 410, "private Map<String, Object> handlePartialToolResponses(ToolResponseMessage toolResponseMessage"),
    (f"{NODE}/AgentToolNode.java", 474, "updatedState.put(\"messages\", newMessages)"),
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
    print(f"[PASS] 之九源码行号全部核对通过，共 {len(CHECKS)} 条（基准 7405a7d / v1.1.2.2）")
    sys.exit(0)


if __name__ == "__main__":
    main()
