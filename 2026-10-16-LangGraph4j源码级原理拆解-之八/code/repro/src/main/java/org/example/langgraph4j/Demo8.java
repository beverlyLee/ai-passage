package org.example.langgraph4j;

import org.bsc.langgraph4j.CompiledGraph;
import org.bsc.langgraph4j.StateGraph;
import org.bsc.langgraph4j.action.AsyncEdgeAction;
import org.bsc.langgraph4j.action.AsyncNodeAction;
import org.bsc.langgraph4j.state.AgentState;
import org.bsc.langgraph4j.state.Channel;
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
 * 之八 复现脚本：条件边与动态路由。
 * 一手事实：langgraph4j-core 1.5.14 字节码（javap 复核）。
 *  - StateGraph.addConditionalEdges(String source, AsyncEdgeAction<State> action, Map<String,String> mapping)
 *    第三个参数 mapping 把 action 返回的“键”映射到目标节点名；值可以是 END 这种常量。
 *  - AsyncEdgeAction<S> 继承 Function<S, CompletableFuture<String>>，apply 返回下一步要去的目标“键”。
 *    action 读的是当前 state，所以路由依据是运行时状态，而不是写死在图结构里，这就是“动态路由”的本质。
 *  - 这一篇用了一个最小自定义状态（messages / category / reply 三个通道），category 由分类节点写入、
 *    再由条件边读出决定走哪条分支；通道本身的机制我们下一篇（之九）从第一性原理拆开讲。
 */
public class Demo8 {

    /**
     * 最小自定义状态：messages 走 appender（对话历史累积），category 和 reply 走 base（覆盖型）。
     * 构造器接收 Map 数据交给父类 AgentState；SCHEMA 声明每个键用哪种通道。
     */
    public static class MyState extends AgentState {
        public static final Map<String, Channel<?>> SCHEMA = Map.of(
                "messages", Channels.appender(ArrayList::new),
                "category", Channels.base(() -> "other"),
                "reply", Channels.base(() -> ""));

        public MyState(Map<String, Object> data) {
            super(data);
        }

        @SuppressWarnings("unchecked")
        public List<String> messages() {
            return this.<List<String>>value("messages").orElse(new ArrayList<>());
        }

        public Optional<String> lastMessage() {
            List<String> m = messages();
            return m.isEmpty() ? Optional.empty() : Optional.of(m.get(m.size() - 1));
        }
    }

    public static void main(String[] args) throws Exception {
        StateGraph<MyState> g = new StateGraph<>(MyState.SCHEMA, MyState::new);

        // 分类节点：读用户留言，判定类别，把结果写进 category 通道（覆盖型，只留最新判定）
        g.addNode("classify", (AsyncNodeAction<MyState>) s -> {
            String text = s.lastMessage().orElse("");
            String category = (text.contains("优惠") || text.contains("发票"))
                    ? "spam"
                    : (text.contains("?") || text.contains("？") || text.contains("吗"))
                            ? "question"
                            : "other";
            return CompletableFuture.completedFuture(Map.of("category", category));
        });

        // 三条处理分支：各自往 messages 追加一条回复，并把处理方式写进 reply
        g.addNode("handleSpam", (AsyncNodeAction<MyState>) s ->
                CompletableFuture.completedFuture(Map.of(
                        "messages", List.of("回复：这条营销/发票类留言已归档，不再跟进"),
                        "reply", "已归档")));
        g.addNode("handleQuestion", (AsyncNodeAction<MyState>) s ->
                CompletableFuture.completedFuture(Map.of(
                        "messages", List.of("回复：问题已转人工客服"),
                        "reply", "转人工")));
        g.addNode("handleOther", (AsyncNodeAction<MyState>) s ->
                CompletableFuture.completedFuture(Map.of(
                        "messages", List.of("回复：已登记，稍后处理"),
                        "reply", "已登记")));

        g.addEdge(START, "classify");

        // 条件边：从 classify 出发，按 state.category 动态选分支
        AsyncEdgeAction<MyState> router = (AsyncEdgeAction<MyState>) s ->
                CompletableFuture.completedFuture(s.<String>value("category").orElse("other"));
        g.addConditionalEdges("classify", router,
                Map.of("spam", "handleSpam", "question", "handleQuestion", "other", "handleOther"));

        g.addEdge("handleSpam", END);
        g.addEdge("handleQuestion", END);
        g.addEdge("handleOther", END);

        CompiledGraph<MyState> graph = g.compile();

        // 初始输入：用户留言放在 messages 通道里（appender 的初值就是这一条）
        Map<String, Object> input = new HashMap<>();
        input.put("messages", new ArrayList<>(List.of("用户留言：你们的发票怎么开？有没有优惠")));

        Optional<MyState> fin = graph.invoke(input);

        String category = fin.get().<String>value("category").orElse("null");
        String reply = fin.get().<String>value("reply").orElse("null");
        List<String> msgs = fin.get().messages();

        System.out.println("[category] " + category);
        System.out.println("[reply] " + reply);
        System.out.println("[messages] " + msgs);
        System.out.println("[lastMessage] " + fin.get().lastMessage().orElse("null"));

        if (args.length > 0 && "--self-test".equals(args[0])) {
            boolean ok = "spam".equals(category)
                    && "已归档".equals(reply)
                    && msgs.size() == 2
                    && "用户留言：你们的发票怎么开？有没有优惠".equals(msgs.get(0))
                    && "回复：这条营销/发票类留言已归档，不再跟进".equals(msgs.get(1));
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
