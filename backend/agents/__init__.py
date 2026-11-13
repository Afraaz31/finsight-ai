"""Level 12: the agents. One Orchestrator talks to the user; two specialist agents work in the background.

    user question (plain English)
        -> Orchestrator   decides which agent(s) and which files       (orchestrator.py)
            -> Spreadsheet Agent   Excel / CSV: exact maths with Pandas (spreadsheet_agent.py)
            -> Document Agent      PDF / Word / TXT: finds the passages (document_agent.py)
        -> Orchestrator   combines their findings into one answer for the user

Plain Python functions, no agent framework: each agent is a function with one job and a clear contract.
"""
