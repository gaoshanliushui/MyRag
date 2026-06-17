#!/usr/bin/env python3
"""
Development startup script for MyRag

This script helps you:
1. Start all required services (Docker)
2. Run database migrations
3. Start the API server
4. Start Celery workers
"""

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.text import Text

console = Console()


def run_command(command: str, cwd: str = None, capture: bool = True) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    console.print(f"Running: [bold cyan]{command}[/bold cyan]")
    result = subprocess.run(
        command,
        shell=True,
        capture_output=capture,
        text=True,
        cwd=cwd or os.getcwd(),
    )
    if result.returncode != 0 and capture:
        console.print(f"[red]Error:[/red] {result.stderr}")
    return result


@click.group()
def cli():
    """MyRag Development CLI"""
    pass


@cli.command()
def start():
    """Start all services"""
    console.print(Panel(
        "[bold blue]MyRag - Distributed Multi-Tenant Hybrid Retrieval Enterprise RAG System[/bold blue]\n"
        "Starting all services...",
        title="MyRag Startup"
    ))

    # Change to docker directory
    docker_dir = Path("docker")
    if not docker_dir.exists():
        console.print("[red]Docker directory not found![/red]")
        sys.exit(1)

    # Step 1: Start Docker services
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task1 = progress.add_task("Starting Docker services...", total=None)

        run_command("docker compose up -d", cwd=str(docker_dir))

        progress.update(task1, description="Docker services started ✓")

        # Wait for services to be ready
        task2 = progress.add_task("Waiting for services to be ready...", total=10)
        for i in range(10):
            time.sleep(2)
            progress.update(task2, advance=1)

    console.print("\n[green]✓ All Docker services started[/green]")

    # Step 2: Run migrations
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("Running database migrations...", total=None)

        result = run_command("alembic upgrade head")
        if result.returncode == 0:
            progress.update(task, description="Database migrations completed ✓")
        else:
            progress.update(task, description="Database migrations failed ✗")
            console.print("[red]Failed to run migrations[/red]")
            return

    console.print("\n[green]✓ Database migrations completed[/green]")

    # Step 3: Start API server (in background)
    console.print("\n[bold]Starting API server...[/bold]")
    api_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    # Step 4: Start Celery worker (in background)
    console.print("[bold]Starting Celery worker...[/bold]")
    celery_process = subprocess.Popen(
        [sys.executable, "-m", "celery", "-A", "app.tasks.celery_app", "worker", "--loglevel=info", "--concurrency=4"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    # Display service URLs
    console.print("\n" + Panel(
        "[bold green]All services are running![/bold green]\n\n"
        "[cyan]API Documentation:[/cyan] http://localhost:8000/docs\n"
        "[cyan]Health Check:[/cyan] http://localhost:8000/health\n"
        "[cyan]Grafana Dashboard:[/cyan] http://localhost:3000 (admin/admin)\n"
        "[cyan]Prometheus:[/cyan] http://localhost:9090\n"
        "[cyan]Redis Insight:[/cyan] http://localhost:8001\n"
        "[cyan]Neo4j Browser:[/cyan] http://localhost:7474 (neo4j/neo4j123)\n\n"
        "[yellow]Press Ctrl+C to stop all services[/yellow]",
        title="Services Ready"
    ))

    try:
        # Monitor processes
        while True:
            # Check API server
            if api_process.poll() is not None:
                console.print("[red]API server stopped![/red]")
                break

            # Check Celery worker
            if celery_process.poll() is not None:
                console.print("[red]Celery worker stopped![/red]")
                break

            time.sleep(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopping all services...[/yellow]")
        api_process.terminate()
        celery_process.terminate()
        api_process.wait()
        celery_process.wait()

        # Stop Docker services
        run_command("docker compose down", cwd=str(docker_dir))
        console.print("[green]✓ All services stopped[/green]")


@cli.command()
def stop():
    """Stop all services"""
    console.print("[bold]Stopping all services...[/bold]")

    docker_dir = Path("docker")
    if docker_dir.exists():
        run_command("docker compose down", cwd=str(docker_dir))

    # Kill any remaining processes
    subprocess.run("pkill -f 'uvicorn app.main:app'", shell=True)
    subprocess.run("pkill -f 'celery -A app.tasks.celery_app'", shell=True)

    console.print("[green]✓ All services stopped[/green]")


@cli.command()
def logs():
    """Show service logs"""
    docker_dir = Path("docker")
    if docker_dir.exists():
        os.chdir(str(docker_dir))
        run_command("docker compose logs -f", capture=False)


@cli.command()
@click.option("--service", help="Specific service to check")
def status(service=None):
    """Check service status"""
    docker_dir = Path("docker")
    if docker_dir.exists():
        if service:
            run_command(f"docker compose ps {service}", cwd=str(docker_dir))
        else:
            run_command("docker compose ps", cwd=str(docker_dir))


@cli.command()
@click.argument("tenant_name")
def create_tenant(tenant_name):
    """Create a new tenant"""
    import httpx

    console.print(f"[bold]Creating tenant: {tenant_name}[/bold]")

    # Wait for API to be ready
    time.sleep(2)

    try:
        with httpx.Client() as client:
            response = client.post(
                "http://localhost:8000/api/v1/admin/tenants",
                json={
                    "name": tenant_name,
                    "description": f"Tenant for {tenant_name}"
                }
            )

            if response.status_code == 201:
                tenant = response.json()
                console.print(f"[green]✓ Tenant created:[/green]")
                console.print(f"  ID: {tenant['id']}")
                console.print(f"  Name: {tenant['name']}")
                console.print(f"  API Key: {tenant['api_key']}")
            else:
                console.print(f"[red]Failed to create tenant:[/red] {response.text}")
    except Exception as e:
        console.print(f"[red]Error connecting to API:[/red] {e}")


if __name__ == "__main__":
    cli()