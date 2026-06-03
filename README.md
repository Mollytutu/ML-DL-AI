# Machine Learing / Deep Learning / AI Portfolio

I build practical AI systems that connect data collection, data cleaning, retrieval, model APIs, and usable applications.

## Featured AI Project: RAG Admissions Advisor

[`RAG/`](./RAG/) is my strongest end-to-end AI project in this repository.

It is a retrieval-augmented generation system that turns web-scraped university admissions data into a searchable AI advisor. The project demonstrates the full workflow behind a real AI product: scraping, cleaning, structured data design, RAG document generation, OpenAI embeddings, FAISS vector search, and a Streamlit chatbot interface.

Quick impact:

- Built a data pipeline covering 16 countries and 1,421 reviewed schools
- Processed 82,111 program rows, 54,767 admission-page rows, and 48,335 school-page fact rows
- Created a RAG workflow from structured CSV data to semantic search and chatbot answers
- Used Selenium and Playwright for scraping, Python for cleaning, OpenAI API for embeddings, and FAISS for vector retrieval
- Designed the project so large generated vector files can be rebuilt locally instead of committed to GitHub

Project context:

This RAG project was built mainly during March-April 2026, when my harness workflow and multi-agent engineering concepts were still developing. I have been focused heavily on other AI projects lately, so this repository should not be read as a complete representation of my latest AI knowledge or engineering approach as of summer 2026.

Start here: [`RAG/README.md`](./RAG/README.md)

## Skills Demonstrated

- Python data engineering
- Web scraping and crawler orchestration
- Data cleaning, deduplication, and validation
- Retrieval-Augmented Generation
- OpenAI API integration
- Vector search with FAISS
- Streamlit AI application development
- Machine learning and time series modeling notebooks
- FastAPI application structure and backend fundamentals

## Repository Structure

- [`RAG/`](./RAG/): end-to-end RAG admissions advisor and data pipeline
- [`ML_modeling/`](./ML_modeling/): machine learning, deep learning, and time series notebooks with datasets
- [`fastapi_project/`](./fastapi_project/): FastAPI backend project

## Why This Portfolio Matters

The RAG project is more than a chatbot demo. It shows that I can work across the full AI application lifecycle:

1. collect messy real-world data
2. clean and structure it for downstream use
3. build retrieval-ready knowledge documents
4. connect model APIs and vector search
5. deliver an interface that users can actually ask questions through

That is the kind of practical engineering needed to move from notebooks to usable AI products.
