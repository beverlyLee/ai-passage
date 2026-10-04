"""LangChain 之五：智能体与工具 — 可复现脚本（无需 API key）。

对应正文：一个函数怎么被封装成模型能调用的工具，以及那个
「决定下一步做什么」的循环长什么样。

链路：@tool / Tool / StructuredTool -> BaseTool(RunnableSerializable)
      -> 模型输出 AgentAction -> 执行工具 -> AgentStep -> AgentFinish

所有工具都是纯函数、无网络、无副作用。模型决策用一个确定性规划器代替，
目的只是把「agent loop」这件事端到端跑通并断言行为，不调用任何大模型。

运行：
    python tools_and_agents.py            # 跑演示
    python tools_and_agents.py --self-test  # 跑断言，全绿退出 0
"""

from langchain_core.tools import tool, BaseTool
from langchain_core.tools.simple import Tool
from langchain_core.tools.structured import StructuredTool
from langchain_core.agents import AgentAction, AgentFinish, AgentStep
from langchain_core.tools.base import ToolException


# --------------------------------------------------------------------------
# 1. 用 @tool 装饰器把普通函数变成工具
#    @tool 在 tools/convert.py:17 定义（重载），返回 StructuredTool 实例
# --------------------------------------------------------------------------
@tool
def add(a: int, b: int) -> int:
    """把两个整数相加。"""
    return a + b


@tool
def reverse_text(text: str) -> str:
    """把一段文本反转。"""
    return text[::-1]


# --------------------------------------------------------------------------
# 2. 用 StructuredTool.from_function 手工造多参工具（structured.py:133）
#    注意：Tool.from_function（simple.py:165）造的是「单输入工具」，
#    只能吃一个字符串；有两个及以上参数必须 StructuredTool.from_function。
# --------------------------------------------------------------------------
def _multiply(a: int, b: int) -> int:
    return a * b


mul = StructuredTool.from_function(
    func=_multiply,
    name="multiply",
    description="两个整数相乘",
)


# --------------------------------------------------------------------------
# 3. 自定义 BaseTool 子类（最底层，验证工具即 Runnable）
# --------------------------------------------------------------------------
class EchoTool(BaseTool):
    name: str = "echo"
    description: str = "原样返回输入"

    def _run(self, text: str) -> str:
        return f"echo: {text}"

    async def _arun(self, text: str) -> str:
        return self._run(text)


# --------------------------------------------------------------------------
# 4. 一个最小的「智能体循环」
#    规划器（代替大模型）先吐 AgentAction，执行工具得到 AgentStep，
#    再吐 AgentFinish 结束。AgentAction / AgentFinish / AgentStep 都是
#    agents.py 里定义的「数据形状」（44 / 146 / 131），真正的循环在
#    langchain / langgraph 里，不在 langchain-core。
# --------------------------------------------------------------------------
def run_agent(planner, tools: dict[str, BaseTool], max_steps: int = 5) -> str:
    steps: list[AgentStep] = []
    for _ in range(max_steps):
        # 规划器根据已走的步骤决定下一步
        decision = planner(steps)
        if isinstance(decision, AgentFinish):
            return decision.return_values["output"]
        # decision 是 AgentAction：去工具箱里找对应工具执行
        action: AgentAction = decision
        tool = tools[action.tool]
        observation = tool.invoke(action.tool_input)
        steps.append(
            AgentStep(action=action, observation=str(observation))
        )
    return "（超过最大步数，未结束）"


def demo() -> None:
    tools = {
        add.name: add,
        reverse_text.name: reverse_text,
        mul.name: mul,
        EchoTool().name: EchoTool(),
    }
    print("工具箱：", list(tools.keys()))

    # 规划器：第一步调 add(2,3)，第二步结束并返回
    def planner(steps):
        if not steps:
            return AgentAction(tool="add", tool_input={"a": 2, "b": 3}, log="先相加")
        last = steps[-1]
        return AgentFinish(
            return_values={"output": f"结果是 {last.observation}"},
            log="完成",
        )

    out = run_agent(planner, tools)
    print("agent 输出：", out)

    # 直接调工具的几种姿势
    print("add.invoke:", add.invoke({"a": 10, "b": 20}))
    print("reverse_text.run:", reverse_text.run("LangChain"))
    print("multiply.invoke:", mul.invoke({"a": 4, "b": 5}))
    print("EchoTool.run:", EchoTool().run("hi"))


def self_test() -> None:
    # 断言1：@tool 造出的是 StructuredTool，名字/描述/参数 schema 都在
    assert isinstance(add, StructuredTool), type(add)
    assert add.name == "add"
    assert "相加" in add.description
    assert "a" in add.args and "b" in add.args
    print("self-test PASS [1] @tool -> StructuredTool，含 name/description/args schema")

    # 断言2：Tool.from_function 造出的 Tool 能 invoke 出正确结果
    assert mul.invoke({"a": 4, "b": 5}) == 20
    print("self-test PASS [2] Tool.from_function.invoke() 返回正确结果")

    # 断言3：BaseTool 是 Runnable，run / invoke 都通
    echo = EchoTool()
    assert echo.run("hi") == "echo: hi"
    assert echo.invoke("hi") == "echo: hi"
    print("self-test PASS [3] 自定义 BaseTool 子类 run/invoke 生效")

    # 断言4：AgentAction / AgentFinish / AgentStep 是可构造的数据形状
    act = AgentAction(tool="add", tool_input={"a": 1, "b": 2}, log="x")
    fin = AgentFinish(return_values={"output": "3"}, log="done")
    step = AgentStep(action=act, observation="3")
    assert act.tool == "add" and act.tool_input["a"] == 1
    assert fin.return_values["output"] == "3"
    assert step.observation == "3"
    print("self-test PASS [4] AgentAction / AgentFinish / AgentStep 数据形状可构造")

    # 断言5：最小 agent loop 跑通：先调工具再结束
    tools = {add.name: add, reverse_text.name: reverse_text, mul.name: mul, EchoTool().name: EchoTool()}

    def planner(steps):
        if not steps:
            return AgentAction(tool="add", tool_input={"a": 2, "b": 3}, log="先相加")
        return AgentFinish(
            return_values={"output": f"结果是 {steps[-1].observation}"},
            log="完成",
        )

    out = run_agent(planner, tools)
    assert out == "结果是 5", out
    print("self-test PASS [5] 最小 agent loop：调 add(2,3) 后 AgentFinish，输出「结果是 5」")

    # 断言6：ToolException 是工具执行失败的专用异常类型
    assert issubclass(ToolException, Exception)
    print("self-test PASS [6] ToolException 是工具失败专用异常（tools/base.py:390）")


if __name__ == "__main__":
    import sys

    if "--self-test" in sys.argv:
        self_test()
        print("ALL self-test PASS")
    else:
        demo()
