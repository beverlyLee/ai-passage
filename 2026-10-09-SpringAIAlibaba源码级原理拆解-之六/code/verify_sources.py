#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""源码行号对照脚本（之六：上下文工程与 HITL）。

逐条核对 (rel_path, line_no, snippet) 是否包含在对应源文件指定行中。
数据源：alibaba/spring-ai-alibaba，tag v1.1.2.2，提交 7405a7dc0d66d582ec79430af6e24d259d5ca6ea。
用法：python3 code/verify_sources.py
"""

import os
import sys

SAA_SRC = os.environ.get("SAA_SRC", "/tmp/saa")

EXPECTED = [
    # ---- HumanInTheLoopHook ----
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/hip/HumanInTheLoopHook.java", 47, "@HookPositions(HookPosition.AFTER_MODEL)"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/hip/HumanInTheLoopHook.java", 48, "public class HumanInTheLoopHook extends ModelHook implements AsyncNodeActionWithConfig, InterruptableAction"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/hip/HumanInTheLoopHook.java", 50, 'public static final String HITL_NODE_NAME = "HITL";'),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/hip/HumanInTheLoopHook.java", 51, "private Map<String, ToolConfig> approvalOn;"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/hip/HumanInTheLoopHook.java", 63, "return afterModel(state, config);"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/hip/HumanInTheLoopHook.java", 67, "public CompletableFuture<Map<String, Object>> afterModel(OverAllState state, RunnableConfig config)"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/hip/HumanInTheLoopHook.java", 68, "config.getMetadataAndRemove(RunnableConfig.HUMAN_FEEDBACK_METADATA_KEY"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/hip/HumanInTheLoopHook.java", 71, "if (interruptionMetadata == null) {"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/hip/HumanInTheLoopHook.java", 99, "if (result == FeedbackResult.APPROVED) {"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/hip/HumanInTheLoopHook.java", 102, "else if (result == FeedbackResult.EDITED) {"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/hip/HumanInTheLoopHook.java", 103, "toolFeedback.getArguments()"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/hip/HumanInTheLoopHook.java", 106, "else if (result == FeedbackResult.REJECTED) {"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/hip/HumanInTheLoopHook.java", 108, "has been rejected by human"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/hip/HumanInTheLoopHook.java", 113, "treat it as approved to continue"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/hip/HumanInTheLoopHook.java", 129, "newMessages.add(new RemoveByHash<>(assistantMessage));"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/hip/HumanInTheLoopHook.java", 137, 'updates.put("messages", newMessages);'),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/hip/HumanInTheLoopHook.java", 148, "public Optional<InterruptionMetadata> interrupt(String nodeId, OverAllState state, RunnableConfig config)"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/hip/HumanInTheLoopHook.java", 151, "if (lastMessage == null || !lastMessage.hasToolCalls()) {"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/hip/HumanInTheLoopHook.java", 161, "if (!validateFeedback((InterruptionMetadata) feedback.get(), lastMessage.getToolCalls())) {"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/hip/HumanInTheLoopHook.java", 190, "private Optional<InterruptionMetadata> buildInterruptionMetadata(OverAllState state, AssistantMessage lastMessage)"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/hip/HumanInTheLoopHook.java", 194, "if (approvalOn.containsKey(toolCall.name())) {"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/hip/HumanInTheLoopHook.java", 207, "builder.addToolsAutomaticallyApproved(toolCall);"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/hip/HumanInTheLoopHook.java", 226, "if (toolCallsNeedingApproval.isEmpty()) {"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/hip/HumanInTheLoopHook.java", 272, "public String getName() {"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/hip/HumanInTheLoopHook.java", 273, "return HITL_NODE_NAME;"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/hip/HumanInTheLoopHook.java", 284, "public Builder approvalOn(String toolName, ToolConfig toolConfig) {"),

    # ---- SummarizationHook ----
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/summarization/SummarizationHook.java", 58, "@HookPositions({HookPosition.BEFORE_MODEL})"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/summarization/SummarizationHook.java", 59, "public class SummarizationHook extends MessagesModelHook {"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/summarization/SummarizationHook.java", 63, "private static final String DEFAULT_SUMMARY_PROMPT ="),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/summarization/SummarizationHook.java", 75, 'private static final String SUMMARY_PREFIX = "## Previous conversation summary:";'),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/summarization/SummarizationHook.java", 76, "private static final int DEFAULT_MESSAGES_TO_KEEP = 20;"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/summarization/SummarizationHook.java", 77, "private static final int SEARCH_RANGE_FOR_TOOL_PAIRS = 5;"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/summarization/SummarizationHook.java", 78, "private static final boolean DEFAULT_KEEP_FIRST_USER_MESSAGE = true;"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/summarization/SummarizationHook.java", 103, "public AgentCommand beforeModel(List<Message> previousMessages, RunnableConfig config)"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/summarization/SummarizationHook.java", 104, "if (maxTokensBeforeSummary == null) {"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/summarization/SummarizationHook.java", 108, "int totalTokens = tokenCounter.countTokens(previousMessages);"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/summarization/SummarizationHook.java", 110, "if (totalTokens < maxTokensBeforeSummary) {"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/summarization/SummarizationHook.java", 117, "int cutoffIndex = findSafeCutoff(previousMessages);"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/summarization/SummarizationHook.java", 124, "UserMessage firstUserMessage = null;"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/summarization/SummarizationHook.java", 125, "if (keepFirstUserMessage) {"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/summarization/SummarizationHook.java", 142, "String summary = createSummary(toSummarize);"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/summarization/SummarizationHook.java", 144, "SystemMessage summaryMessage = new SystemMessage(summaryPrefix + \"\\n\" + summary);"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/summarization/SummarizationHook.java", 151, "List<Message> newMessages = new ArrayList<>();"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/summarization/SummarizationHook.java", 166, "return new AgentCommand(newMessages, UpdatePolicy.REPLACE);"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/summarization/SummarizationHook.java", 175, "private int findSafeCutoff(List<Message> messages) {"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/summarization/SummarizationHook.java", 183, "for (int i = targetCutoff; i >= 0; i--) {"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/summarization/SummarizationHook.java", 195, "private boolean isSafeCutoffPoint(List<Message> messages, int cutoffIndex) {"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/summarization/SummarizationHook.java", 240, "private boolean cutoffSeparatesToolPair("),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/summarization/SummarizationHook.java", 263, "private String createSummary(List<Message> messages) {"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/summarization/SummarizationHook.java", 278, "var response = model.call(summaryPromptObj);"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/summarization/SummarizationHook.java", 318, "private int messagesToKeep = DEFAULT_MESSAGES_TO_KEEP;"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/hook/summarization/SummarizationHook.java", 322, "private boolean keepFirstUserMessage = DEFAULT_KEEP_FIRST_USER_MESSAGE;"),

    # ---- SubAgentInterceptor ----
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/extension/interceptor/SubAgentInterceptor.java", 64, "public class SubAgentInterceptor extends ModelInterceptor {"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/extension/interceptor/SubAgentInterceptor.java", 68, "private static final String DEFAULT_SYSTEM_PROMPT ="),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/extension/interceptor/SubAgentInterceptor.java", 102, "private static final String TASK_TOOL_DESCRIPTION ="),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/extension/interceptor/SubAgentInterceptor.java", 214, "private final List<ToolCallback> tools;"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/extension/interceptor/SubAgentInterceptor.java", 216, "private final Map<String, ReactAgent> subAgents;"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/extension/interceptor/SubAgentInterceptor.java", 225, "if (includeGeneralPurpose && builder.defaultModel != null) {"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/extension/interceptor/SubAgentInterceptor.java", 231, 'this.subAgents.put("general-purpose", generalPurposeAgent);'),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/extension/interceptor/SubAgentInterceptor.java", 235, "ToolCallback taskTool = TaskTool.createTaskToolCallback("),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/extension/interceptor/SubAgentInterceptor.java", 240, "this.tools = Collections.singletonList(taskTool);"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/extension/interceptor/SubAgentInterceptor.java", 243, "private ReactAgent createGeneralPurposeAgent("),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/extension/interceptor/SubAgentInterceptor.java", 252, "saver(new MemorySaver());"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/extension/interceptor/SubAgentInterceptor.java", 265, "private String buildTaskToolDescription() {"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/extension/interceptor/SubAgentInterceptor.java", 293, "public List<ToolCallback> getTools() {"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/extension/interceptor/SubAgentInterceptor.java", 298, "public String getName() {"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/extension/interceptor/SubAgentInterceptor.java", 299, 'return "SubAgent";'),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/extension/interceptor/SubAgentInterceptor.java", 303, "public ModelResponse interceptModel(ModelRequest request, ModelCallHandler handler) {"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/extension/interceptor/SubAgentInterceptor.java", 310, 'request.getSystemMessage().getText() + "\\n\\n" + systemPrompt'),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/extension/interceptor/SubAgentInterceptor.java", 319, "return handler.call(enhancedRequest);"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/extension/interceptor/SubAgentInterceptor.java", 329, "private boolean includeGeneralPurpose = true;"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/extension/interceptor/SubAgentInterceptor.java", 394, "private ReactAgent createSubAgentFromSpec(SubAgentSpec spec) {"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/extension/interceptor/SubAgentInterceptor.java", 399, "saver(new MemorySaver());"),
]


def load_lines(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.readlines()


def main():
    cache = {}
    passed = 0
    failed = 0
    for rel_path, line_no, snippet in EXPECTED:
        full = os.path.join(SAA_SRC, rel_path)
        if full not in cache:
            if not os.path.exists(full):
                print("FAIL  missing file: %s" % rel_path)
                failed += 1
                continue
            cache[full] = load_lines(full)
        lines = cache[full]
        if line_no < 1 or line_no > len(lines):
            print("FAIL  line out of range: %s:%d (file has %d lines)" % (rel_path, line_no, len(lines)))
            failed += 1
            continue
        actual = lines[line_no - 1]
        if snippet in actual:
            passed += 1
        else:
            print("FAIL  %s:%d" % (rel_path, line_no))
            print("       expected snippet: %s" % snippet)
            print("       actual line     : %s" % actual.rstrip("\n"))
            failed += 1
    print("核对 %d 条，通过 %d，失败 %d" % (len(EXPECTED), passed, failed))
    if failed == 0:
        print("self-test PASS")
        return 0
    print("self-test FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
