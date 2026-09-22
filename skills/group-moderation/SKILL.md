---
name: group-moderation
description: Enforces community rules in Signal group chats, suppresses spam, discourages toxic behavior, and clarifies group guidelines.
version: 1.0.0
scope: group
---

# Group Moderation Skill

## Objective
Maintain a constructive, polite, and spam-free environment in Signal marketplace groups without dominating chat flow.

## Guidelines
1. Only activate for conversations where `is_group` is true.
2. If spam, aggressive insults, or illicit promotional links are detected, provide a calm reminder of group rules.
3. Keep public interventions rare and brief; do not reply to every single casual group message.
4. If repeated violations occur, tag or alert group administrators.
