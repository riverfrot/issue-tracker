package com.issuetracker.service

import com.fasterxml.jackson.databind.ObjectMapper
import org.slf4j.LoggerFactory
import org.springframework.context.annotation.Bean
import org.springframework.stereotype.Service
import java.util.function.Function

@Service
class StreamProcessor(
    private val objectMapper: ObjectMapper
) {
    private val logger = LoggerFactory.getLogger(StreamProcessor::class.java)
    
    @Bean
    fun processWorkflowEvent(): Function<String, String> = Function { eventJson ->
        processEvent(eventJson)
    }
    
    private fun processEvent(eventJson: String): String {
        return try {
            val event = objectMapper.readValue(eventJson, WorkflowEvent::class.java)
            
            logger.info("Processing workflow event through SCDF: workflowId={}", event.workflowId)
            
            // Add metadata and routing information
            val enrichedEvent = event.copy(
                timestamp = java.time.Instant.now()
            )
            
            // Transform the event for downstream processing
            val transformedEvent = mapOf(
                "workflowId" to enrichedEvent.workflowId,
                "issueId" to enrichedEvent.issueId,
                "repository" to enrichedEvent.repository,
                "title" to enrichedEvent.title,
                "description" to enrichedEvent.description,
                "labels" to enrichedEvent.labels,
                "timestamp" to enrichedEvent.timestamp.toString(),
                "retryCount" to enrichedEvent.retryCount,
                "processingStage" to "SCDF_PROCESSED",
                "priority" to calculatePriority(enrichedEvent)
            )
            
            objectMapper.writeValueAsString(transformedEvent)
            
        } catch (e: Exception) {
            logger.error("Failed to process workflow event: {}", eventJson, e)
            // Create error event for DLQ
            val errorEvent = mapOf(
                "originalEvent" to eventJson,
                "error" to e.message,
                "timestamp" to java.time.Instant.now().toString(),
                "processingStage" to "SCDF_ERROR"
            )
            objectMapper.writeValueAsString(errorEvent)
        }
    }
    
    private fun calculatePriority(event: WorkflowEvent): String {
        return when {
            event.labels.contains("critical") || event.labels.contains("urgent") -> "HIGH"
            event.labels.contains("bug") -> "MEDIUM"
            else -> "LOW"
        }
    }
}