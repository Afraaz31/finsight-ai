---
title: FinSight AI
emoji: 📊
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
short_description: Evidence-backed AI research on SEC 10-K annual reports
---

# FinSight AI: live demo

An AI financial research assistant that answers questions about the SEC 10-K annual reports of **Apple, Microsoft, Amazon, Alphabet and NVIDIA** with citations to the source passages. **It never invents a number:** every figure comes from the filings or from an exact Python calculation.

**Source code, architecture and documentation:** https://github.com/Afraaz31/finsight-ai

### Try
- *What are NVIDIA's major business risks?* (cited 10-K passages)
- *Compare Apple's revenue with Microsoft's* (exact SEC figures)
- *Audit report of Apple* (a 10-section company report)
- **Upload & Analyze:** *Does the revenue in the spreadsheet match the annual report?* (Orchestrator + 2 agents on fictional sample files)
- **Monitoring:** live traces, latency, AI calls, tokens and guardrail actions

### About this demo
- **Free tier:** the first visit after a quiet period wakes the Space (about 1–2 minutes).
- **Shared quota:** the AI quota is shared by all visitors (a daily budget and a rate limit protect it). The suggested questions are saved, so they answer instantly.
- **Sample files only:** uploading files is turned off in the public demo. It works when you run FinSight locally.
- **Not investment advice.** Research and information only.
