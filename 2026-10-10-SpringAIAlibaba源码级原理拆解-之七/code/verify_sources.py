#!/usr/bin/env python3
"""verify_sources.py — 之七（可观测）源码行号一手核对。

读取环境变量 SAA_SRC（默认 /tmp/saa），逐条核对 (相对路径, 行号, 期望片段)。
任一不匹配则打印差异并 exit(1)；全绿打印 PASS 与条数。

用法：
    SAA_SRC=/tmp/saa python3 code/verify_sources.py
"""
import os
import sys

SAA = os.environ.get("SAA_SRC", "/tmp/saa")

# (相对源码根的路径, 行号, 期望该行包含的片段)
CHECKS = [
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/Builder.java", 111, "protected ObservationRegistry observationRegistry;"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/Builder.java", 113, "protected ChatClientObservationConvention customObservationConvention;"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/Builder.java", 115, "protected AdvisorObservationConvention advisorObservationConvention;"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/Builder.java", 309, "public Builder observationRegistry(ObservationRegistry observationRegistry) {"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/Builder.java", 314, "public Builder customObservationConvention(ChatClientObservationConvention customObservationConvention) {"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/Builder.java", 319, "public Builder advisorObservationConvention(AdvisorObservationConvention advisorObservationConvention) {"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/DefaultBuilder.java", 24, "import io.micrometer.observation.ObservationRegistry;"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/DefaultBuilder.java", 76, "this.observationRegistry == null ? ObservationRegistry.NOOP : this.observationRegistry,"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/tools/task/AgentSpecReactAgentFactory.java", 32, "import io.micrometer.observation.ObservationRegistry;"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/tools/task/AgentSpecReactAgentFactory.java", 65, "private final ObservationRegistry observationRegistry;"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/tools/task/AgentSpecReactAgentFactory.java", 71, "this.observationRegistry = builder.observationRegistry != null"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/tools/task/AgentSpecReactAgentFactory.java", 130, "private ObservationRegistry observationRegistry;"),
    ("spring-ai-alibaba-agent-framework/src/main/java/com/alibaba/cloud/ai/graph/agent/tools/task/AgentSpecReactAgentFactory.java", 156, "public Builder observationRegistry(ObservationRegistry observationRegistry) {"),
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
    print(f"[PASS] 之七源码行号全部核对通过，共 {len(CHECKS)} 条（基准 7405a7d / v1.1.2.2）")
    sys.exit(0)


if __name__ == "__main__":
    main()
