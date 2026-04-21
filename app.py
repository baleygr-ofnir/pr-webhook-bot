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
    
    valid_events = ["git.pullrequest.created", "git.pullrequest.updated"]
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

    update_reason = None
    if event_type == "git.pullrequest.updated":
        update_reason = event.get("message", {}).get("text", "Pull request was updated.")
        
        reason_lower = update_reason.lower()
        is_completion = "completed pull request" in reason_lower
        is_push = "pushed" in reason_lower
        
        if not (is_completion or is_push):
            return "", 200
        
    iterations_response = requests.get(
        f"{base_url}/pullRequests/{pr_id}/iterations?api-version=7.1",
        headers=HEADERS
    )
    iterations = iterations_response.json() if iterations_response.ok else {}

    pr_detail_response = requests.get(
        f"{base_url}/pullRequests/{pr_id}?api-version=7.1",
        headers=HEADERS
    )
    pr_detail = pr_detail_response.json() if pr_detail_response.ok else {}

    # Number of files changed in the request
    latest_iteration = iterations.get("value", [{}])[-1]
    change_count = len(latest_iteration.get("changeList", []))

    # Check for conflicts
    has_conflicts = pr_detail.get("mergeStatus") == "conflicts"


    send_discord_message(pr, change_count, has_conflicts, event_type, update_reason)
    
    return "", 200

def send_discord_message(pr, change_count, has_conflicts, event_type, update_reason=None):
    
    # Determine if new or updated
    is_updated = event_type == "git.pullrequest.updated"
    title_prefix = "Pull Request Updated" if is_updated else "New Pull Request"
   
    fields = [
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
    
    if is_updated and update_reason:
        fields.insert(0, {
            "name": "Update Details",
            "value": update_reason,
            "inline": False
        })
    
    # Create and sends the discord messages
    embed = {
        "title": f"{title_prefix}: {pr.get('title', 'Unknown Title')}",
        "color": 0xe74c3c if has_conflicts else (0x3498db if is_updated else 0x2ecc71),
        "fields": fields,
        "timestamp": pr.get("creationDate"),
    }

    requests.post(DISCORD_WEBHOOK_URL, json={"embeds": [embed]})
    
if __name__ == "__main__":
    app.run(port=3000, debug=True)