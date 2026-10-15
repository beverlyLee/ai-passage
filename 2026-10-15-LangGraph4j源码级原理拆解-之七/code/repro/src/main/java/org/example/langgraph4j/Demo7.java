package org.example.langgraph4j;

import org.bsc.langgraph4j.CompiledGraph;
import org.bsc.langgraph4j.StateGraph;
import org.bsc.langgraph4j.action.AsyncNodeAction;
import org.bsc.langgraph4j.state.AgentState;
import org.bsc.langgraph4j.state.Channels;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;

import static org.bsc.langgraph4j.StateGraph.START;
import static org.bsc.langgraph4j.StateGraph.END;

/**
 * 之七 复现脚本：子图与组合。
 * 一手事实来源：langgraph4j-core 1.5.14 字节码（javap 复核）。
 *   - StateGraph.addSubgraph(String, StateGraph/CompiledGraph) 把一整张子图当成一个节点嵌进父图。
 *   - 子图与父图共享同一个 State 类型，所以子图节点写的状态会直接合并回父图的总状态上。
 *   - SubGraphNode.PREFIX_FORMAT 给子图内部节点名加前缀，避免和父图节点重名。
 * 这个脚本不需要任何大模型密钥，纯本地即可复现，跑 --self-test 做断言校验。
 */
public class Demo7 {

    /** 通用状态：steps 用追加通道累积执行轨迹，count 用覆盖通道记录轮数 */
    public static class MyState extends AgentState {
        public MyState(Map<String, Object> data) {
            super(data);
        }

        @SuppressWarnings("unchecked")
        public List<String> steps() {
            return value("steps", ArrayList::new);
        }

        public int count() {
            return value("count", () -> 0);
        }
    }

    public static void main(String[] args) throws Exception {
        // 父子图共用的 schema
        Map<String, org.bsc.langgraph4j.state.Channel<?>> schema = new HashMap<>();
        schema.put("steps", Channels.appender(() -> new ArrayList<String>()));
        schema.put("count", Channels.base(() -> 0));

        // 子图：内部一个 subNode，往 steps 里追加 "SUB"
        StateGraph<MyState> sub = new StateGraph<>(schema, MyState::new);
        sub.addNode("subNode", (AsyncNodeAction<MyState>) s ->
                CompletableFuture.completedFuture(Map.of("steps", List.of("SUB"))));
        sub.addEdge(START, "subNode");
        sub.addEdge("subNode", END);

        // 父图：a -> sub(子图) -> b
        StateGraph<MyState> g = new StateGraph<>(schema, MyState::new);
        g.addNode("a", (AsyncNodeAction<MyState>) s ->
                CompletableFuture.completedFuture(Map.of("steps", List.of("A"), "count", 1)));
        g.addNode("b", (AsyncNodeAction<MyState>) s ->
                CompletableFuture.completedFuture(Map.of("steps", List.of("B"), "count", 1)));
        g.addSubgraph("sub", sub);
        g.addEdge(START, "a");
        g.addEdge("a", "sub");
        g.addEdge("sub", "b");
        g.addEdge("b", END);

        CompiledGraph<MyState> graph = g.compile();

        Map<String, Object> input = new HashMap<>();
        input.put("steps", new ArrayList<String>());
        input.put("count", 0);

        Optional<MyState> fin = graph.invoke(input);

        List<String> steps = fin.get().steps();
        int count = fin.get().count();

        System.out.println("[steps 执行轨迹] " + steps);
        System.out.println("[count] " + count);
        // 顺带看一下子图内部节点名被加的前缀
        System.out.println("[子图内部节点前缀格式] " + org.bsc.langgraph4j.SubGraphNode.PREFIX_FORMAT);

        if (args.length > 0 && "--self-test".equals(args[0])) {
            boolean ok = steps.size() == 3
                    && "A".equals(steps.get(0))
                    && "SUB".equals(steps.get(1))
                    && "B".equals(steps.get(2))
                    && count == 1;
            if (ok) {
                System.out.println("self-test PASS");
                System.exit(0);
            } else {
                System.out.println("self-test FAIL");
                System.exit(1);
            }
        }
    }
}
