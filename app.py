import base64
import os
import requests
from flask import Flask, request
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

def get_required_env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise ValueError(f"Missing required environment variable: {key}")
    return value

DISCORD_WEBHOOK_URL = get_required_env("DISCORD_WEBHOOK_URL")
AZURE_ORG = get_required_env("AZURE_ORG")
AZURE_PROJECT = get_required_env("AZURE_PROJECT")
raw_pat = get_required_env("AZURE_PAT")
AZURE_PAT = base64.b64encode(f":{raw_pat}".encode()).decode()
HEADERS = {"Authorization": f"Basic {AZURE_PAT}"}

@app.route("/webhook", methods=["POST"])
def webhook():
    event = request.get_json()
    event_type = event.get("eventType", "")
    
    valid_events = [
        "git.pullrequest.created",
        "git.pullrequest.updated",
        "git.pullrequest.merged"
    ]
    if event_type not in valid_events:
        return "", 200
    
    pr = event.get("resource", {})
    pr_id = pr.get("pullRequestId")
    repo_id = pr.get("repository", {}).get("id")
    
    if not pr_id or not repo_id:
        return "", 400
    
    base_url = (
        f"https://dev.azure.com/{AZURE_ORG}/{AZURE_PROJECT}"
        f"/_apis/git/repositories/{repo_id}"
    )

    # 1. Fetch all iterations
    iterations_response = requests.get(
        f"{base_url}/pullRequests/{pr_id}/iterations?api-version=7.1",
        headers=HEADERS
    )
    iterations_list = iterations_response.json().get("value", []) if iterations_response.ok else {}

    change_count = 0
    if iterations_list:
        last_iteration_id = iterations_list[-1].get("id")

        # 2. Fetch actual file changes for that latest iteration
        changes_response = requests.get(
            f"{base_url}/pullRequests/{pr_id}/iterations/{last_iteration_id}/changes?api-version=7.1",
            headers=HEADERS
        )
        if changes_response.ok:
            changes_data = changes_response.json()
            change_count = len(changes_data.get("changeEntries", []))

    pr_detail_response = requests.get(
        f"{base_url}/pullRequests/{pr_id}?api-version=7.1",
        headers=HEADERS
    )
    pr_detail = pr_detail_response.json() if pr_detail_response.ok else {}

    # Check for conflicts
    has_conflicts = pr_detail.get("mergeStatus") == "conflicts"

    update_reason = event.get("message", {}).get("text", "Pull request event triggered.")

    send_discord_message(pr, change_count, has_conflicts, event_type, update_reason)
    
    return "", 200

def send_discord_message(pr, change_count, has_conflicts, event_type, update_reason):
    # Determine if new or updated
    is_completion = event_type == "git.pullrequest.merged"
    is_updated = event_type == "git.pullrequest.updated"

    if is_completion:
        title_prefix = "Pull Request Completed"
        color = 0x9b59b6
    elif is_updated:
        title_prefix = "Pull Request Updated"
        color = 0x3498db
    else:
        title_prefix = "New Pull Request"
        color = 0x2ecc71

    fields = [
        {
            "name": "Event Details",
            "value": update_reason,
            "inline": False
        },
        {
            "name": "Author",
            "value": pr.get("createdBy", {}).get("displayName", "Unknown"),
            "inline": True
        },
        {
            "name": "From branch",
            "value": pr.get("sourceRefName", "").replace("refs/heads/", ""),
            "inline": True
        },
        {
            "name": "Into branch",
            "value": pr.get("targetRefName", "").replace("refs/heads/", ""),
            "inline": True
        },
        {
            "name": "Files changed",
            "value": f"{change_count} file(s)",
            "inline": True
        },
        {
            "name": "Merge conflicts",
            "value": "We got conflicts!!!" if has_conflicts else "All good!",
            "inline": True
        },
    ] 

    # Create and sends the discord messages
    embed = {
        "title": f"{title_prefix}: {pr.get('title', 'Unknown Title')}",
        "color": color,
        "fields": fields,
        "timestamp": pr.get("creationDate"),
    }

    requests.post(DISCORD_WEBHOOK_URL, json={"embeds": [embed]})
    
if __name__ == "__main__":
    app.run(port=3000, debug=True)