package org.example.langgraph4j;

import org.bsc.langgraph4j.CompiledGraph;
import org.bsc.langgraph4j.StateGraph;
import org.bsc.langgraph4j.action.AsyncNodeAction;
import org.bsc.langgraph4j.state.AgentState;
import org.bsc.langgraph4j.state.Channel;
import org.bsc.langgraph4j.state.Channels;
import org.bsc.langgraph4j.state.Reducer;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;

import static org.bsc.langgraph4j.StateGraph.START;
import static org.bsc.langgraph4j.StateGraph.END;

/**
 * 之九 复现脚本：自定义状态类型与自定义通道。
 * 一手事实：langgraph4j-core 1.5.14 字节码（javap 复核）。
 *  - 自定义状态必须继承 AgentState(Map)，并声明一份静态 SCHEMA：Map<String, Channel<?>>，
 *    每个键对应一种通道；图用 new StateGraph<>(SCHEMA, MyState::new) 把声明和工厂一起传进去。
 *  - Channels 提供三种通道：
 *      appender(Supplier)       追加型，节点产出增量，引擎把增量拼到历史末尾（默认去重）
 *      base(Supplier)           覆盖型，同一键后写覆盖先写，只留最新值
 *      base(Reducer, Supplier)  归约型，用自定义 BiFunction 合并“当前值”和“新值”
 *  - Reducer<T> 就是 BiFunction<T,T,T>：apply(当前值, 新值) 返回合并结果。
 */
public class Demo9 {

    public static class MyState extends AgentState {
        // 峰值归约：把“当前峰值”和“新值”合并成更大的那个
        public static final Reducer<Integer> MAX = (a, b) -> Math.max(a, b);

        public static final Map<String, Channel<?>> SCHEMA = Map.of(
                // 事件日志：追加，保留全部历史
                "events", Channels.appender(ArrayList::new),
                // 最新状态：覆盖，只留最后一次写入
                "latest", Channels.base(() -> ""),
                // 峰值：归约，用 Reducer 取更大值
                "peak", Channels.base(MAX, () -> 0));

        public MyState(Map<String, Object> data) {
            super(data);
        }

        @SuppressWarnings("unchecked")
        public List<String> events() {
            return this.<List<String>>value("events").orElse(new ArrayList<>());
        }

        public String latest() {
            return this.<String>value("latest").orElse("");
        }

        public int peak() {
            return this.<Integer>value("peak").orElse(0);
        }
    }

    public static void main(String[] args) throws Exception {
        StateGraph<MyState> g = new StateGraph<>(MyState.SCHEMA, MyState::new);

        // 三个检查步骤，每一步都写 events（追加）、latest（覆盖）、peak（归约取大）
        g.addNode("step1", (AsyncNodeAction<MyState>) s ->
                CompletableFuture.completedFuture(Map.of(
                        "events", List.of("登录尝试"),
                        "latest", "A",
                        "peak", 3)));
        g.addNode("step2", (AsyncNodeAction<MyState>) s ->
                CompletableFuture.completedFuture(Map.of(
                        "events", List.of("密码错误"),
                        "latest", "B",
                        "peak", 7)));
        g.addNode("step3", (AsyncNodeAction<MyState>) s ->
                CompletableFuture.completedFuture(Map.of(
                        "events", List.of("锁定账户"),
                        "latest", "C",
                        "peak", 5)));

        g.addEdge(START, "step1");
        g.addEdge("step1", "step2");
        g.addEdge("step2", "step3");
        g.addEdge("step3", END);

        CompiledGraph<MyState> graph = g.compile();

        Map<String, Object> input = new HashMap<>();
        input.put("events", new ArrayList<String>());

        Optional<MyState> fin = graph.invoke(input);

        List<String> events = fin.get().events();
        String latest = fin.get().latest();
        int peak = fin.get().peak();

        System.out.println("[events] " + events);
        System.out.println("[latest] " + latest);
        System.out.println("[peak] " + peak);

        if (args.length > 0 && "--self-test".equals(args[0])) {
            boolean ok = events.size() == 3
                    && "登录尝试".equals(events.get(0))
                    && "密码错误".equals(events.get(1))
                    && "锁定账户".equals(events.get(2))
                    && "C".equals(latest)
                    && peak == 7;
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
