package org.example.langgraph4j;

import org.bsc.langgraph4j.CompiledGraph;
import org.bsc.langgraph4j.CompileConfig;
import org.bsc.langgraph4j.RunnableConfig;
import org.bsc.langgraph4j.StateGraph;
import org.bsc.langgraph4j.action.AsyncEdgeAction;
import org.bsc.langgraph4j.action.AsyncNodeAction;
import org.bsc.langgraph4j.checkpoint.MemorySaver;
import org.bsc.langgraph4j.state.AgentState;
import org.bsc.langgraph4j.state.AgentStateFactory;
import org.bsc.langgraph4j.state.Channel;
import org.bsc.langgraph4j.state.Channels;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.function.Function;

/**
 * 最小可运行示例：用 LangGraph4j 搭一张「请求分类 + 条件路由」的有状态图。
 * 不调用任何真实大模型，全部是确定性逻辑，所以输出可逐字符复现。
 */
public class Demo1 {

    /** 自定义状态：本质仍是一个共享的 Map，额外提供工厂方法供框架重建状态对象。 */
    static class MyState extends AgentState {
        public MyState(Map<String, Object> initData) {
            super(initData);
        }

        static final AgentStateFactory<MyState> FACTORY = MyState::new;
    }

    @SuppressWarnings("unchecked")
    private static List<String> messages(AgentState s) {
        return (List<String>) s.value("messages").orElse(Collections.emptyList());
    }

    /** 把一个同步的「读状态、返回局部更新」包装成异步节点动作。 */
    private static AsyncNodeAction<MyState> node(Function<MyState, Map<String, Object>> fn) {
        return state -> CompletableFuture.completedFuture(fn.apply(state));
    }

    public static void main(String[] args) throws Exception {
        if (args.length > 0 && args[0].equals("--self-test")) {
            boolean ok = selfTest();
            System.out.println(ok ? "self-test PASS" : "self-test FAIL");
            System.exit(ok ? 0 : 1);
        }
        run();
    }

    public static void run() throws Exception {
        // 1) 状态 schema：messages 是累积通道（appender），列表跨节点追加而不是覆盖
        Map<String, Channel<?>> channels = new java.util.HashMap<>();
        channels.put("messages", Channels.appender(() -> new ArrayList<>()));

        StateGraph<MyState> g = new StateGraph<>(channels, MyState.FACTORY);

        // 2) 节点：classify 读 request，决定走哪条分支
        g.addNode("classify", node(s -> {
            String req = (String) s.value("request").orElse("");
            String lane = req.contains("账单") ? "billing" : "general";
            return Map.of("lane", lane);
        }));

        // 3) 两个处理节点：分别往 messages 追加一条记录
        g.addNode("handleBilling", node(s -> Map.of("messages", List.of("账单专员已受理"))));
        g.addNode("handleGeneral", node(s -> Map.of("messages", List.of("通用客服已受理"))));

        // 4) 边：START -> classify；classify 之后按 lane 条件路由；两个处理节点都指向 END
        g.addEdge(StateGraph.START, "classify");
        AsyncEdgeAction<MyState> route = s ->
                CompletableFuture.completedFuture((String) s.value("lane").orElse("general"));
        g.addConditionalEdges("classify", route,
                Map.of("billing", "handleBilling", "general", "handleGeneral"));
        g.addEdge("handleBilling", StateGraph.END);
        g.addEdge("handleGeneral", StateGraph.END);

        // 5) 编译，并挂上内存检查点（按线程隔离的持久化）
        CompiledGraph<MyState> graph =
                g.compile(CompileConfig.builder().checkpointSaver(new MemorySaver()).build());

        // 场景 A：含「账单」的请求，走 billing 分支（用 stream 展示生命周期）
        RunnableConfig cfgA = RunnableConfig.builder().threadId("thread-A").build();
        Map<String, Object> inA = Map.of("request", "查询本月账单明细");
        var outputsA = graph.stream(inA, cfgA).stream().toList();
        List<String> lifecycleA = outputsA.stream().map(n -> n.node()).toList();
        MyState finalA = outputsA.get(outputsA.size() - 1).state();
        System.out.println("场景A 生命周期        = " + lifecycleA);
        System.out.println("场景A final.lane      = " + finalA.value("lane").orElse("?"));
        System.out.println("场景A final.messages  = " + messages(finalA));
        System.out.println("场景A checkpoint.lane = " + graph.getState(cfgA).state().value("lane").orElse("?"));

        // 场景 B：无「账单」的请求，走 general 分支（用 invoke 拿最终状态）
        RunnableConfig cfgB = RunnableConfig.builder().threadId("thread-B").build();
        Map<String, Object> inB = Map.of("request", "如何修改登录密码");
        MyState finalB = graph.invoke(inB, cfgB).orElseThrow();
        System.out.println("场景B final.lane      = " + finalB.value("lane").orElse("?"));
        System.out.println("场景B final.messages  = " + messages(finalB));
        System.out.println("场景B checkpoint.lane = " + graph.getState(cfgB).state().value("lane").orElse("?"));
    }

    /** 复现性自测：重跑核心场景并断言关键输出，供流水线机检。 */
    public static boolean selfTest() throws Exception {
        Map<String, Channel<?>> channels = new java.util.HashMap<>();
        channels.put("messages", Channels.appender(() -> new ArrayList<>()));
        StateGraph<MyState> g = new StateGraph<>(channels, MyState.FACTORY);
        g.addNode("classify", node(s -> {
            String req = (String) s.value("request").orElse("");
            return Map.of("lane", req.contains("账单") ? "billing" : "general");
        }));
        g.addNode("handleBilling", node(s -> Map.of("messages", List.of("账单专员已受理"))));
        g.addNode("handleGeneral", node(s -> Map.of("messages", List.of("通用客服已受理"))));
        g.addEdge(StateGraph.START, "classify");
        AsyncEdgeAction<MyState> route =
                s -> CompletableFuture.completedFuture((String) s.value("lane").orElse("general"));
        g.addConditionalEdges("classify", route,
                Map.of("billing", "handleBilling", "general", "handleGeneral"));
        g.addEdge("handleBilling", StateGraph.END);
        g.addEdge("handleGeneral", StateGraph.END);
        CompiledGraph<MyState> graph =
                g.compile(CompileConfig.builder().checkpointSaver(new MemorySaver()).build());

        RunnableConfig cfgA = RunnableConfig.builder().threadId("self-A").build();
        MyState a = graph.invoke(Map.of("request", "查账单"), cfgA).orElseThrow();
        boolean okA = "billing".equals(a.value("lane").orElse(""))
                && messages(a).contains("账单专员已受理");

        RunnableConfig cfgB = RunnableConfig.builder().threadId("self-B").build();
        MyState b = graph.invoke(Map.of("request", "改密码"), cfgB).orElseThrow();
        boolean okB = "general".equals(b.value("lane").orElse(""))
                && messages(b).contains("通用客服已受理");

        return okA && okB;
    }
}
