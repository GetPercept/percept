"""Rules for what gets shared vs stays private."""


class SharePolicy:
    """Determines whether a node type should be synced to the team graph."""
    
    # Always shared (work context)
    SHARED_BY_DEFAULT = [
        "Project",        # repos, initiatives
        "PR",             # pull requests
        "Issue",          # github/linear issues
        "Ticket",         # support tickets
        "Decision",       # team decisions
        "Blocker",        # things blocking progress
        "Availability",   # calendar free/busy (not event details)
        "Deployment",     # deploys, releases
    ]
    
    # Never shared (private)
    NEVER_SHARED = [
        "Health",          # oura, biometrics
        "Biometric",       # sleep, HRV, readiness
        "PersonalEmail",   # personal email
        "DM",              # direct messages
        "Finance",         # trading, bank
        "Trading",         # polymarket, robinhood
        "Password",        # credentials
        "Credential",      # API keys
    ]
    
    # Shared on request (agent asks, human approves)
    ASK_FIRST = [
        "MeetingNotes",    # might contain sensitive
        "Document",        # depends on content
        "Conversation",    # work vs personal
    ]

    @classmethod
    def should_share(cls, node_type: str) -> str:
        """
        Returns sharing decision for a node type.
        
        Returns:
            "share" — automatically shared
            "block" — never shared  
            "ask"   — needs human approval
            "share" — unknown types default to shared (work context assumed)
        """
        if node_type in cls.NEVER_SHARED:
            return "block"
        if node_type in cls.ASK_FIRST:
            return "ask"
        if node_type in cls.SHARED_BY_DEFAULT:
            return "share"
        # Unknown types: default to share (work context assumed)
        # This is a deliberate choice — better to over-share work context
        # than to silently drop it. NEVER_SHARED is the hard boundary.
        return "share"
    
    @classmethod
    def filter_nodes(cls, nodes: list[dict], approved_types: set[str] = None) -> tuple[list[dict], list[dict]]:
        """
        Filter nodes into (shareable, blocked) based on policy.
        
        Args:
            nodes: List of node dicts with 'node_type' key
            approved_types: Set of ASK_FIRST types that were approved
        
        Returns:
            (shareable_nodes, blocked_nodes)
        """
        approved = approved_types or set()
        shareable = []
        blocked = []
        
        for node in nodes:
            decision = cls.should_share(node.get("node_type", ""))
            if decision == "share":
                shareable.append(node)
            elif decision == "ask" and node.get("node_type", "") in approved:
                shareable.append(node)
            else:
                blocked.append(node)
        
        return shareable, blocked
    
    @classmethod
    def scrub_properties(cls, node: dict) -> dict:
        """Remove any sensitive fields from node properties before sharing."""
        sensitive_keys = {
            "password", "secret", "token", "api_key", "credential",
            "ssn", "credit_card", "bank_account", "private_key",
        }
        props = node.get("properties", {})
        if isinstance(props, dict):
            scrubbed = {k: v for k, v in props.items() if k.lower() not in sensitive_keys}
            node = {**node, "properties": scrubbed}
        return node
