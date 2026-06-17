#!/usr/bin/env python3
"""
Quick test script to verify MyRag functionality

This script tests:
1. API health check
2. Tenant creation
3. Document upload
4. Document processing
5. Search functionality
6. QA functionality
"""

import asyncio
import httpx
import json
import time
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()

BASE_URL = "http://localhost:8000"


class MyRagTester:
    def __init__(self):
        self.tenant_id = None
        self.api_key = None
        self.document_id = None

    async def test_health(self):
        """Test API health check"""
        console.print("[bold]1. Testing API Health Check...[/bold]")

        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/health")

            if response.status_code == 200:
                data = response.json()
                console.print(f"[green]✓ Health check passed[/green]")
                console.print(f"  Status: {data['status']}")
                console.print(f"  Version: {data['version']}")
                return True
            else:
                console.print(f"[red]✗ Health check failed:[/red] {response.text}")
                return False

    async def create_tenant(self):
        """Create a test tenant"""
        console.print("\n[bold]2. Creating Test Tenant...[/bold]")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BASE_URL}/api/v1/admin/tenants",
                json={
                    "name": "Test Tenant",
                    "description": "Test tenant for MyRag verification"
                }
            )

            if response.status_code == 201:
                data = response.json()
                self.tenant_id = data['id']
                self.api_key = data['api_key']
                console.print(f"[green]✓ Tenant created[/green]")
                console.print(f"  ID: {self.tenant_id}")
                console.print(f"  Name: {data['name']}")
                console.print(f"  API Key: {self.api_key}")
                return True
            else:
                console.print(f"[red]✗ Tenant creation failed:[/red] {response.text}")
                return False

    async def upload_test_document(self):
        """Upload a test document"""
        console.print("\n[bold]3. Uploading Test Document...[/bold]")

        # Create a simple test document
        test_content = """
MyRag Test Document
===================

This is a test document to verify MyRag functionality.

Chapter 1: Introduction
-----------------------
MyRag is a distributed multi-tenant hybrid retrieval enterprise RAG system.
It combines dense vector retrieval, sparse keyword retrieval, and knowledge graph retrieval.

Chapter 2: Key Features
-----------------------
1. Adaptive Semantic Preprocessing Pipeline
2. Three-Way Hybrid Retrieval
3. Two-Level Staged Reranking
4. Distributed Multi-Tenant Isolation
5. Production-Grade High Availability

Chapter 3: Architecture
-----------------------
The system uses:
- FastAPI for the API layer
- Milvus for vector storage
- Elasticsearch for keyword search
- Neo4j for knowledge graphs
- Redis for caching
- Celery for async processing

Chapter 4: Performance Targets
------------------------------
- Retrieval latency: <300ms
- Concurrency: 50+ users
- Document scale: millions of documents

Chapter 5: Security and Compliance
----------------------------------
- Multi-tenant data isolation
- Auditability with source traceability
- Private deployment with offline processing
"""

        # Write test document
        test_file = Path("test_document.txt")
        test_file.write_text(test_content, encoding='utf-8')

        headers = {"X-Tenant-ID": self.tenant_id}
        if self.api_key:
            headers["X-API-Key"] = self.api_key

        async with httpx.AsyncClient() as client:
            with open(test_file, "rb") as f:
                response = await client.post(
                    f"{BASE_URL}/api/v1/{self.tenant_id}/documents/upload",
                    files={"file": ("test_document.txt", f, "text/plain")},
                    headers=headers
                )

        # Clean up test file
        test_file.unlink()

        if response.status_code == 201:
            data = response.json()
            self.document_id = data['id']
            console.print(f"[green]✓ Document uploaded[/green]")
            console.print(f"  ID: {self.document_id}")
            console.print(f"  Filename: {data['original_filename']}")
            console.print(f"  Status: {data['status']}")
            return True
        else:
            console.print(f"[red]✗ Document upload failed:[/red] {response.text}")
            return False

    async def wait_for_processing(self, timeout=60):
        """Wait for document processing to complete"""
        console.print("\n[bold]4. Waiting for Document Processing...[/bold]")

        headers = {"X-Tenant-ID": self.tenant_id}
        if self.api_key:
            headers["X-API-Key"] = self.api_key

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Processing document...", total=timeout)

            start_time = time.time()
            while time.time() - start_time < timeout:
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        f"{BASE_URL}/api/v1/{self.tenant_id}/documents/{self.document_id}/status",
                        headers=headers
                    )

                if response.status_code == 200:
                    data = response.json()
                    status = data['status']
                    progress_ = data.get('processing_progress', 0)

                    progress.update(task, description=f"Processing... {progress_:.0%}")

                    if status == "completed":
                        console.print(f"\n[green]✓ Document processing completed[/green]")
                        console.print(f"  Total pages: {data['total_pages']}")
                        console.print(f"  Total chunks: {data['total_chunks']}")
                        console.print(f"  Total tokens: {data['total_tokens']}")
                        return True
                    elif status == "failed":
                        error = data.get('processing_error', 'Unknown error')
                        console.print(f"\n[red]✗ Processing failed:[/red] {error}")
                        return False

                await asyncio.sleep(2)

        console.print(f"\n[yellow]⚠ Processing timeout[/yellow]")
        return False

    async def test_search(self):
        """Test search functionality"""
        console.print("\n[bold]5. Testing Search Functionality...[/bold]")

        headers = {"X-Tenant-ID": self.tenant_id}
        if self.api_key:
            headers["X-API-Key"] = self.api_key

        test_queries = [
            "What are the key features of MyRag?",
            "How does the hybrid retrieval work?",
            "What databases does MyRag use?",
            "Performance targets",
        ]

        async with httpx.AsyncClient() as client:
            for query in test_queries:
                response = await client.post(
                    f"{BASE_URL}/api/v1/{self.tenant_id}/retrieval/search",
                    json={
                        "query": query,
                        "top_k": 5,
                        "mode": "hybrid",
                        "enable_reranking": True,
                        "enable_confidence": True
                    },
                    headers=headers
                )

                if response.status_code == 200:
                    data = response.json()
                    console.print(f"\n[cyan]Query:[/cyan] {query}")
                    console.print(f"[green]✓ Found {len(data['results'])} results[/green]")
                    console.print(f"  Query type: {data['metrics']['query_type']}")
                    console.print(f"  Latency: {data['metrics']['latency_ms']:.2f}ms")

                    # Show first result
                    if data['results']:
                        result = data['results'][0]
                        console.print(f"  Top result: {result['source']['document_name']} - Page {result['source']['page_number']}")
                else:
                    console.print(f"\n[red]✗ Search failed for '{query}':[/red] {response.text}")

        return True

    async def test_qa(self):
        """Test QA functionality"""
        console.print("\n[bold]6. Testing QA Functionality...[/bold]")

        headers = {"X-Tenant-ID": self.tenant_id}
        if self.api_key:
            headers["X-API-Key"] = self.api_key

        test_questions = [
            "What is MyRag?",
            "How does the hybrid retrieval system work?",
            "What are the performance targets?",
        ]

        async with httpx.AsyncClient() as client:
            for question in test_questions:
                response = await client.post(
                    f"{BASE_URL}/api/v1/{self.tenant_id}/retrieval/qa",
                    json={
                        "question": question,
                        "top_k": 3,
                        "mode": "hybrid",
                        "enable_reranking": True
                    },
                    headers=headers
                )

                if response.status_code == 200:
                    data = response.json()
                    console.print(f"\n[cyan]Question:[/cyan] {question}")
                    console.print(f"[green]✓ Answer generated[/green]")
                    console.print(f"  Confidence: {data['confidence']:.2f}")
                    console.print(f"  Model: {data['model_used']}")
                    console.print(f"  Answer preview: {data['answer'][:200]}...")
                else:
                    console.print(f"\n[red]✗ QA failed for '{question}':[/red] {response.text}")

        return True

    async def cleanup(self):
        """Clean up test data"""
        console.print("\n[bold]7. Cleaning Up Test Data...[/bold]")

        headers = {"X-Tenant-ID": self.tenant_id}
        if self.api_key:
            headers["X-API-Key"] = self.api_key

        # Delete document
        if self.document_id:
            async with httpx.AsyncClient() as client:
                response = await client.delete(
                    f"{BASE_URL}/api/v1/{self.tenant_id}/documents/{self.document_id}",
                    headers=headers
                )
                if response.status_code == 204:
                    console.print("[green]✓ Test document deleted[/green]")

        # Delete tenant (would need admin endpoint)
        console.print("[yellow]ℹ Test tenant not deleted (requires admin access)[/yellow]")

    async def run_all_tests(self):
        """Run all tests"""
        console.print(Panel(
            "[bold blue]MyRag System Test[/bold blue]\n"
            "This test will verify all core functionality of MyRag system",
            title="System Verification"
        ))

        tests = [
            ("Health Check", self.test_health),
            ("Create Tenant", self.create_tenant),
            ("Upload Document", self.upload_test_document),
            ("Process Document", self.wait_for_processing),
            ("Search Test", self.test_search),
            ("QA Test", self.test_qa),
            ("Cleanup", self.cleanup),
        ]

        passed = 0
        total = len(tests)

        for test_name, test_func in tests:
            try:
                if await test_func():
                    passed += 1
                else:
                    console.print(f"[red]✗ {test_name} failed[/red]")
            except Exception as e:
                console.print(f"[red]✗ {test_name} error:[/red] {e}")

        # Summary
        console.print("\n" + Panel(
            f"[bold]Test Summary[/bold]\n\n"
            f"Passed: [green]{passed}[/green]\n"
            f"Failed: [red]{total - passed}[/red]\n"
            f"Total: {total}\n\n"
            f"{'All tests passed! ✓' if passed == total else 'Some tests failed ✗'}",
            title="Test Results"
        ))


async def main():
    """Main entry point"""
    tester = MyRagTester()
    await tester.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())