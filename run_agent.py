#!/usr/bin/env python3
"""
RUNTIME — run this for each scraping/analysis session.

Usage:
    python run_agent.py "Scrape pokerbet.co.za and compute HUD stats"
    python run_agent.py --upload saved_hands/ "Parse these hands and compute stats"
    python run_agent.py --upload hand_data.json "Analyze this data"
"""
import anthropic
import argparse
import glob
import json
import os
import sys
import time


def load_env():
    """Load agent IDs from .env.poker-agent file."""
    env_file = os.path.join(os.path.dirname(__file__), ".env.poker-agent")
    if not os.path.exists(env_file):
        print("ERROR: .env.poker-agent not found. Run setup_agent.py first.")
        sys.exit(1)

    env = {}
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if "=" in line:
                key, value = line.split("=", 1)
                env[key] = value
    return env


def upload_files(client, file_paths):
    """Upload local files and return list of resource dicts for session."""
    resources = []
    for path in file_paths:
        if os.path.isdir(path):
            # Upload all .txt and .json files from directory
            patterns = [
                os.path.join(path, "*.txt"),
                os.path.join(path, "*.json"),
            ]
            files = []
            for pattern in patterns:
                files.extend(sorted(glob.glob(pattern))[:50])  # cap at 50 per type
            if not files:
                print(f"  No .txt/.json files found in {path}")
                continue
            print(f"  Found {len(files)} files in {path}")
            for fp in files:
                uploaded = client.beta.files.upload(file=open(fp, "rb"))
                basename = os.path.basename(fp)
                resources.append({
                    "type": "file",
                    "file_id": uploaded.id,
                    "mount_path": f"/workspace/data/{basename}",
                })
                print(f"    Uploaded: {basename} ({uploaded.id})")
        elif os.path.isfile(path):
            uploaded = client.beta.files.upload(file=open(path, "rb"))
            basename = os.path.basename(path)
            resources.append({
                "type": "file",
                "file_id": uploaded.id,
                "mount_path": f"/workspace/data/{basename}",
            })
            print(f"  Uploaded: {basename} ({uploaded.id})")
        else:
            print(f"  WARNING: {path} not found, skipping")
    return resources


def run_session(client, agent_id, env_id, task, resources=None):
    """Create a session, send task, stream events, download outputs."""
    print(f"\nCreating session...")
    session = client.beta.sessions.create(
        agent=agent_id,
        environment_id=env_id,
        title=f"HUD: {task[:50]}",
        resources=resources or [],
    )
    print(f"  Session: {session.id} ({session.status})")

    # Stream-first, then send
    print(f"\nStreaming agent output:\n{'='*60}")
    with client.beta.sessions.stream(session_id=session.id) as stream:
        client.beta.sessions.events.send(
            session_id=session.id,
            events=[{
                "type": "user.message",
                "content": [{"type": "text", "text": task}],
            }],
        )

        for event in stream:
            if event.type == "agent.message":
                for block in event.content:
                    if block.type == "text":
                        print(block.text, end="", flush=True)

            elif event.type == "agent.thinking":
                pass  # suppress thinking output

            elif event.type == "session.status_idle":
                if event.stop_reason.type == "requires_action":
                    continue
                print(f"\n{'='*60}")
                print("Agent finished.")
                break

            elif event.type == "session.status_terminated":
                print(f"\n{'='*60}")
                print("Session terminated.")
                break

            elif event.type == "session.error":
                print(f"\nERROR: {event}")

    # Download output files
    print("\nChecking for output files...")
    time.sleep(3)  # brief indexing lag

    output_dir = os.path.join(os.path.dirname(__file__), "agent_output")
    os.makedirs(output_dir, exist_ok=True)

    files = client.beta.files.list(session_id=session.id)
    downloaded = []
    for f in files.data:
        safe_name = os.path.basename(f.filename)
        if not safe_name or safe_name in (".", ".."):
            continue
        out_path = os.path.join(output_dir, safe_name)
        content = client.beta.files.download(f.id)
        content.write_to_file(out_path)
        downloaded.append(out_path)
        print(f"  Downloaded: {safe_name} ({f.size_bytes} bytes)")

    if not downloaded:
        print("  No output files found.")
    else:
        print(f"\n{len(downloaded)} files saved to {output_dir}/")

    # Archive session
    # Brief wait for status to settle (post-idle race)
    for _ in range(5):
        s = client.beta.sessions.retrieve(session.id)
        if s.status != "running":
            break
        time.sleep(0.5)

    if s.status != "running":
        client.beta.sessions.archive(session_id=session.id)
        print("Session archived.")

    return downloaded


def main():
    parser = argparse.ArgumentParser(description="Poker HUD Data Agent")
    parser.add_argument("task", nargs="?", help="Task description for the agent")
    parser.add_argument(
        "--upload", "-u",
        action="append",
        default=[],
        help="File or directory to upload into the agent workspace (repeatable)",
    )
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Interactive mode: send multiple messages to the same session",
    )
    args = parser.parse_args()

    if not args.task and not args.interactive:
        parser.print_help()
        print("\nExamples:")
        print('  python run_agent.py "Scrape pokerbet.co.za PLO tables and compute HUD stats"')
        print('  python run_agent.py -u saved_hands/ "Parse these hands and compute stats"')
        print('  python run_agent.py -u hand_data.json "Analyze player tendencies"')
        print('  python run_agent.py -i  # interactive mode')
        sys.exit(0)

    client = anthropic.Anthropic()
    env = load_env()
    agent_id = env["AGENT_ID"]
    env_id = env["ENVIRONMENT_ID"]

    # Upload files if specified
    resources = []
    if args.upload:
        print("Uploading files...")
        resources = upload_files(client, args.upload)
        if resources:
            print(f"  {len(resources)} files will be mounted at /workspace/data/")

    if args.interactive:
        # Interactive multi-turn session
        print(f"\nCreating interactive session...")
        session = client.beta.sessions.create(
            agent=agent_id,
            environment_id=env_id,
            title="HUD Interactive Session",
            resources=resources,
        )
        print(f"  Session: {session.id}")
        print("Type 'quit' to exit, 'download' to fetch output files.\n")

        while True:
            try:
                user_input = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                break

            if not user_input:
                continue
            if user_input.lower() == "quit":
                break
            if user_input.lower() == "download":
                time.sleep(2)
                files = client.beta.files.list(session_id=session.id)
                output_dir = os.path.join(os.path.dirname(__file__), "agent_output")
                os.makedirs(output_dir, exist_ok=True)
                for f in files.data:
                    safe_name = os.path.basename(f.filename)
                    if not safe_name or safe_name in (".", ".."):
                        continue
                    out_path = os.path.join(output_dir, safe_name)
                    content = client.beta.files.download(f.id)
                    content.write_to_file(out_path)
                    print(f"  Downloaded: {safe_name}")
                continue

            with client.beta.sessions.stream(session_id=session.id) as stream:
                client.beta.sessions.events.send(
                    session_id=session.id,
                    events=[{
                        "type": "user.message",
                        "content": [{"type": "text", "text": user_input}],
                    }],
                )

                print("Agent: ", end="", flush=True)
                for event in stream:
                    if event.type == "agent.message":
                        for block in event.content:
                            if block.type == "text":
                                print(block.text, end="", flush=True)
                    elif event.type == "session.status_idle":
                        if event.stop_reason.type == "requires_action":
                            continue
                        print()
                        break
                    elif event.type == "session.status_terminated":
                        print("\nSession terminated.")
                        return

        # Cleanup
        for _ in range(5):
            s = client.beta.sessions.retrieve(session.id)
            if s.status != "running":
                break
            time.sleep(0.5)
        if s.status != "running":
            client.beta.sessions.archive(session_id=session.id)
            print("Session archived.")
    else:
        # Single-shot mode
        run_session(client, agent_id, env_id, args.task, resources)


if __name__ == "__main__":
    main()
