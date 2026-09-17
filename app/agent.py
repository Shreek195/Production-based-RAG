"""
Agent Communication Patterns in LangGraph
Shared state, message passing, and blackboard pattern
"""

from typing import Optional
from typing_extensions import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from langsmith import traceable

from app.config import get_settings

