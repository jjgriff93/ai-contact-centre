from typing import Dict, List

from azure.ai.evaluation import AzureAIProject


class TestSuiteEvaluator:

    def __init__(self, azure_ai_client: AzureAIProject):
        self.azure_ai_client = azure_ai_client

    def evaluate_scenario(
        self,
        name: str,
        function_calls: List[Dict[str, object]],
        expected_function_calls: List[Dict[str, object]],
        unexpected_function_calls: List[Dict[str, object]]
    ) -> None:
        """Evaluate the function calls against expected and unexpected calls."""
        # TODO: implement
        pass
