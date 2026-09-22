# Model Context Protocol (MCP) & Tool Governance

## 1. Tool Permission Hierarchy

To prevent unauthorized actions and data exfiltration, every tool registered in `app.ai.tools.registry.ToolRegistry` declares an explicit `ToolPermission`:

```python
@dataclass
class ToolPermission:
    name: str
    is_read_only: bool = True
    requires_human_approval: bool = False
    allowed_roles: list[str] = field(default_factory=lambda: ["user", "admin"])
```

### Safety Rules
- **Read-Only Tools** (e.g., `search_products`, `get_inventory`): May be executed autonomously by the AI runtime.
- **Write / Destructive Tools** (e.g., `trigger_sample_refund`, `update_order_status`): Blocked with `requires_approval: true`. The agent forces a `draft_for_human` decision, generating a draft for an operator to review and manually execute.

---

## 2. SSRF Guardrails for Remote Tools & MCP Endpoints

All outgoing URLs registered as MCP servers or webhooks pass through `app.ai.tools.governance.validate_outbound_url`:
- **Private IP Blocking**: Addresses resolving to loopback (`127.0.0.1`, `localhost`), link-local (`169.254.0.0/16`), and private RFC 1918 subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`) are strictly rejected.
- **Scheme Validation**: Only `http` and `https` protocols are permitted.

---

## 3. Dynamic MCP Tool Integration

The platform provides `MCPClientManager` supporting dynamic tool registration from standard MCP servers:
- Discovers remote tools conforming to the Model Context Protocol specification.
- Normalizes tool input/output JSON schemas.
- Wraps remote tools with the platform's permission matrix and timeout bounds.
