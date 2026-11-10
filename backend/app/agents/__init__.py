"""Agents: standing instructions to look at the home network in a certain way, run on a schedule
or by hand, each run a LangGraph graph that the owner can follow step by step.

LangGraph's tracing sends what a graph does to LangSmith, a hosted service, when it is switched on
in the environment. What an agent reads is the owner's network, so it is switched off here, and
nothing an agent does leaves the house except the questions to the AI provider that the gateway
(app/ai/gateway.py) sends, redacted and recorded.
"""

import os

# Set, not defaulted: a value in the environment must not turn on sending a network's evidence to a
# service nobody chose.
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"
