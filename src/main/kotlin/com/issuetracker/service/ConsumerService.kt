package com.issuetracker.service

import com.fasterxml.jackson.databind.ObjectMapper
import org.slf4j.LoggerFactory
import org.springframework.kafka.annotation.KafkaListener
import org.springframework.stereotype.Service

data class WorkflowResult(
    val workflowId: String,
    val issueId: String,
    val status: String,
    val result: String?,
    val errorMessage: String?,
    val processingTimeMs: Long,
    val timestamp: String
)

@Service
class ConsumerService(
    private val objectMapper: ObjectMapper
) {
    private val logger = LoggerFactory.getLogger(ConsumerService::class.java)
    
    @KafkaListener(topics = ["workflow-processed"])
    fun handleWorkflowResult(message: String) {
        try {
            val result = objectMapper.readValue(message, WorkflowResult::class.java)
            
            logger.info("Received workflow result: workflowId={}, status={}", 
                result.workflowId, result.status)
            
            when (result.status) {
                "SUCCESS" -> handleSuccessResult(result)
                "FAILURE" -> handleFailureResult(result)
                "RETRY" -> handleRetryResult(result)
                else -> logger.warn("Unknown workflow status: {}", result.status)
            }
            
        } catch (e: Exception) {
            logger.error("Failed to process workflow result message: {}", message, e)
        }
    }
    
    @KafkaListener(topics = ["dlq"])
    fun handleDlqMessage(message: String) {
        logger.error("Received DLQ message - requires manual intervention: {}", message)
        // TODO: Send alert to monitoring system
        // TODO: Store in database for manual review dashboard
    }
    
    private fun handleSuccessResult(result: WorkflowResult) {
        logger.info("Workflow completed successfully: workflowId={}, processingTime={}ms", 
            result.workflowId, result.processingTimeMs)
        // TODO: Update database with success status
        // TODO: Send notification to user
    }
    
    private fun handleFailureResult(result: WorkflowResult) {
        logger.warn("Workflow failed: workflowId={}, error={}", 
            result.workflowId, result.errorMessage)
        // TODO: Update database with failure status
        // TODO: Check if retry is needed
    }
    
    private fun handleRetryResult(result: WorkflowResult) {
        logger.info("Workflow scheduled for retry: workflowId={}", result.workflowId)
        // TODO: Schedule retry with backoff
    }
}