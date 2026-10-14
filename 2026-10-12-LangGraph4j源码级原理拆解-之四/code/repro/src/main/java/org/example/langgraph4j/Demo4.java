package org.example.langgraph4j;

import org.bsc.langgraph4j.CompiledGraph;
import org.bsc.langgraph4j.NodeOutput;
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
 * LangGraph4j 之四：运行引擎与流式。
 *
 * 这个 Demo 用一条最简单的线性图（START -> nodeA -> nodeB -> END）说明三件事：
 *   1. graph.stream(...) 会一个节点一个节点地往外吐 NodeOutput 事件，每个事件带着
 *      该节点执行之后的状态，所以你能“边跑边看”。
 *   2. graph.invoke(...) 不吐中间事件，它把整条链路跑完，只把最终状态还给你。
 *   3. graph.streamSnapshots(...) 吐的也是 NodeOutput（实测是普通 NodeOutput，不是
 *      StateSnapshot），但语义是“这一步结束后的完整状态快照”，包含入口 __START__ 与终态 __END__。
 *
 * 全程只依赖 langgraph4j-core 1.5.14，所有 API 都已用 javap 对字节码一手核实。
 */
public class Demo4 {

    /** 自定义状态：steps 是追加型通道（节点每跑一次就往里加一个名字），count 是覆盖型通道。 */
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
        boolean selfTest = args.length > 0 && args[0].equals("--self-test");

        // ===== 建图 =====
        Map<String, org.bsc.langgraph4j.state.Channel<?>> schema = new HashMap<>();
        schema.put("steps", Channels.appender(() -> new ArrayList<String>())); // 追加型
        schema.put("count", Channels.base(() -> 0));                          // 覆盖型
        StateGraph<MyState> g = new StateGraph<>(schema, MyState::new);
        g.addNode("nodeA", (AsyncNodeAction<MyState>) state ->
                CompletableFuture.completedFuture(Map.of("steps", List.of("A"), "count", 1)));
        g.addNode("nodeB", (AsyncNodeAction<MyState>) state ->
                CompletableFuture.completedFuture(Map.of("steps", List.of("B"), "count", 2)));
        g.addEdge(START, "nodeA");
        g.addEdge("nodeA", "nodeB");
        g.addEdge("nodeB", END);
        CompiledGraph<MyState> graph = g.compile();

        // ===== 1) stream：逐节点事件 =====
        List<String> seen = new ArrayList<>();
        System.out.println("[stream] 逐节点往外吐的 NodeOutput 事件：");
        for (NodeOutput<MyState> o : graph.stream(initialInput())) {
            if (o.isEND()) {
                System.out.println("  -> 到达 END 标记");
                continue;
            }
            if (START.equals(o.node())) {
                System.out.println("  node=__START__（入口，初始状态） steps=" + o.state().steps() + " count=" + o.state().count());
                continue;
            }
            MyState st = o.state();
            System.out.println("  node=" + o.node()
                    + " steps=" + st.steps()
                    + " count=" + st.count());
            seen.add(o.node());
        }

        // ===== 2) invoke：只给最终状态 =====
        Optional<MyState> fin = graph.invoke(initialInput());
        MyState fs = fin.orElseThrow();
        System.out.println("[invoke] 只还最终状态：steps=" + fs.steps() + " count=" + fs.count());

        // ===== 3) streamSnapshots：每一步的状态快照 =====
        // 注意：streamSnapshots 只有带 RunnableConfig 的重载，没有省略 config 的版本，
        // 这里专门起一个带 threadId 的配置，便于和后面“持久化/断点续跑”的 threadId 概念接上。
        // 它吐的是普通的 NodeOutput（已用 instanceof 探针确认非 StateSnapshot），
        // 但语义是“这一步结束后的完整状态快照”，包含入口 __START__ 与终态 __END__。
        System.out.println("[streamSnapshots] 每一步的状态快照（含入口 __START__ 与终态 __END__）：");
        org.bsc.langgraph4j.RunnableConfig snapCfg =
                org.bsc.langgraph4j.RunnableConfig.builder().threadId("demo4-snapshot-run").build();
        for (NodeOutput<MyState> o : graph.streamSnapshots(initialInput(), snapCfg)) {
            System.out.println("  node=" + o.node()
                    + " steps=" + o.state().steps()
                    + " isEND=" + o.isEND());
        }

        if (selfTest) {
            boolean ok = seen.size() == 2
                    && seen.get(0).equals("nodeA")
                    && seen.get(1).equals("nodeB")
                    && fs.steps().equals(List.of("A", "B"))
                    && fs.count() == 2;
            if (ok) {
                System.out.println("self-test PASS");
                System.exit(0);
            } else {
                System.out.println("self-test FAIL seen=" + seen
                        + " final=" + fs.steps() + "," + fs.count());
                System.exit(1);
            }
        }
    }

    private static Map<String, Object> initialInput() {
        Map<String, Object> m = new HashMap<>();
        m.put("steps", new ArrayList<String>());
        m.put("count", 0);
        return m;
    }
}
