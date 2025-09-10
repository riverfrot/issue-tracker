import json
import pytest
import time
from kafka import KafkaProducer, KafkaConsumer
from kafka.errors import KafkaTimeoutError
import docker
import requests

class TestDLQProcessing:
    @pytest.fixture(scope="session")
    def kafka_setup(self):
        """Setup Kafka for testing"""
        client = docker.from_env()
        
        # Start Kafka containers (assuming docker-compose is running)
        # In real implementation, you might want to use testcontainers
        
        producer = KafkaProducer(
            bootstrap_servers=['localhost:9092'],
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
        
        consumer = KafkaConsumer(
            'dlq',
            bootstrap_servers=['localhost:9092'],
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            group_id='test-dlq-group',
            auto_offset_reset='latest',
            consumer_timeout_ms=5000
        )
        
        yield producer, consumer
        
        producer.close()
        consumer.close()
    
    def test_failed_workflow_goes_to_dlq(self, kafka_setup):
        """Test that failed workflows are sent to DLQ"""
        producer, dlq_consumer = kafka_setup
        
        # Send a malformed message that should cause processing to fail
        malformed_message = {
            "workflowId": "test-workflow-001",
            "issueId": "invalid-issue",
            "repository": "test/repo",
            "title": "Test Issue",
            "description": "This message will cause failure",
            "labels": ["test"],
            "forceError": True  # This should trigger an error in processing
        }
        
        # Send to workflow events topic
        producer.send('workflow-events', malformed_message)
        producer.flush()
        
        # Wait for processing and check DLQ
        time.sleep(2)  # Allow processing time
        
        dlq_messages = []
        try:
            for message in dlq_consumer:
                dlq_messages.append(message.value)
                break  # Get just one message for this test
        except:
            pass  # Timeout is expected if no messages
        
        assert len(dlq_messages) > 0, "Expected at least one DLQ message"
        dlq_message = dlq_messages[0]
        
        assert dlq_message['workflow_id'] == 'test-workflow-001'
        assert 'error' in dlq_message
        assert 'timestamp' in dlq_message
        
    def test_retry_mechanism(self, kafka_setup):
        """Test that messages are retried before going to DLQ"""
        producer, dlq_consumer = kafka_setup
        
        retry_message = {
            "workflowId": "test-retry-001", 
            "issueId": "retry-test",
            "repository": "test/repo",
            "title": "Retry Test",
            "description": "This should be retried",
            "labels": ["test"],
            "retryCount": 0,
            "simulateTransientError": True
        }
        
        producer.send('workflow-events', retry_message)
        producer.flush()
        
        # Wait longer for retries
        time.sleep(10)
        
        # Check that retry count increased in DLQ message
        dlq_messages = []
        try:
            for message in dlq_consumer:
                dlq_messages.append(message.value)
                break
        except:
            pass
        
        if dlq_messages:
            dlq_message = dlq_messages[0]
            # Should have retried multiple times before DLQ
            assert dlq_message.get('retry_count', 0) >= 3
    
    def test_successful_workflow_processing(self):
        """Test that successful workflows don't go to DLQ"""
        # Test via REST API
        response = requests.post('http://localhost:8080/api/v1/trigger', json={
            "issueId": "success-test-001",
            "repository": "test/repo", 
            "title": "Success Test",
            "description": "This should process successfully",
            "labels": ["enhancement"]
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data['success'] == True
        assert 'workflowId' in data
        
        # Wait for processing
        time.sleep(5)
        
        # Verify it didn't go to DLQ by checking processed topic
        consumer = KafkaConsumer(
            'workflow-processed',
            bootstrap_servers=['localhost:9092'], 
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            group_id='test-processed-group',
            auto_offset_reset='latest',
            consumer_timeout_ms=3000
        )
        
        processed_messages = []
        try:
            for message in consumer:
                processed_messages.append(message.value)
                break
        except:
            pass
        finally:
            consumer.close()
        
        assert len(processed_messages) > 0
        processed_message = processed_messages[0]
        assert processed_message['status'] == 'SUCCESS'
        assert processed_message['workflow_id'] == data['workflowId']

if __name__ == "__main__":
    pytest.main([__file__, "-v"])