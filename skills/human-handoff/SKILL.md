---
name: human-handoff
description: Seamlessly transitions conversation from AI to human staff when user requests a representative, complexity exceeds AI scope, or safety guardrails trigger.
version: 1.0.0
scope: all
---

# Human Handoff Skill

## Objective
Recognize when a human representative is needed, pause automatic replies if configured, notify the customer that an agent has been summoned, and draft a concise handover context for the inbox.

## Guidelines
1. Trigger human handoff immediately when:
   - The user explicitly asks for a human ("talk to a human", "speak to staff", "call me").
   - The inquiry involves legal threats, severe harassment, or explicit security concerns.
   - The AI has low confidence or two consecutive failed clarification turns.
   - Sensitive financial transactions or non-standard refund approvals are requested.
2. Reply politely with a reassuring acknowledgment: let the user know a team member is reviewing the conversation.
3. Mark decision as `handoff`.
