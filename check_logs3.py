import paramiko

key = paramiko.RSAKey.from_private_key_file('d:/Scrapper/montgomery-scraper.pem')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('3.239.168.243', username='ubuntu', pkey=key, timeout=30)

print("=== Running test (limit=1) ===")
cmd = (
    'cd /home/ubuntu/scraper && '
    'source venv/bin/activate && '
    'python -m montgomery.main '
    '--file montgomery/downloads/Montgomery_Tax_Del_Raw_032726.xlsx '
    '--limit 1 2>&1'
)
stdin, stdout, stderr = ssh.exec_command(cmd, timeout=600)
output = stdout.read().decode()
# Show last 3000 chars (skip Excel loading noise)
lines = output.strip().split('\n')
print('\n'.join(lines[-60:]))
ssh.close()
