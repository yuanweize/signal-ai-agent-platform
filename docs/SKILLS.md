# Progressive Skills Architecture

## 1. Why Progressive Skills?

Monolithic system prompts that include instructions for every conceivable scenario suffer from:
1. **Severe Token Waste**: Incurring high prompt fees on every turn.
2. **Instruction Drift & Confusion**: Conflicting directives degrade model adherence.
3. **Context Dilution**: Less space available for user conversation history and retrieved knowledge.

Signal Market Bot solves this with a **Two-Tier Progressive Skills System**.

---

## 2. Structure of a Skill

Each skill resides in `skills/<skill-name>/SKILL.md` with YAML frontmatter:

```markdown
---
name: product-sales
description: Product catalog search, pricing inquiries, order placement and stock availability.
user_facing: false
requires_tools:
  - search_products
scopes:
  - dm
  - group
---

# Product Sales & Catalog Guidelines
- Always format prices in the requested currency ($ or CZK).
- When a user asks about items in stock, search the product catalog before replying.
```

---

## 3. Two-Tier Loading Strategy

1. **Lightweight Metadata Indexing**: At startup, `SkillRegistry` loads only frontmatter metadata (`name`, `description`, `scopes`, `tools`). This tiny index fits in memory and takes negligible context.
2. **Intent Classification & On-Demand Injection**:
   - The `select_skills` node evaluates the user's turn against skill descriptions and domain keywords.
   - Only the bodies of selected skills are dynamically injected into the system prompt.
   - For an average inquiry, prompt size is reduced by **70%–80%** compared to loading all skills.

---

## 4. Default Built-in Skills

| Skill | Purpose | Scopes |
| :--- | :--- | :--- |
| `customer-support` | Friendly support tone, FAQ answering, inquiry qualification | DM, Group |
| `product-sales` | Product recommendations, pricing, inventory checks | DM, Group |
| `order-status` | Order status lookup and shipping updates | DM |
| `complaints` | Empathetic complaint intake and policy-compliant escalation | DM |
| `human-handoff` | Seamless transfer to human operator when requested | DM, Group |
| `group-moderation` | Respectful group chat behavior and spam prevention | Group only |
