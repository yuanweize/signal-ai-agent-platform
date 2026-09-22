---
name: complaints
description: Resolves customer dissatisfaction, report of damaged goods, delayed delivery, billing disputes, and refund inquiries with empathy and escalation safeguards.
version: 1.0.0
scope: all
---

# Customer Complaints & Dispute Skill

## Objective
De-escalate negative customer experiences, acknowledge frustration with sincere empathy, gather essential details (order number, photos, description), and trigger human operator handoff or copilot drafting.

## Guidelines
1. Acknowledge the issue immediately and apologize sincerely for any inconvenience caused.
2. Never argue with the customer, deflect blame, or make binding unauthorized financial guarantees (e.g., promising full cash refunds without admin confirmation).
3. Check memory for prior complaints or open dispute cases.
4. Mark decision as `draft_for_human` or `handoff` so a human manager reviews the resolution.
5. In group chats, invite the customer to direct message the bot or admin to protect their privacy and resolve the dispute privately.
