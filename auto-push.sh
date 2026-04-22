#!/bin/bash
export HOME=/root
export GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=accept-new -i /root/.ssh/id_ed25519_github"
cd /opt/jarvis-v2 || exit 0
git config --global --add safe.directory /opt/jarvis-v2 >/dev/null 2>&1
git add -A 2>&1 | tee -a /var/log/jarvis-v2/autopush.log
if git diff --cached --quiet; then
  echo "[autopush $(date -Iseconds)] no changes" >> /var/log/jarvis-v2/autopush.log
  exit 0
fi
git -c user.email='jarvis@helsinki' -c user.name='jarvis-helsinki' \
  commit -m "auto: $(date -u +%Y-%m-%dT%H:%M:%SZ) post-deploy" 2>&1 | tee -a /var/log/jarvis-v2/autopush.log
git push origin main 2>&1 | tee -a /var/log/jarvis-v2/autopush.log | tail -2
