import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from kafka import KafkaConsumer, KafkaProducer
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage, HumanMessage
from pydantic import BaseModel
import structlog

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

class WorkflowState(BaseModel):
    workflow_id: str
    issue_id: str
    repository: str
    title: str
    description: str
    labels: List[str]
    messages: List[BaseMessage] = []
    analysis_result: Optional[str] = None
    code_solution: Optional[str] = None
    pr_content: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    error_message: Optional[str] = None

class GitHubIssueWorkflow:
    def __init__(self, kafka_config: Dict[str, Any]):
        self.kafka_config = kafka_config
        self.producer = KafkaProducer(
            bootstrap_servers=kafka_config['bootstrap_servers'],
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
        self.consumer = KafkaConsumer(
            'workflow-events',
            bootstrap_servers=kafka_config['bootstrap_servers'],
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            group_id='langgraph-worker',
            auto_offset_reset='earliest'
        )
        
        self.workflow = self._build_workflow()
        
    def _build_workflow(self) -> StateGraph:
        workflow = StateGraph(WorkflowState)
        
        # Add nodes
        workflow.add_node("analyze_issue", self.analyze_issue)
        workflow.add_node("generate_solution", self.generate_solution)
        workflow.add_node("create_pr_draft", self.create_pr_draft)
        workflow.add_node("handle_error", self.handle_error)
        
        # Set entry point
        workflow.set_entry_point("analyze_issue")
        
        # Add edges
        workflow.add_conditional_edges(
            "analyze_issue",
            self._should_continue,
            {
                "continue": "generate_solution",
                "error": "handle_error"
            }
        )
        
        workflow.add_conditional_edges(
            "generate_solution",
            self._should_continue,
            {
                "continue": "create_pr_draft",
                "error": "handle_error"
            }
        )
        
        workflow.add_edge("create_pr_draft", END)
        workflow.add_edge("handle_error", END)
        
        return workflow.compile()
    
    def analyze_issue(self, state: WorkflowState) -> WorkflowState:
        """Analyze GitHub issue to understand the problem"""
        try:
            logger.info("Analyzing issue", workflow_id=state.workflow_id, issue_id=state.issue_id)
            
            # Simulate AI analysis
            analysis_prompt = f"""
            Analyze this GitHub issue:
            Title: {state.title}
            Description: {state.description}
            Labels: {', '.join(state.labels)}
            
            Provide a structured analysis of:
            1. Problem type (bug, feature, documentation, etc.)
            2. Affected components
            3. Suggested approach
            4. Complexity level
            """
            
            # In real implementation, this would call an LLM
            state.analysis_result = f"Analysis completed for issue {state.issue_id}: " \
                                   f"Type: {'Bug' if 'bug' in state.labels else 'Feature'}, " \
                                   f"Complexity: {'High' if 'critical' in state.labels else 'Medium'}"
            
            state.messages.append(HumanMessage(content=analysis_prompt))
            
            logger.info("Issue analysis completed", 
                       workflow_id=state.workflow_id, 
                       analysis=state.analysis_result)
            
            return state
            
        except Exception as e:
            logger.error("Issue analysis failed", 
                        workflow_id=state.workflow_id, 
                        error=str(e))
            state.error_message = f"Analysis failed: {str(e)}"
            return state
    
    def generate_solution(self, state: WorkflowState) -> WorkflowState:
        """Generate code solution based on analysis"""
        try:
            logger.info("Generating solution", workflow_id=state.workflow_id)
            
            # Simulate code generation
            if state.analysis_result:
                state.code_solution = f"""
                // Generated solution for {state.issue_id}
                // Analysis: {state.analysis_result}
                
                public class IssueFixFor{state.issue_id.replace('-', '')} {{
                    // TODO: Implement solution based on analysis
                    public void fixIssue() {{
                        // Solution implementation here
                    }}
                }}
                """
            
            logger.info("Solution generated", 
                       workflow_id=state.workflow_id,
                       solution_length=len(state.code_solution) if state.code_solution else 0)
            
            return state
            
        except Exception as e:
            logger.error("Solution generation failed", 
                        workflow_id=state.workflow_id, 
                        error=str(e))
            state.error_message = f"Solution generation failed: {str(e)}"
            return state
    
    def create_pr_draft(self, state: WorkflowState) -> WorkflowState:
        """Create PR draft with generated solution"""
        try:
            logger.info("Creating PR draft", workflow_id=state.workflow_id)
            
            state.pr_content = f"""
            ## Fix for Issue #{state.issue_id}
            
            ### Problem
            {state.title}
            
            ### Analysis
            {state.analysis_result}
            
            ### Solution
            This PR addresses the issue by implementing the following changes:
            
            ```
            {state.code_solution}
            ```
            
            ### Testing
            - [ ] Unit tests added/updated
            - [ ] Integration tests passed
            - [ ] Manual testing completed
            
            Fixes #{state.issue_id}
            """
            
            logger.info("PR draft created", workflow_id=state.workflow_id)
            
            return state
            
        except Exception as e:
            logger.error("PR draft creation failed", 
                        workflow_id=state.workflow_id, 
                        error=str(e))
            state.error_message = f"PR creation failed: {str(e)}"
            return state
    
    def handle_error(self, state: WorkflowState) -> WorkflowState:
        """Handle workflow errors with retry logic"""
        logger.warning("Handling workflow error", 
                      workflow_id=state.workflow_id,
                      error=state.error_message,
                      retry_count=state.retry_count)
        
        if state.retry_count < state.max_retries:
            state.retry_count += 1
            logger.info("Scheduling retry", 
                       workflow_id=state.workflow_id, 
                       retry_count=state.retry_count)
            # In real implementation, this would reschedule the workflow
        else:
            logger.error("Max retries exceeded, sending to DLQ", 
                        workflow_id=state.workflow_id)
            self._send_to_dlq(state)
        
        return state
    
    def _should_continue(self, state: WorkflowState) -> str:
        """Determine if workflow should continue or handle error"""
        return "error" if state.error_message else "continue"
    
    def _send_to_dlq(self, state: WorkflowState):
        """Send failed message to Dead Letter Queue"""
        dlq_message = {
            "workflow_id": state.workflow_id,
            "issue_id": state.issue_id,
            "error": state.error_message,
            "retry_count": state.retry_count,
            "timestamp": datetime.now().isoformat(),
            "original_state": state.dict()
        }
        
        self.producer.send('dlq', dlq_message)
        logger.error("Message sent to DLQ", workflow_id=state.workflow_id)
    
    def _send_result(self, state: WorkflowState):
        """Send workflow result to processed topic"""
        start_time = time.time()
        
        status = "SUCCESS" if not state.error_message else "FAILURE"
        
        result = {
            "workflow_id": state.workflow_id,
            "issue_id": state.issue_id,
            "status": status,
            "result": {
                "analysis": state.analysis_result,
                "solution": state.code_solution,
                "pr_content": state.pr_content
            } if status == "SUCCESS" else None,
            "error_message": state.error_message,
            "retry_count": state.retry_count,
            "processing_time_ms": int((time.time() - start_time) * 1000),
            "timestamp": datetime.now().isoformat()
        }
        
        self.producer.send('workflow-processed', result)
        logger.info("Workflow result sent", 
                   workflow_id=state.workflow_id, 
                   status=status)
    
    def process_message(self, message: Dict[str, Any]):
        """Process a single workflow message"""
        try:
            state = WorkflowState(
                workflow_id=message['workflowId'],
                issue_id=message['issueId'],
                repository=message['repository'],
                title=message['title'],
                description=message['description'],
                labels=message.get('labels', []),
                retry_count=message.get('retryCount', 0)
            )
            
            logger.info("Starting workflow", workflow_id=state.workflow_id)
            
            # Execute workflow
            final_state = self.workflow.invoke(state)
            
            # Send result
            self._send_result(final_state)
            
        except Exception as e:
            logger.error("Failed to process message", error=str(e), message=message)
            # Create error state and send to DLQ
            error_state = WorkflowState(
                workflow_id=message.get('workflowId', 'unknown'),
                issue_id=message.get('issueId', 'unknown'),
                repository=message.get('repository', 'unknown'),
                title=message.get('title', ''),
                description=message.get('description', ''),
                error_message=f"Message processing failed: {str(e)}"
            )
            self._send_to_dlq(error_state)
    
    def start_consumer(self):
        """Start consuming messages from Kafka"""
        logger.info("Starting LangGraph workflow consumer")
        
        try:
            for message in self.consumer:
                logger.debug("Received message", 
                            topic=message.topic, 
                            partition=message.partition, 
                            offset=message.offset)
                
                self.process_message(message.value)
                
        except KeyboardInterrupt:
            logger.info("Shutting down consumer")
        finally:
            self.consumer.close()
            self.producer.close()

def main():
    kafka_config = {
        'bootstrap_servers': os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
    }
    
    workflow_processor = GitHubIssueWorkflow(kafka_config)
    workflow_processor.start_consumer()

if __name__ == "__main__":
    main()