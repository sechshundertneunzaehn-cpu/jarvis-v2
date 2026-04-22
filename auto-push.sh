#!/bin/bash
cd /opt/jarvis-v2 || exit 0
export GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=accept-new -i /root/.ssh/id_ed25519_github"
git config --global --add safe.directory /opt/jarvis-v2 >/dev/null 2>&1
git add -A
git diff --cached --quiet && exit 0
git -c user.email='jarvis@helsinki' -c user.name='jarvis-helsinki' \
  commit -m "auto: $(date -u +%Y-%m-%dT%H:%M:%SZ) post-deploy" >/dev/null 2>&1
git push origin main 2>&1 | tail -2
