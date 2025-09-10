package com.issuetracker

import org.springframework.boot.autoconfigure.SpringBootApplication
import org.springframework.boot.runApplication
import org.springframework.kafka.annotation.EnableKafka

@SpringBootApplication
@EnableKafka
class IssueTrackerApplication

fun main(args: Array<String>) {
    runApplication<IssueTrackerApplication>(*args)
}