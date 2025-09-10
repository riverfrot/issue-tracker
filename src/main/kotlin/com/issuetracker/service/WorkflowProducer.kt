package com.issuetracker.service

import com.fasterxml.jackson.databind.ObjectMapper
import com.issuetracker.controller.TriggerRequest
import org.slf4j.LoggerFactory
import org.springframework.kafka.core.KafkaTemplate
import org.springframework.stereotype.Service
import java.time.Instant
import java.util.*

data class WorkflowEvent(
    val workflowId: String,
    val issueId: String,
    val repository: String,
    val title: String,
    val description: String,
    val labels: List<String>,
    val timestamp: Instant,
    val retryCount: Int = 0
)

@Service
class WorkflowProducer(
    private val kafkaTemplate: KafkaTemplate<String, String>,
    private val objectMapper: ObjectMapper
) {
    private val logger = LoggerFactory.getLogger(WorkflowProducer::class.java)
    private val topicName = "workflow-events"
    
    fun sendWorkflowEvent(request: TriggerRequest): String {
        val workflowId = UUID.randomUUID().toString()
        
        val event = WorkflowEvent(
            workflowId = workflowId,
            issueId = request.issueId,
            repository = request.repository,
            title = request.title,
            description = request.description,
            labels = request.labels,
            timestamp = Instant.now()
        )
        
        val eventJson = objectMapper.writeValueAsString(event)
        
        logger.info("Sending workflow event: workflowId={}, issueId={}", workflowId, request.issueId)
        
        kafkaTemplate.send(topicName, workflowId, eventJson)
            .whenComplete { result, ex ->
                if (ex != null) {
                    logger.error("Failed to send workflow event: workflowId={}", workflowId, ex)
                } else {
                    logger.info("Successfully sent workflow event: workflowId={}, offset={}", 
                        workflowId, result?.recordMetadata?.offset())
                }
            }
        
        return workflowId
    }
}