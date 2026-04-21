import base64
import os
import requests
from flask import Flask, request
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
AZURE_PAT = base64.b64encode(f":{os.getenv('AZURE_PAT')}".encode()).decode()
AZURE_ORG = os.getenv("AZURE_ORG")
AZURE_PROJECT = os.getenv("AZURE_PROJECT")
HEADERS = {"Authorization": f"Basic {AZURE_PAT}"}

@app.route("/webhook", methods=["POST"])

def webhook():
    #AZURE DevOps calls this URL everytime a PR event happens
    event = request.get_json()

    #If not pull request
    if not event.get("eventType", "").startswith("git.pullrequest"):
        return "", 200
    
    pr = event["resource"]
    pr_id = pr["pullRequestId"]
    repo = pr["repository"]["id"]
    base = (
        f"https://dev.azure.com/{AZURE_ORG}/{AZURE_PROJECT}"
        f"/_apis/git/repositories/{repo}"
    )

    #Pull request details
    iterations = requests.get(
        f"{base}/pullRequests/{pr_id}/iterations?api-version=7.1",
        headers=HEADERS
    ).json()

    pr_detail = requests.get(
        f"{base}/pullRequests/{pr_id}?api-version=7.1",
        headers=HEADERS
    ).json()

    # Number of files changed in the request
    latest = iterations.get("value", [{}])[-1]
    change_count = len(latest.get("changeList", []))

    # Check for conflicts
    has_conflicts = pr_detail.get("mergeStatus") == "conflicts"

    send_discord_message(pr, change_count, has_conflicts)
    
    return "", 200

def send_discord_message(pr, change_count, has_conflicts):
    
    # Create and sends the discord messages

    embed = {
        "title": f"New Pull Request: {pr['title']}",
        "color": 0xe74c3c if has_conflicts else 0x2ecc71,
        "fields": [
            {
                "name": "Author",
                "value": pr["createdBy"]["displayName"],
                "inline": True
            },
            {
                "name": "From branch",
                "value": pr["sourceRefName"].replace("refs/heads/", ""),
                "inline": True
            },
            {
                "name": "Into branch",
                "value": pr["sourceRefName"].replace("refs/heads/", ""),
                "inline": True
            },
            {
                "name": "Files changed",
                "value": f"{change_count} file(s)",
                "inline": True
            },
            {
                "name": "Merge conflicts",
                "value": "We got a conflict!!!" if has_conflicts else "All good!",
                "inline": True
            },
        ],

        "timestamp": pr["creationDate"],
    }

    requests.post(DISCORD_WEBHOOK_URL, json={"embeds": [embed]})

if __name__ == "__main__":
    app.run(port=3000, debug=True)