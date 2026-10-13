package org.example.langgraph4j;

import org.bsc.langgraph4j.CompiledGraph;
import org.bsc.langgraph4j.CompileConfig;
import org.bsc.langgraph4j.GraphStateException;
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
 * 最小可运行示例：用 LangGraph4j 搭一张「请求分类 + 条件路由 + 子图」的有状态图。
 * 不调用任何真实大模型，全部是确定性逻辑，所以输出可逐字符复现。
 * 重点演示 StateGraph 的图模型 API：addNode、addEdge、addConditionalEdges，以及把另一张 StateGraph 当作节点挂进来（子图共享状态）。
 */
public class Demo2 {

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

    /**
     * 子图：技术研究流程，自成一个小型状态图。
     * 当它通过 addNode 挂到父图时，与父图共享同一个 MyState（同一份 channels 与同一份 Map）。
     */
    static StateGraph<MyState> techSubgraph() throws GraphStateException {
        var g = new StateGraph<>(MyState.FACTORY);
        g.addNode("research", node(s -> Map.of("messages", List.of("[子图] 已检索相关论文"))));
        g.addNode("draft", node(s -> Map.of("messages", List.of("[子图] 已起草技术方案"))));
        g.addEdge(StateGraph.START, "research");
        g.addEdge("research", "draft");
        g.addEdge("draft", StateGraph.END);
        return g;
    }

    /** 声明整张父图：节点、边、条件边、子图节点。 */
    static StateGraph<MyState> build() throws GraphStateException {
        // 状态 schema：messages 是累积通道（appender），跨节点追加而不是覆盖；category 用 base 通道（最后写赢），只用于路由判断
        Map<String, Channel<?>> channels = new java.util.HashMap<>();
        channels.put("messages", Channels.appender(() -> new ArrayList<>()));
        channels.put("category", Channels.base(() -> ""));

        var g = new StateGraph<>(channels, MyState.FACTORY);

        g.addNode("classify", node(s -> {
            String req = (String) s.value("request").orElse("");
            String cat = req.contains("退款") ? "billing" : "tech";
            return Map.of("category", cat);
        }));
        g.addNode("billingHandler", node(s -> Map.of("messages", List.of("[账单] 已进入退款工单队列"))));
        // 把另一张 StateGraph 当成一个节点挂进来：子图与父图共享状态
        g.addNode("techSubgraph", techSubgraph());

        g.addEdge(StateGraph.START, "classify");
        AsyncEdgeAction<MyState> route = s ->
                CompletableFuture.completedFuture((String) s.value("category").orElse("tech"));
        g.addConditionalEdges("classify", route,
                Map.of("billing", "billingHandler", "tech", "techSubgraph"));
        g.addEdge("billingHandler", StateGraph.END);
        g.addEdge("techSubgraph", StateGraph.END);
        return g;
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
        CompiledGraph<MyState> graph = build().compile(
                CompileConfig.builder().checkpointSaver(new MemorySaver()).build());

        // 场景 A：含「退款」 → billing 分支
        RunnableConfig cfgA = RunnableConfig.builder().threadId("thread-A").build();
        Map<String, Object> inA = Map.of("request", "我要申请退款");
        var outsA = graph.stream(inA, cfgA).stream().toList();
        List<String> lifecycleA = outsA.stream().map(n -> n.node()).toList();
        MyState finA = outsA.get(outsA.size() - 1).state();
        System.out.println("场景A 生命周期       = " + lifecycleA);
        System.out.println("场景A final.category = " + finA.value("category").orElse("?"));
        System.out.println("场景A final.messages = " + messages(finA));

        // 场景 B：不含「退款」 → tech 分支 → 进入子图（子图节点被展平为 techSubgraph-research / techSubgraph-draft）
        RunnableConfig cfgB = RunnableConfig.builder().threadId("thread-B").build();
        Map<String, Object> inB = Map.of("request", "模型怎么选型");
        var outsB = graph.stream(inB, cfgB).stream().toList();
        List<String> lifecycleB = outsB.stream().map(n -> n.node()).toList();
        MyState finB = outsB.get(outsB.size() - 1).state();
        System.out.println("场景B 生命周期       = " + lifecycleB);
        System.out.println("场景B final.category = " + finB.value("category").orElse("?"));
        System.out.println("场景B final.messages = " + messages(finB));
        System.out.println("场景B 子图共享状态    = " + (messages(finB).size() == 2));
    }

    /** 复现性自测：重跑核心场景并断言关键输出，供流水线机检。 */
    public static boolean selfTest() throws Exception {
        CompiledGraph<MyState> graph = build().compile(
                CompileConfig.builder().checkpointSaver(new MemorySaver()).build());

        RunnableConfig cfgA = RunnableConfig.builder().threadId("self-A").build();
        MyState a = graph.invoke(Map.of("request", "我要申请退款"), cfgA).orElseThrow();
        boolean okA = "billing".equals(a.value("category").orElse(""))
                && messages(a).contains("[账单] 已进入退款工单队列");

        RunnableConfig cfgB = RunnableConfig.builder().threadId("self-B").build();
        MyState b = graph.invoke(Map.of("request", "模型怎么选型"), cfgB).orElseThrow();
        boolean okB = "tech".equals(b.value("category").orElse(""))
                && messages(b).size() == 2;

        return okA && okB;
    }
}
