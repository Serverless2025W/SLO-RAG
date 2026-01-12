# Serverless Retrieval Augmented Generation (RAG)

A serverless platform that combines large language models with external knowledge retrieval to enable cost-efficient, scalable RAG applications. This project demonstrates how event-driven serverless architecture can optimize the trade-offs between accuracy, latency, and cost in knowledge-intensive applications.

## Overview

Retrieval-Augmented Generation (RAG) systems combine pre-trained large language models with external knowledge retrieval to improve performance in knowledge-intensive applications. Traditional RAG deployments often require maintaining warm GPU instances for sporadic queries, leading to high infrastructure costs.

This platform leverages the **serverless computing paradigm** to achieve:
- **Zero idle cost** - Pay only for actual inference time, not idle resources
- **Dynamic scaling** - Resources allocated proportionally to workload demands
- **Event-driven architecture** - Functions triggered by external events (document uploads, user queries)
- **Dynamic model selection** - SLO-aware routing between different LLMs based on query complexity and constraints

## Getting Started

For detailed installation and setup instructions, see **[SETUP.md](SETUP.md)**.

## Key Workflows

The platform consists of four independent, event-driven workflows:

### 1. Document Ingestion Workflow
When documents are uploaded to object storage, a multi-stage pipeline processes them:
- **Text Extraction** - Parses various document formats (PDF, DOCX, etc.)
- **Chunking** - Splits text into coherent segments with configurable size and overlap
- **Embedding Generation** - Converts chunks into vector representations
- **Vector Storage** - Indexes embeddings alongside metadata in a vector database

Each phase executes as an independent serverless function, enabling parallel processing during bulk uploads.

### 2. Inference Workflow
User queries trigger a two-phase process:
- **Retrieval Phase** - Generates query embeddings and searches the vector database for relevant chunks
- **Generation Phase** - Implements dynamic model selection through an SLO-aware router that chooses between local GPU models (lower cost, potential cold starts) and remote proprietary models (higher cost, lower latency)

### 3. Conversational State Management Workflow
Maintains conversation context for longer-running user sessions by persisting and retrieving conversation history from a database.

### 4. Context Summarization Workflow
When conversations exceed pre-defined limits, a scheduled function compresses older messages into concise summaries, reducing storage costs and token consumption while preserving conversation coherence.
