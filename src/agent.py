# Standard library imports
import sqlite3

from dotenv import load_dotenv

# Third-party imports
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph

# Local module imports
from .agent_state import AgentState, Queries
from .constants import (
    PLAN_PROMPT,
    REFLECTION_PROMPT,
    RESEARCH_CRITIQUE_PROMPT,
    RESEARCH_PLAN_PROMPT,
    WRITER_PROMPT,
)

_ = load_dotenv()


class Agent:
    def __init__(self, model="gpt-3.5-turbo"):
        self.model = ChatOpenAI(model=model, temperature=0)
        self.PLAN_PROMPT = PLAN_PROMPT
        self.WRITER_PROMPT = WRITER_PROMPT
        self.RESEARCH_PLAN_PROMPT = RESEARCH_PLAN_PROMPT
        self.REFLECTION_PROMPT = REFLECTION_PROMPT
        self.RESEARCH_CRITIQUE_PROMPT = RESEARCH_CRITIQUE_PROMPT
        builder = StateGraph(AgentState)
        builder.add_node("planner", self.plan_node)
        builder.add_node("research_plan", self.research_plan_node)
        builder.add_node("generate", self.generation_node)
        builder.add_node("reflect", self.reflection_node)
        builder.add_node("research_critique", self.research_critique_node)
        builder.set_entry_point("planner")
        builder.add_conditional_edges(
            "generate", self.should_continue, {END: END, "reflect": "reflect"}
        )
        builder.add_edge("planner", "research_plan")
        builder.add_edge("research_plan", "generate")
        builder.add_edge("reflect", "research_critique")
        builder.add_edge("research_critique", "generate")
        memory = SqliteSaver(conn=sqlite3.connect(":memory:", check_same_thread=False))
        self.graph = builder.compile(
            checkpointer=memory,
            interrupt_after=[
                "planner",
                "generate",
                "reflect",
                "research_plan",
                "research_critique",
            ],
        )

    def plan_node(self, state: AgentState):
        messages = [
            SystemMessage(content=self.PLAN_PROMPT),
            HumanMessage(content=state["task"]),
        ]
        response = self.model.invoke(messages)
        return {
            "plan": response.content,
            "lnode": "planner",
            "count": 1,
        }

    def research_plan_node(self, state: AgentState):
        queries = self.model.with_structured_output(Queries).invoke(
            [
                SystemMessage(content=self.RESEARCH_PLAN_PROMPT),
                HumanMessage(content=state["task"]),
            ]
        )
        content = state["content"] or []  # add to content
        for q in queries.queries:
            response = self.tavily.search(query=q, max_results=2)
            for r in response["results"]:
                content.append(r["content"])
        return {
            "content": content,
            "queries": queries.queries,
            "lnode": "research_plan",
            "count": 1,
        }

    def generation_node(self, state: AgentState):
        content = "\n\n".join(state["content"] or [])
        user_message = HumanMessage(
            content=f"{state['task']}\n\nHere is my plan:\n\n{state['plan']}"
        )
        messages = [
            SystemMessage(content=self.WRITER_PROMPT.format(content=content)),
            user_message,
        ]
        response = self.model.invoke(messages)
        return {
            "draft": response.content,
            "revision_number": state.get("revision_number", 1) + 1,
            "lnode": "generate",
            "count": 1,
        }

    def reflection_node(self, state: AgentState):
        messages = [
            SystemMessage(content=self.REFLECTION_PROMPT),
            HumanMessage(content=state["draft"]),
        ]
        response = self.model.invoke(messages)
        return {
            "critique": response.content,
            "lnode": "reflect",
            "count": 1,
        }

    def research_critique_node(self, state: AgentState):
        queries = self.model.with_structured_output(Queries).invoke(
            [
                SystemMessage(content=self.RESEARCH_CRITIQUE_PROMPT),
                HumanMessage(content=state["critique"]),
            ]
        )
        content = state["content"] or []
        for q in queries.queries:
            response = self.tavily.search(query=q, max_results=2)
            for r in response["results"]:
                content.append(r["content"])
        return {
            "content": content,
            "lnode": "research_critique",
            "count": 1,
        }

    def should_continue(self, state):
        if state["revision_number"] > state["max_revisions"]:
            return END
        return "reflect"
