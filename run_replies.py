"""
run_replies.py — Lightweight entry point for the frequent reply job.

Runs ONLY the comment auto-reply (no video generation, no uploads), so it
finishes in seconds. Triggered every ~30 minutes by cron-job.org via the
reply_comments.yml workflow, giving near-real-time replies without needing
Meta webhooks or a published app.
"""

from reply_comments import reply_to_new_comments

if __name__ == "__main__":
    reply_to_new_comments()
