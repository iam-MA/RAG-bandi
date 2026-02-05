"""
Analysis Pipeline: Orchestrates the multi-agent extraction pipeline.

Steps:
1. Analyzer Agent - Understand document structure
2. Planner Agent - Create extraction plan
3. Executor Agents - Extract specific information (parallel)
4. Aggregator Agent - Combine and deduplicate insights
5. Validator Agent - Quality check
"""
import asyncio
from typing import List, Dict, Any, Tuple, Optional
from openai import AsyncOpenAI
from datetime import datetime, timezone

from app.config import get_settings
from app.services.agents import (
    AnalyzerAgent,
    PlannerAgent,
    AggregatorAgent,
    ValidatorAgent,
    get_executor,
    ExtractionResult,
    ValidationResult,
    DocumentProfile,
    ExtractionPlan,
)


class AnalysisPipeline:
    """
    Orchestrates the multi-agent tender analysis pipeline.
    
    Usage:
        pipeline = AnalysisPipeline()
        result, validation = await pipeline.run(document_text, "bando.md")
    """
    
    def __init__(
        self,
        model: str = "gpt-4o-mini",
        max_concurrent_executors: int = 3
    ):
        """
        Initialize the pipeline.
        
        Args:
            model: OpenAI model to use
            max_concurrent_executors: Max parallel executor agents
        """
        settings = get_settings()
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = model
        self.max_concurrent = max_concurrent_executors
        
        # Initialize agents
        self.analyzer = AnalyzerAgent(self.client, model)
        self.planner = PlannerAgent(self.client, model)
        self.aggregator = AggregatorAgent(self.client, model)
        self.validator = ValidatorAgent(self.client, model)
    
    async def _run_executors_parallel(
        self,
        plan: ExtractionPlan,
        document: str,
        profile: DocumentProfile
    ) -> Dict[str, List[Dict]]:
        """
        Run executor agents in parallel based on the plan.
        
        Args:
            plan: Extraction plan from planner
            document: Full document text
            profile: Document profile from analyzer
            
        Returns:
            Dict mapping agent_type to list of extracted insights
        """
        semaphore = asyncio.Semaphore(self.max_concurrent)
        results: Dict[str, List[Dict]] = {}
        
        async def run_task(task):
            async with semaphore:
                agent_type = task.agent_type
                executor = get_executor(agent_type, self.client, self.model)
                
                # Get relevant sections text from document
                # For now, we pass the full document since section extraction is not implemented
                # TODO: Implement section extraction based on profile.sections
                sections_text = document
                
                # Run extraction
                result = await executor.run(sections_text, task.focus_areas)
                
                if result.success and isinstance(result.data, dict):
                    insights = result.data.get("insights", [])
                    return agent_type, insights
                return agent_type, []
        
        # Run all tasks
        tasks = [run_task(task) for task in plan.tasks]
        task_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Collect results
        for task_result in task_results:
            if isinstance(task_result, Exception):
                print(f"Executor error: {task_result}")
                continue
            agent_type, insights = task_result
            if agent_type in results:
                results[agent_type].extend(insights)
            else:
                results[agent_type] = insights
        
        return results
    
    async def run(
        self,
        document: str,
        document_name: str = "document.md"
    ) -> Tuple[ExtractionResult, ValidationResult]:
        """
        Run the full analysis pipeline on a document.
        
        Args:
            document: Full markdown text of the tender document
            document_name: Name of the document for tracking
            
        Returns:
            Tuple of (ExtractionResult, ValidationResult)
        """
        print(f"  [Pipeline] Starting analysis of {document_name}...")
        
        # Step 1: Analyze document structure
        print(f"  [1/5] Analyzing document structure...")
        analyzer_result = await self.analyzer.run(document)
        
        if not analyzer_result.success:
            raise RuntimeError(f"Analyzer failed: {analyzer_result.error}")
        
        profile: DocumentProfile = analyzer_result.data
        print(f"        Sector: {profile.sector}, Complexity: {profile.complexity}, Sections: {len(profile.sections)}")
        
        # Step 2: Create extraction plan
        print(f"  [2/5] Creating extraction plan...")
        planner_result = await self.planner.run(profile)
        
        if not planner_result.success:
            raise RuntimeError(f"Planner failed: {planner_result.error}")
        
        plan: ExtractionPlan = planner_result.data
        print(f"        Strategy: {plan.strategy[:50]}..., Tasks: {len(plan.tasks)}")
        
        # Step 3: Execute extraction (parallel)
        print(f"  [3/5] Running {len(plan.tasks)} extraction tasks (parallel)...")
        executor_results = await self._run_executors_parallel(plan, document, profile)
        
        total_insights = sum(len(v) for v in executor_results.values())
        print(f"        Extracted {total_insights} raw insights")
        
        # Step 4: Aggregate results
        print(f"  [4/5] Aggregating and deduplicating...")
        extraction_result = self.aggregator.aggregate(
            executor_results=executor_results,
            profile=profile,
            plan=plan,
            document_name=document_name
        )
        print(f"        Final insights: {len(extraction_result.insights)}")
        
        # Step 5: Validate
        print(f"  [5/5] Validating extraction quality...")
        validator_result = await self.validator.run(extraction_result)
        
        if not validator_result.success:
            # Still return result but with empty validation
            validation = ValidationResult(
                quality_score=0.5,
                is_complete=False,
                summary="Validation failed"
            )
        else:
            validation: ValidationResult = validator_result.data
        
        print(f"        Quality score: {validation.quality_score:.2f}, Complete: {validation.is_complete}")
        
        return extraction_result, validation


async def run_pipeline_for_tender(
    document_text: str,
    document_name: str = "document.md"
) -> Tuple[ExtractionResult, ValidationResult]:
    """
    Convenience function to run the pipeline.
    
    Args:
        document_text: Full markdown text
        document_name: Document name for tracking
        
    Returns:
        Tuple of (ExtractionResult, ValidationResult)
    """
    pipeline = AnalysisPipeline()
    return await pipeline.run(document_text, document_name)
