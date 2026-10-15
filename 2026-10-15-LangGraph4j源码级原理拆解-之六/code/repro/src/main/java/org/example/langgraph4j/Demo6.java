package org.example.langgraph4j;

import org.bsc.langgraph4j.CompiledGraph;
import org.bsc.langgraph4j.StateGraph;
import org.bsc.langgraph4j.action.AsyncNodeAction;
import org.bsc.langgraph4j.prebuilt.MessagesState;
import org.bsc.langgraph4j.state.AgentState;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;

import static org.bsc.langgraph4j.StateGraph.START;
import static org.bsc.langgraph4j.StateGraph.END;

/**
 * 之六 复现脚本：消息状态与消息通道。
 * 一手事实来源：langgraph4j-core 1.5.14 字节码（javap 复核）。
 *   - MessagesState 在 org.bsc.langgraph4j.prebuilt 包，它的静态 SCHEMA 里 "messages" 通道
 *     用的是 Channels.appender，也就是默认去重追加。节点只需要产出“增量消息”，引擎自动把
 *     这些增量拼到历史末尾，这就是对话历史能一路累积的真正原因。
 *   - messages() 读出全量历史，lastMessage() 取最后一条，lastMinus(int) 从末尾往前数着取。
 * 这个脚本不需要任何大模型密钥，纯本地即可复现，跑 --self-test 做断言校验。
 */
public class Demo6 {

    /**
     * 自定义消息状态：直接继承预置的 MessagesState，复用它已经配好的 messages 通道和那几个取值方法。
     * 泛型参数 String 表示把每条消息当成一个字符串来看，方便演示。
     */
    public static class MyState extends MessagesState<String> {
        public MyState(Map<String, Object> data) {
            super(data);
        }
    }

    public static void main(String[] args) throws Exception {
        // 用预置的消息 schema 建图，messages 通道已经自带，不需要自己再定义一遍
        StateGraph<MyState> g = new StateGraph<>(MessagesState.SCHEMA, MyState::new);

        // 节点 userSay：模拟“用户说了一句话”，只产出一条增量消息
        g.addNode("userSay", (AsyncNodeAction<MyState>) s ->
                CompletableFuture.completedFuture(
                        Map.of("messages", List.of("用户：今天天气怎么样？"))));

        // 节点 assistantReply：模拟“助手回复”，再产出一条增量消息
        g.addNode("assistantReply", (AsyncNodeAction<MyState>) s ->
                CompletableFuture.completedFuture(
                        Map.of("messages", List.of("助手：我查不到实时天气，但可以帮你查预报"))));

        g.addEdge(START, "userSay");
        g.addEdge("userSay", "assistantReply");
        g.addEdge("assistantReply", END);

        CompiledGraph<MyState> graph = g.compile();

        // 初始输入给一个空的历史列表，后面由通道逐条追加
        Map<String, Object> input = new HashMap<>();
        input.put("messages", new ArrayList<String>());

        Optional<MyState> fin = graph.invoke(input);

        List<String> all = fin.get().messages();
        Optional<String> last = fin.get().lastMessage();
        Optional<String> prev = fin.get().lastMinus(1);

        System.out.println("[messages 全量历史] " + all);
        System.out.println("[lastMessage] " + last.orElse("null"));
        System.out.println("[lastMinus(1)] " + prev.orElse("null"));

        if (args.length > 0 && "--self-test".equals(args[0])) {
            boolean ok = all.size() == 2
                    && "用户：今天天气怎么样？".equals(all.get(0))
                    && "助手：我查不到实时天气，但可以帮你查预报".equals(all.get(1))
                    && last.isPresent()
                    && "助手：我查不到实时天气，但可以帮你查预报".equals(last.get())
                    && prev.isPresent()
                    && "用户：今天天气怎么样？".equals(prev.get());
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
