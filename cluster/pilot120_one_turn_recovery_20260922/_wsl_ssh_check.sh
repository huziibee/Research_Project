#!/usr/bin/env bash
set -euo pipefail
mkdir -p ~/.ssh
chmod 700 ~/.ssh
KEY=/mnt/c/Users/huzii/.ssh/id_ed25519_wits
test -f "$KEY"
if ! grep -q "Host wits-mscluster" ~/.ssh/config 2>/dev/null; then
  cat >> ~/.ssh/config <<'EOF'
Host wits-mscluster
    HostName 146.141.21.100
    User mbangie
    IdentityFile /mnt/c/Users/huzii/.ssh/id_ed25519_wits
    IdentitiesOnly yes
EOF
fi
chmod 600 ~/.ssh/config
ssh -o BatchMode=yes -o ConnectTimeout=20 wits-mscluster 'echo ssh_ok; hostname'
