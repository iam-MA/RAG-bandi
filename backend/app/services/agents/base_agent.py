"""
Base Agent class that all specialized agents inherit from.
Provides common functionality: API calls, retries, logging.
"""
import asyncio
import json
from typing import Any, Optional, Type, TypeVar
from openai import AsyncOpenAI
from pydantic import BaseModel
from datetime import datetime

T = TypeVar('T', bound=BaseModel)


class AgentResult:
    """Result of an agent execution."""
    def __init__(
        self,
        success: bool,
        data: Any = None,
        error: Optional[str] = None,
        retries_used: int = 0,
        raw_response: Optional[str] = None
    ):
        self.success = success
        self.data = data
        self.error = error
        self.retries_used = retries_used
        self.raw_response = raw_response
        self.timestamp = datetime.now()


class BaseAgent:
    """
    Base class for all agents in the pipeline.
    Handles API calls, retries, and structured output parsing.
    """
    
    def __init__(
        self,
        client: AsyncOpenAI,
        model: str = "gpt-4o-mini",
        max_retries: int = 3,
        temperature: float = 0.1
    ):
        self.client = client
        self.model = model
        self.max_retries = max_retries
        self.temperature = temperature
        self.name = self.__class__.__name__
    
    def get_system_prompt(self) -> str:
        """Override in subclasses to provide agent-specific system prompt."""
        return "Sei un analista esperto di bandi di gara italiani."
    
    def get_user_prompt(self, **kwargs) -> str:
        """Override in subclasses to build the user prompt."""
        raise NotImplementedError("Subclasses must implement get_user_prompt")
    
    async def call_llm(
        self,
        user_prompt: str,
        system_prompt: Optional[str] = None,
        json_mode: bool = True,
        response_model: Optional[Type[T]] = None
    ) -> AgentResult:
        """
        Make an LLM API call with retries and error handling.
        
        Args:
            user_prompt: The prompt to send
            system_prompt: Override default system prompt
            json_mode: Whether to request JSON output
            response_model: Pydantic model to parse response into
            
        Returns:
            AgentResult with success/failure and parsed data
        """
        system = system_prompt or self.get_system_prompt()
        
        for attempt in range(self.max_retries):
            try:
                kwargs = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": self.temperature
                }
                
                if json_mode:
                    kwargs["response_format"] = {"type": "json_object"}
                
                response = await self.client.chat.completions.create(**kwargs)
                content = response.choices[0].message.content
                
                # Parse JSON if requested
                if json_mode:
                    try:
                        parsed = json.loads(content)
                        
                        # Validate with Pydantic if model provided
                        if response_model:
                            parsed = response_model.model_validate(parsed)
                        
                        return AgentResult(
                            success=True,
                            data=parsed,
                            retries_used=attempt,
                            raw_response=content
                        )
                    except json.JSONDecodeError as e:
                        if attempt < self.max_retries - 1:
                            continue  # Retry
                        return AgentResult(
                            success=False,
                            error=f"JSON parsing failed: {e}",
                            raw_response=content,
                            retries_used=attempt
                        )
                    except Exception as e:
                        if attempt < self.max_retries - 1:
                            continue
                        return AgentResult(
                            success=False,
                            error=f"Validation failed: {e}",
                            raw_response=content,
                            retries_used=attempt
                        )
                else:
                    return AgentResult(
                        success=True,
                        data=content.strip(),
                        retries_used=attempt,
                        raw_response=content
                    )
                    
            except Exception as e:
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(1 * (attempt + 1))  # Exponential backoff
                    continue
                return AgentResult(
                    success=False,
                    error=f"API call failed after {attempt + 1} attempts: {e}",
                    retries_used=attempt
                )
        
        return AgentResult(
            success=False,
            error="Max retries exceeded",
            retries_used=self.max_retries
        )
    
    async def run(self, **kwargs) -> AgentResult:
        """
        Execute the agent. Override in subclasses for custom logic.
        Default implementation: build prompt and call LLM.
        """
        user_prompt = self.get_user_prompt(**kwargs)
        return await self.call_llm(user_prompt)
