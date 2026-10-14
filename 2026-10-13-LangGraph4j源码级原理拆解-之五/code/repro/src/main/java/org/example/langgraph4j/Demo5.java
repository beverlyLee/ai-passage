package org.example.langgraph4j;

import org.bsc.langgraph4j.CompileConfig;
import org.bsc.langgraph4j.CompiledGraph;
import org.bsc.langgraph4j.RunnableConfig;
import org.bsc.langgraph4j.StateGraph;
import org.bsc.langgraph4j.action.AsyncNodeAction;
import org.bsc.langgraph4j.checkpoint.FileSystemSaver;
import org.bsc.langgraph4j.checkpoint.MemorySaver;
import org.bsc.langgraph4j.serializer.std.ObjectStreamStateSerializer;
import org.bsc.langgraph4j.state.AgentState;
import org.bsc.langgraph4j.state.Channel;
import org.bsc.langgraph4j.state.Channels;
import org.bsc.langgraph4j.state.StateSnapshot;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;

import static org.bsc.langgraph4j.StateGraph.START;
import static org.bsc.langgraph4j.StateGraph.END;

/**
 * LangGraph4j 之五：持久化与断点续跑。
 *
 * 用同一条线性图（START -> nodeA -> nodeB -> END）演示：
 *   1. 配一个 checkpoint saver，再 interruptBefore("nodeB")，第一次 invoke 在 nodeB 前停下，
 *      状态作为检查点存进 saver；getState(config) 能读回“下一个要跑的节点”是 nodeB。
 *   2. 中断闸门 interruptBefore 是常驻的，同一个编译图再 invoke 还会在 nodeB 前再停一次；
 *      要真正续跑到终点，得用一个不带该中断的编译图，配同一个 saver、同一个 threadId 去 invoke，
 *      引擎从检查点的 nextNode 接着跑，而不是从 __START__ 重来。
 *   3. 两种 saver 各演示一遍：MemorySaver（内存，进程退出即失）和 FileSystemSaver（落盘，
 *      用一个指向同一目录的全新 saver 实例也能读回，证明检查点是真的写到了磁盘）。
 *
 * 全程只依赖 langgraph4j-core 1.5.14，所有 API 均已用 javap 对字节码一手核实。
 */
public class Demo5 {

    /** 自定义状态：steps 是追加型通道，count 是覆盖型通道。 */
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

    private static Map<String, Channel<?>> schema() {
        Map<String, Channel<?>> s = new HashMap<>();
        s.put("steps", Channels.appender(() -> new ArrayList<String>())); // 追加型
        s.put("count", Channels.base(() -> 0));                          // 覆盖型
        return s;
    }

    private static StateGraph<MyState> buildGraph() throws Exception {
        StateGraph<MyState> g = new StateGraph<>(schema(), MyState::new);
        g.addNode("nodeA", (AsyncNodeAction<MyState>) st ->
                CompletableFuture.completedFuture(Map.of("steps", List.of("A"), "count", 1)));
        g.addNode("nodeB", (AsyncNodeAction<MyState>) st ->
                CompletableFuture.completedFuture(Map.of("steps", List.of("B"), "count", 2)));
        g.addEdge(START, "nodeA");
        g.addEdge("nodeA", "nodeB");
        g.addEdge("nodeB", END);
        return g;
    }

    private static Map<String, Object> initialInput() {
        Map<String, Object> m = new HashMap<>();
        m.put("steps", new ArrayList<String>());
        m.put("count", 0);
        return m;
    }

    private static long countFiles(Path dir) throws Exception {
        try (var s = Files.list(dir)) {
            return s.count();
        }
    }

    public static void main(String[] args) throws Exception {
        boolean selfTest = args.length > 0 && args[0].equals("--self-test");

        // ========== 场景一：MemorySaver，进程内断点续跑 ==========
        System.out.println("=== 场景一：MemorySaver 断点续跑 ===");
        MemorySaver memSaver = new MemorySaver();
        CompiledGraph<MyState> g1 = buildGraph().compile(
                CompileConfig.builder()
                        .checkpointSaver(memSaver)
                        .interruptBefore("nodeB")
                        .build());

        RunnableConfig cfg1 = RunnableConfig.builder().threadId("demo5-memory-run").build();

        // 第一次 invoke：跑完 nodeA，在 nodeB 前停下，检查点写进 memSaver
        Optional<MyState> r1 = g1.invoke(initialInput(), cfg1);
        System.out.println("[第一次 invoke] steps=" + r1.map(MyState::steps).orElse(List.of()));

        // getState：从 saver 读回当前检查点，next 指向被中断处要跑的节点
        StateSnapshot<MyState> snap1 = g1.getState(cfg1);
        System.out.println("[getState] next=" + snap1.next()
                + " steps=" + snap1.state().steps() + " count=" + snap1.state().count());

        // 直接拿同一个 g1 再 invoke：interruptBefore 常驻，会在 nodeB 前再停一次
        Optional<MyState> r1b = g1.invoke(initialInput(), cfg1);
        System.out.println("[同一图再 invoke] steps=" + r1b.map(MyState::steps).orElse(List.of())
                + "（中断闸门常驻，仍在 nodeB 前停下）");

        // 续跑：用不带该中断的编译图，配同一个 saver、同一个 threadId，从检查点接着跑
        CompiledGraph<MyState> g1resume = buildGraph().compile(
                CompileConfig.builder().checkpointSaver(memSaver).build());
        Optional<MyState> r2 = g1resume.invoke(initialInput(), cfg1);
        MyState s2 = r2.orElseThrow();
        System.out.println("[换图续跑] steps=" + s2.steps() + " count=" + s2.count());

        // ========== 场景二：FileSystemSaver 落盘，全新 saver 实例也能读回 ==========
        System.out.println("=== 场景二：FileSystemSaver 落盘续跑 ===");
        Path dir = Files.createTempDirectory("lg4j-demo5-fs-");
        FileSystemSaver fsSaver = new FileSystemSaver(dir, new ObjectStreamStateSerializer<>(MyState::new));
        CompiledGraph<MyState> h1 = buildGraph().compile(
                CompileConfig.builder()
                        .checkpointSaver(fsSaver)
                        .interruptBefore("nodeB")
                        .build());

        RunnableConfig cfg2 = RunnableConfig.builder().threadId("demo5-fs-run").build();
        h1.invoke(initialInput(), cfg2); // 跑到 nodeA 后停在 nodeB 前，落盘一个检查点
        long filesAfterFirst = countFiles(dir);
        System.out.println("[第一次 invoke] 落盘检查点文件数=" + filesAfterFirst);

        // 续跑：换一个指向同一目录的全新 FileSystemSaver 实例，证明检查点真的在磁盘上
        FileSystemSaver fsSaver2 = new FileSystemSaver(dir, new ObjectStreamStateSerializer<>(MyState::new));
        CompiledGraph<MyState> h2 = buildGraph().compile(
                CompileConfig.builder().checkpointSaver(fsSaver2).build());
        Optional<MyState> r3 = h2.invoke(initialInput(), cfg2);
        MyState s3 = r3.orElseThrow();
        long filesAfterSecond = countFiles(dir);
        System.out.println("[换 saver 续跑] steps=" + s3.steps() + " count=" + s3.count()
                + " 落盘文件数=" + filesAfterSecond);

        // ========== 自检 ==========
        if (selfTest) {
            boolean ok = r1.isPresent()
                    && r1.get().steps().equals(List.of("A"))     // 第一次只跑到 nodeA
                    && "nodeB".equals(snap1.next())               // 中断处下一个节点是 nodeB
                    && snap1.state().count() == 1
                    && r1b.isPresent()
                    && r1b.get().steps().equals(List.of("A"))     // 同一图再 invoke 仍停在 nodeB 前
                    && s2.steps().equals(List.of("A", "B"))       // 换图续跑到终态
                    && s2.count() == 2
                    && s3.steps().equals(List.of("A", "B"))       // 全新 saver 从磁盘续跑到终态
                    && s3.count() == 2
                    && filesAfterFirst >= 1                       // 落盘确实产生了文件
                    && filesAfterSecond >= filesAfterFirst;
            if (ok) {
                System.out.println("self-test PASS");
                System.exit(0);
            } else {
                System.out.println("self-test FAIL"
                        + " r1=" + r1.map(MyState::steps)
                        + " next=" + snap1.next()
                        + " r1b=" + r1b.map(MyState::steps)
                        + " s2=" + s2.steps() + "," + s2.count()
                        + " s3=" + s3.steps() + "," + s3.count()
                        + " files=" + filesAfterFirst + "/" + filesAfterSecond);
                System.exit(1);
            }
        }
    }
}
