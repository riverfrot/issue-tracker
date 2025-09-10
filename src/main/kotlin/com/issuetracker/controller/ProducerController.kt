package com.issuetracker.controller

import com.issuetracker.service.WorkflowProducer
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.*

data class TriggerRequest(
    val issueId: String,
    val repository: String,
    val title: String,
    val description: String,
    val labels: List<String> = emptyList()
)

data class TriggerResponse(
    val success: Boolean,
    val message: String,
    val workflowId: String? = null
)

@RestController
@RequestMapping("/api/v1")
class ProducerController(
    private val workflowProducer: WorkflowProducer
) {
    
    @PostMapping("/trigger")
    fun triggerWorkflow(@RequestBody request: TriggerRequest): ResponseEntity<TriggerResponse> {
        return try {
            val workflowId = workflowProducer.sendWorkflowEvent(request)
            ResponseEntity.ok(
                TriggerResponse(
                    success = true,
                    message = "Workflow triggered successfully",
                    workflowId = workflowId
                )
            )
        } catch (e: Exception) {
            ResponseEntity.internalServerError().body(
                TriggerResponse(
                    success = false,
                    message = "Failed to trigger workflow: ${e.message}"
                )
            )
        }
    }
    
    @GetMapping("/health")
    fun health(): ResponseEntity<Map<String, String>> {
        return ResponseEntity.ok(mapOf("status" to "UP"))
    }
}