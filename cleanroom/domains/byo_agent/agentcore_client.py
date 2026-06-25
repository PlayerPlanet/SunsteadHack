"""Agent invocation interface for BYO-Agent vertical.

This module provides two implementations:
  1. AgentCoreInvoker: Real AWS Bedrock AgentCore integration (lazy-loaded, no import needed for tests)
  2. StubAgent: Deterministic test double that improves accuracy based on config (for offline curves)

Both implement the same `.invoke(prompt, config) -> {"result": str, "tokens": int}` interface.
DESIGN PRINCIPLE: The agent (contestant) is measured only by the referee (held-out labels + grader).
The agent can never see the test set — only the training split. Config sensitivity drives the curve.
"""

import hashlib


class AgentCoreInvoker:
    """Real AWS Bedrock AgentCore invoker for BYO agents.

    Boto3 and requests are lazy-imported so offline tests don't need AWS credentials.
    """

    def __init__(self, runtime_arn: str = None, endpoint_url: str = None, region: str = "us-east-1"):
        """Initialize the AgentCore invoker.

        Args:
            runtime_arn: ARN of the agent runtime in AWS Bedrock. E.g.,
                "arn:aws:bedrock-agentcore:us-east-1:123456789012:agent/my-agent-id/LIVE"
            endpoint_url: Optional HTTP endpoint URL for local/custom AgentCore (instead of AWS).
            region: AWS region (default: us-east-1). Ignored if endpoint_url is set.
        """
        self.runtime_arn = runtime_arn
        self.endpoint_url = endpoint_url
        self.region = region

    def invoke(self, prompt: str, config: dict) -> dict[str, any]:
        """Invoke the agent and return result + token count.

        Args:
            prompt: The input prompt to send to the agent.
            config: Agent configuration dict (e.g., {"system_prompt": "...", "temperature": 0.7}).

        Returns:
            {"result": str, "tokens": int} — the agent's response and token usage.

        Raises:
            RuntimeError: If boto3 is not installed (when using AWS).
            ValueError: If runtime_arn is not set and endpoint_url is not provided.
        """
        if self.endpoint_url:
            return self._invoke_http(prompt, config)
        else:
            return self._invoke_aws(prompt, config)

    def _invoke_aws(self, prompt: str, config: dict) -> dict[str, any]:
        """Invoke via AWS Bedrock AgentCore."""
        try:
            import boto3
        except ImportError:
            raise RuntimeError(
                "boto3 is required for AWS Bedrock AgentCore. Install with: pip install boto3"
            )

        if not self.runtime_arn:
            raise ValueError("runtime_arn must be set to invoke AWS Bedrock AgentCore")

        client = boto3.client("bedrock-agentcore", region_name=self.region)

        # Build the payload with config overrides merged into prompt context
        payload = {
            "prompt": prompt,
            "config": config,
        }

        response = client.invoke_agent_runtime(
            agentId=self.runtime_arn,
            payload=payload,
        )

        # Parse response (structure depends on Bedrock's actual response format)
        result_text = response.get("result", "")
        tokens = response.get("tokens", 0)

        return {"result": result_text, "tokens": tokens}

    def _invoke_http(self, prompt: str, config: dict) -> dict[str, any]:
        """Invoke via HTTP endpoint (local AgentCore or custom server)."""
        try:
            import requests
        except ImportError:
            raise RuntimeError(
                "requests is required for HTTP invocation. Install with: pip install requests"
            )

        response = requests.post(
            f"{self.endpoint_url}/invocations",
            json={"prompt": prompt, "config": config},
            timeout=30,
        )
        response.raise_for_status()

        data = response.json()
        return {"result": data.get("result", ""), "tokens": data.get("tokens", 0)}


class StubAgent:
    """Deterministic test agent for offline benchmarking — never needs AWS.

    Mimics a configurable agent where accuracy improves when:
      - system_prompt contains certain markers ("expert", "careful", "precise")
      - few_shot list is non-empty (examples improve reasoning)
      - temperature is lower (more deterministic)
      - top_p is lower (less diversity)

    DESIGN PRINCIPLE (Issue #28): This stub is the CONTESTANT being measured.
    The REFEREE is judge.py (which imports NO LLM client) + the held-out labels.
    The stub can never see the holdout data — only the train split during config proposals.
    """

    def __init__(self, quality_by_config: dict = None):
        """Initialize the stub agent.

        Args:
            quality_by_config: Optional dict mapping config hashes to accuracy floats.
                If provided, .invoke() returns accuracy based on config hash.
                If not provided, computes accuracy on-the-fly from config markers.
        """
        self._quality_cache = quality_by_config or {}

    def _hash_config(self, config: dict) -> str:
        """Hash a config dict for caching."""
        import json
        s = json.dumps(config, sort_keys=True)
        return hashlib.sha256(s.encode()).hexdigest()[:8]

    def invoke(self, prompt: str, config: dict) -> dict[str, any]:
        """Invoke the stub and return a deterministic response.

        The response improves (becomes correct more often) based on config quality.

        Args:
            prompt: The input prompt (e.g., "What is 2+2?").
            config: Agent configuration dict.

        Returns:
            {"result": str, "tokens": int} — a response and token count.
        """
        # Compute quality (1.0 = perfect, 0.0 = worst)
        error_rate = self._compute_accuracy(config)
        quality = 1.0 - error_rate

        # Try to extract the expected answer from prompt if it's arithmetic.
        # This makes responses sometimes correct, proportional to config quality.
        result_text = self._try_answer_prompt(prompt, quality)

        # Token count is deterministic based on config complexity
        tokens = 100 + len(str(config)) // 10

        return {"result": result_text, "tokens": tokens}

    def _try_answer_prompt(self, prompt: str, quality: float) -> str:
        """Try to answer an arithmetic prompt, with probability = quality.

        If quality is high enough, try to answer correctly; otherwise return
        a wrong/no-answer response.
        """
        import random

        # Use quality to seed determinism (same prompt + quality = same answer).
        rng = random.Random(hash((prompt, round(quality, 2))) % (2**31))

        # With probability = quality, try to parse and answer correctly.
        if rng.random() < quality:
            # Try to extract arithmetic: "What is 2+2?" -> answer "4"
            import re
            match = re.search(r'(\d+)\s*([+\-*/])\s*(\d+)', prompt)
            if match:
                a, op, b = int(match.group(1)), match.group(2), int(match.group(3))
                try:
                    if op == '+':
                        return str(a + b)
                    elif op == '-':
                        return str(a - b)
                    elif op == '*':
                        return str(a * b)
                    elif op == '/':
                        return str(a // b) if a % b == 0 else str(a / b)
                except:
                    pass

        # Otherwise, return an uncertain/wrong response.
        return "I'm not sure"

    def _compute_accuracy(self, config: dict) -> float:
        """Compute accuracy (lower=better error rate) from config features.

        The curve MUST descend when scripted proposer improves the config,
        so return error_rate (1 - accuracy), not accuracy itself.
        """
        cfg_hash = self._hash_config(config)
        if cfg_hash in self._quality_cache:
            return self._quality_cache[cfg_hash]

        # Base error rate: 0.5 (50% error, 50% accuracy — neutral baseline)
        error_rate = 0.5

        # Improve (reduce error) based on config markers
        system_prompt = config.get("system_prompt", "")
        few_shot = config.get("few_shot", [])
        temperature = config.get("temperature", 1.0)
        top_p = config.get("top_p", 1.0)

        # System prompt quality markers (large bonuses for strong improvements)
        if "expert" in system_prompt.lower():
            error_rate -= 0.20
        if "careful" in system_prompt.lower():
            error_rate -= 0.15
        if "precise" in system_prompt.lower():
            error_rate -= 0.15

        # Few-shot boost (each example helps significantly)
        if few_shot:
            error_rate -= min(0.30, len(few_shot) * 0.15)

        # Temperature penalty (higher = more random = worse)
        if temperature < 0.5:
            error_rate -= 0.20
        elif temperature > 1.5:
            error_rate += 0.10

        # Top-p penalty
        if top_p < 0.5:
            error_rate -= 0.20
        elif top_p < 0.95:
            error_rate -= 0.10

        # Ensure in [0, 1]
        error_rate = max(0.0, min(1.0, error_rate))

        return error_rate
