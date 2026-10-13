package org.example.langgraph4j;

import org.bsc.langgraph4j.CompiledGraph;
import org.bsc.langgraph4j.CompileConfig;
import org.bsc.langgraph4j.GraphStateException;
import org.bsc.langgraph4j.RunnableConfig;
import org.bsc.langgraph4j.StateGraph;
import org.bsc.langgraph4j.action.AsyncNodeAction;
import org.bsc.langgraph4j.checkpoint.MemorySaver;
import org.bsc.langgraph4j.state.AgentState;
import org.bsc.langgraph4j.state.AgentStateFactory;
import org.bsc.langgraph4j.state.Channel;
import org.bsc.langgraph4j.state.Channels;
import org.bsc.langgraph4j.state.RemoveByHash;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.function.Function;

/**
 * 最小可运行示例：演示 LangGraph4j 的「状态与通道」。
 * 不调用任何真实大模型，全部是确定性逻辑，所以输出可逐字符复现。
 * 三条通道覆盖三种合并语义：
 *   messages : Channels.appender —— 节点返回的 List 被「追加」到已有列表，累积而非覆盖
 *   stage    : Channels.base     —— 节点返回的单个值「最后写赢」，直接覆盖
 *   forget   : 节点返回一个 RemoveByHash —— AppenderChannel 把它当删除标识，从已有列表里删掉指定元素
 */
public class Demo3 {

    /** 自定义状态：本质仍是一个共享的 Map，额外提供工厂方法供框架重建状态对象。 */
    static class ChatState extends AgentState {
        public ChatState(Map<String, Object> initData) {
            super(initData);
        }

        static final AgentStateFactory<ChatState> FACTORY = ChatState::new;
    }

    @SuppressWarnings("unchecked")
    private static List<String> messages(AgentState s) {
        return (List<String>) s.value("messages").orElse(Collections.emptyList());
    }

    /** 把一个同步的「读状态、返回局部更新」包装成异步节点动作。 */
    private static AsyncNodeAction<ChatState> node(Function<ChatState, Map<String, Object>> fn) {
        return state -> CompletableFuture.completedFuture(fn.apply(state));
    }

    /** 声明整张图：四个节点串成一条线，分别演示 appender 累积、base 覆盖、RemoveByHash 删除。 */
    static StateGraph<ChatState> build() throws GraphStateException {
        // 状态 schema（三行通道声明，决定了每个键「新值如何和旧值合并」）：
        //   messages : appender 通道 —— 每个节点返回的 List 都会被追加进共享列表
        //   stage    : base 通道     —— 每个节点返回的单个值直接覆盖旧值
        Map<String, Channel<?>> channels = new java.util.HashMap<>();
        channels.put("messages", Channels.appender(() -> new ArrayList<>()));
        channels.put("stage", Channels.base(() -> ""));

        var g = new StateGraph<>(channels, ChatState.FACTORY);

        // 节点 ingest：追加一条用户消息（appender 累加），同时把 stage 覆盖成 received（base 覆盖）
        g.addNode("ingest", node(s -> Map.of(
                "messages", List.of("user: 我要退货"),
                "stage", "received")));
        // 节点 tag：再追加一条机器人消息（于是列表累积成两条），同时把 stage 覆盖成 triaged
        g.addNode("tag", node(s -> Map.of(
                "messages", List.of("bot: 已记录"),
                "stage", "triaged")));
        // 节点 forget：返回一个 RemoveByHash 删除标识，AppenderChannel 据此删掉「user: 我要退货」这一条
        g.addNode("forget", node(s -> Map.of(
                "messages", RemoveByHash.of("user: 我要退货"))));

        g.addEdge(StateGraph.START, "ingest");
        g.addEdge("ingest", "tag");
        g.addEdge("tag", "forget");
        g.addEdge("forget", StateGraph.END);
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
        CompiledGraph<ChatState> graph = build().compile(
                CompileConfig.builder().checkpointSaver(new MemorySaver()).build());

        RunnableConfig cfg = RunnableConfig.builder().threadId("chat-1").build();
        var outs = graph.stream(Map.of(), cfg).stream().toList();
        List<String> lifecycle = outs.stream().map(n -> n.node()).toList();
        ChatState fin = outs.get(outs.size() - 1).state();

        System.out.println("生命周期          = " + lifecycle);
        System.out.println("final.messages   = " + messages(fin));
        System.out.println("final.stage      = " + fin.value("stage").orElse("?"));
    }

    /** 复现性自测：断言三种合并语义的最终结果，供流水线机检。 */
    public static boolean selfTest() throws Exception {
        CompiledGraph<ChatState> graph = build().compile(
                CompileConfig.builder().checkpointSaver(new MemorySaver()).build());

        RunnableConfig cfg = RunnableConfig.builder().threadId("self-1").build();
        ChatState s = graph.invoke(Map.of(), cfg).orElseThrow();

        // appender：两条追加过；RemoveByHash 删掉 user 那条，只剩 bot 那条
        boolean okMsgs = messages(s).size() == 1
                && messages(s).contains("bot: 已记录")
                && !messages(s).contains("user: 我要退货");
        // base：stage 被最后一次写入覆盖成 triaged
        boolean okStage = "triaged".equals(s.value("stage").orElse(""));

        return okMsgs && okStage;
    }
}
