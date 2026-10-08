# Spring AI Alibaba 之三：graph-core 状态图引擎深拆

基准是 tag v1.1.2.2，提交 7405a7d。本篇所有行号都来自这个提交，没在源码上核实过的我不写。

graph-core 是 SAA 真正的第一个增量层。它把智能体流程建模成一张有向图：节点是动作，边是路由，整张图共享一块叫 OverAllState 的状态。之上 agent-framework 的 ReactAgent 不过是这张图的一种固定拼法。先把引擎本身拆清楚，之四再看 ReactAgent 怎么用它拼出 ReAct。

![graph-core 三件套与关键类](diagram/01_graphcore_overview@2x.png)

## 一、三件套各自是什么

StateGraph（StateGraph.java:43）是建图阶段的声明式入口。它不执行，只收集节点和边。addNode 有七种形态（:230 同步动作 / :242 带配置 / :255 直接塞 Node / :279 单命令动作 / :295 多命令并行 / :311 内嵌已编译子图 / :337 内嵌未编译子图），addEdge（:362/:382/:392）普通边，addConditionalEdges（:411/:441/:456）条件边。compile（:517/:531）把这张声明图固化成 CompiledGraph。

OverAllState（OverAllState.java:77）是整张图的共享黑板。每个节点只拿到这块状态的一份引用，往里写 partial update，由 KeyStrategy 决定新值怎么并入旧值。默认输入键 input 用 ReplaceStrategy（:145/:155/:167/:180）。

CompiledGraph（CompiledGraph.java:58）是真正跑起来的执行引擎。compile 之后节点动作、边路由、状态归约策略都被钉死，不能再改。

## 二、共享状态怎么并：KeyStrategy 三策略

节点不自己决定状态怎么写，它只抛一个 partial map，OverAllState.updateState（:263）逐键交给对应的 KeyStrategy。策略缺失时退化为 REPLACE。

ReplaceStrategy（ReplaceStrategy.java:20/:23）最简单，apply 直接 return newValue，覆盖写。

AppendStrategy（AppendStrategy.java:31/:43）处理列表追加。它的第一条规则是 newValue 为 null 时 return oldValue，也就是这次节点没产出这个键就不碰旧值（:44）。newValue 是个 ReplaceAllWith 包裹则整体替换（:48）；newValue 是 RemoveIdentifier 则从旧列表里抠掉对应项（:58/:60）；否则把新元素并到旧列表尾部。这套机制让消息列表这种会不断生长的键可以安全累加，不需要每个节点自己读旧列表再写回去。

要删一个键，节点写 MARK_FOR_REMOVAL（OverAllState.java:78），updateState 检测到就 data.remove(key)（:271）。

![图执行与状态归约流水线](diagram/02_execution_flow@2x.png)

## 三、图怎么跑起来

入口是 GraphRunner.run（GraphRunner.java:30/:53），最后一道 mainGraphExecutor.execute(context, resultValue) 把控制权交给执行器。执行器从入口节点开始，调 CompiledGraph.streamFromInitialNode（:578）产出 Flux<NodeOutput>。

每到一个节点，执行器取该节点的动作算结果，然后走 nextNodeId（:366/:410）决定下一跳。路由值在 EdgeValue 里：若是常量 id，直接 new Command(id)；若带命令，command.gotoNode() 拿到目标，再从 command.update() 取状态增量，过 OverAllState.updateState（:366 段里 currentState = OverAllState.updateState(state, command.update(), keyStrategyMap)）归约进总状态，再带着新状态继续。普通无路由的边由 entryPoint = edges.get(START)（:416）和相邻边表推进。

关键点是状态归约发生在边的推进里，不在节点里。节点只负责算自己的 partial，框架负责把它并回总状态再决定去哪。这也是 graph-core 能支持子图（addNode 收 CompiledGraph 或 StateGraph，:311/:337）的原因：子图对外也只是一段接受状态、返回状态加跳转的节点。

## 四、复现模块

本篇附 code/verify_sources.py，把上面引用的每个文件、每个行号都用 git 在 7405a7d 上重新 grep 核对一次，跑通即证明行号没漂。无外部依赖，纯标准库。

## 五、系列排期

之一整体概览（已发）/ 之二 Spring AI 底座（已发）/ 之三本篇 graph-core / 之四 ReactAgent 与 ReAct 循环 / 之五内置编排与 A2A / 之六上下文工程与 HITL / 之七可观测 studio admin sandbox / 之八沙箱与工具安全 / 之九实战收尾。

## 六、结尾钩子

之一我说 ReactAgent 不过是 graph-core 的一种固定拼法，你有没有想过框架为什么要把节点和边做成声明式再编译，而不是直接写个 while 循环？答案藏在 nextNodeId 把状态归约和路由拆开的那一刻。之四我们把 ReactAgent 的图拆开，看它怎么把这段引擎拼成 ReAct。你在自己的项目里用状态机还是直接堆 if else，评论区聊聊。
